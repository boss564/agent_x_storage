"""Isolated News-Agent (Stufe 2) — RSS + keyword sentiment → JSONL."""

from agents_b2g.news.agent import NewsAgent, append_score, default_jsonl_path
from agents_b2g.news.scraper import DEFAULT_FEEDS, fetch_news, parse_rss_xml
from agents_b2g.news.sentiment import (
    classify_coin,
    detect_assets,
    detect_entities,
    is_relevant,
    score_sentiment,
)

__all__ = [
    "NewsAgent",
    "append_score",
    "default_jsonl_path",
    "DEFAULT_FEEDS",
    "fetch_news",
    "parse_rss_xml",
    "score_sentiment",
    "classify_coin",
    "is_relevant",
    "detect_assets",
    "detect_entities",
]
