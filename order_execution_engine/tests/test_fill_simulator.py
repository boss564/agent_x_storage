"""Zeugen Fill-Tiefe Commit 1 — FillSimulator neben dem Bestand-Matcher.

match()/_cross bleiben unberührt; dieses Modul wird direkt gezeugt.
W-STALE-1/2 laufen gegen den Engine-Harness (siehe test_engine.py).
"""

from __future__ import annotations

import ast
import uuid
from decimal import Decimal
from pathlib import Path

from order_execution_engine.fill_simulator import (
    FillSimConfig,
    FillSimulator,
    StalenessPolicy,
)
from order_execution_engine.models import (
    Direction,
    OrderSide,
    OrderType,
    PaperOrder,
    SignalPayload,
    default_expiration,
)
from order_execution_engine.shadow_execution_engine import (
    MarketSnapshot,
    OrderBookLevel,
)


def _lvl(price: str, size: str) -> OrderBookLevel:
    return OrderBookLevel(Decimal(price), Decimal(size))


def _snap(
    asks: list[tuple[str, str]] | tuple = (),
    bids: list[tuple[str, str]] | tuple = (),
    *,
    received_at: float = 1_000.0,
    token: str = "t1",
) -> MarketSnapshot:
    return MarketSnapshot(
        token_id=token,
        asks=tuple(_lvl(p, s) for p, s in asks),
        bids=tuple(_lvl(p, s) for p, s in bids),
        received_at=received_at,
    )


def _order(
    side: OrderSide = OrderSide.BUY,
    price: str = "0.60",
    size: str = "100",
    oid: uuid.UUID | None = None,
) -> PaperOrder:
    o = PaperOrder(
        signal_id=SignalPayload(
            target_token_id="t1", market_id="m1",
            direction=Direction.UP, confidence=Decimal("70"),
        ).signal_id,
        token_id="t1",
        side=side,
        price=Decimal(price),
        size=Decimal(size),
        expiration=default_expiration(5),
        order_type=OrderType.GTC,
    )
    if oid is not None:
        o = o.model_copy(update={"order_id": oid})
    return o


SIM = FillSimulator(FillSimConfig(fee_bps=Decimal("10")))


def test_w_vwap_1_and_levels_1() -> None:
    """W-VWAP-1 / W-LEVELS-1: Walk über 2 Level, VWAP + Kanon-Fee."""
    s = _snap(asks=[("0.50", "40"), ("0.55", "80"), ("0.70", "50")])
    fills, m = SIM.cross(_order(OrderSide.BUY), s, size=Decimal("100"))
    assert m.levels_consumed == 2
    assert m.vwap == (Decimal("0.50") * 40 + Decimal("0.55") * 60) / 100
    assert m.fill_ratio == Decimal(1)
    assert fills[0].fee == Decimal("0.50") * 40 * Decimal(10) / Decimal(10_000)
    print("OK test_w_vwap_1_and_levels_1")


def test_w_ratio_1() -> None:
    """W-RATIO-1: Limit-Stop mittendrin → Partial; keine Tiefe → 0."""
    s = _snap(asks=[("0.50", "40"), ("0.55", "80")])
    _, m = SIM.cross(
        _order(OrderSide.BUY, price="0.52"), s, size=Decimal("100"),
    )
    assert m.fill_ratio == Decimal("0.4")
    _, m0 = SIM.cross(
        _order(OrderSide.BUY, price="0.40"), s, size=Decimal("100"),
    )
    assert m0.fill_ratio == Decimal(0)
    assert m0.levels_consumed == 0
    assert m0.vwap is None
    print("OK test_w_ratio_1")


def test_w_cap_1() -> None:
    """W-CAP-1: Cap pro Level vs. Touch-reference_price, nicht vs. run_vwap."""
    sim = FillSimulator(FillSimConfig(max_slippage_bps=Decimal("500")))
    s = _snap(asks=[("0.50", "50"), ("0.53", "50")])  # +6 % vs. Touch
    fills, m = sim.cross(_order(OrderSide.BUY), s, size=Decimal("100"))
    assert m.slippage.capped is True
    assert m.filled_size == Decimal("50")
    assert m.levels_consumed == 1
    assert len(fills) == 1
    print("OK test_w_cap_1")


