"""RSS fetch for the isolated News-Agent — stdlib only, no feedparser.

Isolated from `imports/legacy_daytrading/news_bot/scraper.py` (DeepSeek/Discord).
Pre-Reg: docs/NEWS_FEED_STRUCTURE_PREREG.md — structure_ok = container presence.

XML/date parsing: ``src.ingestion.rss_parser`` (M2 ``published_at`` / ``detection_lag``).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from agents_b2g.news.feed_health import feed_report
from src.ingestion.rss_parser import (
    item_id,
    parse_feed_datetime,
    parse_rss_xml,
    parse_rss_xml_with_structure,
)

DEFAULT_FEEDS = (
    ("coindesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("cointelegraph", "https://cointelegraph.com/rss"),
)

_DEFAULT_USER_AGENT = "agent-x-news/0 (diagnostic_only; no order send)"

__all__ = [
    "DEFAULT_FEEDS",
    "fetch_feed",
    "fetch_feed_report",
    "fetch_news",
    "http_user_agent",
    "item_id",
    "parse_feed_datetime",
    "parse_rss_xml",
    "parse_rss_xml_with_structure",
]


def http_user_agent() -> str:
    """Cluster CronJob may set HTTP_USER_AGENT (see NEWS_24H_SCHEDULER_GATE §8.4)."""
    import os

    raw = os.environ.get("HTTP_USER_AGENT", "").strip()
    return raw if raw else _DEFAULT_USER_AGENT


def fetch_feed_report(
    url: str,
    *,
    source: str,
    timeout_s: float = 15.0,
) -> Tuple[List[Dict[str, str]], dict]:
    """One feed, isolated. Maps HTTP/parse/structure onto feed_report."""
    try:
        req = Request(url, headers={"User-Agent": http_user_agent()})
        with urlopen(req, timeout=timeout_s) as resp:
            status = int(getattr(resp, "status", None) or resp.getcode() or 0) or None
            body = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return [], feed_report(
            status=int(exc.code) if exc.code else None,
            bozo=1,
            entries=0,
            bozo_exception=exc,
        )
    except (URLError, TimeoutError, OSError) as exc:
        return [], feed_report(
            status=None,
            bozo=1,
            entries=0,
            bozo_exception=exc,
        )

    try:
        items, structure_ok = parse_rss_xml_with_structure(body, source=source)
        bozo = 0
        bozo_exc = None
    except ET.ParseError as exc:
        items = []
        structure_ok = True
        bozo = 1
        bozo_exc = exc
    return items, feed_report(
        status=status,
        bozo=bozo,
        entries=len(items),
        bozo_exception=bozo_exc,
        structure_ok=structure_ok,
    )


def fetch_feed(
    url: str,
    *,
    source: str,
    timeout_s: float = 15.0,
) -> List[Dict[str, str]]:
    items, _report = fetch_feed_report(url, source=source, timeout_s=timeout_s)
    return items


def fetch_news(
    feeds: Optional[List[tuple]] = None,
    *,
    timeout_s: float = 15.0,
) -> Tuple[List[Dict[str, str]], List[str]]:
    """Fetch all feeds. Dead transport → errors. Quiet empty 200 is not an error."""
    out: List[Dict[str, str]] = []
    errors: List[str] = []
    for source, url in feeds or DEFAULT_FEEDS:
        items, report = fetch_feed_report(url, source=source, timeout_s=timeout_s)
        if report["health"] == "dead":
            errors.append(
                f"{source}: dead status={report['status']} bozo={report['bozo']} "
                f"{report.get('bozo_exception') or ''}".strip()
            )
        elif report["health"] == "degraded":
            why = (
                f"structure_ok={report.get('structure_ok')}"
                if report.get("structure_ok") is False
                else f"bozo={report['bozo']}"
            )
            errors.append(f"{source}: degraded {why}")
        out.extend(items)
    return out, errors
