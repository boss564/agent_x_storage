"""M2 live monitor — lag bucket summary (no daemon)."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.m2_live_monitor import build_report, count_lag_buckets


def test_count_lag_buckets_spec() -> None:
    lags = [30.0, 1200.0, 4000.0, 2700.0]
    counts = count_lag_buckets(lags)
    assert counts["LT_15M"] == 1
    assert counts["M15_60"] == 2
    assert counts["GT_60"] == 1


def test_build_report_from_fixture(tmp_path: Path) -> None:
    jsonl = tmp_path / "news.jsonl"
    audit = tmp_path / "m2_audit.jsonl"
    rows = [
        {
            "schema": "news_agent_multi/v1.3",
            "source_type": "rss",
            "timestamp": "2026-09-08T12:00:00+00:00",
            "detection_lag": 900,
            "sentiment_score": 0.5,
        },
        {
            "schema": "news_agent_multi/v1.3",
            "source_type": "rss",
            "timestamp": "2026-09-08T13:00:00+00:00",
            "detection_lag": 1800,
            "volatility_15m": 0.01,
        },
    ]
    jsonl.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    report = build_report(jsonl, sample_size=10)
    assert report["lag_samples"] == 2
    assert report["lag_bucket_counts"]["M15_60"] == 2
    assert report["avg_slippage_bps"] is not None

    from scripts.m2_live_monitor import run_cycle

    code = run_cycle(jsonl, audit, sample_size=10, as_json=False, log_file="")
    assert code == 0
    marker = json.loads(audit.read_text(encoding="utf-8").strip())
    assert marker["kind"] == "run_marker"
    assert marker["writer"] == "m2_live_monitor"
    assert marker["lag_samples"] == 2
