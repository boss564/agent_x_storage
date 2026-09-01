"""Audit-writer liveness invariant (instance 3: news run_marker).

INVARIANT: Every audit writer whose normal state is silence must write at least
one liveness mark per observation period; absence of that mark is a fault.

Instances: feed-gap heartbeat, cross-venue per-venue heartbeat, news run_marker,
price-gap run_marker (instance 4), news-sentiment PhaseSource (instance 5),
price-gap PhaseSource (instance 6).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from agents_b2g.news.feed_health import classify_transport_health, feed_report

INVARIANT = (
    "Jeder Audit-Writer, dessen Normalzustand Schweigen ist, muss pro "
    "Beobachtungszeitraum mindestens eine Liveness-Marke schreiben; "
    "ihr Fehlen ist ein Fehlerzustand."
)

RUN_MARKER_TYPE = "run_marker"

# Pre-Reg 2026-08-30 — frozen before first live quiet-streak.
# CoinDesk publishes several times per day; 72h consecutive quiet ⇒ stale
# (same move as null_gaps_proven / 80% coverage: duration bound, not a snapshot).
# Amendment: new constant + note original value 259200; do not retune after a feed looks odd.
QUIET_STALE_AFTER_S = 72 * 3600
QUIET_STALE_PRE_REG = "2026-08-30"
QUIET_STALE_ORIGINAL_S = 259200

# Hourly host cron (:00) — missing/stale marker is a fault, not a manual observation.
# Default 2h: one missed hour still within budget; two missed hours → STALE.
NEWS_MARKER_MAX_AGE_H = float(os.environ.get("NEWS_MARKER_MAX_AGE_H", "2"))
NEWS_MARKER_MAX_AGE_S = NEWS_MARKER_MAX_AGE_H * 3600.0

# First autonomous Hetzner cron :00 (2026-09-01T12:00:01Z) — syslog CRON proof + run_marker WORM.
# Pre-epoch run_markers (smoke, manual SSH, Mac VOID launchd) are Vorlauf.
NEWS_SCHEDULER_EPOCH_TS = "2026-09-01T12:00:01.615076+00:00"
NEWS_SCHEDULER_GATE_CLOSE_TS = "2026-09-02T12:00:01.615076+00:00"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_marker_ts(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        raw = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def ts_ge_scheduler_epoch(
    ts: Optional[str], *, epoch_ts: str = NEWS_SCHEDULER_EPOCH_TS
) -> bool:
    left = parse_marker_ts(ts or "")
    right = parse_marker_ts(epoch_ts)
    if left is None or right is None:
        return False
    return left >= right


def measurement_run_markers(
    markers: List[Mapping[str, Any]],
    *,
    epoch_ts: str = NEWS_SCHEDULER_EPOCH_TS,
) -> List[dict]:
    """Run markers on or after scheduler epoch — for streaks and feed-quality views."""
    return [
        dict(m)
        for m in markers
        if ts_ge_scheduler_epoch(str(m.get("ts") or ""), epoch_ts=epoch_ts)
    ]


def load_run_markers(path: Path) -> List[dict]:
    rows: List[dict] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("source_type") == RUN_MARKER_TYPE:
            rows.append(row)
    return rows


def derive_quiet_streaks(
    prior_markers: List[Mapping[str, Any]],
    current_feeds: Mapping[str, Mapping[str, Any]],
    *,
    now: Optional[str] = None,
    stale_after_s: int = QUIET_STALE_AFTER_S,
) -> Dict[str, dict]:
    """Per-run health stays quiet/dead/ok; stale is a duration claim on consecutive quiet.

    Pre-Reg: stale_after_s defaults to QUIET_STALE_AFTER_S (72h). Do not pass a
    different value because a feed 'looks' empty.
    """
    now_ts = now or utc_now()
    now_dt = parse_marker_ts(now_ts)
    names = set(current_feeds) | {
        name
        for m in prior_markers
        for name in (m.get("feeds") or {})
    }
    out: Dict[str, dict] = {}
    for name in sorted(names):
        current_health = (current_feeds.get(name) or {}).get("health")
        streak_start: Optional[datetime] = None
        n_quiet = 0
        if current_health == "quiet" and now_dt is not None:
            streak_start = now_dt
            n_quiet = 1
            for marker in reversed(prior_markers):
                health = ((marker.get("feeds") or {}).get(name) or {}).get("health")
                ts = parse_marker_ts(str(marker.get("ts") or ""))
                if health != "quiet" or ts is None:
                    break
                n_quiet += 1
                streak_start = ts
        span_s = 0.0
        if streak_start is not None and now_dt is not None:
            span_s = max(0.0, (now_dt - streak_start).total_seconds())
        stale = bool(
            current_health == "quiet" and span_s >= float(stale_after_s)
        )
        out[name] = {
            "consecutive_quiet": n_quiet,
            "span_s": round(span_s, 3),
            "stale": stale,
            "stale_after_s": int(stale_after_s),
        }
    return out


def run_marker_record(
    feeds: Mapping[str, Mapping[str, Any]],
    *,
    ts: Optional[str] = None,
    streaks: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> dict:
    ts_now = ts or utc_now()
    return {
        "source_type": RUN_MARKER_TYPE,
        "ts": ts_now,
        "feeds": {name: dict(report) for name, report in feeds.items()},
        "streaks": {name: dict(row) for name, row in (streaks or {}).items()},
        "diagnostic_only": True,
        "live_execution": False,
        "order_send": False,
        "not_investment_advice": True,
        "liveness_invariant": INVARIANT,
        "quiet_stale_after_s": QUIET_STALE_AFTER_S,
        "quiet_stale_pre_reg": QUIET_STALE_PRE_REG,
        "scheduler_epoch_ts": NEWS_SCHEDULER_EPOCH_TS,
    }


def last_run_marker(path: Path) -> Optional[dict]:
    last = None
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("source_type") == RUN_MARKER_TYPE:
            last = row
    return last


def run_marker_freshness(
    path: Path,
    *,
    max_age_s: Optional[float] = None,
    now: Optional[str] = None,
) -> Dict[str, Any]:
    """Whether the news audit writer marked within max_age (default NEWS_MARKER_MAX_AGE_H).

    MISSING / STALE / UNPARSEABLE → ok=False (fault). ACTIVE → ok=True.
    Checked against the *prior* marker — call before writing the current run_marker.
    """
    limit = float(NEWS_MARKER_MAX_AGE_S if max_age_s is None else max_age_s)
    now_dt = parse_marker_ts(now or utc_now())
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)
    last = last_run_marker(path)
    if last is None:
        return {
            "status": "MISSING",
            "age_s": None,
            "max_age_s": limit,
            "last_ts": None,
            "ok": False,
        }
    last_ts = str(last.get("ts") or "")
    ts = parse_marker_ts(last_ts)
    if ts is None:
        return {
            "status": "UNPARSEABLE",
            "age_s": None,
            "max_age_s": limit,
            "last_ts": last_ts or None,
            "ok": False,
        }
    age_s = max(0.0, (now_dt - ts).total_seconds())
    ok = age_s <= limit
    return {
        "status": "ACTIVE" if ok else "STALE",
        "age_s": round(age_s, 3),
        "max_age_s": limit,
        "last_ts": last_ts,
        "ok": ok,
    }


__all__ = [
    "INVARIANT",
    "RUN_MARKER_TYPE",
    "classify_transport_health",
    "feed_report",
    "run_marker_record",
    "last_run_marker",
    "load_run_markers",
    "derive_quiet_streaks",
    "run_marker_freshness",
    "QUIET_STALE_AFTER_S",
    "QUIET_STALE_ORIGINAL_S",
    "NEWS_MARKER_MAX_AGE_H",
    "NEWS_MARKER_MAX_AGE_S",
    "NEWS_SCHEDULER_EPOCH_TS",
    "NEWS_SCHEDULER_GATE_CLOSE_TS",
    "ts_ge_scheduler_epoch",
    "measurement_run_markers",
]
