"""Audit-writer liveness — instance 7: M2 live monitor (hourly systemd/cron).

Separate JSONL from news_scores — proves the monitor ran, not just that news
rows contain lag metrics.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from services.news_agent.liveness import INVARIANT, parse_marker_ts, utc_now

RUN_MARKER_KIND = "run_marker"
WRITER_NAME = "m2_live_monitor"
SCHEMA = "m2_live_monitor/v1"

DEFAULT_AUDIT_JSONL = os.environ.get(
    "M2_LIVE_MONITOR_AUDIT_JSONL", "data/m2_live_monitor.jsonl"
)
# Hourly timer — same budget as news cron (one missed hour OK, two → STALE).
MARKER_MAX_AGE_H = float(os.environ.get("M2_MONITOR_MARKER_MAX_AGE_H", "2"))
MARKER_MAX_AGE_S = MARKER_MAX_AGE_H * 3600.0


def run_marker_record(
    report: Mapping[str, Any],
    *,
    ts: Optional[str] = None,
    status: str = "ok",
    error: Optional[str] = None,
) -> dict:
    row: Dict[str, Any] = {
        "schema": SCHEMA,
        "kind": RUN_MARKER_KIND,
        "writer": WRITER_NAME,
        "ts": ts or utc_now(),
        "status": status,
        "diagnostic_only": True,
        "live_execution": False,
        "order_send": False,
        "not_investment_advice": True,
        "liveness_invariant": INVARIANT,
        "jsonl_target": report.get("jsonl"),
        "lag_samples": report.get("lag_samples"),
        "lag_bucket_counts": report.get("lag_bucket_counts"),
        "median_lag_min": report.get("median_lag_min"),
    }
    if error:
        row["error"] = error[:500]
    if report.get("warning"):
        row["warning"] = report["warning"]
    return row


def append_run_marker(
    audit_path: Path,
    report: Mapping[str, Any],
    *,
    status: str = "ok",
    error: Optional[str] = None,
) -> dict:
    row = run_marker_record(report, status=status, error=error)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def load_run_markers(path: Path) -> List[dict]:
    if not path.is_file():
        return []
    rows: List[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("kind") == RUN_MARKER_KIND and row.get("writer") == WRITER_NAME:
            rows.append(row)
    return rows


def last_run_marker(path: Path) -> Optional[dict]:
    markers = load_run_markers(path)
    best: Optional[dict] = None
    best_ts = None
    for row in markers:
        ts = parse_marker_ts(str(row.get("ts") or ""))
        if ts is None:
            continue
        if best_ts is None or ts >= best_ts:
            best_ts = ts
            best = row
    return best


def run_marker_freshness(
    path: Path,
    *,
    max_age_s: Optional[float] = None,
    now: Optional[str] = None,
) -> Dict[str, Any]:
    from datetime import datetime, timezone

    limit = float(MARKER_MAX_AGE_S if max_age_s is None else max_age_s)
    now_dt = parse_marker_ts(now or utc_now())
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)

    if not path.is_file():
        return {
            "status": "MISSING",
            "age_s": None,
            "max_age_s": limit,
            "last_ts": None,
            "ok": False,
            "audit_path": str(path),
        }

    last = last_run_marker(path)
    if last is None:
        return {
            "status": "MISSING",
            "age_s": None,
            "max_age_s": limit,
            "last_ts": None,
            "ok": False,
            "audit_path": str(path),
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
            "audit_path": str(path),
        }

    age_s = max(0.0, (now_dt - ts).total_seconds())
    ok = age_s <= limit
    return {
        "status": "ACTIVE" if ok else "STALE",
        "age_s": round(age_s, 3),
        "max_age_s": limit,
        "last_ts": last_ts,
        "ok": ok,
        "audit_path": str(path),
    }
