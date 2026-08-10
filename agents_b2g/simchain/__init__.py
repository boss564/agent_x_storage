"""Agent X SimChain — Multi-Chain Economic Simulation (Wave 35).

9 agents across 3 heterogeneous chains:
  - DEPIN_APPCHAIN:  High-frequency sensor data, micro-payouts (S1–S3)
  - SETTLEMENT_L1:   Low-frequency VOB/B settlements, Z3 proofs (L1–L3)
  - LIQUIDITY_L2:    Token minting, staking, burns, fees (T1–T3)

Architecture: Multi-Chain Orchestrator → 9 Subagents → Cross-Chain Bridge.
All agents return standardized JSON, use JSONLogger, try/except + retry,
and support multi-tenancy via user_id.
"""

from .economic_orchestrator_multi import EconomicOrchestratorMulti

__all__ = ["EconomicOrchestratorMulti"]
