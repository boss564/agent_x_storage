"""SimChain Subagents — 9 agents across 3 chains.

Chain DEPIN_APPCHAIN (High-Freq, Low-Value):
  - S1: SensorAggregatorAgent — 1000 TPS batch proofs
  - S2: BridgeAgent — Cross-chain Merkle proofs + latency
  - S3: DePINWalletAgent — Micro-payout aggregation

Chain SETTLEMENT_L1 (Low-Freq, High-Value):
  - L1: VOBSettlementAgent — VOB/B milestone settlements + Z3
  - L2: LegalComplianceAgent — GoBD archiving + tax computation
  - L3: SettlementExecutorAgent — Multi-split + escrow retention

Chain LIQUIDITY_L2 (Event-Driven, Tokenomics):
  - T1: TokenMinterAgent — Minting with burn mechanics
  - T2: StakingPoolAgent — Lockups + APY distribution
  - T3: BurnFeeAgent — Fee collection + token burns (friction)
"""

from .sensor_aggregator import SensorAggregatorAgent
from .bridge_agent import BridgeAgent
from .depin_wallet import DePINWalletAgent
from .vob_settlement import VOBSettlementAgent
from .legal_compliance import LegalComplianceAgent
from .settlement_executor import SettlementExecutorAgent
from .token_minter import TokenMinterAgent
from .staking_pool import StakingPoolAgent
from .burn_fee_agent import BurnFeeAgent

__all__ = [
    "SensorAggregatorAgent",
    "BridgeAgent",
    "DePINWalletAgent",
    "VOBSettlementAgent",
    "LegalComplianceAgent",
    "SettlementExecutorAgent",
    "TokenMinterAgent",
    "StakingPoolAgent",
    "BurnFeeAgent",
]
