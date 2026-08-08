"""
Wave 27: Binnenmarkt-Clearing & Settlement Engine.

9 Agenten, 81 Subagenten — multilaterales Netting (100 TXs → 1 Netto-Zahlung),
BHO-Zero-Sum-Verifikation, GoBD-WORM-Archivierung, Fiat-Gateway-Synchronisation.

Usage:
    from agents_b2g.clearing import SettlementOrchestrator
    orch = SettlementOrchestrator(user_id='my_tenant')
    result = orch.process_monthly_settlement(transactions, year=2026, month=8)
"""

from agents_b2g.clearing.clearing_settlement_orchestrator import (
    ClearingConfig,
    JSONLogger,
    SettlementOrchestrator,
    TransactionAccumulator,
    BilateralNettingEngine,
    MultilateralNettingAggregator,
    SettlementPriorityQueue,
    FinalSettlementDispatcher,
    SettlementVerificationOracle,
    FiatGatewaySynchronizer,
    NettingEfficiencyTracker,
    SettlementAuditArchiver,
)

__all__ = [
    "ClearingConfig",
    "JSONLogger",
    "SettlementOrchestrator",
    "TransactionAccumulator",
    "BilateralNettingEngine",
    "MultilateralNettingAggregator",
    "SettlementPriorityQueue",
    "FinalSettlementDispatcher",
    "SettlementVerificationOracle",
    "FiatGatewaySynchronizer",
    "NettingEfficiencyTracker",
    "SettlementAuditArchiver",
]
