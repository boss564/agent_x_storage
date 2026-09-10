"""Tests for M2 ingest status reporter."""
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.m2_ingest_status import collect_status, count_lines


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n",
        encoding="utf-8",
    )


def test_count_lines(tmp_path: Path):
    p = tmp_path / "a.jsonl"
    p.write_text("a\nb\nc\n", encoding="utf-8")
    assert count_lines(p) == 3


def test_collect_status_missing_file(tmp_path: Path):
    status = collect_status(tmp_path / "missing.jsonl")
    assert status.file_exists is False
    assert "fehlt" in status.recommendation.lower()


def test_collect_status_tail_lag_buckets(tmp_path: Path):
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {"source_type": "run_marker", "ts": now},
    ]
    for lag in (60, 1200, 5000):
        rows.append(
            {
                "schema": "news_agent_multi/v1.3",
                "timestamp": now,
                "published_at": now,
                "detection_lag": lag,
                "sentiment_score": 0.5,
                "source_name": "test",
                "source_type": "rss",
            }
        )
    path = tmp_path / "news_scores.jsonl"
    _write_jsonl(path, rows)
    status = collect_status(path, tail_n=10)
    assert status.file_exists
    assert status.line_count == 4
    assert status.tail_lag_count == 3
    assert status.tail_lag_buckets["LT_15M"] == 1
    assert status.tail_lag_buckets["M15_60"] == 1
    assert status.tail_lag_buckets["GT_60"] == 1
