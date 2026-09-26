"""Hub-Verdrahtung fuer den Dry-Run-Satelliten.

Reihenfolge des Contracts:
    1. Book-Feed: PolySentinel-WS -> engine.on_book_update(snapshot)
    2. Tick: Cron/Timer -> engine.reap_expired()
    3. Selbst-Audit im selben Takt: JournalReplay vs. portfolio.snapshot()

Charter: diagnostic_only=true, live_execution=false, order_send=false.
Auch dieses Modul besitzt keinen Order-Sende-Pfad; der optionale
PolymarketWsFeed ist read-only und abonniert nur Marktdaten.

Importiert ausschliesslich den Kanon (kein Overlay-``replay.py``).

``ShadowHub.run``: Bei Audit-Divergenz und ``raise_on_divergence=True``
bricht der Timer-Loop ab (Fail-fast); der Book-Feed laeuft unabhaengig weiter.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from order_execution_engine.models import _utcnow
from order_execution_engine.market_data_feed import (
    PolySentinelBookHandler,
    PolymarketWsFeed,
    SnapshotCache,
)
from order_execution_engine.shadow_replay import AuditReport
from order_execution_engine.shadow_execution_engine import (
    MarketSnapshot,
    PaperOrder,
    ShadowExecutionEngine,
)


class EngineBookHandler(PolySentinelBookHandler):
    """PolySentinel-Handler, der jeden Snapshot zusaetzlich in die Engine speist."""

    def __init__(self, cache: SnapshotCache, engine: ShadowExecutionEngine) -> None:
        super().__init__(cache)
        self._engine = engine

    def on_book_update(
        self,
        token_id: str,
        bids: list[tuple],
        asks: list[tuple],
        received_at: Optional[float] = None,
    ) -> MarketSnapshot:
        """Speist ein Book-Event in Cache und Engine."""
        snapshot = super().on_book_update(
            token_id, bids=bids, asks=asks, received_at=received_at,
        )
        self._engine.on_book_update(snapshot)
        return snapshot


@dataclass(frozen=True)
class BookFeedBinding:
    """Rueckgabe der Feed-Verdrahtung."""

    cache: SnapshotCache
    handler: EngineBookHandler
    feed: Optional[PolymarketWsFeed]


def attach_book_feed(
    engine: ShadowExecutionEngine,
    cache: Optional[SnapshotCache] = None,
    start_ws_feed: bool = False,
) -> BookFeedBinding:
    """Verdrahtet PolySentinel-Book-Events mit der Engine."""
    snapshot_cache = cache or SnapshotCache()
    handler = EngineBookHandler(snapshot_cache, engine)
    feed = PolymarketWsFeed(handler) if start_ws_feed else None
    return BookFeedBinding(cache=snapshot_cache, handler=handler, feed=feed)


@dataclass(frozen=True)
class HubTickResult:
    """Ergebnis eines Hub-Takts."""

    ticked_at: datetime
    expired_orders: tuple[PaperOrder, ...]
    audit: AuditReport
    full_audit: bool


class ShadowHub:
    """Kombiniert Reaper und Selbst-Audit in einem deterministischen Takt.

    Bei ``raise_on_divergence=True`` (Default) bricht ein Audit-Fund den Takt
    mit ``ShadowAuditDivergence`` ab. Bei ``False`` erscheinen Findings wie
    ``peak_equity.monotonic`` und ``journal`` oft nur beim ersten Auftreten
    (Cursor/Monotonie-Anker ruecken trotzdem vor) — der Aufrufer muss
    ``report.findings`` protokollieren und darf sich nicht allein auf
    ``report.ok`` verlassen.
    """

    def __init__(
        self,
        engine: ShadowExecutionEngine,
        raise_on_divergence: bool = True,
        full_audit_every_n_ticks: Optional[int] = 300,
    ) -> None:
        """Initialisiert den Hub.

        Args:
            engine: Ziel-Engine.
            raise_on_divergence: Fail-fast bei Audit-Fund.
            full_audit_every_n_ticks: Alle N Ticks Voll-Replay (None = nie).
                Default 300 (~5 Min bei 1 s Intervall) als Kontrolle gegen
                Drift im inkrementellen Cursor.
        """
        self.engine = engine
        self.raise_on_divergence = raise_on_divergence
        self.full_audit_every_n_ticks = full_audit_every_n_ticks
        self._tick_count = 0

    def tick(self, now: Optional[datetime] = None) -> HubTickResult:
        """Fuehrt Punkt 2 und 3 des Hub-Vertrags atomar aus."""
        ticked_at = now or _utcnow()
        self.engine.reap_expired(ticked_at)
        self._tick_count += 1
        do_full = (
            self.full_audit_every_n_ticks is not None
            and self.full_audit_every_n_ticks > 0
            and self._tick_count % self.full_audit_every_n_ticks == 0
        )
        audit = self.engine.audit_shadow_state(
            raise_on_divergence=self.raise_on_divergence,
            full=do_full,
        )
        return HubTickResult(
            ticked_at=ticked_at,
            expired_orders=self.engine.last_expired_orders,
            audit=audit,
            full_audit=do_full,
        )

    async def run(
        self,
        interval_seconds: float = 1.0,
        stop_event: Optional[asyncio.Event] = None,
    ) -> None:
        """Async-Timer fuer den Hub-Takt (Alternative zum System-Cron).

        Fail-fast: Eine ungefaangene ``ShadowAuditDivergence`` beendet die
        Schleife; der Book-Feed ist davon entkoppelt und laeuft weiter.
        """
        stop = stop_event or asyncio.Event()
        while not stop.is_set():
            self.tick()
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                continue
