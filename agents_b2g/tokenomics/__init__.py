# agents_b2g/tokenomics/__init__.py
"""
Wave 23 — Token Creation, Governance & Launch Engine.

Vollständiger Lebenszyklus: Tokenomics-Modellierung, ERC-20-Deployment,
Vesting-Tresore, DEX-Liquiditäts-Pools, DAO-Governance, MiCAR/SEC-Compliance,
Airdrop-Systeme, IPFS-Metadaten, Launch-Orchestrierung.
9 Root-Agenten mit 81 Subagenten.
"""
from agents_b2g.tokenomics.token_launch_orchestrator import TokenLaunchOrchestrator

__all__ = ["TokenLaunchOrchestrator"]
