"""News PhaseSource — fixture JSONL, no live HTTP, zero cluster."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from astrocore.sources.news_sentiment_source import (
    build_phase_signal,
    compute_aggregated_sentiment,
    load_recent_entries,
    run_once,
)

NOW = datetime(2026, 8, 30, 16, 0, tzinfo=timezone.utc)


def _write_jsonl(path: Path, rows: list) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def sample_rows() -> list:
    return [
        {
            "timestamp": (NOW - timedelta(hours=1)).isoformat(),
            "assets": ["BTC"],
            "sentiment": 1,
        },
        {
            "timestamp": (NOW - timedelta(hours=2)).isoformat(),
            "assets": ["ETH", "SOL"],
            "sentiment": -1,
        },
        {
            "timestamp": (NOW - timedelta(hours=5)).isoformat(),
            "assets": ["BTC", "MACRO"],
            "sentiment": 0,
        },
        {
            "timestamp": (NOW - timedelta(hours=30)).isoformat(),
            "assets": ["XRP"],
            "sentiment": 1,
        },
        {
            "timestamp": (NOW - timedelta(hours=3)).isoformat(),
            "assets": ["GENERAL"],
            "sentiment": -1,
        },
        {"source_type": "run_marker", "timestamp": NOW.isoformat(), "assets": ["BTC"], "sentiment": 1},
    ]


def test_load_recent_entries():
    root = Path(tempfile.mkdtemp())
    path = root / "news_scores.jsonl"
    _write_jsonl(path, sample_rows())
    entries = load_recent_entries(path, lookback_hours=24, now=NOW)
    assert len(entries) == 4
    assert all(r.get("source_type") != "run_marker" for r in entries)


def test_load_recent_entries_asset_filter():
    root = Path(tempfile.mkdtemp())
    path = root / "news_scores.jsonl"
    _write_jsonl(path, sample_rows())
    entries = load_recent_entries(path, lookback_hours=24, asset_filter="BTC", now=NOW)
    assert len(entries) == 2
    assert all("BTC" in r["assets"] for r in entries)


def test_compute_aggregated_sentiment():
    root = Path(tempfile.mkdtemp())
    path = root / "news_scores.jsonl"
    _write_jsonl(path, sample_rows())
    entries = load_recent_entries(path, lookback_hours=24, now=NOW)
    scores = compute_aggregated_sentiment(entries)
    assert abs(scores["BTC"] - 0.5) < 0.01
    assert abs(scores["ETH"] + 0.9) < 0.01
    assert abs(scores["SOL"] + 0.8) < 0.01
    assert abs(scores["_general"] + 0.3) < 0.01
    assert "_overall" in scores
    assert "XRP" not in scores


def test_target_assets_and_sentiment_score():
    rows = [
        {
            "timestamp": (NOW - timedelta(hours=1)).isoformat(),
            "target_assets": ["BTC", "MACRO"],
            "sentiment_score": 0.8,
        }
    ]
    scores = compute_aggregated_sentiment(rows)
    assert abs(scores["BTC"] - 0.8) < 0.01
    assert abs(scores["_macro"] - 0.4) < 0.01


def test_build_phase_signal_schema():
    signal = build_phase_signal("BTC", 0.75, confidence=0.9, metadata={"extra": "test"})
    required = {"timestamp", "provider", "phase_bias", "confidence", "metadata"}
    assert required.issubset(signal.keys())
    assert signal["provider"] == "news_sentiment_v1"
    assert -1.0 <= signal["phase_bias"] <= 1.0
    assert 0.0 <= signal["confidence"] <= 1.0
    assert signal["metadata"]["asset"] == "BTC"
    assert signal["metadata"]["extra"] == "test"
    assert signal["order_send"] is False
    clipped = build_phase_signal("ETH", 2.0)
    assert signal["phase_bias"] == 0.75
    assert clipped["phase_bias"] == 1.0
    assert isinstance(signal["timestamp"], str)
    assert isinstance(signal["metadata"], dict)


def test_run_once_empty_and_signals():
    root = Path(tempfile.mkdtemp())
    empty = run_once(jsonl_path=root / "missing.jsonl", now=NOW)
    assert empty["status"] == "empty"
    assert empty["signals"] == []
    path = root / "news_scores.jsonl"
    _write_jsonl(path, sample_rows())
    result = run_once(jsonl_path=path, lookback_hours=24, now=NOW)
    assets = {s["metadata"]["asset"] for s in result["signals"]}
    assert "BTC" in assets
    assert "OVERALL" in assets
    assert all(s["order_send"] is False for s in result["signals"])


def test_append_jsonl_and_run_marker():
    root = Path(tempfile.mkdtemp())
    news = root / "news_scores.jsonl"
    _write_jsonl(news, sample_rows())
    out = root / "phase_signals" / "news_sentiment.jsonl"
    first = run_once(jsonl_path=news, lookback_hours=24, now=NOW, output_jsonl=out)
    assert first["run_marker"] is True
    lines1 = out.read_text(encoding="utf-8").strip().splitlines()
    assert any(json.loads(ln).get("kind") == "run_marker" for ln in lines1)
    assert any(json.loads(ln).get("provider") == "news_sentiment_v1" for ln in lines1)
    run_once(jsonl_path=news, lookback_hours=24, now=NOW, output_jsonl=out)
    lines2 = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines2) == 2 * len(lines1)
    empty_path = root / "missing.jsonl"
    empty_out = root / "phase_signals" / "empty.jsonl"
    empty = run_once(jsonl_path=empty_path, now=NOW, output_jsonl=empty_out)
    assert empty["status"] == "empty"
    assert empty["signals"] == []
    marker_only = [json.loads(ln) for ln in empty_out.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(marker_only) == 1
    assert marker_only[0]["kind"] == "run_marker"


def test_handoff_rejects_writeback():
    root = Path(tempfile.mkdtemp())
    news = root / "news_scores.jsonl"
    _write_jsonl(news, sample_rows())
    before = news.read_text(encoding="utf-8")
    try:
        run_once(jsonl_path=news, now=NOW, output_jsonl=news)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "order_send_forbidden" in str(exc)
    try:
        run_once(
            jsonl_path=news,
            now=NOW,
            output_jsonl=root / "phase_signals" / "news_scores.jsonl",
        )
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "order_send_forbidden" in str(exc)
    try:
        run_once(jsonl_path=news, now=NOW, output_jsonl=root / "derived.jsonl")
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "phase_signals" in str(exc)
    assert news.read_text(encoding="utf-8") == before


if __name__ == "__main__":
    test_load_recent_entries()
    test_load_recent_entries_asset_filter()
    test_compute_aggregated_sentiment()
    test_target_assets_and_sentiment_score()
    test_build_phase_signal_schema()
    test_run_once_empty_and_signals()
    test_append_jsonl_and_run_marker()
    test_handoff_rejects_writeback()
    print("OK: test_phase_source_news 8/8")
