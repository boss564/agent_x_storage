"""Agent X Demo — 9-Agent Pitch Pipeline with Differentiated Transform Profiles.

3 Acts × 3 Agents = 27 Subagents. Each agent applies its own fee,
retention, and burn rates — creating visibly different numbers at every step.

Modules:
  transform_profiles: 9 agent profiles with individual rates
  demo_orchestrator:  9-agent pipeline runner with table/JSON export
"""

from .demo_orchestrator import DemoOrchestrator, DemoReport, AgentStep
from .transform_profiles import PROFILES, TransformProfile, get_profile, get_act

__all__ = [
    "DemoOrchestrator",
    "DemoReport",
    "AgentStep",
    "PROFILES",
    "TransformProfile",
    "get_profile",
    "get_act",
]
