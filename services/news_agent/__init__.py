"""Modular multi-scraper news agent (RSS + announcements)."""

from services.news_agent.models import NewsItem
from services.news_agent.runner import run_once
from services.news_agent.scrapers import load_scrapers

__all__ = ["NewsItem", "load_scrapers", "run_once"]
