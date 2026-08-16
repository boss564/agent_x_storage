"""Wirtschaftsagenten: 9 economic agents (Kapital / Ausfuehrung / Governance).

Baustein 1: foundation. Baustein 2: Funktionsschranken + 9 profiles.
Baustein 3: concrete agents + distributed Freigabe/Delegation.
Baustein 4: KlassenResolver + Envelope↔AgentMessage routing.
"""
from agents_b2g.wirtschaft.base import (
    KompetenzKlasse,
    KompetenzProfil,
    StateKeeper,
    GasFrictionMonitor,
    WormLog,
    CryptoModule,
    MessageBus,
    WirtschaftAgent,
)
from agents_b2g.wirtschaft.profiles import Aktion, WIRTSCHAFT_PROFILE, profil_fuer
from agents_b2g.wirtschaft.agents import (
    LiquidityAgent, TreasuryAgent, StakingAgent, MinterAgent, SettlementAgent,
    PaymasterAgent, BurnAgent, RetentionAgent, RiskAuditorAgent,
    AGENT_CLASSES, create_agent,
)
from agents_b2g.wirtschaft.schwarm import WirtschaftsSchwarm, build_schwarm
from agents_b2g.wirtschaft.subagents import ComplianceEngine, PolicyStore
from agents_b2g.wirtschaft.routing_adapter import (
    KlassenResolver, WirtschaftsRouter,
    envelope_to_agent_message, agent_message_to_envelope,
)
from agents_b2g.wirtschaft.emergence_adapter import (
    EmergenceResult, run_simulation_logs, evaluate_emergence,
)

__all__ = [
    "KompetenzKlasse",
    "KompetenzProfil",
    "StateKeeper",
    "GasFrictionMonitor",
    "WormLog",
    "CryptoModule",
    "MessageBus",
    "WirtschaftAgent",
    "Aktion",
    "WIRTSCHAFT_PROFILE",
    "profil_fuer",
    "LiquidityAgent",
    "TreasuryAgent",
    "StakingAgent",
    "MinterAgent",
    "SettlementAgent",
    "PaymasterAgent",
    "BurnAgent",
    "RetentionAgent",
    "RiskAuditorAgent",
    "AGENT_CLASSES",
    "create_agent",
    "WirtschaftsSchwarm",
    "build_schwarm",
    "ComplianceEngine",
    "PolicyStore",
    "KlassenResolver",
    "WirtschaftsRouter",
    "envelope_to_agent_message",
    "agent_message_to_envelope",
    "EmergenceResult",
    "run_simulation_logs",
    "evaluate_emergence",
]