def test_w_slip_2() -> None:
    """W-SLIP-2: suggested_price → Fallback order.price (Limit-Stop bleibt)."""
    sim = FillSimulator(FillSimConfig())
    s = _snap(asks=[("0.55", "100")])
    oid2 = uuid.uuid4()
    # Limit muss ≥ Ask sein, sonst kein Fill; Ref = suggested 0.50
    sim.register_signal_ref(oid2, Decimal("0.50"))
    _, m = sim.cross(
        _order(OrderSide.BUY, price="0.60", oid=oid2), s, size=Decimal("100"),
    )
    assert m.slippage.vs_signal_bps == Decimal("1000")  # (0.55-0.50)/0.50
    # Ohne register_signal_ref: Ref = Limit 0.60
    _, m2 = sim.cross(
        _order(OrderSide.BUY, price="0.60", oid=uuid.uuid4()),
        s, size=Decimal("100"),
    )
    assert m2.slippage.vs_signal_bps == (
        (Decimal("0.55") - Decimal("0.60")) / Decimal("0.60") * Decimal("10000")
    )
    print("OK test_w_slip_2")


def test_w_queue_1() -> None:
    """W-QUEUE-1: Trade-Through → Fill zum eigenen Limit, kein Improvement."""
    o = _order(OrderSide.BUY, price="0.50")
    SIM.place_resting(
        o,
        _snap(asks=[("0.55", "30")], bids=[("0.50", "70")]),
        remaining_size=Decimal("100"),
    )
    through = _snap(asks=[("0.49", "10")], bids=[("0.50", "70")])
    out = SIM.on_book_update(o, through, remaining_size=Decimal("100"))
    assert out is not None
    fills, m = out
    assert fills[0].execution_price == Decimal("0.50")
    assert fills[0].executed_size == Decimal("100")
    assert m.fill_ratio == 1
    print("OK test_w_queue_1")


def test_w_queue_3() -> None:
    """W-QUEUE-3: Level-Schwund ohne Durchbruch → queue_ahead sinkt, kein Fill."""
    sim = FillSimulator(FillSimConfig())
    o = _order(OrderSide.BUY, price="0.50")
    sim.place_resting(
        o,
        _snap(asks=[("0.55", "30")], bids=[("0.50", "70")]),
        remaining_size=Decimal("100"),
    )
    shrunk = _snap(asks=[("0.55", "30")], bids=[("0.50", "40")])
    assert sim.on_book_update(o, shrunk, remaining_size=Decimal("100")) is None
    assert sim._resting_queue[o.order_id].queue_ahead == Decimal("40")
    print("OK test_w_queue_3")


def test_w_charter_1() -> None:
    """W-CHARTER-1: kein Netzwerk-Import im Modul."""
    path = Path(__file__).resolve().parents[1] / "fill_simulator.py"
    tree = ast.parse(path.read_text())
    banned = {"socket", "requests", "http", "urllib", "aiohttp", "websockets"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names = {(node.module or "").split(".")[0]}
        else:
            continue
        assert not names & banned, names
    print("OK test_w_charter_1")


def test_is_stale_book_and_signal() -> None:
    """Hilfszeuge: is_stale nur bool — Literal bleibt in der Engine."""
    sim = FillSimulator(FillSimConfig(max_book_age_ms=2000))
    snap = _snap(asks=[("0.50", "10")], received_at=1.0)  # epoch s
    # now = 4s → book_age = 3000 ms > 2000
    assert sim.is_stale(snap, now_ms=4_000.0, signal_timestamp_ms=3_900.0)
    assert not sim.is_stale(snap, now_ms=2_500.0, signal_timestamp_ms=2_400.0)
    print("OK test_is_stale_book_and_signal")


def test_place_resting_staleness_applied_next_tick() -> None:
    """NEXT_TICK-Park-Metrik am Simulator (Engine verdichtet in Commit 2)."""
    sim = FillSimulator(FillSimConfig())
    o = _order(OrderSide.BUY, price="0.50")
    m = sim.place_resting(
        o,
        _snap(asks=[("0.55", "30")], bids=[("0.50", "70")]),
        remaining_size=Decimal("100"),
        staleness_applied=StalenessPolicy.NEXT_TICK,
    )
    assert m.staleness_applied is StalenessPolicy.NEXT_TICK
    assert m.queue_ahead_at_rest == Decimal("70")
    print("OK test_place_resting_staleness_applied_next_tick")
