"""Fill-Tiefe Stufe — extrahierbarer Buch-Walk (Commit 1).

Charter (unverändert): diagnostic_only=true, live_execution=false,
order_send=false. Kein Netzwerk.

ADR 12: Records = frozen BaseModel; interne Queue-Buchhaltung = Dataclass.

Staleness-Producer (Anker D): ``ShadowExecutionEngine._preflight_staleness``
trägt das Literal ``RejectReason.STALE_SNAPSHOT``. Dieses Modul liefert nur
``is_stale() -> bool``.

Commit 1: Modul + Zeugen; ``PaperMatchEngine.match`` / ``_cross`` unberührt.
Commit 2: Delegation; Commit 3: ``_cross`` entfernen.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional, Protocol, Sequence

from pydantic import BaseModel, ConfigDict

from order_execution_engine.models import FillResult, OrderSide, PaperOrder

_BPS = Decimal("10000")


class StalenessPolicy(str, Enum):
    """Politik bei überaltertem Buch / Signal-Latenz."""

    REJECT_STALE = "reject_stale"  # Default, fail-closed
    NEXT_TICK = "next_tick"  # nur per Config: parken via GTC-Resting


class FillSimConfig(BaseModel):
    """Konfiguration der Fill-Simulation (frozen)."""

    model_config = ConfigDict(frozen=True)

    max_book_age_ms: int = 2000
    staleness_policy: StalenessPolicy = StalenessPolicy.REJECT_STALE
    conservative_queue: bool = True
    # Commit 2: 1:1 von PaperMatchEngine übernehmen
    max_slippage_bps: Optional[Decimal] = None
    fee_bps: Decimal = Decimal("0")


class SlippageReport(BaseModel):
    """Zwei Basen, explizit getrennt — keine ersetzt die andere."""

    model_config = ConfigDict(frozen=True)

    vs_touch_ref_bps: Optional[Decimal]  # (a) VWAP vs. Touch
    vs_signal_bps: Optional[Decimal]  # (b) vs. suggested_price, Fallback Limit
    capped: bool


class FillMetrics(BaseModel):
    """First-Class-Telemetrie pro Match-Vorgang."""

    model_config = ConfigDict(frozen=True)

    requested_size: Decimal
    filled_size: Decimal
    fill_ratio: Decimal
    levels_consumed: int
    vwap: Optional[Decimal]
    slippage: SlippageReport
    staleness_applied: Optional[StalenessPolicy] = None
    queue_ahead_at_rest: Optional[Decimal] = None


@dataclass
class _RestingQueue:
    """Queue-Buchhaltung. remaining_size bleibt im Kanon-_RestingOrder."""

    queue_ahead: Decimal
    last_level_size: Decimal


class _BookLevel(Protocol):
    price: Decimal
    size: Decimal


class _BookSnapshot(Protocol):
    """Strukturelles Snapshot-Protokoll (vermeidet Zirkularimport)."""

    asks: Sequence[_BookLevel]
    bids: Sequence[_BookLevel]
    received_at: float

    def best_ask(self) -> Optional[Decimal]: ...
    def best_bid(self) -> Optional[Decimal]: ...


def _level_size(
    snapshot: _BookSnapshot, side: OrderSide, price: Decimal,
) -> Decimal:
    """Tiefe am eigenen Limit — ``size_at_price`` fehlt im Kanon."""
    book_side = snapshot.bids if side == OrderSide.BUY else snapshot.asks
    for level in book_side:
        if level.price == price:
            return level.size
    return Decimal("0")


class FillSimulator:
    """Buch-Walk + Queue/Staleness-Hilfen (Commit 1, neben dem Matcher)."""

    def __init__(self, config: FillSimConfig) -> None:
        self._cfg = config
        self._resting_queue: dict[uuid.UUID, _RestingQueue] = {}
        self._signal_refs: dict[uuid.UUID, Decimal] = {}

    def is_stale(
        self,
        snapshot: _BookSnapshot,
        *,
        now_ms: float,
        signal_timestamp_ms: Optional[float],
    ) -> bool:
        """Reine Frischeprüfung. Reason-Literal liegt in der Engine (Anker D)."""
        book_age_ms = now_ms - snapshot.received_at * 1000.0
        latency_ms = (
            (now_ms - signal_timestamp_ms)
            if signal_timestamp_ms is not None
            else 0.0
        )
        return max(book_age_ms, latency_ms) > self._cfg.max_book_age_ms

    @property
    def staleness_policy(self) -> StalenessPolicy:
        return self._cfg.staleness_policy

    def register_signal_ref(
        self, order_id: uuid.UUID, suggested_price: Optional[Decimal],
    ) -> None:
        """Engine: ``suggested_price`` für vs_signal_bps (Korrektur B)."""
        if suggested_price is not None:
            self._signal_refs[order_id] = suggested_price

    def cross(
        self,
        order: PaperOrder,
        snapshot: _BookSnapshot,
        *,
        size: Decimal,
        market_id: Optional[str] = None,
    ) -> tuple[list[FillResult], FillMetrics]:
        """1:1-Walk aus ``_cross`` (Limit/Cap/Fee) plus Beobachtungs-Metriken.

        ``size`` = ``order.size`` bei Frischorders, ``remaining_size`` bei
        Resting-Nachwertung.
        """
        book_side = snapshot.asks if order.side == OrderSide.BUY else snapshot.bids
        remaining = size
        fills: list[FillResult] = []
        levels = 0
        notional = Decimal("0")
        capped = False
        # Kanon: Touch = erstes gültiges Level (nicht order.price)
        reference_price = order.price
        for _lvl in book_side:
            if _lvl.price > 0 and _lvl.size > 0:
                reference_price = _lvl.price
                break
        touch = reference_price

        for level in book_side:
            if remaining <= 0:
                break
            if level.price <= 0 or level.size <= 0:
                continue
            # Limit-Stop (Kanon, inline)
            if order.side == OrderSide.BUY and level.price > order.price:
                break
            if order.side == OrderSide.SELL and level.price < order.price:
                break
            executed = min(remaining, level.size)
            # Cap: pro Level vs. laufendem reference_price — nicht vs. run_vwap
            slip = level.price - reference_price
            if order.side == OrderSide.SELL:
                slip = -slip
            slip_bps = (slip / reference_price) * _BPS
            if (
                self._cfg.max_slippage_bps is not None
                and slip_bps > self._cfg.max_slippage_bps
            ):
                capped = True
                break
            reference_price = level.price  # erst NACH dem Cap-Check
            fee = (level.price * executed) * self._cfg.fee_bps / _BPS
            fills.append(FillResult(
                order_id=order.order_id,
                execution_price=level.price,
                executed_size=executed,
                slippage=slip,  # Kanon: Absolutbetrag, nicht bps
                fee=fee,
                side=order.side,
                token_id=order.token_id,
                market_id=market_id,
            ))
            levels += 1
            notional += level.price * executed
            remaining -= executed

        filled = size - remaining
        vwap = (notional / filled) if filled > 0 else None
        metrics = FillMetrics(
            requested_size=size,
            filled_size=filled,
            fill_ratio=(filled / size) if size > 0 else Decimal("0"),
            levels_consumed=levels,
            vwap=vwap,
            slippage=SlippageReport(
                vs_touch_ref_bps=self._bps(vwap, touch, order.side),
                vs_signal_bps=self._slippage_vs_signal(vwap, order),
                capped=capped,
            ),
        )
        return fills, metrics

    def place_resting(
        self,
        order: PaperOrder,
        snapshot: _BookSnapshot,
        *,
        remaining_size: Decimal,
        staleness_applied: Optional[StalenessPolicy] = None,
    ) -> FillMetrics:
        level_size = _level_size(snapshot, order.side, order.price)
        self._resting_queue[order.order_id] = _RestingQueue(
            queue_ahead=(
                level_size if self._cfg.conservative_queue else Decimal("0")
            ),
            last_level_size=level_size,
        )
        filled = order.size - remaining_size
        return FillMetrics(
            requested_size=order.size,
            filled_size=filled,
            fill_ratio=(filled / order.size) if order.size > 0 else Decimal("0"),
            levels_consumed=0,
            vwap=None,
            slippage=SlippageReport(
                vs_touch_ref_bps=None, vs_signal_bps=None, capped=False,
            ),
            staleness_applied=staleness_applied,
            queue_ahead_at_rest=level_size,
        )

    def on_book_update(
        self,
        order: PaperOrder,
        snapshot: _BookSnapshot,
        *,
        remaining_size: Decimal,
        market_id: Optional[str] = None,
    ) -> Optional[tuple[list[FillResult], FillMetrics]]:
        """Trade-Through-Fill; Level-Schwund ohne Durchbruch nur Queue."""
        st = self._resting_queue.get(order.order_id)
        if st is None:
            return None
        cur_level = _level_size(snapshot, order.side, order.price)
        if not self._trades_through(order, snapshot):
            shrink = max(Decimal("0"), st.last_level_size - cur_level)
            st.queue_ahead = max(Decimal("0"), st.queue_ahead - shrink)
            st.last_level_size = cur_level
            return None
        fills = [FillResult(
            order_id=order.order_id,
            execution_price=order.price,
            executed_size=remaining_size,
            slippage=Decimal("0"),
            fee=(order.price * remaining_size) * self._cfg.fee_bps / _BPS,
            side=order.side,
            token_id=order.token_id,
            market_id=market_id,
        )]
        queue_at_rest = st.queue_ahead
        self._resting_queue.pop(order.order_id, None)
        metrics = FillMetrics(
            requested_size=order.size,
            filled_size=order.size,
            fill_ratio=Decimal("1") if order.size > 0 else Decimal("0"),
            levels_consumed=1,
            vwap=order.price,
            slippage=SlippageReport(
                vs_touch_ref_bps=None,
                vs_signal_bps=self._slippage_vs_signal(order.price, order),
                capped=False,
            ),
            queue_ahead_at_rest=queue_at_rest,
        )
        return fills, metrics

    def _slippage_vs_signal(
        self, vwap: Optional[Decimal], order: PaperOrder,
    ) -> Optional[Decimal]:
        ref = self._signal_refs.get(order.order_id) or order.price
        if vwap is None or ref is None or ref == 0:
            return None
        sign = Decimal("1") if order.side == OrderSide.BUY else Decimal("-1")
        return (vwap - ref) / ref * _BPS * sign

    @staticmethod
    def _bps(
        vwap: Optional[Decimal],
        ref: Optional[Decimal],
        side: OrderSide,
    ) -> Optional[Decimal]:
        if vwap is None or ref is None or ref == 0:
            return None
        sign = Decimal("1") if side == OrderSide.BUY else Decimal("-1")
        return (vwap - ref) / ref * _BPS * sign

    @staticmethod
    def _trades_through(order: PaperOrder, snapshot: _BookSnapshot) -> bool:
        if order.side == OrderSide.BUY:
            best = snapshot.best_ask()
            return best is not None and best < order.price
        best = snapshot.best_bid()
        return best is not None and best > order.price
