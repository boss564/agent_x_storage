"""NewsItem — unified event for RSS / announcements / social / regulatory."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Literal

from agents_b2g.news.config import empty_entities
from services.news_agent.impact import empty_cross_chain_impact

SourceType = Literal["rss", "announcement", "social", "regulatory"]
ImpactLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]

SCHEMA = "news_agent_multi/v1.2"


@dataclass
class NewsItem:
    timestamp: str
    source_type: SourceType
    source_name: str
    title: str
    url: str
    target_assets: List[str] = field(default_factory=list)
    entities: Dict[str, List[str]] = field(default_factory=empty_entities)
    cross_chain_impact: Dict[str, object] = field(default_factory=empty_cross_chain_impact)
    sentiment_score: float = 0.0
    impact_level: ImpactLevel = "LOW"
    summary: str = ""
    item_id: str = ""
    feed_error: str = ""

    def to_dict(self) -> dict:
        row = asdict(self)
        merged = empty_entities()
        src = row.get("entities") or {}
        for cat in merged:
            merged[cat] = list(src.get(cat) or [])
        row["entities"] = merged
        cci = empty_cross_chain_impact()
        src_cci = row.get("cross_chain_impact") or {}
        cci["bridges"] = list(src_cci.get("bridges") or [])
        cci["affected_chains"] = list(src_cci.get("affected_chains") or [])
        try:
            cci["impact_score"] = float(src_cci.get("impact_score") or 0.0)
        except (TypeError, ValueError):
            cci["impact_score"] = 0.0
        row["cross_chain_impact"] = cci
        row["schema"] = SCHEMA
        row["diagnostic_only"] = True
        row["live_execution"] = False
        row["order_send"] = False
        row["not_investment_advice"] = True
        return row
