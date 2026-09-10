"""Tag-7 detection_lag report — coverage + verdict (spec §5.1)."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.backtest_h1_news_m2_skeleton import report_detection_lag

SCHEMA = "news_agent_multi/v1.3"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_lag_report_coverage_and_verdict(tmp_path: Path) -> None:
    jsonl = tmp_path / "news.jsonl"
    rows = [
        {
            "schema": SCHEMA,
            "source_type": "rss",
            "source_name": "CoinDesk",
            "timestamp": "2026-09-08T12:00:00+00:00",
            "published_at": "2026-09-08T11:45:00+00:00",
            "detection_lag": 900,
        },
        {
            "schema": SCHEMA,
            "source_type": "rss",
            "source_name": "CoinDesk",
            "timestamp": "2026-09-08T13:00:00+00:00",
            "published_at": "2026-09-08T12:50:00+00:00",
            "detection_lag": 600,
        },
        {
            "schema": SCHEMA,
            "source_type": "rss",
            "source_name": "Cointelegraph",
            "timestamp": "2026-09-08T12:00:00+00:00",
            "published_at": "2026-09-08T11:30:00+00:00",
            "detection_lag": 1800,
        },
        {
            "schema": SCHEMA,
            "source_type": "announcement",
            "source_name": "Binance",
            "timestamp": "2026-09-08T12:00:00+00:00",
            "published_at": "",
            "detection_lag": None,
        },
        {
            "schema": "news_agent_multi/v1.2",
            "source_type": "rss",
            "source_name": "CoinDesk",
            "timestamp": "2026-09-08T12:00:00+00:00",
            "detection_lag": 60,
        },
    ]
    _write_jsonl(jsonl, rows)

    report = report_detection_lag(jsonl)

    assert report["n_items_total"] == 4
    assert report["n_with_published_at"] == 3
    assert report["n_with_lag"] == 3
    assert report["lag_coverage"] == 0.75
    assert report["coverage_by_source"]["CoinDesk"] == 1.0
    assert report["coverage_by_source"]["Cointelegraph"] == 1.0
    assert report["coverage_by_source"]["Binance"] == 0.0
    assert report["median_lag_by_source"]["CoinDesk"] == 12.5
    assert report["median_lag_by_source"]["Cointelegraph"] == 30.0
    assert report["median_lag_by_source"]["Binance"] is None
    assert report["measurability"] == "INSUFFICIENT_DATA"
    assert report["verdict"] is None


def test_lag_report_no_go_when_median_above_threshold(tmp_path: Path) -> None:
    jsonl = tmp_path / "news.jsonl"
    rows = []
    for i in range(100):
        rows.append(
            {
                "schema": SCHEMA,
                "source_type": "rss",
                "source_name": "CoinDesk",
                "timestamp": "2026-09-08T12:00:00+00:00",
                "published_at": "2026-09-08T11:25:00+00:00",
                "detection_lag": 2100,
            }
        )
    _write_jsonl(jsonl, rows)

    report = report_detection_lag(jsonl)

    assert report["n_items_total"] == 100
    assert report["lag_coverage"] == 1.0
    assert report["verdict"] == "NO_GO"
    assert report["median_lag_min"] == 35.0
    assert report["prior_prediction"] == "NO_GO"
