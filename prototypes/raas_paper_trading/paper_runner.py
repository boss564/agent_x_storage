"""Live paper bridge: WebSocket ticks → WORM → daemon (monitoring only).

Charter: live_execution is hardcoded False. Never starts an order path.
Option B exit: PAPER_EXIT_MODE=time_hold (Pre-Reg PAPER_EXIT_IMPLEMENTATION_PREREG).
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from prototypes.raas_paper_trading.feed import (
    BinanceWebSocketFeed,
    MockWebSocketFeed,
    PaperTick,
    binance_trade_ws_url,
)
from prototypes.raas_paper_trading.paper_exit import exit_config_from_env
from prototypes.raas_paper_trading.runner import PaperTradingRunner
from prototypes.raas_paper_trading.worm_log import PaperWormLog

LIVE_EXECUTION = False


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class LivePaperBridge:
    """Writes SIGNAL rows via PaperTradingRunner; daemon only reads the WORM dir."""

    live_execution = LIVE_EXECUTION

    def __init__(
        self,
        *,
        symbol: str,
        worm_dir: Path,
        feed: Optional[Iterable[PaperTick]] = None,
        runner: Optional[PaperTradingRunner] = None,
        attach_orderbook: bool = False,
    ) -> None:
        if LIVE_EXECUTION is True:
            raise RuntimeError("live_execution must stay false")
        self.symbol = symbol.upper()
        self.worm_dir = Path(worm_dir)
        self.worm_dir.mkdir(parents=True, exist_ok=True)
        self.worm = PaperWormLog(
            tenant_id="live",
            run_id=self.symbol.lower(),
            data_root=self.worm_dir,
        )
        if runner is not None:
            self.runner = runner
        else:
            cfg = exit_config_from_env()
            exit_mode = cfg["exit_mode"]
            # Live shadow defaults to Option-B time_hold (Pre-Reg).
            # State/edges live next to the WORM tree unless env overrides absolute paths.
            state_path = Path(cfg["state_path"])
            edges_path = Path(cfg["edges_path"])
            gaps_path = self.worm_dir / "audit" / "feed_gaps.jsonl"
            gap_state_path = self.worm_dir / "state" / "feed_gap_state.json"
            if "PAPER_POSITION_STATE_PATH" not in os.environ:
                state_path = self.worm_dir / "state" / "paper_position.json"
            if "PAPER_EDGES_PATH" not in os.environ:
                edges_path = self.worm_dir / "audit" / "paper_edges.jsonl"
            if "PAPER_FEED_GAPS_PATH" in os.environ:
                gaps_path = Path(os.environ["PAPER_FEED_GAPS_PATH"])
            if "PAPER_FEED_GAP_STATE_PATH" in os.environ:
                gap_state_path = Path(os.environ["PAPER_FEED_GAP_STATE_PATH"])
            if exit_mode in ("", "legacy", "break", "off", "none"):
                self.runner = PaperTradingRunner(
                    tenant_id="live",
                    run_id=self.symbol.lower(),
                    worm=self.worm,
                    attach_orderbook=attach_orderbook,
                    feed_gaps_path=gaps_path,
                    feed_gap_state_path=gap_state_path,
                    enable_feed_gap=True,
                )
            else:
                self.runner = PaperTradingRunner(
                    tenant_id="live",
                    run_id=self.symbol.lower(),
                    worm=self.worm,
                    attach_orderbook=attach_orderbook,
                    exit_mode="time_hold",
                    hold_seconds=int(cfg["hold_seconds"]),
                    gap_dt_s=float(cfg["gap_dt_s"]),
                    max_wait_s=float(cfg["max_wait_s"]),
                    position_state_path=state_path,
                    edges_path=edges_path,
                    feed_gaps_path=gaps_path,
                    feed_gap_state_path=gap_state_path,
                    enable_feed_gap=True,
                )
        self.feed: Iterable[PaperTick] = feed if feed is not None else self._feed_from_env()
        self.ticks_written = 0

    def _socket_disconnect(self) -> None:
        mon = self.runner.feed_gap
        if mon is None:
            return
        fsm = self.runner.exit.state if self.runner.exit else "UNKNOWN"
        mon.on_socket_disconnect(fsm_state=fsm)

    def _socket_reconnect(self) -> None:
        mon = self.runner.feed_gap
        if mon is None:
            return
        fsm = "UNKNOWN"
        position_open = False
        hold_deadline = None
        round_trip_id = None
        if self.runner.exit is not None:
            fsm = self.runner.exit.state
            store = self.runner.exit.store
            position_open = store.state in ("HOLDING", "EXIT_PENDING", "ENTRY_PENDING")
            round_trip_id = store.entry_signal_id
            if store.entry_tick_ts:
                from datetime import datetime, timezone

                from prototypes.raas_paper_trading.paper_exit import parse_ts_unix

                try:
                    deadline_u = parse_ts_unix(store.entry_tick_ts) + float(
                        store.hold_seconds_target
                    )
                    hold_deadline = datetime.fromtimestamp(
                        deadline_u, tz=timezone.utc
                    ).isoformat()
                except ValueError:
                    hold_deadline = None
        mon.on_socket_reconnect(
            fsm_state=fsm,
            position_open=position_open,
            hold_deadline_ts=hold_deadline,
            round_trip_id=round_trip_id,
        )

    def _feed_from_env(self) -> Iterable[PaperTick]:
        url = binance_trade_ws_url(self.symbol)
        return BinanceWebSocketFeed(
            url,
            default_symbol=self.symbol,
            on_disconnect=self._socket_disconnect,
            on_reconnect=self._socket_reconnect,
        )

    def ingest_tick(self, tick: PaperTick) -> Dict[str, Any]:
        if tick.symbol.upper() != self.symbol:
            tick = PaperTick(
                symbol=self.symbol,
                ts=tick.ts,
                price=tick.price,
                source=tick.source,
            )
        row = self.runner.on_tick(tick)
        self.ticks_written += 1
        return row

    def drain_feed(self, *, max_ticks: Optional[int] = None) -> int:
        n = 0
        for tick in self.feed:
            self.ingest_tick(tick)
            n += 1
            if max_ticks is not None and n >= max_ticks:
                break
        return n

    def start_background(self, *, stop: Optional[threading.Event] = None) -> threading.Thread:
        """Daemon thread: consume feed until stop is set (or feed ends)."""

        def _loop() -> None:
            for tick in self.feed:
                if stop is not None and stop.is_set():
                    break
                self.ingest_tick(tick)

        t = threading.Thread(target=_loop, name="live-paper-feed", daemon=True)
        t.start()
        return t

    @classmethod
    def from_env(cls, *, worm_dir: Path, frames: Optional[Iterable[str]] = None) -> "LivePaperBridge":
        symbol = os.environ.get("LIVE_FEED_SYMBOL", "ETHUSDT").upper()
        if frames is not None:
            feed: Iterable[PaperTick] = MockWebSocketFeed(list(frames), default_symbol=symbol)
        else:
            feed = None
        return cls(symbol=symbol, worm_dir=worm_dir, feed=feed)


def live_feed_enabled() -> bool:
    return _env_bool("LIVE_FEED_ENABLED", False)
