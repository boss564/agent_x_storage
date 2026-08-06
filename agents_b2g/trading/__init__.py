# agents_b2g/trading/__init__.py
"""
Wave 24 — Trading Infrastructure: DEX Routing, MEV Protection & Market Making.

9 Root-Agenten mit 81 Subagenten für vollständige Handelsinfrastruktur.
"""
from agents_b2g.trading.token_trading_orchestrator import TokenTradingOrchestrator

__all__ = ["TokenTradingOrchestrator"]
