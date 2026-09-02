"""NEWS 24h scheduler gate — G1 n_min from uptime and cron interval.

Pre-Reg: docs/NEWS_24H_SCHEDULER_GATE.md
  A1 — factor 0.85 on awake/up hours (hourly slots)
  A3 — scale slots by 60/interval_min (Polling-Epoche, vor erstem 5-min-Gate)
"""
from __future__ import annotations

import math

from services.news_agent.cron_schedule import measure_scheduler_interval_minutes

DEFAULT_GATE_WINDOW_H = 24.0
DEFAULT_G1_FACTOR = 0.85
DEFAULT_SCHEDULER_INTERVAL_MIN = 60


def scheduler_interval_minutes() -> int:
    """Cadence from crontab/launchd; env only when schedule unreadable."""
    interval, _source = measure_scheduler_interval_minutes()
    return interval


def scheduler_interval_with_source() -> tuple[int, str]:
    """Interval plus provenance (crontab, launchd, env:…, default)."""
    return measure_scheduler_interval_minutes()


def g1_n_min(
    downtime_h: float,
    *,
    window_h: float = DEFAULT_GATE_WINDOW_H,
    interval_min: int | float | None = None,
    factor: float = DEFAULT_G1_FACTOR,
) -> int:
    """
    Minimum post-epoch run_markers required in the gate window.

    ``downtime_h`` = total_sleep_h (macOS) or downtime_h (Linux) — time the
    scheduler could not have fired.

    A1 anchor: downtime_h=0, interval_min=60 → floor(24 × 1 × 0.85) = 20.
    A3 (5 min): downtime_h=0 → floor(24 × 12 × 0.85) = 244.
    """
    if interval_min is None:
        interval_min = scheduler_interval_minutes()
    interval_min = float(interval_min)
    if interval_min <= 0:
        raise ValueError("interval_min must be positive")
    hours_up = max(0.0, window_h - downtime_h)
    slots_per_hour = 60.0 / interval_min
    return max(1, math.floor(hours_up * slots_per_hour * factor))


def g1_formula_doc() -> str:
    return (
        "n_min = max(1, floor(hours_up × (60 / interval_min) × 0.85))"
    )
