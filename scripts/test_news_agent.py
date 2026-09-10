"""News-Agent unit tests — fixture RSS, no live HTTP, zero cluster."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.news.agent import NewsAgent, append_score
from agents_b2g.news.scraper import fetch_news, parse_rss_xml
from agents_b2g.news.sentiment import classify_coin, detect_assets, detect_entities, is_relevant, score_sentiment

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>fixture</title>
  <item>
    <title>Bitcoin ETF inflows hit record high</title>
    <link>https://example.test/btc-etf</link>
    <description>Institutional adoption continues as spot ETF inflows surge.</description>
  </item>
  <item>
    <title>Exchange hack drains ETH wallets</title>
    <link>https://example.test/eth-hack</link>
    <description>Exploit and liquidation cascade after the hack.</description>
  </item>
  <item>
    <title>City council approves park renovations</title>
    <link>https://example.test/parks</link>
    <description>Unrelated municipal news.</description>
  </item>
</channel></rss>
"""


def test_parse_rss_three_items():
    items = parse_rss_xml(RSS, source="fixture")
    assert len(items) == 3
    assert items[0]["title"].startswith("Bitcoin")
    assert items[0]["id"]


def test_sentiment_bull_and_bear():
    bull = score_sentiment("Bitcoin ETF inflows hit record high", "spot ETF inflows")
    bear = score_sentiment("Exchange hack drains ETH", "exploit and liquidation")
    assert bull["sentiment"] == 1
    assert bear["sentiment"] == -1
    assert "BTC" in bull["symbols"]
    assert "ETH" in bear["symbols"]
    assert "BTC" in bull["assets"]
    assert "ETH" in bear["assets"]


def test_ingest_filters_and_dedup(tmp_path: Path | None = None):
    root = Path(tmpfile := tempfile.mkdtemp()) if tmp_path is None else tmp_path
    jsonl = root / "news_scores.jsonl"
    agent = NewsAgent(jsonl_path=jsonl, relevant_only=True)
    first = agent.ingest_xml(RSS, source="fixture")
    assert first["written"] == 2
    assert first["skipped_irrelevant"] == 1
    second = agent.ingest_xml(RSS, source="fixture")
    assert second["written"] == 0
    assert second["skipped_seen"] == 2
    assert second["skipped_irrelevant"] == 1
    lines = jsonl.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    rows = [json.loads(line) for line in lines]
    assert rows[0]["prev_hash"] == "0" * 64
    assert rows[1]["prev_hash"] == rows[0]["hash"]
    assert rows[0]["live_execution"] is False
    assert rows[0]["order_send"] is False
    assert rows[0]["diagnostic_only"] is True
    labels = {r["label"] for r in rows}
    assert "BULLISH" in labels and "BEARISH" in labels
    assert "BTC" in rows[0]["assets"] or "ETH" in rows[0]["assets"]
    assert all("assets" in r for r in rows)
    assert all("entities" in r for r in rows)
    assert all("cross_chain_impact" in r for r in rows)
    assert all(set(r["entities"]) == {"chains", "bridges", "protocols", "persons"} for r in rows)


def test_append_rejects_order_send():
    root = Path(tempfile.mkdtemp())
    path = root / "n.jsonl"
    try:
        append_score(path, {"item_id": "x", "order_send": True})
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "order_send_forbidden" in str(exc)


def test_eth_substring_is_not_ethereum():
    traps = (
        "WHETHER Bitcoin rallies this week",
        "Together with market makers",
        "Ethics in crypto research",
        "Netherlands considers a ban",
    )
    for title in traps:
        assert classify_coin(title) == "BTC", title
        assert "ETH" not in score_sentiment(title, "").get("symbols", [])
        assert "ETH" not in detect_assets(title)
    assert not is_relevant("Together with Ethics in the Netherlands", "Whether parks open")
    assert is_relevant("WHETHER Bitcoin rallies", "")
    assert classify_coin("Exchange hack drains ETH wallets") == "ETH"
    assert classify_coin("ethereum upgrade on mainnet") == "ETH"
    assert "ETH" in score_sentiment("Exchange hack drains ETH wallets", "exploit").get("symbols", [])


