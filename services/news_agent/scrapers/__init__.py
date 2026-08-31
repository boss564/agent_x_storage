"""Discover BaseScraper plugins in this package."""
from __future__ import annotations

import importlib
import pkgutil
from typing import List, Type

from services.news_agent.scrapers.base_scraper import BaseScraper


def iter_scraper_classes() -> List[Type[BaseScraper]]:
    import services.news_agent.scrapers as pkg

    found: List[Type[BaseScraper]] = []
    for info in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + "."):
        if info.name.rsplit(".", 1)[-1] in ("base_scraper",):
            continue
        module = importlib.import_module(info.name)
        for value in vars(module).values():
            if (
                isinstance(value, type)
                and issubclass(value, BaseScraper)
                and value is not BaseScraper
            ):
                found.append(value)
    return found


def load_scrapers(*, enabled_only: bool = True) -> List[BaseScraper]:
    instances: List[BaseScraper] = []
    for cls in iter_scraper_classes():
        if enabled_only and not getattr(cls, "enabled", True):
            continue
        instances.append(cls())
    return instances
