"""Score, multi-asset tags, impact, JSONL dedup."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, List, Optional, Set

from agents_b2g.news.config import empty_entities
from agents_b2g.news.sentiment import score_sentiment
from services.news_agent.impact import compute_cross_chain_impact
from services.news_agent.models import NewsItem
from src.ingestion.news_jsonl_loader import iter_jsonl_store

CRITICAL_MARKERS = (
    "hack",
    "exploit",
    "insolvent",
    "rug pull",
    "delist",
    "suspended",
    "security incident",
    "sec charges",
)

NotifyFn = Callable[[NewsItem], None]


def impact_level(title: str, summary: str, *, sentiment: int, confidence: float) -> str:
    blob = f"{title} {summary}".lower()
    critical_hit = any(m in blob for m in CRITICAL_MARKERS)
    if critical_hit and confidence >= 0.7 and sentiment != 0:
        return "CRITICAL"
    if confidence > 0.7 and sentiment in (1, -1):
        return "HIGH"
    if confidence > 0.4 or sentiment != 0:
        return "MEDIUM"
    return "LOW"


def enrich(item: NewsItem) -> NewsItem:
    scored = score_sentiment(item.title, item.summary)
    sentiment = int(scored["sentiment"])
    confidence = float(scored["confidence"])
    item.target_assets = list(scored.get("assets") or [])
    item.entities = dict(scored.get("entities") or empty_entities())
    item.cross_chain_impact = compute_cross_chain_impact(item.entities)
    item.sentiment_score = round(sentiment * confidence, 4)
    item.impact_level = impact_level(
        item.title, item.summary, sentiment=sentiment, confidence=confidence
    )
    return item


def load_seen(path: Path) -> Set[str]:
    """Dedup keys across active JSONL and logrotate archives (read-only)."""
    seen: Set[str] = set()
    for row in iter_jsonl_store(path):
        if row.get("source_type") == "run_marker":
            continue
        for key in ("item_id", "url"):
            val = row.get(key)
            if val:
                seen.add(str(val))
    return seen


def append_jsonl(path: Path, item: NewsItem) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    row = item.to_dict()
    if row.get("live_execution") is True or row.get("order_send") is True:
        raise RuntimeError("order_send_forbidden: news JSONL is diagnostic_only")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, default=str) + "\n")


def append_run_marker(path: Path, feeds: dict, *, streaks: Optional[dict] = None) -> dict:
    import json

    from services.news_agent.liveness import run_marker_record

    path.parent.mkdir(parents=True, exist_ok=True)
    row = run_marker_record(feeds, streaks=streaks)
    if row.get("live_execution") is True or row.get("order_send") is True:
        raise RuntimeError("order_send_forbidden: news JSONL is diagnostic_only")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, default=str) + "\n")
    return row


class NewsProcessor:
    def __init__(
        self,
        jsonl_path: Path,
        *,
        notify_critical: Optional[NotifyFn] = None,
        telegram_enabled: bool = False,
    ) -> None:
        self.jsonl_path = jsonl_path
        self.notify_critical = notify_critical
        self.telegram_enabled = telegram_enabled

    def process(self, items: Iterable[NewsItem]) -> dict:
        seen = load_seen(self.jsonl_path)
        written = 0
        skipped_seen = 0
        critical = 0
        alerts = 0
        last: Optional[NewsItem] = None
        for raw in items:
            if raw.source_type == "run_marker":
                continue
            key = raw.item_id or raw.url
            if not key:
                continue
            item = enrich(raw)
            if key in seen or (raw.url and raw.url in seen):
                skipped_seen += 1
                continue
            append_jsonl(self.jsonl_path, item)
            seen.add(key)
            if item.url:
                seen.add(item.url)
            written += 1
            last = item
            if item.impact_level == "CRITICAL":
                critical += 1
                if self.telegram_enabled and self.notify_critical is not None:
                    self.notify_critical(item)
                    alerts += 1
        return {
            "status": "ok",
            "path": str(self.jsonl_path),
            "written": written,
            "skipped_seen": skipped_seen,
            "critical": critical,
            "alerts": alerts,
            "last_impact": None if last is None else last.impact_level,
        }

    def write_run_marker(self, feeds: dict, *, streaks: Optional[dict] = None) -> dict:
        return append_run_marker(self.jsonl_path, feeds, streaks=streaks)
