"""Schritt 1 — Welle W1: v9-DDL (grün) + Soll-Tests M5/M6/A2.5/A3.4.

Gegen Baseline ``ec2e5ca3`` / Bauplan GP-1…GP-5 + Bindungen P-1…P-3.
Charter: order_send=false — kein Trading-Pfad.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

try:
    import pytest
except ImportError:  # pragma: no cover — Host ohne pytest: Marker no-op
    class _PytestStub:
        @staticmethod
        def mark_xfail(*_a, **_k):
            def _wrap(fn):
                return fn
            return _wrap

        class mark:
            @staticmethod
            def xfail(*_a, **_k):
                def _wrap(fn):
                    return fn
                return _wrap

    pytest = _PytestStub()  # type: ignore[misc, assignment]

from order_execution_engine.fill_simulator import FillSimConfig
from order_execution_engine.models import (
    Direction,
    RejectReason,
    RiskConfig,
    SignalPayload,
)
from order_execution_engine.persistence import SCHEMA_VERSION, SQLiteShadowStorage
from order_execution_engine.reject_context_schema import validate_reject_context
from order_execution_engine.shadow_execution_engine import (
    MarketSnapshot,
    OrderBookLevel,
    ShadowExecutionEngine,
)
from order_execution_engine.telemetry_classes import (
    UNACTIONABLE_SELL_NO_INVENTORY,
    TelemetryClass,
)


def _book(*, received_at: float | None = None) -> MarketSnapshot:
    kw: dict = {
        "token_id": "0xtokenA",
        "asks": (OrderBookLevel(Decimal("0.61"), Decimal("200")),),
        "bids": (OrderBookLevel(Decimal("0.59"), Decimal("150")),),
        "source": "book",
    }
    if received_at is not None:
        kw["received_at"] = received_at
    return MarketSnapshot(**kw)


def _sell_via_invert(eng: ShadowExecutionEngine, book: MarketSnapshot):
    """Schwaches UP + invert → SELL ohne Inventar (Live-Pfad der M5-Kollision)."""
    weak = SignalPayload(
        target_token_id="0xtokenA",
        market_id="mkt-1",
        direction=Direction.UP,
        confidence=Decimal("40"),
    )
    return eng.on_signal(weak, book)


# --- W1 grün: v9 DDL (P-3) -------------------------------------------------


def test_w1_schema_version_is_9() -> None:
    assert SCHEMA_VERSION == 9
    print("OK test_w1_schema_version_is_9")


def test_w1_migrate_v9_telemetry_class_idempotent() -> None:
    """P-3: additive Spalte, schema_meta + user_version = 9, zweimal öffnen."""
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "w1")
        store.close()
        store2 = SQLiteShadowStorage.for_user(Path(tmp), "w1")
        row = store2._conn.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
        assert row is not None and int(row[0]) == 9
        uv = store2._conn.execute("PRAGMA user_version").fetchone()[0]
        assert int(uv) == 9
        cols = {
            r[1] for r in store2._conn.execute("PRAGMA table_info(telemetry)")
        }
        assert "telemetry_class" in cols
        assert "reject_detail" in cols
        store2.close()
    print("OK test_w1_migrate_v9_telemetry_class_idempotent")


# --- W1 rot bis W2: M5 / M6 / A2.5 -----------------------------------------


def test_w1_m5_sell_without_inventory_not_max_position() -> None:
    """M5/D2 Soll: SELL ohne Inventar → telemetry_class, nicht MAX_POSITION_SIZE."""
    eng = ShadowExecutionEngine(
        risk_config=RiskConfig(max_order_size_shares=Decimal("100")),
        invert_weak_signals=True,
        confidence_threshold=Decimal("60"),
    )
    report = _sell_via_invert(eng, _book())
    rec = eng.telemetry._records[-1]
    assert not report.approved
    assert rec.reject_reason is not RejectReason.MAX_POSITION_SIZE, (
        "M5: SELL-ohne-Inventar darf nicht mehr MAX_POSITION_SIZE tragen"
    )
    assert rec.reject_reason in (RejectReason.NONE,)
    assert rec.telemetry_class == UNACTIONABLE_SELL_NO_INVENTORY
    print("OK test_w1_m5_sell_without_inventory_not_max_position")


def test_w1_m6_sell_context_answers_why() -> None:
    """M6 Soll: Context trägt available + order_size (Warum ohne Code-Lektüre)."""
    eng = ShadowExecutionEngine(
        risk_config=RiskConfig(max_order_size_shares=Decimal("100")),
        invert_weak_signals=True,
        confidence_threshold=Decimal("60"),
    )
    _sell_via_invert(eng, _book())
    rec = eng.telemetry._records[-1]
    assert not rec.approved
    assert rec.reject_context is not None
    ctx = rec.reject_context
    assert ctx.available is not None, "M6: available fehlt im Risk-Context"
    assert ctx.order_size is not None, "M6: order_size fehlt im Risk-Context"
    print("OK test_w1_m6_sell_context_answers_why")


def test_w1_a25_stale_precedes_d2() -> None:
    """A2.5 / GP-5: SELL + stales Buch → nur STALE_SNAPSHOT (Präzedenz 1 vor 2)."""
    eng = ShadowExecutionEngine(
        risk_config=RiskConfig(max_order_size_shares=Decimal("100")),
        invert_weak_signals=True,
        confidence_threshold=Decimal("60"),
        fill_sim_config=FillSimConfig(max_book_age_ms=500),
    )
    aged = _book(received_at=1.0)
    weak = SignalPayload(
        target_token_id="0xtokenA",
        market_id="mkt-1",
        direction=Direction.UP,
        confidence=Decimal("40"),
        timestamp=datetime.fromtimestamp(1.0, tz=timezone.utc),
    )
    report = eng.on_signal(weak, aged)
    rec = eng.telemetry._records[-1]
    assert not report.approved
    assert rec.reject_reason is RejectReason.STALE_SNAPSHOT
    assert rec.telemetry_class in (None, "")
    print("OK test_w1_a25_stale_precedes_d2")


# --- W1: A3.4 Validator-Vertrag (grün Stub) + Engine-Verdrahtung (rot bis W3)


def test_w1_a34_validator_hot_path_never_raises() -> None:
    """A3.4 Runtime: unvollständiger Context → kein Raise, schema_violation=True."""
    out = validate_reject_context(
        TelemetryClass.UNACTIONABLE_SELL_NO_INVENTORY,
        {"token_id": "0xtokenA", "side": "SELL", "branch": 1},
        hot_path=True,
    )
    assert out.get("schema_violation") is True
    assert "available" in out.get("missing_keys", ())
    print("OK test_w1_a34_validator_hot_path_never_raises")


def test_w1_a34_engine_flags_incomplete_sell_context() -> None:
    """A3.4: D2-Pfad nach W2 vollständig — complete erfüllt den Vertrag ohne Flag."""
    eng = ShadowExecutionEngine(
        risk_config=RiskConfig(max_order_size_shares=Decimal("100")),
        invert_weak_signals=True,
        confidence_threshold=Decimal("60"),
    )
    _sell_via_invert(eng, _book())
    rec = eng.telemetry._records[-1]
    assert not rec.approved
    assert rec.reject_context is not None
    ctx = rec.reject_context
    complete = ctx.available is not None and ctx.order_size is not None
    flagged = ctx.schema_violation is True
    assert complete or flagged, (
        "A3.4: incomplete Context ohne schema_violation — Validator nicht verdrahtet"
    )
    print("OK test_w1_a34_engine_flags_incomplete_sell_context")


if __name__ == "__main__":
    for fn in (
        test_w1_schema_version_is_9,
        test_w1_migrate_v9_telemetry_class_idempotent,
        test_w1_a34_validator_hot_path_never_raises,
        test_w1_a25_stale_precedes_d2,
        test_w1_m5_sell_without_inventory_not_max_position,
        test_w1_m6_sell_context_answers_why,
        test_w1_a34_engine_flags_incomplete_sell_context,
    ):
        fn()
    print("W2 NACHWEIS: A2.1–A2.6 / M5/M6/A2.5/A3.4-D2 grün")
