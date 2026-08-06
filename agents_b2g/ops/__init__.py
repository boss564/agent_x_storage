"""
Agent X — Operations, Maintenance & Production Readiness (Waves 7 + 8 + 22, 27 Agents).

Wave 7 (agents.py) — System-level monitoring, self-healing, operational control.
Wave 8 (pilot_agents.py) — GoBD export, authority API, notifications,
    compliance reports, multi-tenant isolation, simulation testing,
    live WebSocket dashboard.
Wave 22 (relay_orchestrator.py) — Secure Relay, Gas-Optimierung, Nonce-Management,
    Meta-Transaktionen, Autotasks, Webhook-Integration, Deployment-Verifikation,
    Multi-Sig-gesteuerte Deployments.

Total Agent X Fleet: 162 agents across 18 waves.
"""
from agents_b2g.ops.agents import (
    OrchestratorAgent,
    HealthCheckAgent,
    LogAggregatorAgent,
    MetricsCollectorAgent,
    AlertingAgent,
    DeadLetterHandlerAgent,
    ConfigManagerAgent,
    BackupAgent,
    SelfHealingAgent,
    OpsSupervisor,
)
from agents_b2g.ops.pilot_agents import (
    CircuitBreaker,
    OpsHealthAgent,
    DeadLetterRecoveryAgent,
    AuditExporterAgent,
    TenderAPIGatewayAgent,
    UserNotificationAgent,
    ComplianceReportAgent,
    MultiTenantIsolatorAgent,
    SimulationTestAgent,
    PilotDashboardAgent,
    PilotSupervisor,
    ALL_AGENTS,
)
from agents_b2g.ops.relay_orchestrator import RelayOrchestrator

__all__ = [
    # Wave 7
    "OrchestratorAgent", "HealthCheckAgent", "LogAggregatorAgent",
    "MetricsCollectorAgent", "AlertingAgent", "DeadLetterHandlerAgent",
    "ConfigManagerAgent", "BackupAgent", "SelfHealingAgent", "OpsSupervisor",
    # Wave 8
    "CircuitBreaker", "OpsHealthAgent", "DeadLetterRecoveryAgent",
    "AuditExporterAgent", "TenderAPIGatewayAgent", "UserNotificationAgent",
    "ComplianceReportAgent", "MultiTenantIsolatorAgent",
    "SimulationTestAgent", "PilotDashboardAgent", "PilotSupervisor",
    "ALL_AGENTS",
    # Wave 22
    "RelayOrchestrator",
]
