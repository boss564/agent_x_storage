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
    load_news_watchdog_env,
    m2_monitor_check_enabled,
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


def test_critical_m2_monitor_stale(tmp_path: Path, monkeypatch) -> None:
    """Stale audit marker is CRITICAL when instance-7 check is armed."""
    monkeypatch.setenv("WATCHDOG_M2_MONITOR", "1")
    now = datetime.now(timezone.utc)
    news = tmp_path / "news.jsonl"
    audit = tmp_path / "m2_live_monitor.jsonl"
    marker_ts = (now - timedelta(hours=3)).isoformat()
    _write_jsonl(
        news,
        [{"timestamp": now.isoformat(), "source_type": "run_marker"}],
    )
    audit.write_text(
        json.dumps(
            {
                "kind": "run_marker",
                "writer": "m2_live_monitor",
                "ts": marker_ts,
                "status": "ok",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    news.touch()
    os.utime(news, (time.time(), time.time()))

    cfg = get_config()
    cfg["M2_MONITOR_AUDIT_JSONL"] = str(audit)
    code, result = analyze_jsonl(news, cfg)
    assert code == 2
    assert result.checks.get("m2_monitor_fresh") is False


def test_critical_m2_monitor_missing(tmp_path: Path, monkeypatch) -> None:
    """WATCHDOG_M2_MONITOR=1 without audit file → CRITICAL (never-started timer)."""
    monkeypatch.setenv("WATCHDOG_M2_MONITOR", "1")
    now = datetime.now(timezone.utc)
    news = tmp_path / "news.jsonl"
    audit = tmp_path / "m2_live_monitor.jsonl"
    _write_jsonl(
        news,
        [
            {
                "timestamp": now.isoformat(),
                "source_type": "rss",
                "sentiment_score": 0.1,
            }
        ],
    )
    news.touch()
    os.utime(news, (time.time(), time.time()))

    cfg = get_config()
    cfg["M2_MONITOR_AUDIT_JSONL"] = str(audit)
    assert m2_monitor_check_enabled(cfg) is True
    code, result = analyze_jsonl(news, cfg)
    assert code == 2
    assert result.checks.get("m2_monitor_fresh") is False
    assert (result.metrics.get("m2_monitor_liveness") or {}).get("status") == "MISSING"


def test_load_news_watchdog_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("WATCHDOG_M2_MONITOR", raising=False)
    env_file = tmp_path / "news_watchdog.env"
    env_file.write_text(
        "# comment\nWATCHDOG_M2_MONITOR=1\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("NEWS_WATCHDOG_ENV_FILE", str(env_file))
    load_news_watchdog_env()
    assert os.environ.get("WATCHDOG_M2_MONITOR") == "1"


def test_m2_monitor_auto_off_without_audit_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WATCHDOG_M2_MONITOR", "auto")
    cfg = get_config()
    cfg["M2_MONITOR_AUDIT_JSONL"] = str(tmp_path / "missing.jsonl")
    assert m2_monitor_check_enabled(cfg) is False


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
    print("watchdog_news_ingestion: 7/7 passed (run pytest for m2 monitor test)")


if __name__ == "__main__":
    run()
