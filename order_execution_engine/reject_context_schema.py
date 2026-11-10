"""Pflicht-Context-Schemas je RejectReason / TelemetryClass (Bauplan §2.3).

GP-2: Runtime = validate + warn + minimal context + ``schema_violation``;
nie Hot-Path-Kill. CI = rot. Welle W3 füllt REQUIRED_FIELDS vollständig;
W1 liefert den Vertrag + Stub, damit A3.4 rot gegen Baseline belegt ist.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, MutableMapping, Optional, Sequence, Union

from order_execution_engine.models import RejectReason
from order_execution_engine.telemetry_classes import TelemetryClass

_LOG = logging.getLogger(__name__)

SchemaKey = Union[RejectReason, TelemetryClass, str]

# Bauplan §2.3 — bindende Feldlisten (GP-3). W3 verdrahtet Validator-Lauf.
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


def _key_name(key: SchemaKey) -> str:
    if isinstance(key, (RejectReason, TelemetryClass)):
        return key.value
    return str(key)


def validate_reject_context(
    key: SchemaKey,
    ctx: Optional[Mapping[str, Any]],
    *,
    hot_path: bool = True,
) -> dict[str, Any]:
    """Prüft Pflichtfelder. Runtime: nie raise. CI (hot_path=False): Assertion.

    W1-Stub: REQUIRED_FIELDS sind definiert, aber die Engine ruft diese
    Funktion noch nicht auf — A3.4 belegt den Vertrag gegen den Stub.
    W3 verdrahtet den Hot-Path und den Violation-Zähler.
    """
    name = _key_name(key)
    required = REQUIRED_FIELDS.get(name, ())
    base: MutableMapping[str, Any] = dict(ctx or {})
    missing = [
        f
        for f in required
        if f not in base or base[f] is None
    ]
    if not missing:
        base.setdefault("schema_violation", False)
        return dict(base)

    if not hot_path:
        raise AssertionError(
            f"Context-Schema verletzt für {name}: missing={missing}"
        )

    # GP-2 Runtime: warn + Flag, Loop weiter.
    _LOG.warning(
        "reject_context schema_violation key=%s missing=%s",
        name,
        missing,
    )
    base["schema_violation"] = True
    base["missing_keys"] = tuple(missing)
    return dict(base)


def required_fields_for(key: SchemaKey) -> Sequence[str]:
    return REQUIRED_FIELDS.get(_key_name(key), ())
