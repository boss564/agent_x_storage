#!/usr/bin/env python3
"""
Fail-Closed Gate Proto — Map §10 simulation (SCREEN only)

Uses services.fail_closed_gate.gate_core (same core as infra-gate).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.fail_closed_gate.gate_core import (  # noqa: E402
    SCOPE,
    GateInput,
    TradeSignal,
    evaluate_gate,
)

SEEDS = (20270701, 20270702, 20270703)


def _scenarios() -> List[tuple[str, GateInput, str]]:
    base = TradeSignal(
        signal_id="SIG-OK",
        source="P4",
        notional_eur=10_000.0,
        stress_score=0.2,
    )
    return [
        ("clean_but_gate_closed", GateInput(signal=base, human_gate_open=False), "BLOCKED"),
        ("clean_human_open", GateInput(signal=base, human_gate_open=True), "RELEASED"),
        (
            "m7_poison",
            GateInput(signal=base, human_gate_open=True, latency_spike=1e6),
            "BLOCKED",
        ),
        (
            "z3_cascade",
            GateInput(signal=base, human_gate_open=True, cascade_risk=0.9),
            "BLOCKED",
        ),
        (
            "bho_break",
            GateInput(signal=base, human_gate_open=True, bho_delta=0.05),
            "BLOCKED",
        ),
        (
            "p3_exec_risk",
            GateInput(signal=base, human_gate_open=True, exec_risk=0.95),
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
    print("Fail-Closed Gate Proto (Map §10 · shared gate_core)")
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
    no_live = all(not r["live_execution"] for r in rows)
    payload = {
        "screen": "fail_closed_gate_v0",
        "scope": SCOPE,
        "map_ref": "docs/AGENT_SWARM_P9_MAP_v0.md §10",
        "core": "services/fail_closed_gate/gate_core.py",
        "elapsed_s": round(elapsed, 3),
        "budget_ok": elapsed < 16.0,
        "n_pass": n_ok,
        "n_total": n_total,
        "verdict": "GATE_PROTO_PASS" if all_pass and no_live else "GATE_PROTO_FAIL",
        "invariants": {
            "no_live_execution": no_live,
            "default_closed_blocks": all(
                r["decision"] == "BLOCKED"
                for r in rows
                if r["scenario"] == "clean_but_gate_closed"
            ),
            "human_open_can_release": all(
                r["decision"] == "RELEASED"
                for r in rows
                if r["scenario"] == "clean_human_open"
            ),
        },
        "results": rows,
    }
    out = _HERE / "FAIL_CLOSED_GATE_PROTO.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print("-" * 72)
    print(f"VERDICT: {payload['verdict']}  {n_ok}/{n_total}")
    print(f"elapsed={elapsed:.3f}s  → {out}")
    return payload


if __name__ == "__main__":
    run_screen()
