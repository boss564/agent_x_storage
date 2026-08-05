# agents_b2g/macro/__init__.py
"""
Wave 17 — MacroEconomy Engine (9 Agents)

Programmierbare Volkswirtschaft: Closed-Loop-Makroanalyse für das
Agent-X-Ökosystem. Misst Geldumlauf, Inflation, Kapital-Effizienz,
Lieferketten-Multiplikatoren und systemische Risiken in Echtzeit.

Agenten:
  1. MacroEconomyOrchestrator        — Root: Scheduler, Aggregation, Alarm-Dispatcher
  2. VelocityOfMoneyTracker          — Umlaufgeschwindigkeit (V = PT/M)
  3. ProgrammableStimulusEngine      — Fiskalische Impulse, Konditional-Transfers
  4. RealTimeTaxSplitter             — Echtzeit-Steuerabzug (USt, GewSt, ESt)
  5. CapitalEfficiencyAnalyzer       — ROIC, Kapitalbindung, Working Capital
  6. SupplyChainMultiplierCalc       — Multiplikator-Effekte entlang Lieferketten
  7. SystemicRiskAndCartelMonitor    — Graphentheorie: Kartell- & Monopolerkennung
  8. RealTimeInflationOracle         — Preisindex aus GAEB-Einheitspreisen
  9. CentralBankLedgerTwin           — Digitaler Zwilling der Zentralbank-Bilanz
"""

from agents_b2g.macro.macro_economy_orchestrator import MacroEconomyOrchestrator

__all__ = [
    "MacroEconomyOrchestrator",
]
