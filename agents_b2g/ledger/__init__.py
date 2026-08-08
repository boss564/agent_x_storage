"""
B2G Universal Tap-to-Sign Ledger — Multi-Sector NFC/ZK Settlement Engine.

1 Master Agent + 8 Subagents. Kontext-Profile für BAU, HEALTH, SUBSIDY, CUSTOMS, JUSTICE.
3-Sekunden-Workflow: Scan → Verify → Split → Escrow → Archive.

Usage:
    from agents_b2g.ledger import LedgerOrchestrator
    ledger = LedgerOrchestrator(context="BAU")
    result = ledger.process_tap_to_sign(scan_1, scan_2, milestone_id, contract_id)
"""
from agents_b2g.ledger.ledger_orchestrator import (
    LedgerConfig, JSONLogger, LedgerOrchestrator,
    NFCReaderAgent, ZKProofEngineAgent, RoleResolverAgent,
    MilestoneMatcherAgent, LegalConditionAgent, TimerGuardianAgent,
    AtomicSplitterAgent, EscrowRetentionAgent, GoBDArchiverAgent,
)
from agents_b2g.ledger.context_profiles import CONTEXT_PROFILES

__all__ = [
    "LedgerConfig", "JSONLogger", "LedgerOrchestrator", "CONTEXT_PROFILES",
    "NFCReaderAgent", "ZKProofEngineAgent", "RoleResolverAgent",
    "MilestoneMatcherAgent", "LegalConditionAgent", "TimerGuardianAgent",
    "AtomicSplitterAgent", "EscrowRetentionAgent", "GoBDArchiverAgent",
]
