"""9-Agent Regime-Drift Schwarm (Baustein 2) — monitoring only."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prototypes.raas_paper_trading.regime_swarm.orchestrator import RegimeSwarmOrchestrator

__all__ = ["RegimeSwarmOrchestrator"]


def __getattr__(name: str):
    if name == "RegimeSwarmOrchestrator":
        from prototypes.raas_paper_trading.regime_swarm.orchestrator import RegimeSwarmOrchestrator

        return RegimeSwarmOrchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
