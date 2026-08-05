# agents_b2g/macro/subagents/__init__.py
"""
Wave 17 Subagents — Makroökonomische Analyse-Module (8/8 implementiert)

  ✅ Agent 2  VelocityOfMoneyTrackerSubagent
  ✅ Agent 3  ProgrammableStimulusEngineSubagent
  ✅ Agent 4  RealTimeTaxSplitterSubagent
  ✅ Agent 5  CapitalEfficiencyAnalyzerSubagent
  ✅ Agent 6  SupplyChainMultiplierCalcSubagent
  ✅ Agent 7  SystemicRiskAndCartelMonitorSubagent
  ✅ Agent 8  RealTimeInflationOracleSubagent
  ✅ Agent 9  CentralBankLedgerTwinSubagent
"""
from agents_b2g.macro.subagents.velocity_of_money_tracker import VelocityOfMoneyTrackerSubagent
from agents_b2g.macro.subagents.programmable_stimulus_engine import ProgrammableStimulusEngineSubagent
from agents_b2g.macro.subagents.real_time_tax_splitter import RealTimeTaxSplitterSubagent
from agents_b2g.macro.subagents.capital_efficiency_analyzer import CapitalEfficiencyAnalyzerSubagent
from agents_b2g.macro.subagents.supply_chain_multiplier_calc import SupplyChainMultiplierCalcSubagent
from agents_b2g.macro.subagents.systemic_risk_and_cartel_monitor import SystemicRiskAndCartelMonitorSubagent
from agents_b2g.macro.subagents.real_time_inflation_oracle import RealTimeInflationOracleSubagent
from agents_b2g.macro.subagents.central_bank_ledger_twin import CentralBankLedgerTwinSubagent

__all__ = [
    "VelocityOfMoneyTrackerSubagent",
    "ProgrammableStimulusEngineSubagent",
    "RealTimeTaxSplitterSubagent",
    "CapitalEfficiencyAnalyzerSubagent",
    "SupplyChainMultiplierCalcSubagent",
    "SystemicRiskAndCartelMonitorSubagent",
    "RealTimeInflationOracleSubagent",
    "CentralBankLedgerTwinSubagent",
]
