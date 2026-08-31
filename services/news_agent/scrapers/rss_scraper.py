"""RSS ingest — CoinDesk / Cointelegraph, per-feed transport health."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

from agents_b2g.news.scraper import DEFAULT_FEEDS, fetch_feed_report
from services.news_agent.models import NewsItem
from services.news_agent.scrapers.base_scraper import BaseScraper

FetchNews = Callable[..., Tuple[List[dict], List[str]]]

_LABEL = {
    "coindesk": "CoinDesk",
    "cointelegraph": "Cointelegraph",
}


class RssScraper(BaseScraper):
    source_type = "rss"
    source_name = "rss"
    enabled = True

    def __init__(self, fetch_news: Optional[FetchNews] = None) -> None:
        super().__init__()
        self._fetch_news = fetch_news
        self.feed_reports: Dict[str, dict] = {}

    def fetch(self) -> List[NewsItem]:
        now = datetime.now(timezone.utc).isoformat()
        self.feed_reports = {}
        self.last_error = ""
        if self._fetch_news is not None:
            return self._fetch_injected(now)

        out: List[NewsItem] = []
        dead_notes: List[str] = []
        for source, url in DEFAULT_FEEDS:
            label = _LABEL.get(source, source)
            rows, report = fetch_feed_report(url, source=source)
            self.feed_reports[label] = report
            if report["health"] == "dead":
                dead_notes.append(f"{label}: {report.get('bozo_exception') or report}")
            for row in rows:
                out.append(self._item(row, now))
        if dead_notes:
            self.last_error = "; ".join(dead_notes)
        return out

    def _fetch_injected(self, now: str) -> List[NewsItem]:
        rows, _errors = self._fetch_news()
        by_source: Dict[str, int] = {}
        out: List[NewsItem] = []
        for row in rows:
            source = str(row.get("source") or "rss")
            by_source[source] = by_source.get(source, 0) + 1
            out.append(self._item(row, now))
        for source, url in DEFAULT_FEEDS:
            label = _LABEL.get(source, source)
            n = by_source.get(source, 0)
            self.feed_reports[label] = {
                "status": 200,
                "bozo": 0,
                "entries": n,
                "health": "ok" if n else "quiet",
                "bozo_exception": None,
            }
        return out

    @staticmethod
    def _item(row: dict, now: str) -> NewsItem:
        source = str(row.get("source") or "rss")
        return NewsItem(
            timestamp=now,
            source_type="rss",
            source_name=source,
            title=str(row.get("title") or ""),
            url=str(row.get("link") or ""),
            summary=str(row.get("summary") or ""),
            item_id=str(row.get("id") or ""),
        )
