"""M2 live monitor audit-writer liveness (instance 7)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.m2_live_monitor.liveness import (
    append_run_marker,
    last_run_marker,
    run_marker_freshness,
    run_marker_record,
)


def test_run_marker_record_shape() -> None:
    row = run_marker_record(
        {"jsonl": "data/news_scores.jsonl", "lag_samples": 3, "lag_bucket_counts": {"M15_60": 3}},
        status="ok",
    )
    assert row["kind"] == "run_marker"
    assert row["writer"] == "m2_live_monitor"
    assert row["lag_samples"] == 3
    assert "liveness_invariant" in row


def test_append_and_freshness(tmp_path: Path) -> None:
    audit = tmp_path / "m2_live_monitor.jsonl"
    report = {
        "jsonl": str(tmp_path / "news.jsonl"),
        "lag_samples": 0,
        "lag_bucket_counts": {"LT_15M": 0, "M15_60": 0, "GT_60": 0},
    }
    append_run_marker(audit, report, status="ok")
    assert last_run_marker(audit) is not None
    fresh = run_marker_freshness(audit)
    assert fresh["ok"] is True
    assert fresh["status"] == "ACTIVE"


def test_stale_marker(tmp_path: Path) -> None:
    audit = tmp_path / "m2_live_monitor.jsonl"
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    row = run_marker_record({"jsonl": "x", "lag_samples": 0}, ts=old_ts)
    audit.write_text(json.dumps(row) + "\n", encoding="utf-8")
    fresh = run_marker_freshness(audit, max_age_s=7200.0)
    assert fresh["ok"] is False
    assert fresh["status"] == "STALE"
