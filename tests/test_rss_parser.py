"""Unit tests for src.ingestion.rss_parser — published_at and detection_lag."""
from __future__ import annotations

from datetime import datetime, timezone

from src.ingestion.rss_parser import (
    RssIngestRecord,
    compute_detection_lag_seconds,
    parse_feed_datetime,
    parse_rss_xml,
)

RFC822_XML = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>Bitcoin rises</title>
    <link>https://example.test/btc</link>
    <pubDate>Mon, 01 Sep 2025 10:03:00 GMT</pubDate>
    <description>BTC up</description>
  </item>
</channel></rss>"""

ISO_XML = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>ETH upgrade</title>
    <link>https://example.test/eth</link>
    <pubDate>2026-09-02T07:10:00Z</pubDate>
  </item>
</channel></rss>"""

MISSING_DATE_XML = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>No date item</title>
    <link>https://example.test/nodate</link>
  </item>
</channel></rss>"""

ATOM_XML = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Atom published</title>
    <link href="https://example.test/atom"/>
    <published>2026-09-02T06:00:00+00:00</published>
  </entry>
</feed>"""

ATOM_UPDATED_ONLY_XML = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Atom updated only</title>
    <link href="https://example.test/atom2"/>
    <updated>2026-09-02T05:30:00Z</updated>
  </entry>
</feed>"""


def test_parse_feed_datetime_rfc822_gmt() -> None:
    out = parse_feed_datetime("Mon, 01 Sep 2025 10:03:00 GMT")
    assert out is not None
    assert out.startswith("2025-09-01T10:03:00")
    assert "+00:00" in out or out.endswith("Z")


def test_parse_feed_datetime_iso8601_z() -> None:
    out = parse_feed_datetime("2026-09-02T07:10:00Z")
    assert out is not None
    assert out.startswith("2026-09-02T07:10:00")


def test_parse_feed_datetime_missing_returns_none() -> None:
    assert parse_feed_datetime(None) is None
    assert parse_feed_datetime("") is None
    assert parse_feed_datetime("   ") is None


def test_parse_feed_datetime_invalid_returns_none() -> None:
    assert parse_feed_datetime("not-a-date") is None


def test_parse_rss_xml_rfc822_pubdate() -> None:
    rows = parse_rss_xml(RFC822_XML, source="cointelegraph")
    assert len(rows) == 1
    assert rows[0]["published_at"].startswith("2025-09-01T10:03")


def test_parse_rss_xml_iso_pubdate() -> None:
    rows = parse_rss_xml(ISO_XML, source="coindesk")
    assert rows[0]["published_at"].startswith("2026-09-02T07:10:00")


def test_parse_rss_xml_missing_pubdate_empty_not_now() -> None:
    rows = parse_rss_xml(MISSING_DATE_XML, source="coindesk")
    assert rows[0]["published_at"] == ""


def test_parse_rss_xml_atom_published() -> None:
    rows = parse_rss_xml(ATOM_XML, source="coindesk")
    assert rows[0]["published_at"].startswith("2026-09-02T06:00:00")


def test_parse_rss_xml_atom_updated_fallback() -> None:
    rows = parse_rss_xml(ATOM_UPDATED_ONLY_XML, source="coindesk")
    assert rows[0]["published_at"].startswith("2026-09-02T05:30:00")


def test_compute_detection_lag_seconds() -> None:
    ingest = datetime(2026, 9, 2, 7, 15, 0, tzinfo=timezone.utc)
    published = "2026-09-02T07:10:00+00:00"
    assert compute_detection_lag_seconds(ingest, published) == 300


def test_compute_detection_lag_missing_published() -> None:
    ingest = datetime(2026, 9, 2, 7, 15, 0, tzinfo=timezone.utc)
    assert compute_detection_lag_seconds(ingest, None) is None
    assert compute_detection_lag_seconds(ingest, "") is None


def test_rss_ingest_record_jsonl_shape() -> None:
    rows = parse_rss_xml(ISO_XML, source="cointelegraph")
    ingest = datetime(2026, 9, 2, 7, 15, 0, tzinfo=timezone.utc)
    record = RssIngestRecord.from_feed_row(
        rows[0],
        t_ingest=ingest,
        sentiment_score=0.42,
        asset="BTC",
    )
    payload = record.to_dict()
    assert payload["timestamp"].startswith("2026-09-02T07:15:00")
    assert payload["published_at"].startswith("2026-09-02T07:10:00")
    assert payload["detection_lag_sec"] == 300
    assert payload["source"] == "rss_cointelegraph"
    assert payload["asset"] == "BTC"
    assert payload["sentiment_score"] == 0.42
    assert payload["raw_title"] == "ETH upgrade"


def test_newsitem_to_dict_detection_lag_sec_alias() -> None:
    from services.news_agent.core.processor import enrich
    from services.news_agent.models import NewsItem

    item = NewsItem(
        timestamp="2026-09-02T07:15:00+00:00",
        source_type="rss",
        source_name="Cointelegraph",
        title="ETH upgrade",
        url="https://example.test/eth",
        published_at="2026-09-02T07:10:00+00:00",
    )
    row = enrich(item).to_dict()
    assert row["detection_lag"] == 300
    assert row["detection_lag_sec"] == 300
    assert row["published_at"].startswith("2026-09-02T07:10:00")
