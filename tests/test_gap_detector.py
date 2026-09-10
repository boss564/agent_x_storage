"""Gap-detector — fixture JSONL, no live HTTP, zero cluster."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.news_agent.gap_detector import (
    DEFAULT_MIN_COUNT,
    build_report,
    detect_gaps,
    known_surface,
    load_articles,
    run_gap_report,
    write_report,
)


def _article(title: str, *, item_id: str, summary: str = "") -> dict:
    return {
        "source_type": "rss",
        "title": title,
        "summary": summary,
        "item_id": item_id,
    }


def test_known_catalog_not_reported():
    known = known_surface()
    assert "sui" in known
    assert "btc" in known
    assert "ethereum" in known
    articles = [
        _article("SUI ecosystem update on Solana", item_id=f"sui-{i}")
        for i in range(6)
    ]
    gaps = detect_gaps(articles, min_count=4)
    entities = {g["entity"] for g in gaps}
    assert "SUI" not in entities
    assert "Solana" not in entities


def test_hyper_gap_above_threshold():
    articles = [
        _article("Hyperliquid HYPER token listing", item_id="h1"),
        _article("HYPER staking goes live", item_id="h2"),
        _article("Hyperliquid launches HYPER perpetuals", item_id="h3"),
        _article("Traders pile into HYPER", item_id="h4"),
    ]
    gaps = {g["entity"]: g for g in detect_gaps(articles, min_count=DEFAULT_MIN_COUNT)}
    assert "HYPER" in gaps
    assert gaps["HYPER"]["count"] >= 4
    assert "TOKEN_KEYWORDS" in gaps["HYPER"]["suggestion"]
    assert any("HYPER" in c or "Hyperliquid" in c for c in gaps["HYPER"]["context"])
    report = build_report(articles, min_count=2)
    names = {g["entity"]: g for g in report["detected_gaps"]}
    assert "HYPER" in names
    assert "Hyperliquid" in names
    assert names["Hyperliquid"]["count"] >= 2
    assert report["price_anomaly"] is None
    assert report["order_send"] is False


def test_stopwords_and_run_marker_and_window(tmp_path: Path | None = None):
    root = Path(tempfile.mkdtemp()) if tmp_path is None else tmp_path
    jsonl = root / "news_scores.jsonl"
    rows = [
        {"source_type": "run_marker", "title": "HYPER should be ignored"},
        _article("This Week Bitcoin ETF inflows", item_id="btc-1"),
        _article("BCH listing rumor", item_id="b1"),
        _article("BCH listing rumor", item_id="b2"),
        _article("BCH listing rumor", item_id="b3"),
        _article("BCH listing rumor", item_id="b4"),
        _article("BCH listing rumor", item_id="b5"),
    ]
    jsonl.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    loaded = load_articles(jsonl, last_n=4)
    assert len(loaded) == 4
    assert all(r.get("source_type") != "run_marker" for r in loaded)
    gaps = detect_gaps(loaded, min_count=4)
    entities = {g["entity"] for g in gaps}
    assert "BCH" in entities
    assert "This" not in entities
    assert "Week" not in entities
    assert "Bitcoin" not in entities
    assert "ETF" not in entities
    windowed = detect_gaps(load_articles(jsonl, last_n=2), min_count=4)
    assert windowed == []


def test_write_json_and_markdown(tmp_path: Path | None = None):
    root = Path(tempfile.mkdtemp()) if tmp_path is None else tmp_path
    jsonl = root / "news_scores.jsonl"
    articles = [_article(f"HYPER note {i}", item_id=f"n{i}") for i in range(5)]
    jsonl.write_text("\n".join(json.dumps(a) for a in articles) + "\n", encoding="utf-8")
    out = root / "exports" / "reports" / "gap_analysis.json"
    md = root / "exports" / "reports" / "gap_analysis.md"
    result = run_gap_report(jsonl=jsonl, output=out, md=md, last_n=100, min_count=4)
    assert result["status"] == "ok"
    assert result["gaps"] >= 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["detected_gaps"][0]["entity"] == "HYPER"
    assert "HYPER" in md.read_text(encoding="utf-8")
    written = write_report(payload, root / "copy.json")
    assert Path(written["path"]).is_file()


if __name__ == "__main__":
    test_known_catalog_not_reported()
    test_hyper_gap_above_threshold()
    test_stopwords_and_run_marker_and_window()
    test_write_json_and_markdown()
    print("OK: test_gap_detector 4/4")
