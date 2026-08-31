"""News processor package."""
from services.news_agent.core.processor import NewsProcessor, enrich, impact_level

__all__ = ["NewsProcessor", "enrich", "impact_level"]
