"""MultiChain Subchains — 9 Sovereign Appchains across 4 Chain Layers.

Chain DEPIN_APPCHAIN (High-Speed, 1000 TPS):
  A1: SensorAggregatorChain — batch proofs, Merkle root
  A2: BridgeRelayerChain — cross-chain relay, latency simulation
  A3: DePINWalletChain — micro-payout aggregation

Chain SETTLEMENT_L1 (Low-Freq, Z3 Proofs):
  A4: VOBSettlementChain — VOB/B milestone settlements
  A5: LegalComplianceChain — GoBD archiving, tax computation
  A6: SettlementExecutorChain — multi-split, escrow retention

Chain LIQUIDITY_L2 (Event-Driven, Tokenomics):
  A7: TokenMinterChain — mint/burn mechanics
  A8: StakingPoolChain — lockups, APY distribution

Chain IDENTITY_CHAIN (On-Demand, SSI/ZK):
  A9: IdentityComplianceChain — DIDs, verifiable credentials
"""

from .sensor_aggregator import SensorAggregatorChain
from .bridge_relayer import BridgeRelayerChain
from .depin_wallet import DePINWalletChain
from .vob_settlement import VOBSettlementChain
from .legal_compliance import LegalComplianceChain
from .settlement_executor import SettlementExecutorChain
from .token_minter import TokenMinterChain
from .staking_pool import StakingPoolChain
from .identity_compliance import IdentityComplianceChain

__all__ = [
    "SensorAggregatorChain",
    "BridgeRelayerChain",
    "DePINWalletChain",
    "VOBSettlementChain",
    "LegalComplianceChain",
    "SettlementExecutorChain",
    "TokenMinterChain",
    "StakingPoolChain",
    "IdentityComplianceChain",
]
