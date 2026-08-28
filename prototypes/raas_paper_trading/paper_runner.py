"""Live paper bridge: WebSocket ticks → WORM → daemon (monitoring only).

Charter: live_execution is hardcoded False. Never starts an order path.
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
        self.runner = runner or PaperTradingRunner(
            tenant_id="live",
            run_id=self.symbol.lower(),
            worm=self.worm,
            attach_orderbook=attach_orderbook,
        )
        self.feed: Iterable[PaperTick] = feed if feed is not None else self._feed_from_env()
        self.ticks_written = 0

    def _feed_from_env(self) -> Iterable[PaperTick]:
        url = binance_trade_ws_url(self.symbol)
        return BinanceWebSocketFeed(url, default_symbol=self.symbol)

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
