"""S2-W0: GP-S2-8 Nullbarkeits-Matrix + A-D3 Sweep."""

from __future__ import annotations

from decimal import Decimal

from order_execution_engine.models import RejectReason
from order_execution_engine.reject_context_schema import (
    NULLABLE,
    REQUIRED_FIELDS,
    validate_reject_context,
)
from order_execution_engine.telemetry_classes import TelemetryClass


def test_w0_available_none_is_violation() -> None:
    out = validate_reject_context(
        TelemetryClass.UNACTIONABLE_SELL_NO_INVENTORY,
        {
            "available": None,
            "order_size": Decimal("25"),
            "pos_size": None,
            "token_id": "t",
            "side": "SELL",
            "branch": 1,
        },
        hot_path=True,
    )
    assert out["schema_violation"] is True
    assert any("available" in str(x) for x in out.get("missing_keys", ()))
    print("OK test_w0_available_none_is_violation")


def test_w0_pos_size_none_ok_for_d2() -> None:
    out = validate_reject_context(
        TelemetryClass.UNACTIONABLE_SELL_NO_INVENTORY,
        {
            "available": Decimal("0"),
            "order_size": Decimal("25"),
            "pos_size": None,
            "token_id": "t",
            "side": "SELL",
            "branch": 1,
        },
        hot_path=True,
    )
    assert out.get("schema_violation") is False
    print("OK test_w0_pos_size_none_ok_for_d2")


def test_w0_empty_side_one_null_ok() -> None:
    out = validate_reject_context(
        RejectReason.EMPTY_SIDE,
        {
            "token_id": "t",
            "side": "BUY",
            "best_bid": None,
            "best_ask": Decimal("0.61"),
            "source": "book",
            "branch": 1185,
        },
        hot_path=True,
    )
    assert out.get("schema_violation") is False
    print("OK test_w0_empty_side_one_null_ok")


def test_w0_empty_side_both_null_violation() -> None:
    out = validate_reject_context(
        RejectReason.EMPTY_SIDE,
        {
            "token_id": "t",
            "side": "BUY",
            "best_bid": None,
            "best_ask": None,
            "source": "book",
            "branch": 1185,
        },
        hot_path=True,
    )
    assert out["schema_violation"] is True
    print("OK test_w0_empty_side_both_null_violation")


def test_w0_a_d3_fixture_sweep_minimal_contexts() -> None:
    """A-D3: realistische Minimal-Contexts — Violation nur wo Matrix es verlangt."""
    fixtures: list[tuple[object, dict, bool]] = [
        (RejectReason.NEUTRAL_SIGNAL, {"token_id": "t", "branch": 1160}, False),
        (
            RejectReason.NO_SNAPSHOT,
            # Produzent Z.1227: source=None ist Ist — Sweep → NULLABLE.
            {"token_id": "t", "side": "BUY", "source": None, "branch": 1174},
            False,
        ),
        (
            RejectReason.EMPTY_SIDE,
            {
                "token_id": "t",
                "side": "BUY",
                "best_bid": None,
                "best_ask": Decimal("0.5"),
                "source": "book",
                "branch": 1185,
            },
            False,
        ),
        (
            RejectReason.EMPTY_SIDE,
            # Beidseitig leer: Matrix verlangt Violation (eher NO_SNAPSHOT).
            # Produzent kann das heute noch als EMPTY_SIDE liefern — Fund, kein Fix.
            {
                "token_id": "t",
                "side": "BUY",
                "best_bid": None,
                "best_ask": None,
                "source": "book",
                "branch": 1185,
            },
            True,
        ),
        (
            RejectReason.SIDE_NOT_DELIVERED,
            {"token_id": "t", "side": "BUY", "source": "ticker", "branch": 1185},
            False,
        ),
        (
            RejectReason.SIDE_UNKNOWN_SOURCE,
            # Produzent Z.1248–1278: source=None → SIDE_UNKNOWN_SOURCE.
            {"token_id": "t", "side": "BUY", "source": None, "branch": 1185},
            False,
        ),
        (
            RejectReason.INVALID_PRICE,
            {
                "price": Decimal("1.5"),
                "side": "BUY",
                "price_min": Decimal("0"),
                "price_max": Decimal("1"),
                "token_id": "t",
                "branch": 1260,
            },
            False,
        ),
        (
            RejectReason.STALE_SNAPSHOT,
            {
                "snapshot_age_s": 5.0,
                "max_book_age_ms": 500,
                "token_id": "t",
                "side": "BUY",
                "source": "book",
                "branch": 1323,
            },
            False,
        ),
        (
            TelemetryClass.UNACTIONABLE_SELL_NO_INVENTORY,
            {
                "available": Decimal("0"),
                "order_size": Decimal("10"),
                "pos_size": None,
                "token_id": "t",
                "side": "SELL",
                "branch": 1346,
            },
            False,
        ),
        (
            RejectReason.MAX_POSITION_SIZE,
            {
                "current_notional": Decimal("100"),
                "order_notional": Decimal("50"),
                "max_position_size_usdc": Decimal("100"),
                "token_id": "t",
                "side": "BUY",
                "branch": 1370,
            },
            False,
        ),
        (
            RejectReason.MAX_EVENT_EXPOSURE,
            {
                "event_exposure": Decimal("10"),
                "order_notional": Decimal("5"),
                "max_event_exposure_usdc": Decimal("10"),
                "market_id": "m",
                "token_id": "t",
                "side": "BUY",
                "branch": 1370,
            },
            False,
        ),
        (
            RejectReason.INSUFFICIENT_CASH,
            {
                "cash": Decimal("1"),
                "order_notional": Decimal("50"),
                "token_id": "t",
                "side": "BUY",
                "branch": 1370,
            },
            False,
        ),
        (
            RejectReason.DRAWDOWN_LOCKOUT,
            {
                "drawdown_pct": Decimal("20"),
                "token_id": "t",
                "side": "BUY",
                "branch": 1370,
            },
            False,
        ),
        (RejectReason.NONE, {"branch": 0}, False),
    ]
    covered = {getattr(k, "value", str(k)) for k, _, _ in fixtures}
    assert set(REQUIRED_FIELDS) <= covered | {RejectReason.NONE.value}
    for key, ctx, expect_viol in fixtures:
        out = validate_reject_context(key, ctx, hot_path=True)
        got = bool(out.get("schema_violation"))
        assert got is expect_viol, f"{key}: expected viol={expect_viol} got={got} {out}"
    assert "pos_size" in NULLABLE[TelemetryClass.UNACTIONABLE_SELL_NO_INVENTORY.value]
    print("OK test_w0_a_d3_fixture_sweep_minimal_contexts")


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and fn.__name__.startswith("test_"):
            fn()
    print("S2-W0 NACHWEIS grün")
