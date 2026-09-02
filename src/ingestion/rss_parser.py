"""RSS/Atom publication-time extraction for Agent-X news ingest (M2 Arm A/B).

Canonical date parsing lives here; ``agents_b2g.news.scraper`` re-exports for HTTP fetch.
Production JSONL uses ``NewsItem.to_dict()`` (schema v1.3) — fields map as:

  timestamp / published_at / detection_lag (+ detection_lag_sec alias)
  source_name / title / target_assets / sentiment_score
"""
from __future__ import annotations

import hashlib
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional, Tuple, Union

_ATOM = "{http://www.w3.org/2005/Atom}"
_HTML_TAG = re.compile(r"<[^>]+>")
_ISO_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}T")

DatetimeInput = Union[datetime, str]


def item_id(source: str, link: str, title: str) -> str:
    """Stable identity: source|link (title fallback when link empty)."""
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


def parse_feed_datetime(raw: Optional[str]) -> Optional[str]:
    """Parse RSS ``pubDate`` or Atom ``published``/``updated`` to UTC ISO-8601.

    Returns ``None`` when missing or unparsable — never substitutes ``now()``.
    """
    if raw is None or not str(raw).strip():
        return None
    text = str(raw).strip()
    try:
        if _ISO_PREFIX.match(text):
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        else:
            dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError):
        return None


def _coerce_utc_datetime(value: DatetimeInput) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_detection_lag_seconds(
    t_ingest: DatetimeInput,
    published_at: Optional[str],
) -> Optional[int]:
    """``detection_lag = int((t_ingest - t_published).total_seconds())`` when both valid."""
    if not published_at or not str(published_at).strip():
        return None
    try:
        ingest = _coerce_utc_datetime(t_ingest)
        published = _coerce_utc_datetime(str(published_at))
        return int((ingest - published).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return None


def _published_from_rss_item(item: ET.Element) -> str:
    raw = _text(item.find("pubDate")) or _text(item.find("date"))
    return parse_feed_datetime(raw) or ""


def _find_child(parent: ET.Element, *tags: str) -> Optional[ET.Element]:
    for tag in tags:
        el = parent.find(tag)
        if el is not None:
            return el
    return None


def _published_from_atom_entry(entry: ET.Element) -> str:
    raw = _text(
        _find_child(
            entry,
            f"{_ATOM}published",
            "published",
            f"{_ATOM}updated",
            "updated",
        )
    )
    return parse_feed_datetime(raw) or ""


def feed_structure_present(root: ET.Element) -> bool:
    """True when RSS channel or Atom feed container is present (Pre-Reg structure_ok)."""
    if root.find("channel") is not None:
        return True
    tag = root.tag or ""
    if tag == f"{_ATOM}feed" or tag == "feed" or tag.endswith("}feed"):
        return True
    return False


def _extract_items(root: ET.Element, source: str) -> List[Dict[str, str]]:
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
                "published_at": _published_from_rss_item(item),
            }
        )

    if items:
        return items

    for entry in root.findall(f".//{_ATOM}entry") or root.findall("./entry"):
        title = _text(_find_child(entry, f"{_ATOM}title", "title"))
        link_el = _find_child(entry, f"{_ATOM}link", "link")
        href = ""
        if link_el is not None:
            href = (link_el.get("href") or "").strip() or _text(link_el)
        summary = _text(
            _find_child(entry, f"{_ATOM}summary", "summary", f"{_ATOM}content")
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
                "published_at": _published_from_atom_entry(entry),
            }
        )
    return items


def parse_rss_xml(xml_text: str, *, source: str) -> List[Dict[str, str]]:
    """Parse RSS 2.0 or Atom into rows with ``published_at`` (empty when absent)."""
    root = ET.fromstring(xml_text)
    return _extract_items(root, source)


def parse_rss_xml_with_structure(
    xml_text: str,
    *,
    source: str,
) -> Tuple[List[Dict[str, str]], bool]:
    """Parse once: items + ``structure_ok`` (container presence)."""
    root = ET.fromstring(xml_text)
    return _extract_items(root, source), feed_structure_present(root)


@dataclass(frozen=True)
class RssIngestRecord:
    """Minimal M2-oriented ingest view (tests / previews)."""

    timestamp: str
    published_at: Optional[str]
    detection_lag_sec: Optional[int]
    source: str
    asset: Optional[str]
    sentiment_score: float
    raw_title: str

    @classmethod
    def from_feed_row(
        cls,
        row: Dict[str, str],
        *,
        t_ingest: DatetimeInput,
        sentiment_score: float = 0.0,
        asset: Optional[str] = None,
        source_prefix: str = "rss_",
    ) -> RssIngestRecord:
        slug = str(row.get("source") or "rss")
        published = row.get("published_at") or None
        if published is not None and not str(published).strip():
            published = None
        ingest_iso = _coerce_utc_datetime(t_ingest).isoformat()
        lag = compute_detection_lag_seconds(ingest_iso, published)
        return cls(
            timestamp=ingest_iso,
            published_at=published,
            detection_lag_sec=lag,
            source=f"{source_prefix}{slug}",
            asset=asset,
            sentiment_score=sentiment_score,
            raw_title=str(row.get("title") or ""),
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "published_at": self.published_at,
            "detection_lag_sec": self.detection_lag_sec,
            "source": self.source,
            "asset": self.asset,
            "sentiment_score": self.sentiment_score,
            "raw_title": self.raw_title,
        }
