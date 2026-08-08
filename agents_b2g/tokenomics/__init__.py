# agents_b2g/tokenomics/__init__.py
"""
Wave 23 — Token Creation, Governance & Launch Engine (Design-Time).
Wave 29 — Token Runtime Operations & Live Mechanics (Run-Time).

Vollständiger Lebenszyklus: Tokenomics-Modellierung, ERC-20-Deployment,
Vesting-Tresore, DEX-Liquiditäts-Pools, DAO-Governance, MiCAR/SEC-Compliance,
Airdrop-Systeme, IPFS-Metadaten, Launch-Orchestrierung (Wave 23).
Laufender Betrieb: Compute-Abrechnung, Slashing, Priority-Queue, Dispute-Bonds,
Buyback/Burn, Live-Staking-Yields, Oracle-Entlohnung, ERP-Quota (Wave 29).
18 Root-Agenten mit 162 Subagenten.
"""
from agents_b2g.tokenomics.token_launch_orchestrator import TokenLaunchOrchestrator
from agents_b2g.tokenomics.token_runtime_orchestrator import TokenRuntimeOrchestrator, TokenRuntimeConfig

__all__ = ["TokenLaunchOrchestrator", "TokenRuntimeOrchestrator", "TokenRuntimeConfig"]
