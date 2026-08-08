# agents_b2g/wallet/__init__.py
"""
Wave 25 — Institutional Smart Wallet & Identity Engine.

ERC-4337 Smart Wallet für Behörden: Multi-Sig-Kassenführung, BHO-Zero-Sum,
eIDAS-Identity, ZK-Privacy, GoBD-Archivierung, Amtsübergabe.
9 Root-Agenten mit 81 Subagenten.
"""
from agents_b2g.wallet.smart_wallet_orchestrator import SmartWalletOrchestrator

__all__ = ["SmartWalletOrchestrator"]
