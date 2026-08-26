"""Fail-closed gate core — Map §10 (no live execution).

Shared by HTTP service and prototypes/v5_fail_closed_gate screen.
Scope: DEFENSIVE_CAUSAL_GROUNDING
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agents_b2g.emergence.kanten_ledger import (
    LATENCY_MODE_M7_TRIM,
    LATENCY_N_MIN,
    LedgerBook,
)

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"
BHO_TOL = 0.01
CASCADE_BLOCK = 0.75
EXEC_RISK_BLOCK = 0.80


@dataclass
class TradeSignal:
    signal_id: str
    source: str
    notional_eur: float
    stress_score: float = 0.0
    oracle_ok: bool = True
    scenario_ok: bool = True


@dataclass
class GateInput:
    signal: TradeSignal
    exec_risk: float = 0.0
    cascade_risk: float = 0.0
    latency_spike: Optional[float] = None
    bho_delta: float = 0.0
    human_gate_open: bool = False


@dataclass
class GateVerdict:
    decision: str
    reasons: List[str] = field(default_factory=list)
    checks: Dict[str, Any] = field(default_factory=dict)
    scope: str = SCOPE
    live_execution: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision,
            "reasons": self.reasons,
            "checks": self.checks,
            "scope": self.scope,
            "live_execution": self.live_execution,
        }


def check_m7(latency_spike: Optional[float]) -> Dict[str, Any]:
    poison: List[dict] = []
    book = LedgerBook(
        latency_mode=LATENCY_MODE_M7_TRIM,
        on_latency_poison=poison.append,
    )
    for t in range(LATENCY_N_MIN):
        book.update("P2", "P3", t, success=True, signed_net=1.0, latency=1.0)
    tripped = False
    if latency_spike is not None:
        book.update(
            "P2",
            "P3",
            LATENCY_N_MIN,
            success=True,
            signed_net=1.0,
            latency=float(latency_spike),
        )
        tripped = bool(poison) and poison[-1].get("reason") == "mad_gate_reject"
    return {
        "name": "M7",
        "tripped": tripped,
        "poison_events": len(poison),
        "latency_injected": latency_spike,
    }


def check_z3_cascade(cascade_risk: float) -> Dict[str, Any]:
    tripped = cascade_risk >= CASCADE_BLOCK
    return {
        "name": "Z3_CASCADE",
        "tripped": tripped,
        "cascade_risk": cascade_risk,
        "threshold": CASCADE_BLOCK,
        "note": "score gate; optional HTTP to infra-z3 is additive later",
    }


def check_bho(delta: float) -> Dict[str, Any]:
    tripped = abs(delta) > BHO_TOL
    return {
        "name": "BHO",
        "tripped": tripped,
        "delta": delta,
        "tolerance": BHO_TOL,
    }


def check_p3_p8(exec_risk: float, cascade_risk: float) -> Dict[str, Any]:
    exec_trip = exec_risk >= EXEC_RISK_BLOCK
    casc_trip = cascade_risk >= CASCADE_BLOCK
    return {
        "name": "P3_P8_RISK",
        "tripped": exec_trip or casc_trip,
        "exec_risk": exec_risk,
        "cascade_risk": cascade_risk,
        "exec_block": exec_trip,
        "cascade_block": casc_trip,
    }


def evaluate_gate(inp: GateInput) -> GateVerdict:
    reasons: List[str] = []
    checks: Dict[str, Any] = {
        "signal": {
            "id": inp.signal.signal_id,
            "source": inp.signal.source,
            "oracle_ok": inp.signal.oracle_ok,
            "scenario_ok": inp.signal.scenario_ok,
            "stress_score": inp.signal.stress_score,
        },
        "human_gate_open": inp.human_gate_open,
        "charter_scope": SCOPE,
    }

    if not inp.signal.oracle_ok or not inp.signal.scenario_ok:
        reasons.append("SIGNAL_INVALID")

    p38 = check_p3_p8(inp.exec_risk, inp.cascade_risk)
    checks["p3_p8"] = p38
    if p38["tripped"]:
        if p38["exec_block"]:
            reasons.append("P3_EXEC_RISK")
        if p38["cascade_block"]:
            reasons.append("P8_CASCADE_RISK")

    m7 = check_m7(inp.latency_spike)
    checks["m7"] = m7
    if m7["tripped"]:
        reasons.append("M7_LATENCY_POISON")

    z3 = check_z3_cascade(inp.cascade_risk)
    checks["z3"] = z3
    if z3["tripped"] and "P8_CASCADE_RISK" not in reasons:
        reasons.append("Z3_CASCADE_UNSAFE")

    bho = check_bho(inp.bho_delta)
    checks["bho"] = bho
    if bho["tripped"]:
        reasons.append("BHO_DELTA")

    if reasons:
        return GateVerdict(decision="BLOCKED", reasons=reasons, checks=checks)

    if not inp.human_gate_open:
        return GateVerdict(
            decision="BLOCKED",
            reasons=["HUMAN_GATE_CLOSED"],
            checks=checks,
        )

    return GateVerdict(
        decision="RELEASED",
        reasons=["HUMAN_GATE_OPEN", "ALL_CHECKS_PASS"],
        checks=checks,
    )
