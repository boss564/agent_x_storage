"""Agent X MultiChain — Sovereign Appchain Ecosystem (Wave 36).

9 Sovereign Appchains across 4 specialized Chain Layers:
  DEPIN_APPCHAIN (High-Speed/Low-Cost): A1 Sensor, A2 Bridge, A3 Wallet
  SETTLEMENT_L1  (Legal & Z3):         A4 VOB, A5 Legal, A6 Executor
  LIQUIDITY_L2   (Tokenomics):          A7 Minter, A8 Staking
  IDENTITY_CHAIN (SSI & ZK):           A9 Identity & Compliance

Each chain is a sovereign appchain with its own:
  - Block height & state root
  - Mempool for pending transactions
  - Consensus interval (TPS, weekly, event-driven)
  - Cross-chain communication via Merkle proofs

Architecture: ChainOrchestrator → 4 Layers → 9 Appchains → 27 Subagents.
"""

from .chain_orchestrator import ChainOrchestrator
from .bridge_protocol import BridgeProtocol

__all__ = ["ChainOrchestrator", "BridgeProtocol"]
