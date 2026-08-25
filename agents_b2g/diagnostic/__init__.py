"""
Wave 38 — Causal Audit & Signal Guard (Bridge Filter Diagnostic lineage)

Post-V3_PERSISTENZ: operational causal audit with 9×9 subagent target.
Contract-first: DiagnosticSignalEnvelope (Agent 9) defined before upstream stages.

Agents (target 9×9):
  1–5 Data capture plane
  6–8 Analysis plane (CTE, resampling, Pre-Reg/FDR)
  9. GatekeeperDispatcherAgent — RELEASED/BLOCKED envelope

Bridge study confirmatory: agents_b2g/diagnostic/confirmatory.py (read-only series)
Pre-reg (study): docs/BRIDGE_DIAGNOSTIC_PREREG.md
Spec: docs/WAVE38_DIAGNOSTIC_SPEC.md
"""

from agents_b2g.diagnostic.agents import DiagnosticSupervisor
from agents_b2g.diagnostic.diagnostic_orchestrator import DiagnosticPipelineOrchestrator
from agents_b2g.diagnostic.data_ingestion_agent import DataIngestionAgent
from agents_b2g.diagnostic.gatekeeper_dispatcher_agent import GatekeeperDispatcherAgent
from agents_b2g.diagnostic.intent_and_stablecoin_agent import IntentAndStablecoinAgent
from agents_b2g.diagnostic.liquidation_cascade_agent import LiquidationCascadeAgent
from agents_b2g.diagnostic.mev_capture_agent import MEVCaptureAgent
from agents_b2g.diagnostic.oracle_signal_agent import OracleSignalAgent
from agents_b2g.diagnostic.resampling_invariance_agent import ResamplingInvarianceAgent
from agents_b2g.diagnostic.subagents.diagnostic_report_composer import (
    DiagnosticReportComposer,
)
from agents_b2g.diagnostic.wave38_analysis_pipeline import Wave38AnalysisPipeline
from agents_b2g.diagnostic.wave38_capture_pipeline import Wave38CaptureToCTEPipeline
from agents_b2g.diagnostic.wave38_full_pipeline import Wave38FullPipeline
from agents_b2g.diagnostic.wave38_live_pipeline import Wave38LivePipeline

__all__ = [
    "DataIngestionAgent",
    "IntentAndStablecoinAgent",
    "LiquidationCascadeAgent",
    "MEVCaptureAgent",
    "OracleSignalAgent",
    "DiagnosticPipelineOrchestrator",
    "DiagnosticSupervisor",
    "DiagnosticReportComposer",
    "GatekeeperDispatcherAgent",
    "ResamplingInvarianceAgent",
    "Wave38AnalysisPipeline",
    "Wave38CaptureToCTEPipeline",
    "Wave38FullPipeline",
    "Wave38LivePipeline",
]
