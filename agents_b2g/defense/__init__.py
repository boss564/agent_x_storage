"""
Wave 28: External Threat Defense & Swarm Immunity.

9 Agenten, 81 Subagenten — Perimeter-Schutz, Schwarm-Erkennung,
Bedrohungsklassifizierung, aktive Gegenmaßnahmen, Honeypot-Fallen,
selbstlernende Abwehr, externe Threat-Intelligence, Defense-Dashboard.

Usage:
    from agents_b2g.defense import DefenseOrchestrator
    orch = DefenseOrchestrator(user_id='my_tenant')
    result = orch.process_external_request(request)
"""

from agents_b2g.defense.swarm_defense_orchestrator import (
    DefenseConfig,
    JSONLogger,
    IPBlacklist,
    DefenseOrchestrator,
    PerimeterGatewayDefender,
    SwarmDetectionRadar,
    ThreatClassifierEngine,
    ActiveResponseCoordinator,
    DeceptionAndHoneypotFactory,
    SwarmLearningAdapter,
    ExternalIntelAggregator,
    DefenseMetricsDashboard,
)

__all__ = [
    "DefenseConfig",
    "JSONLogger",
    "IPBlacklist",
    "DefenseOrchestrator",
    "PerimeterGatewayDefender",
    "SwarmDetectionRadar",
    "ThreatClassifierEngine",
    "ActiveResponseCoordinator",
    "DeceptionAndHoneypotFactory",
    "SwarmLearningAdapter",
    "ExternalIntelAggregator",
    "DefenseMetricsDashboard",
]
