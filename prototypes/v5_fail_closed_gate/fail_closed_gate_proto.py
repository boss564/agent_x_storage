#!/usr/bin/env python3
"""
Fail-Closed Gate Proto — Map §10 simulation (SCREEN only)

Sandbox: prototypes/v5_fail_closed_gate/
Charter: DEFENSIVE_CAUSAL_GROUNDING — no live orders / no Searcher send.

Pipeline (docs/AGENT_SWARM_P9_MAP_v0.md §10):
  Signal (P4/P5/P7) → Exec/Cascade check (P3/P8)
  → Abort: M7 ∨ Z3-cascade ∨ BHO
  → Human gate (default CLOSED)
  → BLOCKED | RELEASED  (RELEASED = Freigabe-Artefakt only)

Usage:
  python3 prototypes/v5_fail_closed_gate/fail_closed_gate_proto.py
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agents_b2g.emergence.kanten_ledger import (  # noqa: E402
    LATENCY_MODE_M7_TRIM,
    LATENCY_N_MIN,
    LedgerBook,
)

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"
BHO_TOL = 0.01
CASCADE_BLOCK = 0.75  # P8-style cascade risk score
EXEC_RISK_BLOCK = 0.80  # P3-style exec risk
SEEDS = (20270701, 20270702, 20270703)


@dataclass
class TradeSignal:
    """Proposed trade / freigabe request — never executed by this proto."""

    signal_id: str
    source: str  # P4 | P5 | P7
    notional_eur: float
    stress_score: float = 0.0
    oracle_ok: bool = True
    scenario_ok: bool = True


@dataclass
class GateInput:
    signal: TradeSignal
    exec_risk: float = 0.0  # P3
    cascade_risk: float = 0.0  # P8
    latency_spike: Optional[float] = None  # None = no M7 probe; float = inject
    bho_delta: float = 0.0
    human_gate_open: bool = False  # default CLOSED


@dataclass
class GateVerdict:
    decision: str  # BLOCKED | RELEASED
    reasons: List[str] = field(default_factory=list)
    checks: Dict[str, Any] = field(default_factory=dict)
    scope: str = SCOPE
    live_execution: bool = False  # always False under Option 1


def _check_m7(latency_spike: Optional[float]) -> Dict[str, Any]:
    """Real trimmed_m7 MAD gate; returns tripped=True if poison rejected."""
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
        tripped = len(poison) > 0 and poison[-1].get("reason") == "mad_gate_reject"
    return {
        "name": "M7",
        "tripped": tripped,
        "poison_events": len(poison),
        "latency_injected": latency_spike,
    }


def _check_z3_cascade(cascade_risk: float) -> Dict[str, Any]:
    """Mock Z3 cascade gate — high cascade score ⇒ unkalkulierbar / BLOCK."""
    tripped = cascade_risk >= CASCADE_BLOCK
    return {
        "name": "Z3_CASCADE",
        "tripped": tripped,
        "cascade_risk": cascade_risk,
        "threshold": CASCADE_BLOCK,
        "note": "mock SMT prognosis — no live z3_solver HTTP in this screen",
    }


def _check_bho(delta: float) -> Dict[str, Any]:
    tripped = abs(delta) > BHO_TOL
    return {
        "name": "BHO",
        "tripped": tripped,
        "delta": delta,
        "tolerance": BHO_TOL,
    }


def _check_p3_p8(exec_risk: float, cascade_risk: float) -> Dict[str, Any]:
    """Execution-Gate layer: risk scores may block before abort triad."""
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

    p38 = _check_p3_p8(inp.exec_risk, inp.cascade_risk)
    checks["p3_p8"] = p38
    if p38["tripped"]:
        if p38["exec_block"]:
            reasons.append("P3_EXEC_RISK")
        if p38["cascade_block"]:
            reasons.append("P8_CASCADE_RISK")

    m7 = _check_m7(inp.latency_spike)
    checks["m7"] = m7
    if m7["tripped"]:
        reasons.append("M7_LATENCY_POISON")

    z3 = _check_z3_cascade(inp.cascade_risk)
    checks["z3"] = z3
    if z3["tripped"] and "P8_CASCADE_RISK" not in reasons:
        reasons.append("Z3_CASCADE_UNSAFE")

    bho = _check_bho(inp.bho_delta)
    checks["bho"] = bho
    if bho["tripped"]:
        reasons.append("BHO_DELTA")

    # Fail-closed: any reason ⇒ BLOCKED
    if reasons:
        return GateVerdict(decision="BLOCKED", reasons=reasons, checks=checks)

    # Human gate default CLOSED
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


def _scenarios() -> List[tuple[str, GateInput, str]]:
    """(name, input, expected_decision) — expected may include reason prefix."""
    base = TradeSignal(
        signal_id="SIG-OK",
        source="P4",
        notional_eur=10_000.0,
        stress_score=0.2,
    )
    return [
        (
            "clean_but_gate_closed",
            GateInput(signal=base, human_gate_open=False),
            "BLOCKED",
        ),
        (
            "clean_human_open",
            GateInput(signal=base, human_gate_open=True),
            "RELEASED",
        ),
        (
            "m7_poison",
            GateInput(
                signal=base,
                human_gate_open=True,
                latency_spike=1e6,
            ),
            "BLOCKED",
        ),
        (
            "z3_cascade",
            GateInput(
                signal=base,
                human_gate_open=True,
                cascade_risk=0.9,
            ),
            "BLOCKED",
        ),
        (
            "bho_break",
            GateInput(
                signal=base,
                human_gate_open=True,
                bho_delta=0.05,
            ),
            "BLOCKED",
        ),
        (
            "p3_exec_risk",
            GateInput(
                signal=base,
                human_gate_open=True,
                exec_risk=0.95,
            ),
            "BLOCKED",
        ),
        (
            "bad_oracle",
            GateInput(
                signal=TradeSignal(
                    signal_id="SIG-BAD",
                    source="P5",
                    notional_eur=1.0,
                    oracle_ok=False,
                ),
                human_gate_open=True,
            ),
            "BLOCKED",
        ),
    ]


def run_screen() -> Dict[str, Any]:
    t0 = time.perf_counter()
    print("Fail-Closed Gate Proto (Map §10)")
    print("=" * 72)
    print(f"scope={SCOPE}  live_execution=FORBIDDEN  seeds={list(SEEDS)}")
    print("-" * 72)

    rows: List[Dict[str, Any]] = []
    n_ok = 0
    for seed in SEEDS:
        for name, inp, expected in _scenarios():
            verdict = evaluate_gate(inp)
            match = verdict.decision == expected
            n_ok += int(match)
            rows.append(
                {
                    "seed": seed,
                    "scenario": name,
                    "expected": expected,
                    "decision": verdict.decision,
                    "reasons": verdict.reasons,
                    "match": match,
                    "live_execution": verdict.live_execution,
                }
            )
            flag = "PASS" if match else "FAIL"
            print(
                f"seed={seed} {name:<22} → {verdict.decision:<8} "
                f"{verdict.reasons} [{flag}]"
            )

    n_total = len(rows)
    elapsed = time.perf_counter() - t0
    all_pass = n_ok == n_total
    # Structural invariants
    no_live = all(not r["live_execution"] for r in rows)
    closed_blocks = all(
        r["decision"] == "BLOCKED"
        for r in rows
        if r["scenario"] == "clean_but_gate_closed"
    )
    release_only_open = all(
        r["decision"] == "RELEASED"
        for r in rows
        if r["scenario"] == "clean_human_open"
    )

    payload = {
        "screen": "fail_closed_gate_v0",
        "scope": SCOPE,
        "map_ref": "docs/AGENT_SWARM_P9_MAP_v0.md §10",
        "elapsed_s": round(elapsed, 3),
        "budget_ok": elapsed < 16.0,
        "n_pass": n_ok,
        "n_total": n_total,
        "verdict": "GATE_PROTO_PASS" if all_pass and no_live else "GATE_PROTO_FAIL",
        "invariants": {
            "no_live_execution": no_live,
            "default_closed_blocks": closed_blocks,
            "human_open_can_release": release_only_open,
        },
        "abort_conditions": ["M7", "Z3_CASCADE", "BHO", "P3_P8", "HUMAN_GATE_CLOSED"],
        "results": rows,
    }

    out = _HERE / "FAIL_CLOSED_GATE_PROTO.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print("-" * 72)
    print(f"VERDICT: {payload['verdict']}  {n_ok}/{n_total}")
    print(f"invariants: {payload['invariants']}")
    print(f"elapsed={elapsed:.3f}s  → {out}")
    return payload


if __name__ == "__main__":
    run_screen()
