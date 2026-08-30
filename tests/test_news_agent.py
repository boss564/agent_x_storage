"""Multi-scraper News-Agent — plugin architecture, no live HTTP, zero cluster."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.news.feed_health import classify_transport_health
from services.news_agent.core.processor import NewsProcessor, enrich
from services.news_agent.liveness import (
    INVARIANT,
    QUIET_STALE_AFTER_S,
    QUIET_STALE_ORIGINAL_S,
    derive_quiet_streaks,
    last_run_marker,
)
from services.news_agent.models import NewsItem
from services.news_agent.runner import run_once
from services.news_agent.scrapers import load_scrapers
from services.news_agent.scrapers.announcement_scraper import parse_binance_payload
from services.news_agent.scrapers.base_scraper import BaseScraper
from services.news_agent.scrapers.rss_scraper import RssScraper


REQUIRED = (
    "timestamp",
    "source_type",
    "source_name",
    "title",
    "url",
    "target_assets",
    "entities",
    "cross_chain_impact",
    "sentiment_score",
    "impact_level",
)


def test_newsitem_required_fields():
    names = {f.name for f in fields(NewsItem)}
    for name in REQUIRED:
        assert name in names, name
    item = NewsItem(
        timestamp="2026-08-30T14:00:00+00:00",
        source_type="rss",
        source_name="CoinDesk",
        title="Bitcoin rises as Fed signals rate cut",
        url="https://example.test/btc-fed",
    )
    scored = enrich(item)
    row = scored.to_dict()
    for name in REQUIRED:
        assert name in row
    assert scored.target_assets == ["BTC", "MACRO"]
    assert scored.entities["chains"] == []
    assert scored.entities["persons"] == []
    assert -1.0 <= scored.sentiment_score <= 1.0
    assert scored.impact_level in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert row["order_send"] is False
    assert row["source_type"] == "rss"


def test_plugin_discovery():
    scrapers = load_scrapers()
    names = {type(s).__name__ for s in scrapers}
    assert "RssScraper" in names
    assert "AnnouncementScraper" in names
    assert all(isinstance(s, BaseScraper) for s in scrapers)
    assert all(hasattr(s, "fetch") for s in scrapers)


def test_rss_scraper_uses_injected_fetch():
    def fake_fetch():
        return (
            [
                {
                    "id": "abc",
                    "source": "coindesk",
                    "title": "WHETHER Bitcoin rallies",
                    "link": "https://example.test/w",
                    "summary": "",
                }
            ],
            [],
        )

    items = RssScraper(fetch_news=fake_fetch).fetch()
    assert len(items) == 1
    assert items[0].source_type == "rss"
    scored = enrich(items[0])
    assert "ETH" not in scored.target_assets
    assert "BTC" in scored.target_assets


def test_announcement_parser_fixture():
    payload = {
        "data": {
            "catalogs": [
                {
                    "articles": [
                        {
                            "id": "99",
                            "code": "sol-list",
                            "title": "Binance Will List SOL",
                            "releaseDate": 1690000000000,
                        }
                    ]
                }
            ]
        }
    }
    items = parse_binance_payload(payload)
    assert len(items) == 1
    assert items[0].source_type == "announcement"
    assert items[0].source_name == "Binance"
    scored = enrich(items[0])
    assert "SOL" in scored.target_assets


def test_processor_dedup_and_critical_notify():
    root = Path(tempfile.mkdtemp())
    path = root / "news_scores.jsonl"
    alerts = []

    def notify(item: NewsItem):
        alerts.append(item.title)

    proc = NewsProcessor(path, notify_critical=notify, telegram_enabled=True)
    critical = NewsItem(
        timestamp="2026-08-30T14:00:00+00:00",
        source_type="announcement",
        source_name="Binance",
        title="Exchange hack drains ETH wallets",
        url="https://example.test/hack",
        summary="Exploit and liquidation cascade after the hack.",
        item_id="hack-1",
    )
    quiet = NewsItem(
        timestamp="2026-08-30T14:00:00+00:00",
        source_type="rss",
        source_name="coindesk",
        title="Bitcoin ETF inflows hit record high",
        url="https://example.test/etf",
        summary="spot ETF inflows",
        item_id="etf-1",
    )
    first = proc.process([critical, quiet])
    assert first["written"] == 2
    assert first["critical"] == 1
    assert alerts == ["Exchange hack drains ETH wallets"]
    assert enrich(critical).impact_level == "CRITICAL"
    second = proc.process([critical, quiet])
    assert second["written"] == 0
    assert second["skipped_seen"] == 2
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    rows = [json.loads(line) for line in lines]
    assert all("target_assets" in r for r in rows)
    assert rows[0]["impact_level"] == "CRITICAL"


def test_transport_health_matrix():
    assert classify_transport_health(status=404, bozo=1, entries=0) == "dead"
    assert classify_transport_health(status=200, bozo=0, entries=0) == "quiet"
    assert classify_transport_health(status=200, bozo=0, entries=5) == "ok"
    assert classify_transport_health(status=200, bozo=1, entries=5) == "degraded"
    assert classify_transport_health(status=None, bozo=1, entries=0) == "dead"
    # Pre-Reg §3: ¬structure_ok → degraded (before quiet)
    assert (
        classify_transport_health(
            status=200, bozo=0, entries=0, structure_ok=False
        )
        == "degraded"
    )
    assert INVARIANT.startswith("Jeder Audit-Writer")


def test_run_marker_carries_health_not_counts_only(tmp_path: Path | None = None):
    root = Path(tempfile.mkdtemp()) if tmp_path is None else tmp_path
    jsonl = root / "news_scores.jsonl"
    prev = os.environ.get("NEWS_AGENT_MULTI_JSONL")
    os.environ["NEWS_AGENT_MULTI_JSONL"] = str(jsonl)

    class QuietRss(RssScraper):
        def fetch(self):
            self.feed_reports = {
                "CoinDesk": {
                    "status": 200,
                    "bozo": 0,
                    "entries": 0,
                    "health": "quiet",
                    "bozo_exception": None,
                },
                "Cointelegraph": {
                    "status": 404,
                    "bozo": 1,
                    "entries": 0,
                    "health": "dead",
                    "bozo_exception": "HTTPError 404",
                },
            }
            self.last_error = "Cointelegraph: dead"
            return []

    class OkAnnounce:
        source_name = "Binance"
        last_error = ""
        feed_reports = {
            "BinanceCMS": {
                "status": 200,
                "bozo": 0,
                "entries": 5,
                "health": "ok",
                "bozo_exception": None,
            }
        }

        def fetch(self):
            return [
                NewsItem(
                    timestamp="2026-08-30T14:00:00+00:00",
                    source_type="announcement",
                    source_name="Binance",
                    title="Binance Will List SOL",
                    url="https://example.test/sol",
                    item_id="binance:sol",
                )
            ]

    try:
        result = run_once(scrapers=[QuietRss(), OkAnnounce()])
        assert result["status"] == "DEGRADED"
        assert result["feeds"]["CoinDesk"]["health"] == "quiet"
        assert result["feeds"]["Cointelegraph"]["health"] == "dead"
        assert result["feeds"]["BinanceCMS"]["health"] == "ok"
        marker = last_run_marker(jsonl)
        assert marker is not None
        assert marker["feeds"]["Cointelegraph"]["health"] == "dead"
        assert marker["feeds"]["CoinDesk"]["entries"] == 0
        assert marker["order_send"] is False
        assert result["written"] == 1
    finally:
        if prev is None:
            os.environ.pop("NEWS_AGENT_MULTI_JSONL", None)
        else:
            os.environ["NEWS_AGENT_MULTI_JSONL"] = prev


def test_quiet_stale_duration_frozen():
    assert QUIET_STALE_AFTER_S == 72 * 3600
    assert QUIET_STALE_ORIGINAL_S == 259200
    assert QUIET_STALE_AFTER_S == QUIET_STALE_ORIGINAL_S
    now = datetime(2026, 8, 30, 15, 0, tzinfo=timezone.utc)
    quiet = {"health": "quiet", "status": 200, "bozo": 0, "entries": 0}
    prior_short = [
        {
            "source_type": "run_marker",
            "ts": (now - timedelta(hours=71)).isoformat(),
            "feeds": {"CoinDesk": quiet},
        }
    ]
    short = derive_quiet_streaks(
        prior_short, {"CoinDesk": quiet}, now=now.isoformat()
    )
    assert short["CoinDesk"]["stale"] is False
    prior_long = [
        {
            "source_type": "run_marker",
            "ts": (now - timedelta(hours=72)).isoformat(),
            "feeds": {"CoinDesk": quiet},
        }
    ]
    long = derive_quiet_streaks(
        prior_long, {"CoinDesk": quiet}, now=now.isoformat()
    )
    assert long["CoinDesk"]["stale"] is True
    assert long["CoinDesk"]["consecutive_quiet"] == 2
    broken = derive_quiet_streaks(
        [
            {
                "source_type": "run_marker",
                "ts": (now - timedelta(hours=80)).isoformat(),
                "feeds": {"CoinDesk": {"health": "ok", "entries": 3}},
            }
        ],
        {"CoinDesk": quiet},
        now=now.isoformat(),
    )
    assert broken["CoinDesk"]["stale"] is False


def test_degraded_breaks_quiet_streak():
    """Auflage 3: degraded must interrupt consecutive quiet (Pre-Reg §3)."""
    now = datetime(2026, 8, 30, 18, 0, tzinfo=timezone.utc)
    quiet = {"health": "quiet", "status": 200, "bozo": 0, "entries": 0}
    prior = [
        {
            "source_type": "run_marker",
            "ts": (now - timedelta(hours=80)).isoformat(),
            "feeds": {"CoinDesk": quiet},
        },
        {
            "source_type": "run_marker",
            "ts": (now - timedelta(hours=40)).isoformat(),
            "feeds": {"CoinDesk": quiet},
        },
    ]
    # Current degraded (non-feed) — streak must not continue as quiet.
    degraded = {
        "health": "degraded",
        "status": 200,
        "bozo": 0,
        "entries": 0,
        "structure_ok": False,
    }
    out = derive_quiet_streaks(
        prior, {"CoinDesk": degraded}, now=now.isoformat()
    )
    assert out["CoinDesk"]["consecutive_quiet"] == 0
    assert out["CoinDesk"]["stale"] is False
    assert out["CoinDesk"]["span_s"] == 0.0


def test_structure_ok_s1_to_s7():
    """Pre-Reg NEWS_FEED_STRUCTURE_PREREG Smoke S1–S7."""
    from agents_b2g.news.feed_health import feed_report
    from agents_b2g.news.scraper import parse_rss_xml_with_structure
    import xml.etree.ElementTree as ET

    # S1 — empty channel: structure_ok true, quiet
    items, ok = parse_rss_xml_with_structure(
        "<rss><channel></channel></rss>", source="t"
    )
    assert ok is True and items == []
    r = feed_report(status=200, bozo=0, entries=0, structure_ok=ok)
    assert r["health"] == "quiet" and r["structure_ok"] is True

    # S2 — well-formed non-feed
    items, ok = parse_rss_xml_with_structure(
        "<error><message>Not found</message></error>", source="t"
    )
    assert ok is False and items == []
    r = feed_report(status=200, bozo=0, entries=0, structure_ok=ok)
    assert r["health"] == "degraded" and r["structure_ok"] is False

    # S3 — malformed → ParseError path (bozo/dead)
    try:
        parse_rss_xml_with_structure("<rss><channel>", source="t")
        raise AssertionError("expected ParseError")
    except ET.ParseError:
        pass
    r = feed_report(status=200, bozo=1, entries=0, bozo_exception="ParseError")
    assert r["health"] == "dead"

    # S4 — HTTP fail
    assert feed_report(status=404, bozo=1, entries=0)["health"] == "dead"
    assert feed_report(status=None, bozo=1, entries=0)["health"] == "dead"

    # S5 — RSS with items
    items, ok = parse_rss_xml_with_structure(
        "<rss><channel><item><title>News</title>"
        "<link>https://example.test/n</link></item></channel></rss>",
        source="t",
    )
    assert ok is True and len(items) == 1
    r = feed_report(status=200, bozo=0, entries=len(items), structure_ok=ok)
    assert r["health"] == "ok"

    # S6 — Atom feed (+ entry)
    atom = (
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        "<entry><title>News</title>"
        '<link href="https://example.test/a"/></entry></feed>'
    )
    items, ok = parse_rss_xml_with_structure(atom, source="t")
    assert ok is True and len(items) == 1
    r = feed_report(status=200, bozo=0, entries=len(items), structure_ok=ok)
    assert r["health"] == "ok"

    # empty Atom feed still structure_ok (container, not item count)
    items, ok = parse_rss_xml_with_structure(
        '<feed xmlns="http://www.w3.org/2005/Atom"></feed>', source="t"
    )
    assert ok is True and items == []
    assert (
        feed_report(status=200, bozo=0, entries=0, structure_ok=ok)["health"]
        == "quiet"
    )

    # S7 — regression: prior matrix lines unchanged for default structure_ok
    assert classify_transport_health(status=404, bozo=1, entries=0) == "dead"
    assert classify_transport_health(status=200, bozo=0, entries=0) == "quiet"
    assert classify_transport_health(status=200, bozo=0, entries=5) == "ok"
    assert classify_transport_health(status=200, bozo=1, entries=5) == "degraded"


def test_stale_quiet_elevates_run_status():
    """72h quiet → streaks.stale and status=DEGRADED (not only in the marker)."""
    root = Path(tempfile.mkdtemp())
    jsonl = root / "news_scores.jsonl"
    now = datetime(2026, 8, 30, 15, 0, tzinfo=timezone.utc)
    quiet = {"health": "quiet", "status": 200, "bozo": 0, "entries": 0}
    prior = {
        "source_type": "run_marker",
        "ts": (now - timedelta(hours=72)).isoformat(),
        "feeds": {"CoinDesk": quiet, "Cointelegraph": quiet},
        "diagnostic_only": True,
        "live_execution": False,
        "order_send": False,
    }
    jsonl.write_text(json.dumps(prior) + "\n", encoding="utf-8")
    prev = os.environ.get("NEWS_AGENT_MULTI_JSONL")
    os.environ["NEWS_AGENT_MULTI_JSONL"] = str(jsonl)

    class AllQuiet(RssScraper):
        def fetch(self):
            self.feed_reports = {
                "CoinDesk": dict(quiet),
                "Cointelegraph": dict(quiet),
            }
            self.last_error = ""
            return []

    try:
        result = run_once(scrapers=[AllQuiet()])
        assert result["stale"], result
        assert result["status"] == "DEGRADED", result["status"]
        assert not any(
            r.get("health") == "dead" for r in result["feeds"].values()
        )
    finally:
        if prev is None:
            os.environ.pop("NEWS_AGENT_MULTI_JSONL", None)
        else:
            os.environ["NEWS_AGENT_MULTI_JSONL"] = prev


def test_run_marker_freshness_stale_and_active():
    from services.news_agent.liveness import (
        NEWS_MARKER_MAX_AGE_S,
        run_marker_freshness,
    )

    assert NEWS_MARKER_MAX_AGE_S == 2 * 3600
    root = Path(tempfile.mkdtemp())
    jsonl = root / "news_scores.jsonl"
    now = datetime(2026, 8, 30, 16, 0, tzinfo=timezone.utc)
    missing = run_marker_freshness(jsonl, now=now.isoformat())
    assert missing["status"] == "MISSING"
    assert missing["ok"] is False
    jsonl.write_text(
        json.dumps(
            {
                "source_type": "run_marker",
                "ts": (now - timedelta(hours=3)).isoformat(),
                "feeds": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    stale = run_marker_freshness(jsonl, now=now.isoformat())
    assert stale["status"] == "STALE"
    assert stale["ok"] is False
    assert stale["age_s"] >= 3 * 3600
    jsonl.write_text(
        json.dumps(
            {
                "source_type": "run_marker",
                "ts": (now - timedelta(minutes=30)).isoformat(),
                "feeds": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    active = run_marker_freshness(jsonl, now=now.isoformat())
    assert active["status"] == "ACTIVE"
    assert active["ok"] is True


def test_writer_stale_elevates_run_status():
    root = Path(tempfile.mkdtemp())
    jsonl = root / "news_scores.jsonl"
    # Wall-clock age: marker older than NEWS_MARKER_MAX_AGE_H (2h).
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    jsonl.write_text(
        json.dumps(
            {
                "source_type": "run_marker",
                "ts": old_ts,
                "feeds": {
                    "CoinDesk": {
                        "health": "ok",
                        "status": 200,
                        "bozo": 0,
                        "entries": 1,
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    prev = os.environ.get("NEWS_AGENT_MULTI_JSONL")
    os.environ["NEWS_AGENT_MULTI_JSONL"] = str(jsonl)

    class OkRss(RssScraper):
        def fetch(self):
            self.feed_reports = {
                "CoinDesk": {
                    "health": "ok",
                    "status": 200,
                    "bozo": 0,
                    "entries": 1,
                    "bozo_exception": None,
                }
            }
            return [
                NewsItem(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    source_type="rss",
                    source_name="coindesk",
                    title="Bitcoin holds steady",
                    url="https://example.test/btc-hold",
                    item_id="btc-hold",
                )
            ]

    try:
        result = run_once(scrapers=[OkRss()])
        assert result["marker_liveness"]["status"] == "STALE", result["marker_liveness"]
        assert result["status"] == "WRITER_STALE", result["status"]
    finally:
        if prev is None:
            os.environ.pop("NEWS_AGENT_MULTI_JSONL", None)
        else:
            os.environ["NEWS_AGENT_MULTI_JSONL"] = prev


def test_item_id_stable_on_title_change():
    from agents_b2g.news.scraper import item_id

    a = item_id("coindesk", "https://example.test/x", "Bitcoin rises")
    b = item_id("coindesk", "https://example.test/x", "Bitcoin rises hard")
    assert a == b
    c = item_id("coindesk", "https://example.test/y", "Bitcoin rises")
    assert a != c
    no_link = item_id("coindesk", "", "  Bitcoin   Rises  ")
    no_link2 = item_id("coindesk", "", "bitcoin rises")
    assert no_link == no_link2


def test_entities_on_enrich_and_jsonl():
    item = NewsItem(
        timestamp="2026-08-30T15:00:00+00:00",
        source_type="rss",
        source_name="CoinDesk",
        title="Wormhole bridge exploit on Solana",
        url="https://example.test/wh",
        summary="",
        item_id="wh-1",
    )
    scored = enrich(item)
    assert scored.entities["chains"] == ["solana"]
    assert scored.entities["bridges"] == ["wormhole"]
    assert scored.entities["protocols"] == []
    assert scored.entities["persons"] == []
    assert scored.target_assets == ["SOL"]
    row = scored.to_dict()
    assert row["schema"] == "news_agent_multi/v1.2"
    assert row["entities"]["bridges"] == ["wormhole"]
    assert row["cross_chain_impact"]["bridges"] == ["wormhole"]
    assert row["cross_chain_impact"]["affected_chains"] == [
        "ethereum",
        "avalanche",
        "arbitrum",
    ]
    assert row["cross_chain_impact"]["impact_score"] == 0.8
    root = Path(tempfile.mkdtemp())
    path = root / "news_scores.jsonl"
    proc = NewsProcessor(path)
    proc.process([item])
    written = json.loads(path.read_text(encoding="utf-8").strip().splitlines()[0])
    assert written["entities"]["chains"] == ["solana"]
    assert written["entities"]["bridges"] == ["wormhole"]
    assert written["cross_chain_impact"]["impact_score"] == 0.8
    assert "ETH" not in written["target_assets"]


if __name__ == "__main__":
    test_newsitem_required_fields()
    test_plugin_discovery()
    test_rss_scraper_uses_injected_fetch()
    test_announcement_parser_fixture()
    test_processor_dedup_and_critical_notify()
    test_transport_health_matrix()
    test_run_marker_carries_health_not_counts_only()
    test_quiet_stale_duration_frozen()
    test_stale_quiet_elevates_run_status()
    test_run_marker_freshness_stale_and_active()
    test_writer_stale_elevates_run_status()
    test_item_id_stable_on_title_change()
    test_entities_on_enrich_and_jsonl()
    print("OK: tests/test_news_agent 13/13")
