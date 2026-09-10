"""Swarm gap detector — fixture prices + news, no live HTTP by default."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.gap_detector.detector import (
    THRESHOLD_1H_PCT,
    THRESHOLD_24H_PCT,
    WATCHLIST,
    fetch_price_move,
    last_run_marker,
    rule_a_coverage_gaps,
    rule_b_untracked,
    run_once,
)


NOW = datetime(2026, 8, 30, 16, 0, tzinfo=timezone.utc)


class FakeOk:
    def fetch_ticker(self, symbol: str):
        return {"percentage": 9.5, "last": 100.0}

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 3):
        return [[0, 0, 0, 0, 100.0], [0, 0, 0, 0, 106.0]]


class FakeQuiet:
    def fetch_ticker(self, symbol: str):
        return {"percentage": 1.0, "last": 100.0}

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 3):
        return [[0, 0, 0, 0, 100.0], [0, 0, 0, 0, 101.0]]


class FakeBoom:
    def fetch_ticker(self, symbol: str):
        raise RuntimeError("timeout")

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 3):
        raise RuntimeError("timeout")


def test_watchlist_and_thresholds():
    assert "SUI" in WATCHLIST
    assert THRESHOLD_1H_PCT == 5.0
    assert THRESHOLD_24H_PCT == 8.0


def test_rule_a_gap_without_news():
    prices = [
        {"asset": "BTC", "pct_1h": 6.2, "pct_24h": 2.0, "last": 1, "error": None},
        {"asset": "ETH", "pct_1h": 1.0, "pct_24h": 9.1, "last": 1, "error": None},
        {"asset": "SOL", "pct_1h": 1.0, "pct_24h": 1.0, "last": 1, "error": None},
    ]
    news = [
        {
            "timestamp": "2026-08-30T15:30:00+00:00",
            "title": "Unrelated park news",
            "target_assets": [],
        }
    ]
    events = rule_a_coverage_gaps(prices, news, now=NOW)
    kinds = {(e["asset"], e["window"]) for e in events}
    assert ("BTC", "1h") in kinds
    assert ("ETH", "24h") in kinds
    assert not any(e["asset"] == "SOL" for e in events)


def test_rule_a_suppressed_when_news_matches():
    prices = [{"asset": "BTC", "pct_1h": 6.2, "pct_24h": 9.5, "last": 1, "error": None}]
    news = [
        {
            "timestamp": "2026-08-30T15:30:00+00:00",
            "title": "Bitcoin ETF inflows",
            "target_assets": ["BTC"],
        }
    ]
    events = rule_a_coverage_gaps(prices, news, now=NOW)
    assert events == []


def test_rule_b_cashtag_and_watchlist():
    news = [
        {"title": "Retail piles into $HYPER and $SUI", "summary": "$FOO listed"},
        {"title": "More $HYPER chatter", "summary": ""},
    ]
    events = {e["asset"]: e for e in rule_b_untracked(news)}
    assert "HYPER" in events
    assert "FOO" in events
    assert "SUI" not in events
    assert "Aufnahme von $HYPER" in events["HYPER"]["recommendation"]


def test_ccxt_failure_does_not_abort():
    move = fetch_price_move("BTC", client=FakeBoom())
    assert move["error"]
    assert move["pct_1h"] is None
    root = Path(tempfile.mkdtemp())
    news = root / "news_scores.jsonl"
    news.write_text(
        json.dumps(
            {
                "timestamp": "2026-08-30T15:50:00+00:00",
                "title": "Watch $ABC pump",
                "target_assets": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    result = run_once(
        news_path=news,
        events_path=root / "gap_reports.jsonl",
        md_path=root / "SWARM_GAP_ANALYSIS.md",
        client=FakeBoom(),
        now=NOW,
    )
    assert result["status"] == "ok"
    assert result["feed_errors"] >= 1
    assert result["untracked"] >= 1
    assert result["order_send"] is False


def test_run_once_writes_jsonl_and_md():
    root = Path(tempfile.mkdtemp())
    news = root / "news_scores.jsonl"
    news.write_text("", encoding="utf-8")
    result = run_once(
        news_path=news,
        events_path=root / "gap_reports.jsonl",
        md_path=root / "SWARM.md",
        client=FakeOk(),
        now=NOW,
    )
    assert result["coverage_gaps"] == len(WATCHLIST)
    text = (root / "SWARM.md").read_text(encoding="utf-8")
    assert "COVERAGE_GAP" in text
    lines = (root / "gap_reports.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert any(json.loads(ln)["kind"] == "COVERAGE_GAP" for ln in lines)
    assert any(json.loads(ln)["kind"] == "run_marker" for ln in lines)


def test_quiet_market_still_writes_run_marker():
    root = Path(tempfile.mkdtemp())
    news = root / "news_scores.jsonl"
    news.write_text("", encoding="utf-8")
    events = root / "gap_reports.jsonl"
    result = run_once(
        news_path=news,
        events_path=events,
        md_path=root / "SWARM.md",
        client=FakeQuiet(),
        now=NOW,
    )
    assert result["coverage_gaps"] == 0
    marker = last_run_marker(events)
    assert marker is not None
    assert marker["kind"] == "run_marker"
    assert marker["coverage_gaps"] == 0
    assert "Jeder Audit-Writer" in marker["liveness_invariant"]


if __name__ == "__main__":
    test_watchlist_and_thresholds()
    test_rule_a_gap_without_news()
    test_rule_a_suppressed_when_news_matches()
    test_rule_b_cashtag_and_watchlist()
    test_ccxt_failure_does_not_abort()
    test_run_once_writes_jsonl_and_md()
    test_quiet_market_still_writes_run_marker()
    print("OK: test_swarm_gap_detector 7/7")
