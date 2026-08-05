"""
Agent X — Operations, Maintenance & Production Readiness (Waves 7 + 8, 18 Agents).

Wave 7 (agents.py) — System-level monitoring, self-healing, operational control.
Wave 8 (pilot_agents.py) — GoBD export, authority API, notifications,
    compliance reports, multi-tenant isolation, simulation testing,
    live WebSocket dashboard.

Total Agent X Fleet: 72 agents across 8 waves.
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
]
