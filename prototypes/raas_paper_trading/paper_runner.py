"""Live paper bridge: WebSocket ticks → WORM → daemon (monitoring only).

Charter: live_execution is hardcoded False. Never starts an order path.
Option B exit: PAPER_EXIT_MODE=time_hold (Pre-Reg PAPER_EXIT_IMPLEMENTATION_PREREG).
Cross-venue connectivity: t_recv only (Pre-Reg CROSS_VENUE_FEED_VALIDATION_PREREG).
"""
from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from prototypes.raas_paper_trading.cross_venue import (
    CrossVenueMonitor,
    cross_venue_paths_from_env,
)
from prototypes.raas_paper_trading.feed import (
    BinanceWebSocketFeed,
    CoinbaseMatchRecvFeed,
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
        cross_venue: Optional[CrossVenueMonitor] = None,
        enable_cross_venue: Optional[bool] = None,
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

        if enable_cross_venue is None:
            enable_cross_venue = _env_bool("CROSS_VENUE_ENABLED", False)
        self.cross_venue = cross_venue
        if self.cross_venue is None and enable_cross_venue:
            paths = cross_venue_paths_from_env()
            gaps = Path(os.environ.get("CROSS_VENUE_GAPS_PATH", str(paths["gaps_path"])))
            slots = Path(os.environ.get("CROSS_VENUE_SLOTS_PATH", str(paths["slots_path"])))
            st = Path(os.environ.get("CROSS_VENUE_STATE_PATH", str(paths["state_path"])))
            if "CROSS_VENUE_GAPS_PATH" not in os.environ:
                gaps = self.worm_dir / "audit" / "cross_venue_gaps.jsonl"
            if "CROSS_VENUE_SLOTS_PATH" not in os.environ:
                slots = self.worm_dir / "audit" / "cross_venue_slots.jsonl"
            if "CROSS_VENUE_STATE_PATH" not in os.environ:
                st = self.worm_dir / "state" / "cross_venue_state.json"
            gap_dt = float(os.environ.get("CROSS_VENUE_GAP_DT_S", "30"))
            self.cross_venue = CrossVenueMonitor.from_paths(
                gaps_path=gaps,
                slots_path=slots,
                state_path=st,
                gap_dt_v1=gap_dt,
                gap_dt_v2=gap_dt,
            )
        self._v2_thread: Optional[threading.Thread] = None
        self._v2_stop: Optional[threading.Event] = None

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
        # Cross-venue V1: local accept time — not exchange tick.ts (Pre-Reg §3.2)
        if self.cross_venue is not None:
            self.cross_venue.on_recv(
                "v1", recv_ts=datetime.now(timezone.utc).isoformat()
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
        if self.cross_venue is not None:
            self.start_cross_venue_v2(stop=stop)
        return t

    def start_cross_venue_v2(
        self,
        *,
        stop: Optional[threading.Event] = None,
        frames: Optional[Iterable[str]] = None,
    ) -> threading.Thread:
        """Coinbase matches → V2 t_recv pulses (no prices on audit path)."""
        if self.cross_venue is None:
            raise RuntimeError("cross_venue monitor not enabled")
        self._v2_stop = stop or threading.Event()
        product = os.environ.get("CROSS_VENUE_V2_PRODUCT", "ETH-USD")
        url = os.environ.get(
            "CROSS_VENUE_V2_WS_URL", "wss://ws-feed.exchange.coinbase.com"
        )
        feed = CoinbaseMatchRecvFeed(
            url,
            product_id=product,
            frames=list(frames) if frames is not None else None,
            stop=lambda: bool(self._v2_stop and self._v2_stop.is_set()),
            venue="v2",
        )

        def _loop() -> None:
            assert self.cross_venue is not None
            for pulse in feed:
                if self._v2_stop is not None and self._v2_stop.is_set():
                    break
                self.cross_venue.on_recv(pulse.venue, recv_ts=pulse.recv_ts)

        self._v2_thread = threading.Thread(
            target=_loop, name="cross-venue-v2", daemon=True
        )
        self._v2_thread.start()
        return self._v2_thread

    @classmethod
    def from_env(
        cls, *, worm_dir: Path, frames: Optional[Iterable[str]] = None
    ) -> "LivePaperBridge":
        symbol = os.environ.get("LIVE_FEED_SYMBOL", "ETHUSDT").upper()
        if frames is not None:
            feed: Iterable[PaperTick] = MockWebSocketFeed(
                list(frames), default_symbol=symbol
            )
        else:
            feed = None
        return cls(symbol=symbol, worm_dir=worm_dir, feed=feed)


def live_feed_enabled() -> bool:
    return _env_bool("LIVE_FEED_ENABLED", False)
