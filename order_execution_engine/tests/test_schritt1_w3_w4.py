"""Schritt 1 — W3 Context-Validator + W4 Epoch-Andock / P-1."""

from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path

from order_execution_engine.epoch_hydrate import (
    FILLS_NO_DELETE_INVARIANT,
    assert_fills_rowid_anchor,
    positions_since_epoch,
    try_hydrate_engine_portfolio,
)
from order_execution_engine.models import Direction, RejectReason, RiskConfig, SignalPayload
from order_execution_engine.persistence import SQLiteShadowStorage
from order_execution_engine.reject_context_schema import validate_reject_context
from order_execution_engine.shadow_execution_engine import (
    MarketSnapshot,
    OrderBookLevel,
    ShadowExecutionEngine,
)
from order_execution_engine.telemetry_classes import TelemetryClass


def _book() -> MarketSnapshot:
    return MarketSnapshot(
        token_id="0xtokenA",
        asks=(OrderBookLevel(Decimal("0.61"), Decimal("200")),),
        bids=(OrderBookLevel(Decimal("0.59"), Decimal("150")),),
        source="book",
    )


def test_w3_ci_path_raises_on_incomplete() -> None:
    try:
        validate_reject_context(
            RejectReason.MAX_POSITION_SIZE,
            {"token_id": "t", "side": "BUY", "branch": 1},
            hot_path=False,
        )
    except AssertionError as exc:
        assert "missing" in str(exc).lower() or "MAX_POSITION" in str(exc)
        print("OK test_w3_ci_path_raises_on_incomplete")
        return
    raise AssertionError("CI-Pfad hätte AssertionError werfen müssen")


def test_w3_engine_wires_validator_no_raise() -> None:
    eng = ShadowExecutionEngine()
    before = eng.telemetry.schema_violations_total
    neutral = SignalPayload(
        target_token_id="0xtokenA", market_id="mkt-1",
        direction=Direction.NEUTRAL, confidence=Decimal("80"),
    )
    eng.on_signal(neutral, _book())
    # NEUTRAL Schema ist vollständig (token_id, branch) → keine Violation.
    assert eng.telemetry.schema_violations_total == before
    rec = eng.telemetry._records[-1]
    assert rec.reject_context is not None
    assert rec.reject_context.schema_violation in (None, False)
    print("OK test_w3_engine_wires_validator_no_raise")


def test_w3_d2_context_complete_no_violation() -> None:
    eng = ShadowExecutionEngine(
        risk_config=RiskConfig(max_order_size_shares=Decimal("100")),
        invert_weak_signals=True,
        confidence_threshold=Decimal("60"),
    )
    weak = SignalPayload(
        target_token_id="0xtokenA", market_id="mkt-1",
        direction=Direction.UP, confidence=Decimal("40"),
    )
    eng.on_signal(weak, _book())
    rec = eng.telemetry._records[-1]
    assert rec.telemetry_class == TelemetryClass.UNACTIONABLE_SELL_NO_INVENTORY.value
    assert rec.reject_context is not None
    assert rec.reject_context.schema_violation in (None, False)
    assert eng.telemetry.schema_violations_total == 0
    print("OK test_w3_d2_context_complete_no_violation")


def test_p1_fills_rowid_anchor() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "e1")
        mode = assert_fills_rowid_anchor(store._conn)
        assert mode in ("autoincrement", "rowid_no_delete")
        assert "DELETE" in FILLS_NO_DELETE_INVARIANT
        store.close()
    print("OK test_p1_fills_rowid_anchor")


def test_w4_positions_since_epoch_empty_after_marker() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "e1")
        # Keine Fills → Marker 0 → leeres Portfolio (D1-b Eröffnung)
        pf = positions_since_epoch(store, 0)
        assert pf.cash == Decimal("10000")
        assert not pf.positions
        eng = ShadowExecutionEngine()
        assert try_hydrate_engine_portfolio(
            eng, store, epoch_marker_rowid=0, enabled=True,
        )
        assert not try_hydrate_engine_portfolio(
            eng, store, epoch_marker_rowid=0, enabled=False,
        )
        store.close()
    print("OK test_w4_positions_since_epoch_empty_after_marker")


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and fn.__name__.startswith("test_"):
            fn()
    print("W3/W4 NACHWEIS grün")
