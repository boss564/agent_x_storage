"""Abstract scraper plugin."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List

from services.news_agent.models import NewsItem


class BaseScraper(ABC):
    """One source. Transport is classified per source; fetch does not abort the run."""

    source_type: str = "rss"
    source_name: str = ""
    enabled: bool = True

    def __init__(self) -> None:
        self.last_error: str = ""
        self.feed_reports: Dict[str, dict] = {}

    @abstractmethod
    def fetch(self) -> List[NewsItem]:
        raise NotImplementedError
