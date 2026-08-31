#!/usr/bin/env python3
"""Derive total_sleep_h in the NEWS 24h gate window from macOS pmset sleep/wake log.

Pre-Reg: docs/NEWS_24H_SCHEDULER_GATE.md §5 (G4) — prefer sleep_source=pmset over manual.
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from services.news_agent.liveness import NEWS_SCHEDULER_EPOCH_TS, parse_marker_ts

GATE_CLOSE_TS = "2026-09-01T09:00:00+00:00"
WINDOW_H = 24.0
G1_FACTOR = 0.85

_LINE_RE = re.compile(
    r"^\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ([+-]\d{4})\s+"
    r"(Sleep|Wake|Dark Wake|Maintenance Sleep)"
)


def _parse_pmset_ts(date_s: str, tz_s: str) -> Optional[datetime]:
    sign = 1 if tz_s[0] == "+" else -1
    hours = int(tz_s[1:3])
    minutes = int(tz_s[3:5])
    offset = timezone(sign * timedelta(hours=hours, minutes=minutes))
    try:
        naive = datetime.strptime(date_s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return naive.replace(tzinfo=offset)


def _clip_interval(
    start: datetime, end: datetime, window_start: datetime, window_end: datetime
) -> float:
    lo = max(start, window_start)
    hi = min(end, window_end)
    if hi <= lo:
        return 0.0
    return (hi - lo).total_seconds()


def sleep_intervals_from_pmset_log(
    text: str,
    *,
    window_start: datetime,
    window_end: datetime,
) -> List[Tuple[datetime, datetime]]:
    """Return sleep intervals [start, end) clipped to the observation window."""
    events: List[Tuple[datetime, str]] = []
    for line in text.splitlines():
        m = _LINE_RE.match(line)
        if not m:
            continue
        dt = _parse_pmset_ts(m.group(1), m.group(2))
        if dt is None:
            continue
        kind = m.group(3)
        if kind == "Sleep":
            events.append((dt, "sleep"))
        elif kind in ("Wake", "Dark Wake"):
            events.append((dt, "wake"))

    events.sort(key=lambda x: x[0])
    intervals: List[Tuple[datetime, datetime]] = []
    sleep_start: Optional[datetime] = None

    for dt, kind in events:
        if kind == "sleep":
            if sleep_start is None:
                sleep_start = dt
        elif kind == "wake" and sleep_start is not None:
            intervals.append((sleep_start, dt))
            sleep_start = None

    if sleep_start is not None:
        intervals.append((sleep_start, window_end))

    clipped: List[Tuple[datetime, datetime]] = []
    for start, end in intervals:
        secs = _clip_interval(start, end, window_start, window_end)
        if secs > 0:
            lo = max(start, window_start)
            hi = min(end, window_end)
            clipped.append((lo, hi))
    return clipped


def total_sleep_seconds(
    intervals: List[Tuple[datetime, datetime]],
) -> float:
    return sum((end - start).total_seconds() for start, end in intervals)


def g1_n_min(total_sleep_h: float) -> int:
    import math

    hours_awake = WINDOW_H - total_sleep_h
    return max(1, math.floor(hours_awake * G1_FACTOR))


def main(argv: List[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    window_start = parse_marker_ts(NEWS_SCHEDULER_EPOCH_TS)
    window_end = parse_marker_ts(GATE_CLOSE_TS)
    if window_start is None or window_end is None:
        print("error: invalid gate window constants", file=sys.stderr)
        return 2

    if argv and argv[0] == "--file":
        text = open(argv[1], encoding="utf-8", errors="replace").read()
    else:
        proc = subprocess.run(
            ["pmset", "-g", "log"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print(f"error: pmset failed ({proc.returncode})", file=sys.stderr)
            return proc.returncode
        text = proc.stdout

    intervals = sleep_intervals_from_pmset_log(
        text, window_start=window_start, window_end=window_end
    )
    sleep_s = total_sleep_seconds(intervals)
    sleep_h = round(sleep_s / 3600.0, 2)
    n_min = g1_n_min(sleep_h)

    print(f"sleep_source=pmset sleep_h={sleep_h} n_min={n_min} intervals={len(intervals)}")
    for start, end in intervals:
        print(f"  sleep_interval {start.isoformat()} .. {end.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
