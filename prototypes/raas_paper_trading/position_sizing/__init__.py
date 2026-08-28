"""B0–B8 position sizing sub-swarm — boundary diagnostics only (charter §4)."""

from __future__ import annotations

from prototypes.raas_paper_trading.position_sizing.config import position_sizing_enabled
from prototypes.raas_paper_trading.position_sizing.orchestrator import (
    PositionSizingOrchestrator,
)

__all__ = [
    "PositionSizingOrchestrator",
    "position_sizing_enabled",
]
