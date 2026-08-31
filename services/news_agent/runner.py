"""Load all scrapers, process, write data/news_scores.jsonl.

CRITICAL → Telegram only if NEWS_AGENT_TELEGRAM_CRITICAL=true.
Does not touch the regime-swarm cluster.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import List, Optional

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.news_agent.core.processor import NewsProcessor
from services.news_agent.liveness import (
    derive_quiet_streaks,
    load_run_markers,
    measurement_run_markers,
    run_marker_freshness,
)
from services.news_agent.models import NewsItem
from services.news_agent.scrapers import load_scrapers

DEFAULT_JSONL = "data/news_scores.jsonl"


def jsonl_path() -> Path:
    return Path(os.environ.get("NEWS_AGENT_MULTI_JSONL", DEFAULT_JSONL))


def telegram_critical_enabled() -> bool:
    return os.environ.get("NEWS_AGENT_TELEGRAM_CRITICAL", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def notify_telegram(item: NewsItem) -> None:
    from scripts.raas_alert import send_telegram

    send_telegram(
        "CRITICAL news [{src}] {title}\n{url}\n"
        "assets={assets} score={score}\n"
        "(diagnostic_only, not investment advice)".format(
            src=item.source_name,
            title=item.title,
            url=item.url,
            assets=item.target_assets,
            score=item.sentiment_score,
        )
    )


def collect(scrapers=None) -> tuple[List[NewsItem], List[str], dict]:
    errors: List[str] = []
    items: List[NewsItem] = []
    feeds: dict = {}
    for scraper in scrapers if scrapers is not None else load_scrapers():
        batch = scraper.fetch()
        items.extend(batch)
        feeds.update(getattr(scraper, "feed_reports", {}) or {})
        if getattr(scraper, "last_error", ""):
            errors.append(f"{scraper.source_name}: {scraper.last_error}")
    return items, errors, feeds


def run_once(*, notify=None, scrapers=None) -> dict:
    loaded = scrapers if scrapers is not None else load_scrapers()
    items, errors, feeds = collect(loaded)
    enabled = telegram_critical_enabled()
    processor = NewsProcessor(
        jsonl_path(),
        notify_critical=notify if notify is not None else notify_telegram,
        telegram_enabled=enabled,
    )
    # Prior marker age — before this run appends a fresh mark.
    marker_liveness = run_marker_freshness(processor.jsonl_path)
    result = processor.process(items)
    prior = measurement_run_markers(load_run_markers(processor.jsonl_path))
    streaks = derive_quiet_streaks(prior, feeds)
    marker = processor.write_run_marker(feeds, streaks=streaks)
    result["fetched"] = len(items)
    result["scrapers"] = [s.source_name or s.__class__.__name__ for s in loaded]
    result["feed_errors"] = errors
    result["feeds"] = feeds
    result["streaks"] = streaks
    result["stale"] = [n for n, s in streaks.items() if s.get("stale")]
    result["run_marker"] = marker
    result["marker_liveness"] = marker_liveness
    dead = [n for n, r in feeds.items() if r.get("health") == "dead"]
    if dead and not items:
        result["status"] = "FEED_SILENT"
    elif dead:
        result["status"] = "DEGRADED"
    elif result["stale"] and str(result.get("status", "ok")).lower() == "ok":
        # 72h consecutive quiet — already in streaks; now surfaces in status.
        result["status"] = "DEGRADED"
    elif (
        marker_liveness.get("status") in ("STALE", "UNPARSEABLE")
        and str(result.get("status", "ok")).lower() == "ok"
    ):
        # Prior mark older than NEWS_MARKER_MAX_AGE_H (cold-start MISSING is not this).
        result["status"] = "WRITER_STALE"
    result["preview"] = [
        {
            "title": it.title,
            "source_type": it.source_type,
            "source_name": it.source_name,
            "target_assets": it.target_assets,
            "entities": it.entities,
            "cross_chain_impact": it.cross_chain_impact,
            "impact_level": it.impact_level,
            "sentiment_score": it.sentiment_score,
        }
        for it in items[:5]
    ]
    return result


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Multi-scraper news agent (diagnostic_only)")
    parser.add_argument("--once", action="store_true", default=True)
    parser.add_argument(
        "--gap-report",
        action="store_true",
        help="after ingest, write entity-gap report (not on by default)",
    )
    parser.add_argument("--gap-output", default=None)
    args = parser.parse_args()
    _ = args.once
    result = run_once()
    if args.gap_report:
        from services.news_agent.gap_detector import run_gap_report

        result["gap_report"] = run_gap_report(
            jsonl=jsonl_path(),
            output=Path(args.gap_output) if args.gap_output else None,
        )
        result["gap_report"].pop("report", None)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
