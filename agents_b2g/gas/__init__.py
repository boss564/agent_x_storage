"""Agent X Gas Module — Autonomous fuel management for 9 agents.

Each agent has a gas balance (tank), consumption rate, minimum reserve,
and an automatic refuel loop from the central gas treasury.
OUT_OF_GAS triggers autonomous pause + emergency refuel.
"""

from .gas_profiles import GasProfile, AGENT_GAS_PROFILES
from .gas_orchestrator import GasOrchestrator

__all__ = ["GasProfile", "AGENT_GAS_PROFILES", "GasOrchestrator"]
