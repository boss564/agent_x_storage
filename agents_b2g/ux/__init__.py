"""
Wave 31: Omnichannel UX & Verwaltungs-Dashboard.

9 Agenten, 81 Subagenten — Rollenbasierte Dashboards, Responsive Web (Mobile/Tablet/Desktop),
Sprach-Assistent mit Intent-Erkennung, Workflow-Visualisierung, Real-Time-Analytics,
Sandbox-Simulationen, Smart Alerts und GoBD-Berichte.

Usage:
    from agents_b2g.ux import UXOrchestrator
    ux = UXOrchestrator(user_id='my_tenant')
    ux.login(user_id='kaemmerer', role='KAEMMERER', device='desktop', language='de')
    result = ux.render_dashboard()
"""

from agents_b2g.ux.ux_orchestrator import (
    UXConfig, JSONLogger, UXOrchestrator,
    RoleBasedDashboardComposer, ResponsiveWebPortal,
    NaturalLanguageAssistant, ProcessWorkflowVisualizer,
    RealTimeAnalyticsHub, SandboxSimulationPlayer,
    SmartAlertAndNotification, GoBDReportGenerator,
    SessionStateManager,
)

__all__ = [
    "UXConfig", "JSONLogger", "UXOrchestrator",
    "RoleBasedDashboardComposer", "ResponsiveWebPortal",
    "NaturalLanguageAssistant", "ProcessWorkflowVisualizer",
    "RealTimeAnalyticsHub", "SandboxSimulationPlayer",
    "SmartAlertAndNotification", "GoBDReportGenerator",
    "SessionStateManager",
]
