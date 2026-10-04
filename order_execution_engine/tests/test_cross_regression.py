"""Regression Commit 2 — Golden FillResult-Listen nach FillSimulator-Delegation.

W-SLIP-1: bit-identisch zu ``tests/fixtures/cross_golden.json`` (pre-delegation).
W-QUEUE-2: Crossing-Pfad unabhängig von ``conservative_queue``.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from pathlib import Path

from order_execution_engine.fill_simulator import FillSimConfig
from order_execution_engine.models import (
    OrderSide,
    OrderType,
    PaperOrder,
    default_expiration,
)
from order_execution_engine.shadow_execution_engine import (
    MarketSnapshot,
    OrderBookLevel,
    PaperMatchEngine,
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


def _build_matcher(
    *,
    fee_bps: Decimal = Decimal("0"),
    max_slippage_bps: Decimal | None = None,
    conservative_queue: bool = True,
) -> PaperMatchEngine:
    return PaperMatchEngine(
        fee_bps=fee_bps,
        max_slippage_bps=max_slippage_bps,
        fill_sim_config=FillSimConfig(conservative_queue=conservative_queue),
    )


def _matcher_for_case(case: dict, *, conservative_queue: bool = True) -> PaperMatchEngine:
    fee = Decimal(case["fee_bps"])
    cap = (
        None if case["max_slippage_bps"] is None
        else Decimal(case["max_slippage_bps"])
    )
    return _build_matcher(
        fee_bps=fee,
        max_slippage_bps=cap,
        conservative_queue=conservative_queue,
    )


def test_w_slip_1_golden_fills() -> None:
    """W-SLIP-1: FillResult-Listen bit-identisch zu Golden Fixtures."""
    assert GOLDEN, "cross_golden.json leer — dump_cross_fixtures.py erneut?"
    for case in GOLDEN:
        eng = _matcher_for_case(case)
        order = _load_order(case["order"])
        snapshot = _load_snapshot(case["snapshot"])
        fills, remaining, ref = eng._cross(
            order, snapshot, Decimal(case["size"]),
            market_id=case["market_id"],
        )
        assert _fills_as_dicts(fills) == case["expected_fills"], case["name"]
        assert str(remaining) == case["expected_remaining"], case["name"]
        assert str(ref) == case["expected_reference"], case["name"]
    print("OK test_w_slip_1_golden_fills")


def test_w_queue_2_cross_unaffected_by_queue() -> None:
    """W-QUEUE-2: Crossing unabhängig von conservative_queue an/aus."""
    for conservative in (True, False):
        for case in GOLDEN:
            eng = _matcher_for_case(case, conservative_queue=conservative)
            fills, _, _ = eng._cross(
                _load_order(case["order"]),
                _load_snapshot(case["snapshot"]),
                Decimal(case["size"]),
                market_id=case["market_id"],
            )
            assert _fills_as_dicts(fills) == case["expected_fills"], (
                f"{case['name']} conservative_queue={conservative}"
            )
    print("OK test_w_queue_2_cross_unaffected_by_queue")


def test_match_exposes_fill_metrics() -> None:
    """Stichprobe: match() trägt reale FillMetrics (Telemetrie-Seam)."""
    eng = PaperMatchEngine(fee_bps=Decimal("10"))
    order = _load_order(GOLDEN[0]["order"])
    snapshot = _load_snapshot(GOLDEN[0]["snapshot"])
    # size aus Fixture (200) — Order-Objekt trägt size=200 bereits
    result = eng.match(order, snapshot, market_id="mkt-1")
    assert result.fill_metrics is not None
    assert result.fill_metrics.filled_size == Decimal("200")
    assert result.fill_metrics.levels_consumed == 1
    assert result.fill_metrics.slippage.capped is False
    print("OK test_match_exposes_fill_metrics")


def test_engine_telemetry_carries_fill_metrics() -> None:
    """Engine-Telemetrie auf approved-Pfad enthält fill_metrics."""
    from order_execution_engine.models import Direction, RiskConfig, SignalPayload
    from order_execution_engine.shadow_execution_engine import ShadowExecutionEngine

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
