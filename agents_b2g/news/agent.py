"""Isolated News-Agent: RSS → keyword sentiment → JSONL.

Charter: diagnostic_only · live_execution=false · no order send.
Does not patch the regime-swarm daemon or Helm chart.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from agents_b2g.news.scraper import DEFAULT_FEEDS, fetch_news, parse_rss_xml
from agents_b2g.news.sentiment import is_relevant, score_sentiment
from services.news_agent.impact import compute_cross_chain_impact

SCHEMA = "news_agent_score/v1.3"
GENESIS = "0" * 64
DEFAULT_JSONL = "logs/audit/news_scores.jsonl"


def default_jsonl_path() -> Path:
    return Path(os.environ.get("NEWS_AGENT_JSONL", DEFAULT_JSONL))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _last_hash(path: Path) -> str:
    if not path.is_file():
        return GENESIS
    last = ""
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                last = line
    if not last:
        return GENESIS
    try:
        return str(json.loads(last).get("hash") or GENESIS)
    except json.JSONDecodeError:
        return GENESIS


def load_seen_ids(path: Path) -> Set[str]:
    seen: Set[str] = set()
    if not path.is_file():
        return seen
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = row.get("item_id") or row.get("id")
            if item:
                seen.add(str(item))
    return seen


def append_score(path: Path, record: Dict[str, Any]) -> Dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if record.get("live_execution") is True or record.get("order_send") is True:
        raise RuntimeError("order_send_forbidden: news JSONL is diagnostic_only")
    prev = _last_hash(path)
    row = {
        **record,
        "schema": SCHEMA,
        "ts": record.get("ts") or _now(),
        "diagnostic_only": True,
        "live_execution": False,
        "order_send": False,
        "not_investment_advice": True,
        "prev_hash": prev,
    }
    payload = json.dumps(
        {k: v for k, v in row.items() if k != "hash"},
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha256((prev + payload).encode("utf-8")).hexdigest()
    row["hash"] = digest
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, default=str) + "\n")
    return row


class NewsAgent:
    def __init__(
        self,
        *,
        jsonl_path: Optional[Path] = None,
        feeds: Optional[Sequence[tuple]] = None,
        relevant_only: bool = True,
    ) -> None:
        self.jsonl_path = jsonl_path or default_jsonl_path()
        self.feeds = list(feeds or DEFAULT_FEEDS)
        self.relevant_only = relevant_only

    def ingest_items(self, items: Iterable[Dict[str, str]]) -> Dict[str, Any]:
        seen = load_seen_ids(self.jsonl_path)
        written = 0
        skipped_seen = 0
        skipped_irrelevant = 0
        last: Optional[Dict[str, Any]] = None
        for item in items:
            iid = str(item.get("id") or "")
            if not iid:
                continue
            if iid in seen:
                skipped_seen += 1
                continue
            title = str(item.get("title") or "")
            summary = str(item.get("summary") or "")
            if self.relevant_only and not is_relevant(title, summary):
                skipped_irrelevant += 1
                continue
            scored = score_sentiment(title, summary)
            row = append_score(
                self.jsonl_path,
                {
                    "item_id": iid,
                    "source": item.get("source") or "",
                    "title": title,
                    "link": item.get("link") or "",
                    "summary": summary,
                    "sentiment": scored["sentiment"],
                    "label": scored["label"],
                    "confidence": scored["confidence"],
                    "reason": scored["reason"],
                    "symbols": scored["symbols"],
                    "assets": scored["assets"],
                    "entities": scored["entities"],
                    "cross_chain_impact": compute_cross_chain_impact(scored["entities"]),
                    "scorer": "keyword_v1",
                },
            )
            seen.add(iid)
            written += 1
            last = row
        return {
            "status": "ok",
            "path": str(self.jsonl_path),
            "written": written,
            "skipped_seen": skipped_seen,
            "skipped_irrelevant": skipped_irrelevant,
            "last_label": None if last is None else last.get("label"),
        }

    def ingest_xml(self, xml_text: str, *, source: str) -> Dict[str, Any]:
        return self.ingest_items(parse_rss_xml(xml_text, source=source))

    def run_once(self, *, timeout_s: float = 15.0) -> Dict[str, Any]:
        items, feed_errors = fetch_news(self.feeds, timeout_s=timeout_s)
        result = self.ingest_items(items)
        result["fetched"] = len(items)
        result["feed_errors"] = feed_errors
        preview = []
        for item in items[:5]:
            scored = score_sentiment(str(item.get("title") or ""), str(item.get("summary") or ""))
            preview.append(
                {
                    "title": item.get("title") or "",
                    "sentiment": scored["sentiment"],
                    "assets": scored["assets"],
                    "entities": scored["entities"],
                }
            )
        result["preview"] = preview
        if feed_errors and not items:
            result["status"] = "FEED_SILENT"
        elif feed_errors:
            result["status"] = "DEGRADED"
        return result
