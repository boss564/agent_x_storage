"""Cross-chain map + impact — no live HTTP, zero cluster."""
from __future__ import annotations

import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.news_agent.core.processor import enrich
from services.news_agent.impact import (
    compute_cross_chain_impact,
    empty_cross_chain_impact,
    load_map,
    validate_default_map,
    validate_map,
)
from services.news_agent.models import NewsItem


def test_map_file_valid():
    data = validate_default_map()
    assert data["version"] == "v1.0"
    names = [b["name"] for b in data["bridges"]]
    assert names == ["wormhole", "layerzero", "axelar"]
    assert "uniswap" in [p["name"] for p in data["protocols"]]
    assert "solana" in data["correlation_matrix"]
    try:
        validate_map({"version": "v1.0"})
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "missing keys" in str(exc)


def test_solana_wormhole_example():
    hit = compute_cross_chain_impact({"chains": ["solana"], "bridges": [], "protocols": [], "persons": []})
    assert hit["bridges"] == ["wormhole"]
    assert hit["affected_chains"] == ["ethereum", "avalanche", "arbitrum"]
    assert hit["impact_score"] == 0.8
    item = NewsItem(
        timestamp="2026-08-30T15:00:00+00:00",
        source_type="rss",
        source_name="CoinDesk",
        title="Wormhole bridge exploit on Solana",
        url="https://example.test/wh",
    )
    scored = enrich(item)
    assert scored.cross_chain_impact == hit


def test_no_entities_empty_impact():
    empty = compute_cross_chain_impact(
        {"chains": [], "bridges": [], "protocols": [], "persons": []}
    )
    assert empty == empty_cross_chain_impact()
    item = NewsItem(
        timestamp="2026-08-30T14:00:00+00:00",
        source_type="rss",
        source_name="CoinDesk",
        title="Bitcoin rises as Fed signals rate cut",
        url="https://example.test/btc-fed",
    )
    scored = enrich(item)
    assert scored.entities["chains"] == []
    assert scored.cross_chain_impact == empty_cross_chain_impact()
    assert "polygon" not in compute_cross_chain_impact(
        {"chains": ["solana"]}
    )["affected_chains"]


def test_bridge_only_and_protocol_score():
    named = compute_cross_chain_impact({"bridges": ["wormhole"]})
    assert named["bridges"] == ["wormhole"]
    assert "solana" in named["affected_chains"]
    assert named["impact_score"] == 0.8
    eth = compute_cross_chain_impact({"chains": ["ethereum"]})
    assert "wormhole" in eth["bridges"]
    assert "layerzero" in eth["bridges"]
    assert eth["impact_score"] == 0.9
    assert eth["affected_chains"][:3] == ["solana", "polygon", "arbitrum"]
    mapping = copy.deepcopy(load_map())
    mapping["bridges"] = [b for b in mapping["bridges"] if b["name"] != "wormhole"]
    no_wh = compute_cross_chain_impact({"chains": ["solana"]}, mapping=mapping)
    assert no_wh["bridges"] == []
    assert no_wh["affected_chains"] == ["ethereum", "avalanche", "arbitrum"]
    assert no_wh["impact_score"] == 0.6


if __name__ == "__main__":
    test_map_file_valid()
    test_solana_wormhole_example()
    test_no_entities_empty_impact()
    test_bridge_only_and_protocol_score()
    print("OK: test_cross_chain_impact 4/4")
