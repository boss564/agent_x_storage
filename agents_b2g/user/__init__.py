"""
Agent X — User & Project Management (Wave 9, 9 Agents).

Human-facing layer: BundID authentication, project lifecycle management,
task dispatching, document management, notifications, compliance reports,
data privacy (GDPR), and user feedback collection.

Total Agent X B2G Fleet: 81 agents across 9 waves.
"""
from agents_b2g.user.agents import (
    BundIDProxy,
    RoleMapper,
    SessionManager,
    UserAuthenticatorAgent,
    ProjectManagerAgent,
    TaskDispatcherAgent,
    DocumentManagerAgent,
    NotificationCenterAgent,
    ReportGeneratorAgent,
    ComplianceCheckerAgent,
    DataPrivacyAgent,
    FeedbackCollectorAgent,
    UserSupervisor,
    WAVE_9_AGENTS,
)

__all__ = [
    "BundIDProxy", "RoleMapper", "SessionManager",
    "UserAuthenticatorAgent", "ProjectManagerAgent",
    "TaskDispatcherAgent", "DocumentManagerAgent",
    "NotificationCenterAgent", "ReportGeneratorAgent",
    "ComplianceCheckerAgent", "DataPrivacyAgent",
    "FeedbackCollectorAgent", "UserSupervisor",
    "WAVE_9_AGENTS",
]
