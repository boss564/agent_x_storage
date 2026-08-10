"""Agent Crew — 5-member internal crew + DID-based forensic attribution.

Crew pipeline: CommsDispatcher → Navigator → TacticalOfficer → GasManager → DecisionEngine
Identity: DIDRegistry (dynamic, demo/production modes, Identity Chain / HSM sync)
Attribution: ForensicStamp → 3-failure revocation → audit log
"""

from .crew import AgentCrew, FLOTTE, demo_crew_pipeline, Action, CrewStatus
from .agents import (
    IoTIngestAgent, MilestoneValidatorAgent, ComplianceAgent,
    EscrowSettlementAgent, AuditComplianceAgent, StakingPoolAgent,
    TreasuryAgent, GovernorAgent, TokenBurnerAgent, create_fleet,
)
from .did_tracker import (
    ForensicStamp, ForensicStampGenerator,
    AttackType, detect_attack_type,
)
from .did_registry import (
    DIDRegistry, DIDStatus, DIDRecord, VerificationResult,
    get_registry, DEMO_DIDS,
)

__all__ = [
    "AgentCrew", "FLOTTE", "demo_crew_pipeline", "Action", "CrewStatus",
    "IoTIngestAgent", "MilestoneValidatorAgent", "ComplianceAgent",
    "EscrowSettlementAgent", "AuditComplianceAgent", "StakingPoolAgent",
    "TreasuryAgent", "GovernorAgent", "TokenBurnerAgent", "create_fleet",
    "DIDRegistry", "DIDStatus", "DIDRecord", "VerificationResult",
    "get_registry", "DEMO_DIDS",
    "ForensicStamp", "ForensicStampGenerator",
    "AttackType", "detect_attack_type",
]
