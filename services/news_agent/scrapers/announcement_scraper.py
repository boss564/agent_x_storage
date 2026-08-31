"""Exchange announcement ingest (Binance public CMS catalog)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from services.news_agent.models import NewsItem
from services.news_agent.scrapers.base_scraper import BaseScraper
from agents_b2g.news.feed_health import feed_report

_USER_AGENT = "agent-x-news/0 (diagnostic_only; no order send)"
DEFAULT_BINANCE_URL = (
    "https://www.binance.com/bapi/composite/v1/public/cms/article/catalog/list/query"
    "?catalogId=48&pageNo=1&pageSize=20"
)


def _ms_to_iso(value: Any) -> str:
    try:
        ms = int(value)
        if ms > 10_000_000_000:
            ms = ms / 1000.0
        return datetime.fromtimestamp(ms, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return datetime.now(timezone.utc).isoformat()


def parse_binance_payload(payload: Dict[str, Any]) -> List[NewsItem]:
    """Map Binance CMS JSON (catalogs[] or articles[]) to NewsItem. No HTTP."""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    articles: List[dict] = []
    if isinstance(data, dict):
        catalogs = data.get("catalogs") or []
        if isinstance(catalogs, list):
            for cat in catalogs:
                if isinstance(cat, dict):
                    articles.extend(cat.get("articles") or [])
        if not articles:
            articles = list(data.get("articles") or [])
    out: List[NewsItem] = []
    now = datetime.now(timezone.utc).isoformat()
    for art in articles:
        if not isinstance(art, dict):
            continue
        title = str(art.get("title") or "")
        code = str(art.get("code") or art.get("id") or "")
        if not title:
            continue
        url = str(art.get("url") or "")
        if not url and code:
            url = f"https://www.binance.com/en/support/announcement/{code}"
        out.append(
            NewsItem(
                timestamp=_ms_to_iso(art.get("releaseDate") or art.get("releaseDateStr")),
                source_type="announcement",
                source_name="Binance",
                title=title,
                url=url,
                summary=str(art.get("body") or art.get("brief") or "")[:500],
                item_id=f"binance:{code or title}",
            )
        )
    if not out and payload.get("title"):
        out.append(
            NewsItem(
                timestamp=now,
                source_type="announcement",
                source_name="Binance",
                title=str(payload["title"]),
                url=str(payload.get("url") or ""),
                item_id=str(payload.get("item_id") or payload["title"]),
            )
        )
    return out


class AnnouncementScraper(BaseScraper):
    source_type = "announcement"
    source_name = "Binance"
    enabled = True

    def __init__(self, url: Optional[str] = None, payload: Optional[Dict[str, Any]] = None) -> None:
        super().__init__()
        self.url = url or DEFAULT_BINANCE_URL
        self._payload = payload

    def fetch(self) -> List[NewsItem]:
        self.feed_reports = {}
        self.last_error = ""
        if self._payload is not None:
            items = parse_binance_payload(self._payload)
            n = len(items)
            self.feed_reports["BinanceCMS"] = feed_report(
                status=200, bozo=0, entries=n, bozo_exception=None
            )
            return items
        req = Request(self.url, headers={"User-Agent": _USER_AGENT})
        try:
            with urlopen(req, timeout=15) as resp:
                status = int(getattr(resp, "status", None) or resp.getcode() or 0) or None
                raw = resp.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            report = feed_report(
                status=int(exc.code) if exc.code else None,
                bozo=1,
                entries=0,
                bozo_exception=exc,
            )
            self.feed_reports["BinanceCMS"] = report
            self.last_error = f"BinanceCMS: dead {exc.code}"
            return []
        except (URLError, TimeoutError, OSError) as exc:
            report = feed_report(status=None, bozo=1, entries=0, bozo_exception=exc)
            self.feed_reports["BinanceCMS"] = report
            self.last_error = f"BinanceCMS: dead {type(exc).__name__}"
            return []

        try:
            payload = json.loads(raw)
            bozo = 0
            bozo_exc = None
        except json.JSONDecodeError as exc:
            report = feed_report(status=status, bozo=1, entries=0, bozo_exception=exc)
            self.feed_reports["BinanceCMS"] = report
            self.last_error = "BinanceCMS: dead JSON"
            return []

        if not isinstance(payload, dict):
            report = feed_report(status=status, bozo=1, entries=0, bozo_exception="invalid_json")
            self.feed_reports["BinanceCMS"] = report
            self.last_error = "BinanceCMS: dead invalid_json"
            return []

        items = parse_binance_payload(payload)
        report = feed_report(status=status, bozo=bozo, entries=len(items), bozo_exception=bozo_exc)
        self.feed_reports["BinanceCMS"] = report
        if report["health"] == "dead":
            self.last_error = "BinanceCMS: dead"
        return items
