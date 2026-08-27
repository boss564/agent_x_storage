"""Hybrid shell schemas — untrusted proposal vs trusted envelope.

Charter: DEFENSIVE_CAUSAL_GROUNDING · live_execution=false
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"


@dataclass
class LLMStrategyProposal:
    """Untrusted shell output — never a release decision."""

    proposal_id: str
    label: str
    rebalance_interval_h: float
    max_slippage_pct: float
    latency_budget_ms: float
    profile_hint: str = "default"  # default | aggressive | oracle_stress
    untrusted: bool = True
    source: str = "synthetic_shell"  # not a live LLM claim

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SafetyEnvelope:
    """Trusted core output — Blue/P9 shaped; no investment advice."""

    envelope_id: str
    proposal_id: str
    run_id: Optional[str]
    gate_verdict: str
    audit_verdict: str
    risk_block_rate: float
    countermeasures: List[str] = field(default_factory=list)
    scope: str = SCOPE
    live_execution: bool = False
    not_investment_advice: bool = True  # D1 — layer 1 until ScopeEnforcer
    shell_untrusted: bool = True
    core_verified: bool = True
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
