"""Tests for scripts/watchdog_news_ingestion.py"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.watchdog_news_ingestion import (
    analyze_jsonl,
    derive_interval_thresholds,
    get_config,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_interval_thresholds_five_minute_polling_epoch() -> None:
    """Post-§11 polling epoch: same formulas, no manual threshold edits."""
    t = derive_interval_thresholds(5)
    assert t["WARN_STALE_MINUTES"] == 7
    assert t["MAX_STALE_MINUTES"] == 12


def test_interval_thresholds_hourly() -> None:
    t = derive_interval_thresholds(60)
    assert t["WARN_STALE_MINUTES"] == 90
    assert t["MAX_STALE_MINUTES"] == 150


def test_ok_fresh_content_with_lag(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    ingest = now.isoformat()
    published = (now - timedelta(minutes=10)).isoformat()
    rows = [
        {
            "timestamp": ingest,
            "source_type": "rss",
            "source_name": "CoinDesk",
            "title": "BTC",
            "url": "https://example.test/1",
            "sentiment_score": 0.2,
            "published_at": published,
            "detection_lag": 600,
        },
        {"timestamp": ingest, "source_type": "run_marker", "feeds": {}},
    ]
    path = tmp_path / "news.jsonl"
    _write_jsonl(path, rows)
    path.touch()
    os.utime(path, (time.time(), time.time()))

    code, result = analyze_jsonl(path, get_config())
    assert code == 0
    assert result.status == "OK"
    assert result.metrics["lag_samples"] == 1


def test_ok_mid_cycle_file_age_45min(tmp_path: Path) -> None:
    """45 min since last cron write must not WARN (threshold 90 min)."""
    now = datetime.now(timezone.utc)
    marker_ts = (now - timedelta(minutes=45)).isoformat()
    rows = [{"timestamp": marker_ts, "source_type": "run_marker"}]
    path = tmp_path / "news.jsonl"
    _write_jsonl(path, rows)
    mtime = (now - timedelta(minutes=45)).timestamp()
    os.utime(path, (mtime, mtime))

    code, result = analyze_jsonl(path, get_config())
    assert code == 0
    assert result.status == "OK"


def test_pooled_pubdate_does_not_warn_with_announcements(tmp_path: Path) -> None:
    """High announcement share without published_at must not affect exit code."""
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "timestamp": now,
            "source_type": "announcement",
            "source_name": "Binance",
            "title": "listing",
            "url": "https://example.test/b",
            "sentiment_score": 0.0,
            "published_at": "",
        },
        {
            "timestamp": now,
            "source_type": "rss",
            "source_name": "coindesk",
            "title": "btc",
            "url": "https://example.test/c",
            "sentiment_score": 0.1,
            "published_at": now,
        },
        {"timestamp": now, "source_type": "run_marker"},
    ]
    path = tmp_path / "news.jsonl"
    _write_jsonl(path, rows)
    os.utime(path, (time.time(), time.time()))

    code, result = analyze_jsonl(path, get_config())
    assert code == 0
    assert "coverage_by_source" in result.metrics
    assert "Binance" not in result.metrics["coverage_by_source"]


def test_lag_median_30min_does_not_warn(tmp_path: Path) -> None:
    """Hourly polling ~30 min median is normal — metrics only, exit OK."""
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "timestamp": now,
            "source_type": "rss",
            "source_name": "coindesk",
            "title": "a",
            "url": "https://example.test/a",
            "sentiment_score": 0.0,
            "published_at": now,
            "detection_lag": 1800,
        },
        {
            "timestamp": now,
            "source_type": "rss",
            "source_name": "coindesk",
            "title": "b",
            "url": "https://example.test/b",
            "sentiment_score": 0.0,
            "published_at": now,
            "detection_lag": 1800,
        },
        {"timestamp": now, "source_type": "run_marker"},
    ]
    path = tmp_path / "news.jsonl"
    _write_jsonl(path, rows)
    os.utime(path, (time.time(), time.time()))

    code, result = analyze_jsonl(path, get_config())
    assert code == 0
    assert result.metrics["median_lag_sec"] == 1800


def test_critical_stale_data_age(tmp_path: Path) -> None:
    old = (datetime.now(timezone.utc) - timedelta(minutes=160)).isoformat()
    rows = [
        {
            "timestamp": old,
            "source_type": "rss",
            "source_name": "CoinDesk",
            "title": "stale",
            "url": "https://example.test/s",
            "sentiment_score": 0.1,
            "published_at": old,
            "detection_lag": 60,
        }
    ]
    path = tmp_path / "news.jsonl"
    _write_jsonl(path, rows)
    old_ts = (datetime.now(timezone.utc) - timedelta(minutes=160)).timestamp()
    os.utime(path, (old_ts, old_ts))

    code, result = analyze_jsonl(path, get_config())
    assert code == 2
    assert result.status == "CRITICAL"
    assert result.checks["data_freshness"] is False


def run() -> None:
    from tempfile import TemporaryDirectory

    test_interval_thresholds_hourly()
    test_interval_thresholds_five_minute_polling_epoch()
    with TemporaryDirectory() as td:
        root = Path(td)
        test_ok_fresh_content_with_lag(root)
        test_ok_mid_cycle_file_age_45min(root)
        test_pooled_pubdate_does_not_warn_with_announcements(root)
        test_lag_median_30min_does_not_warn(root)
        test_critical_stale_data_age(root)
    print("watchdog_news_ingestion: 7/7 passed")


if __name__ == "__main__":
    run()
