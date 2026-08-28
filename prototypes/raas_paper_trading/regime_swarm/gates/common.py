"""Shared helpers for infrastructure gate adapters (monitoring charter)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from services.fail_closed_gate.gate_core import GateVerdict

# Reasons that veto the swarm cycle before A3–A8 (distinct from HUMAN_GATE_CLOSED).
INFRA_BLOCK_REASONS = frozenset(
    {
        "SIGNAL_INVALID",
        "P3_EXEC_RISK",
        "P8_CASCADE_RISK",
        "Z3_CASCADE_UNSAFE",
        "M7_LATENCY_POISON",
        "BHO_DELTA",
    }
)


def infra_verdict_passed(verdict: GateVerdict) -> bool:
    """True when evaluate_gate() found no infrastructure fault (human latch may still be closed)."""
    return not any(reason in INFRA_BLOCK_REASONS for reason in verdict.reasons)


@dataclass
class InfraGateResult:
    passed: bool
    agent: str
    message: str
    gate_verdict: Dict[str, Any] = field(default_factory=dict)
    infra_reasons: List[str] = field(default_factory=list)

    def to_audit_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "passed": self.passed,
            "message": self.message,
            "gate_verdict": self.gate_verdict,
            "infra_reasons": self.infra_reasons,
        }