def test_fetch_http_error_is_feed_silent():
    from urllib.error import URLError
    from unittest.mock import patch

    with patch("agents_b2g.news.scraper.urlopen", side_effect=URLError("404")):
        items, errors = fetch_news(
            [("coindesk", "http://example.test/rss")],
            timeout_s=1,
        )
    assert items == []
    assert errors
    assert "coindesk" in errors[0]

    agent = NewsAgent(jsonl_path=Path(tempfile.mkdtemp()) / "n.jsonl")
    with patch("agents_b2g.news.agent.fetch_news", return_value=([], ["coindesk: URLError 404"])):
        result = agent.run_once()
    assert result["status"] == "FEED_SILENT"
    assert result["fetched"] == 0
    assert result["feed_errors"]


def test_multi_asset_macro_and_no_substring():
    tagged = detect_assets("Bitcoin rises as Fed signals rate cut")
    assert tagged == ["BTC", "MACRO"]
    scored = score_sentiment("Bitcoin rises as Fed signals rate cut", "")
    assert scored["assets"] == ["BTC", "MACRO"]
    assert scored["symbols"] == ["BTC"]
    assert "SOL" not in detect_assets("also sold unique community tokens")
    assert "UNI" not in detect_assets("also sold unique community tokens")
    assert "ETH" not in detect_assets("WHETHER Together Ethics Netherlands")
    assert is_relevant("Solana outage", "")
    assert is_relevant("SEC charges exchange", "")
    assert not is_relevant("City council market hall renovation", "")


def test_entity_tagging():
    worm = detect_entities("Wormhole bridge exploit on Solana")
    assert worm["chains"] == ["solana"]
    assert worm["bridges"] == ["wormhole"]
    assert worm["protocols"] == []
    assert worm["persons"] == []
    scored = score_sentiment("Wormhole bridge exploit on Solana", "")
    assert scored["assets"] == ["SOL"]
    assert scored["entities"]["bridges"] == ["wormhole"]
    assert scored["entities"]["chains"] == ["solana"]
    both = detect_entities("Wormhole exploit on Solana and Ethereum")
    assert both["chains"] == ["ethereum", "solana"]
    assert both["bridges"] == ["wormhole"]
    assert "ETH" in detect_assets("Wormhole exploit on Solana and Ethereum")
    assert "SOL" in detect_assets("Wormhole bridge exploit on Solana")
    assert detect_entities("automatic unique community tokens")["chains"] == []
    assert "polygon" not in detect_entities("automatic settlement")["chains"]
    assert detect_entities("WHETHER Together Ethics")["chains"] == []
    assert detect_entities("because of open markets")["persons"] == []
    assert detect_entities("CZ comments on listing")["persons"] == ["cz"]
    assert detect_entities("Vitalik Buterin on Layer 2")["persons"] == ["vitalik"]
    assert "ethereum" in detect_entities("Vitalik Buterin on Layer 2")["chains"]
    assert detect_entities("Uniswap v3 on Arbitrum")["protocols"] == ["uniswap"]
    assert detect_entities("Uniswap v3 on Arbitrum")["chains"] == ["arbitrum"]
    rows_path_check = score_sentiment("City council park renovations", "")
    assert set(rows_path_check["entities"]) == {
        "chains",
        "bridges",
        "protocols",
        "persons",
    }


if __name__ == "__main__":
    test_parse_rss_three_items()
    test_sentiment_bull_and_bear()
    test_ingest_filters_and_dedup()
    test_append_rejects_order_send()
    test_eth_substring_is_not_ethereum()
    test_fetch_http_error_is_feed_silent()
    test_multi_asset_macro_and_no_substring()
    test_entity_tagging()
    print("OK: test_news_agent 8/8")
