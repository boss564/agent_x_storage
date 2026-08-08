"""
Wave 32: Crypto-Philately & Digital Stamp Protocol.

9 Agenten, 81 Subagenten — Briefmarken als ERC-1155-Token: Mint, Postage Validation,
Cancellation/Postmark, Rarity Classification, Album Management, Secondary Market,
Museum Exhibition, Stamp Staking.

Usage:
    from agents_b2g.philately import PhilatelyOrchestrator
    orch = PhilatelyOrchestrator(user_id='my_tenant')
    result = orch.process_stamp_lifecycle(sender='...', recipient='...', ...)
"""
from agents_b2g.philately.philately_orchestrator import (
    PhilatelyConfig, JSONLogger, PhilatelyOrchestrator,
    StampMintAndIssuanceEngine, MessagePostageValidator,
    CancellationAndPostmarkEngine, RarityAndEditionClassifier,
    PhilatelicAlbumManager, SecondaryMarketTrader,
    MuseumExhibitionCurator, StampStakingVault,
)
from agents_b2g.philately.philately_vault_orchestrator import (
    PhilatelyVaultOrchestrator, VaultConfig as PVaultConfig, StakingVaultManager,
    StampRarityAndValuationEngine, YieldAndAPYOptimizer, StampTokenomicsManager,
    AntiSpamFirewallVault, TradeAndAtomicSwapMonitor, CollectorPortfolioAdvisor,
    PhilatelyComplianceAndAuditGuard,
)
from agents_b2g.philately.governance_circle import (
    GovernanceCircleOrchestrator, GovConfig,
    ProposalLifecycleManager, VotingPowerCalculator, DelegationAndProxyManager,
    AutonomousVoteAdvisor, WhitelistGovernanceAgent, FeeAndProtocolParameterGovernor,
    TreasuryAllocationGovernor, QuorumAndTimelockEnforcer,
)
from agents_b2g.philately.collectors_club import (
    CollectorsClubOrchestrator, ClubConfig,
    TieredGatekeeperAgent, EarlyAccessMintManager, FeeDiscountCalculator,
    LoyaltyNFTMintEngine, ExpirationNotifierAgent, MultiVaultStrategyRouter,
    AutoReStakingCompounder, OnChainReputationTracker,
)
from agents_b2g.philately.collector_vault import (
    VaultCoordinator, VaultConfig,
    IssuerVerificationAgent, QuarantineManagerAgent, BurnAgent,
    AtomicSwapExecutorAgent, OfferAgent, TradeMonitorAgent,
    ProvenanceTrackerAgent, GradingAgent, CertificateGeneratorAgent,
)
__all__ = [
    "PhilatelyConfig", "JSONLogger", "PhilatelyOrchestrator",
    "StampMintAndIssuanceEngine", "MessagePostageValidator",
    "CancellationAndPostmarkEngine", "RarityAndEditionClassifier",
    "PhilatelicAlbumManager", "SecondaryMarketTrader",
    "MuseumExhibitionCurator", "StampStakingVault",
    "VaultCoordinator", "VaultConfig",
    "IssuerVerificationAgent", "QuarantineManagerAgent", "BurnAgent",
    "AtomicSwapExecutorAgent", "OfferAgent", "TradeMonitorAgent",
    "ProvenanceTrackerAgent", "GradingAgent", "CertificateGeneratorAgent",
]
