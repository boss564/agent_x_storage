"""Transport health: dead vs quiet vs degraded vs ok.

Same invariant as feed-gap / cross-venue heartbeats: silence is not liveness.
Pre-Reg: docs/NEWS_FEED_STRUCTURE_PREREG.md — structure_ok (container presence).
"""
from __future__ import annotations

from typing import Any, Optional

# Frozen: do not collapse bozo-only and HTTP-fail into one alarm.
HEALTH_OK = "ok"
HEALTH_QUIET = "quiet"
HEALTH_DEGRADED = "degraded"
HEALTH_DEAD = "dead"


def classify_transport_health(
    *,
    status: Optional[int],
    bozo: int,
    entries: int,
    structure_ok: bool = True,
) -> str:
    """HTTP/parse/structure classification.

    Pre-Reg §3 order:
      1. bad status or (bozo ∧ empty) → dead
      2. bozo ∧ entries>0 → degraded
      3. ¬structure_ok → degraded
      4. entries==0 → quiet
      5. else → ok

    structure_ok defaults True (backward compatible when unset).
    """
    n = int(entries)
    bozo_flag = 1 if bozo else 0
    if status not in (None, 200) or (bozo_flag and n == 0):
        return HEALTH_DEAD
    if bozo_flag:
        return HEALTH_DEGRADED
    if not structure_ok:
        return HEALTH_DEGRADED
    if n == 0:
        return HEALTH_QUIET
    return HEALTH_OK


def feed_report(
    *,
    status: Optional[int],
    bozo: int,
    entries: int,
    bozo_exception: Any = None,
    structure_ok: bool = True,
) -> dict:
    health = classify_transport_health(
        status=status,
        bozo=bozo,
        entries=entries,
        structure_ok=structure_ok,
    )
    return {
        "status": status,
        "bozo": 1 if bozo else 0,
        "entries": int(entries),
        "health": health,
        "structure_ok": bool(structure_ok),
        "bozo_exception": None if not bozo else repr(bozo_exception),
    }
