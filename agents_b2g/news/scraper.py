"""RSS fetch for the isolated News-Agent — stdlib only, no feedparser.

Isolated from `imports/legacy_daytrading/news_bot/scraper.py` (DeepSeek/Discord).
Pre-Reg: docs/NEWS_FEED_STRUCTURE_PREREG.md — structure_ok = container presence.
"""
from __future__ import annotations

import hashlib
import html
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from agents_b2g.news.feed_health import feed_report

DEFAULT_FEEDS = (
    ("coindesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("cointelegraph", "https://cointelegraph.com/rss"),
)

_ATOM = "{http://www.w3.org/2005/Atom}"
_HTML_TAG = re.compile(r"<[^>]+>")
_USER_AGENT = "agent-x-news/0 (diagnostic_only; no order send)"


def item_id(source: str, link: str, title: str) -> str:
    """Stable identity: source|link. Title only if link is empty (normalized).

    Title in the hash caused duplicate alerts when editors retitled the same URL.
    """
    link_s = (link or "").strip()
    if link_s:
        material = f"{source}|{link_s}".encode("utf-8")
    else:
        norm = re.sub(r"\s+", " ", (title or "").strip().lower())
        material = f"{source}|{norm}".encode("utf-8")
    return hashlib.md5(material).hexdigest()


def _text(node: Optional[ET.Element]) -> str:
    if node is None:
        return ""
    cleaned = _HTML_TAG.sub(" ", html.unescape("".join(node.itertext())))
    return re.sub(r"\s+", " ", cleaned).strip()


def feed_structure_present(root: ET.Element) -> bool:
    """Container presence as used by the item extractor — not item count.

    Pre-Reg Auflage 1/2: True iff parse_rss_xml's paths have a container
    (RSS ``./channel`` or Atom ``feed`` root), even when zero items.
    """
    if root.find("channel") is not None:
        return True
    tag = root.tag or ""
    if tag == f"{_ATOM}feed" or tag == "feed" or tag.endswith("}feed"):
        return True
    return False


def _extract_items(root: ET.Element, source: str) -> List[Dict[str, str]]:
    """Same extraction paths as historical parse_rss_xml (RSS then Atom)."""
    items: List[Dict[str, str]] = []

    for item in root.findall("./channel/item"):
        title = _text(item.find("title"))
        link = _text(item.find("link"))
        summary = _text(item.find("description"))[:500]
        if not title and not link:
            continue
        items.append(
            {
                "id": item_id(source, link, title),
                "source": source,
                "title": title,
                "summary": summary,
                "link": link,
            }
        )

    if items:
        return items

    for entry in root.findall(f".//{_ATOM}entry") or root.findall("./entry"):
        title = _text(entry.find(f"{_ATOM}title") or entry.find("title"))
        link_el = entry.find(f"{_ATOM}link") or entry.find("link")
        href = ""
        if link_el is not None:
            href = (link_el.get("href") or "").strip() or _text(link_el)
        summary = _text(
            entry.find(f"{_ATOM}summary")
            or entry.find("summary")
            or entry.find(f"{_ATOM}content")
        )[:500]
        if not title and not href:
            continue
        items.append(
            {
                "id": item_id(source, href, title),
                "source": source,
                "title": title,
                "summary": summary,
                "link": href,
            }
        )
    return items


def parse_rss_xml(xml_text: str, *, source: str) -> List[Dict[str, str]]:
    """Parse RSS 2.0 or Atom into {id, source, title, summary, link}."""
    root = ET.fromstring(xml_text)
    return _extract_items(root, source)


def parse_rss_xml_with_structure(
    xml_text: str, *, source: str
) -> Tuple[List[Dict[str, str]], bool]:
    """Parse once: items + structure_ok (container presence, Pre-Reg §3)."""
    root = ET.fromstring(xml_text)
    return _extract_items(root, source), feed_structure_present(root)


def fetch_feed_report(
    url: str,
    *,
    source: str,
    timeout_s: float = 15.0,
) -> Tuple[List[Dict[str, str]], dict]:
    """One feed, isolated. Maps HTTP/parse/structure onto feed_report.

    stdlib urlopen (no feedparser): HTTP status ≈ feed.status; ParseError ≈ bozo.
    """
    try:
        req = Request(url, headers={"User-Agent": _USER_AGENT})
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
        structure_ok = True  # moot: bozo leads to dead; default keeps field present
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
