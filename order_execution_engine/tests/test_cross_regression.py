"""Regression — Golden FillResult-Listen über den produktiven ``match()``-Seam.

W-SLIP-1: bit-identisch zu ``tests/fixtures/cross_golden.json`` (pre-delegation).
W-QUEUE-2: Crossing-Pfad unabhängig von ``conservative_queue``.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from pathlib import Path

from order_execution_engine.fill_simulator import FillSimConfig, RestingModel
from order_execution_engine.models import (
    Direction,
    OrderSide,
    OrderStatus,
    OrderType,
    PaperOrder,
    RiskConfig,
    SignalPayload,
    default_expiration,
)
from order_execution_engine.shadow_execution_engine import (
    MarketSnapshot,
    OrderBookLevel,
    PaperMatchEngine,
    ShadowExecutionEngine,
)

GOLDEN_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "cross_golden.json"
)
GOLDEN = json.loads(GOLDEN_PATH.read_text())


def _load_snapshot(data: dict) -> MarketSnapshot:
    return MarketSnapshot(
        token_id=data["token_id"],
        asks=tuple(
            OrderBookLevel(Decimal(x["price"]), Decimal(x["size"]))
            for x in data["asks"]
        ),
        bids=tuple(
            OrderBookLevel(Decimal(x["price"]), Decimal(x["size"]))
            for x in data["bids"]
        ),
        received_at=float(data["received_at"]),
    )


def _load_order(data: dict) -> PaperOrder:
    return PaperOrder(
        order_id=uuid.UUID(data["order_id"]),
        signal_id=uuid.UUID(data["signal_id"]),
        token_id=data["token_id"],
        side=OrderSide(data["side"]),
        price=Decimal(data["price"]),
        size=Decimal(data["size"]),
        expiration=default_expiration(5),
        order_type=OrderType(data["order_type"]),
    )


def _fills_as_dicts(fills) -> list[dict]:
    return [
        {
            "order_id": str(f.order_id),
            "execution_price": str(f.execution_price),
            "executed_size": str(f.executed_size),
            "slippage": str(f.slippage),
            "fee": str(f.fee),
            "side": f.side.value,
            "token_id": f.token_id,
            "market_id": f.market_id,
        }
        for f in fills
    ]


def _matcher_for_case(
    case: dict, *, conservative_queue: bool = True,
) -> PaperMatchEngine:
    fee = Decimal(case["fee_bps"])
    cap = (
        None if case["max_slippage_bps"] is None
        else Decimal(case["max_slippage_bps"])
    )
    return PaperMatchEngine(
        fee_bps=fee,
        max_slippage_bps=cap,
        fill_sim_config=FillSimConfig(conservative_queue=conservative_queue),
    )


def test_w_slip_1_golden_fills() -> None:
    """W-SLIP-1: FillResult-Listen bit-identisch über ``match()``."""
    assert GOLDEN, "cross_golden.json leer — dump_cross_fixtures.py erneut?"
    for case in GOLDEN:
        eng = _matcher_for_case(case)
        order = _load_order(case["order"])
        # Fixture-size == order.size (Dump-Vertrag); Match nutzt order.size.
        assert str(order.size) == case["size"], case["name"]
        result = eng.match(
            order, _load_snapshot(case["snapshot"]),
            market_id=case["market_id"],
        )
        assert _fills_as_dicts(result.fills) == case["expected_fills"], case["name"]
        assert str(result.remaining_size) == case["expected_remaining"], case["name"]
    print("OK test_w_slip_1_golden_fills")


def test_w_queue_2_cross_unaffected_by_queue() -> None:
    """W-QUEUE-2: Crossing unabhängig von conservative_queue an/aus."""
    for conservative in (True, False):
        for case in GOLDEN:
            eng = _matcher_for_case(case, conservative_queue=conservative)
            result = eng.match(
                _load_order(case["order"]),
                _load_snapshot(case["snapshot"]),
                market_id=case["market_id"],
            )
            assert _fills_as_dicts(result.fills) == case["expected_fills"], (
                f"{case['name']} conservative_queue={conservative}"
            )
    print("OK test_w_queue_2_cross_unaffected_by_queue")


def test_match_exposes_fill_metrics() -> None:
    """Stichprobe: match() trägt reale FillMetrics."""
    eng = PaperMatchEngine(fee_bps=Decimal("10"))
    order = _load_order(GOLDEN[0]["order"])
    snapshot = _load_snapshot(GOLDEN[0]["snapshot"])
    result = eng.match(order, snapshot, market_id="mkt-1")
    assert result.fill_metrics is not None
    assert result.fill_metrics.filled_size == Decimal("200")
    assert result.fill_metrics.levels_consumed == 1
    assert result.fill_metrics.slippage.capped is False
    print("OK test_match_exposes_fill_metrics")


def test_engine_telemetry_carries_fill_metrics() -> None:
    """Engine-Telemetrie auf approved-Pfad enthält fill_metrics."""
    eng = ShadowExecutionEngine(
        risk_config=RiskConfig(max_order_size_shares=Decimal("100")),
    )
    snap = MarketSnapshot(
        token_id="0xtokenA",
        asks=(OrderBookLevel(Decimal("0.61"), Decimal("200")),),
        bids=(OrderBookLevel(Decimal("0.59"), Decimal("150")),),
    )
    sig = SignalPayload(
        target_token_id="0xtokenA", market_id="mkt-1",
        direction=Direction.UP, confidence=Decimal("80"),
    )
    report = eng.on_signal(sig, snap)
    assert report.approved
    rec = eng.telemetry._records[-1]
    assert rec.fill_metrics is not None
    assert rec.fill_metrics.filled_size > 0
    print("OK test_engine_telemetry_carries_fill_metrics")


def test_resting_model_trade_through_opt_in() -> None:
    """TRADE_THROUGH: Fill nur bei striktem Durchbruch; Default bleibt RE_CROSS."""
    # RE_CROSS (Default): neue Tiefe am Limit füllt Rest — Kanon.
    m_recross = PaperMatchEngine()
    thin = MarketSnapshot(
        token_id="0xtokenA",
        asks=(OrderBookLevel(Decimal("0.61"), Decimal("200")),),
        bids=(OrderBookLevel(Decimal("0.59"), Decimal("150")),),
    )
    more_depth = MarketSnapshot(
        token_id="0xtokenA",
        asks=(OrderBookLevel(Decimal("0.61"), Decimal("500")),),
        bids=(OrderBookLevel(Decimal("0.59"), Decimal("150")),),
    )
    o = PaperOrder(
        signal_id=uuid.uuid4(), token_id="0xtokenA", side=OrderSide.BUY,
        price=Decimal("0.61"), size=Decimal("400"),
        expiration=default_expiration(5), order_type=OrderType.GTC,
    )
    assert m_recross.match(o, thin, market_id="mkt-1").remaining_size == Decimal("200")
    evals = m_recross.on_book_update(more_depth)
    assert evals[0].result.status is OrderStatus.FILLED

    # TRADE_THROUGH: gleiche Tiefe am Limit — kein Fill; erst best_ask < Limit.
    m_tt = PaperMatchEngine(
        fill_sim_config=FillSimConfig(resting_model=RestingModel.TRADE_THROUGH),
    )
    o2 = o.model_copy(update={"order_id": uuid.uuid4()})
    assert m_tt.match(o2, thin, market_id="mkt-1").remaining_size == Decimal("200")
    idle = m_tt.on_book_update(more_depth)
    assert idle[0].result.fills == ()
    assert idle[0].result.remaining_size == Decimal("200")
    through = MarketSnapshot(
        token_id="0xtokenA",
        asks=(OrderBookLevel(Decimal("0.60"), Decimal("10")),),
        bids=(OrderBookLevel(Decimal("0.59"), Decimal("150")),),
    )
    filled = m_tt.on_book_update(through)
    assert filled[0].result.status is OrderStatus.FILLED
    assert filled[0].result.fills[0].execution_price == Decimal("0.61")
    print("OK test_resting_model_trade_through_opt_in")


def test_fill_sim_property_on_engine() -> None:
    """Engine.fill_sim ist der Matcher-Seam (keine stille Privatkopplung)."""
    eng = ShadowExecutionEngine()
    assert eng.fill_sim is eng.matcher.fill_sim
    print("OK test_fill_sim_property_on_engine")
