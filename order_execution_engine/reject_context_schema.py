"""Pflicht-Context-Schemas je RejectReason / TelemetryClass (Bauplan §2.3).

GP-2: Runtime = validate + warn + ``schema_violation``; nie Hot-Path-Kill.
GP-S2-8: Nullbarkeit **feldgenau** per Reason — nicht global „Wert darf None“.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, MutableMapping, Optional, Sequence, Union

from order_execution_engine.models import RejectReason
from order_execution_engine.telemetry_classes import TelemetryClass

_LOG = logging.getLogger(__name__)

SchemaKey = Union[RejectReason, TelemetryClass, str]

REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    RejectReason.NONE.value: ("branch",),
    RejectReason.MAX_POSITION_SIZE.value: (
        "current_notional",
        "order_notional",
        "max_position_size_usdc",
        "token_id",
        "side",
        "branch",
    ),
    TelemetryClass.UNACTIONABLE_SELL_NO_INVENTORY.value: (
        "available",
        "order_size",
        "pos_size",
        "token_id",
        "side",
        "branch",
    ),
    RejectReason.MAX_EVENT_EXPOSURE.value: (
        "event_exposure",
        "order_notional",
        "max_event_exposure_usdc",
        "market_id",
        "token_id",
        "side",
        "branch",
    ),
    RejectReason.INSUFFICIENT_CASH.value: (
        "cash",
        "order_notional",
        "token_id",
        "side",
        "branch",
    ),
    RejectReason.DRAWDOWN_LOCKOUT.value: (
        "drawdown_pct",
        "token_id",
        "side",
        "branch",
    ),
    RejectReason.STALE_SNAPSHOT.value: (
        "snapshot_age_s",
        "max_book_age_ms",
        "token_id",
        "side",
        "source",
        "branch",
    ),
    RejectReason.NEUTRAL_SIGNAL.value: ("token_id", "branch"),
    RejectReason.NO_SNAPSHOT.value: ("token_id", "side", "source", "branch"),
    RejectReason.EMPTY_SIDE.value: (
        "token_id",
        "side",
        "best_bid",
        "best_ask",
        "source",
        "branch",
    ),
    RejectReason.SIDE_NOT_DELIVERED.value: (
        "token_id",
        "side",
        "source",
        "branch",
    ),
    RejectReason.SIDE_UNKNOWN_SOURCE.value: (
        "token_id",
        "side",
        "source",
        "branch",
    ),
    RejectReason.INVALID_PRICE.value: (
        "price",
        "side",
        "price_min",
        "price_max",
        "token_id",
        "branch",
    ),
}

# GP-S2-8: None erlaubt nur hier (Key muss trotzdem existieren).
# Sweep A-D3 gegen Produzenten in shadow_execution_engine.py:
#   NO_SNAPSHOT Z.1227 source=None · SIDE_UNKNOWN_SOURCE Z.1248–1278 source=None
#   EMPTY_SIDE: genau eine Seite nullable; beide None = Violation (→ eher NO_SNAPSHOT)
#   SIDE_NOT_DELIVERED: source immer "ticker" → nicht nullable
NULLABLE: dict[str, frozenset[str]] = {
    TelemetryClass.UNACTIONABLE_SELL_NO_INVENTORY.value: frozenset({"pos_size"}),
    RejectReason.EMPTY_SIDE.value: frozenset({"best_bid", "best_ask"}),
    RejectReason.NO_SNAPSHOT.value: frozenset({"source"}),
    RejectReason.SIDE_UNKNOWN_SOURCE.value: frozenset({"source"}),
}


def _key_name(key: SchemaKey) -> str:
    if isinstance(key, (RejectReason, TelemetryClass)):
        return key.value
    return str(key)


def _null_violations(name: str, base: Mapping[str, Any], required: Sequence[str]) -> list[str]:
    nullable = NULLABLE.get(name, frozenset())
    bad: list[str] = []
    for f in required:
        if f not in base:
            continue
        if base[f] is None and f not in nullable:
            bad.append(f)
    if name == RejectReason.EMPTY_SIDE.value:
        bid = base.get("best_bid", _MISSING)
        ask = base.get("best_ask", _MISSING)
        if bid is not _MISSING and ask is not _MISSING and bid is None and ask is None:
            bad.append("best_bid|best_ask")
    return bad


_MISSING = object()


def validate_reject_context(
    key: SchemaKey,
    ctx: Optional[Mapping[str, Any]],
    *,
    hot_path: bool = True,
) -> dict[str, Any]:
    """Prüft Pflichtfelder + feldgenaue Nullbarkeit (GP-S2-8)."""
    name = _key_name(key)
    required = REQUIRED_FIELDS.get(name, ())
    base: MutableMapping[str, Any] = dict(ctx or {})
    missing = [f for f in required if f not in base]
    null_bad = _null_violations(name, base, required)
    problems = missing + [f"null:{f}" for f in null_bad]
    if not problems:
        base.setdefault("schema_violation", False)
        return dict(base)

    if not hot_path:
        raise AssertionError(
            f"Context-Schema verletzt für {name}: missing={missing} null={null_bad}"
        )

    _LOG.warning(
        "reject_context schema_violation key=%s missing=%s null=%s",
        name,
        missing,
        null_bad,
    )
    base["schema_violation"] = True
    base["missing_keys"] = tuple(problems)
    return dict(base)


def required_fields_for(key: SchemaKey) -> Sequence[str]:
    return REQUIRED_FIELDS.get(_key_name(key), ())


def nullable_fields_for(key: SchemaKey) -> frozenset[str]:
    return NULLABLE.get(_key_name(key), frozenset())
