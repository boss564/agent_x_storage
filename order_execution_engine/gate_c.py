"""Gate-C freshness from raw Event-Log fields (Bauplan v1.2 §4 / N-5).

Authority: runner ``book_update`` only (GP-M-4). Never reads ``cache_state``.
Named thresholds:
  - engine: ``engine_fresh_s`` = FillSimConfig().max_book_age_ms / 1000 (default 2.0)
  - probe:  ``probe_fresh_s`` = 30.0 (comparison column; configurable)
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Sequence

from order_execution_engine.fill_simulator import FillSimConfig

MappingLike = Mapping[str, Any]

# Named thresholds — read FillSimConfig default; do not mutate max_book_age_ms.
ENGINE_FRESH_S: float = float(FillSimConfig().max_book_age_ms) / 1000.0
PROBE_FRESH_S: float = 30.0


def engine_fresh_s_default() -> float:
    """Engine freshness threshold in seconds (= max_book_age_ms default / 1000)."""
    return float(FillSimConfig().max_book_age_ms) / 1000.0


def last_book_update_age_s(
    events: Sequence[MappingLike],
    token_id: str,
    *,
    producer: str = "runner",
    now: Optional[float] = None,
) -> Optional[float]:
    """Age of last matching ``book_update`` from raw wall_ts/received_at.

    N-5 / GP-M-4: ignores ``cache_state``, ``tick_sample``, ``probe_sample``.
    Prefers ``received_at`` when present; else ``wall_ts``.
    """
    import time

    wall = float(now) if now is not None else time.time()
    last_ref: Optional[float] = None
    for ev in events:
        if ev.get("event_type") != "book_update":
            continue
        if ev.get("producer") != producer:
            continue
        if ev.get("token_id") != token_id:
            continue
        # Raw fields only — never cache_state.
        if ev.get("received_at") is not None:
            last_ref = float(ev["received_at"])
        elif ev.get("wall_ts") is not None:
            last_ref = float(ev["wall_ts"])
    if last_ref is None:
        return None
    return max(0.0, wall - last_ref)


def freshness_ok(
    age_s: Optional[float],
    *,
    threshold_s: float,
) -> bool:
    """Fresh iff age is known and ≤ named threshold (seconds)."""
    if age_s is None:
        return False
    return float(age_s) <= float(threshold_s)


def assert_no_cache_state_dependency(source: str) -> None:
    """Fail-closed guard for Gate-C modules: cache_state must not drive decisions."""
    # Strip this helper's own body so its documentation tokens are not false positives.
    marker = "def assert_no_cache_state_dependency"
    if marker in source:
        head, _, rest = source.partition(marker)
        # Drop until next top-level def/class or EOF.
        cut = rest.find("\ndef ")
        if cut == -1:
            cut = rest.find("\nclass ")
        body_free = head + (rest[cut:] if cut != -1 else "")
    else:
        body_free = source
    # Forbid attribute / mapping reads of cache_state (N-5).
    key = "cache_state"
    needles = (
        f'["{key}"]',
        f"['{key}']",
        f'.get("{key}"',
        f".get('{key}'",
    )
    for token in needles:
        if token in body_free:
            raise AssertionError(
                f"Gate-C must not read cache_state (N-5); found {token!r}"
            )
