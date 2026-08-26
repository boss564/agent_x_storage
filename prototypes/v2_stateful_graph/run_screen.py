#!/usr/bin/env python3
"""16s screen — Stateful Graph Automata (sandbox Serie v2).

Gate: ΔQ > 0  ∧  H_Kante > ε  ∧  Arm-C-Bruch
Fail → DISCARD. Seeds 20270101–03.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from stateful_graph_proto import run_stateful_graph_cell  # noqa: E402

SEEDS = (20270101, 20270102, 20270103)
BUDGET_S = 16.0


def main() -> int:
    print("=" * 60)
    print("STATEFUL-GRAPH proto · sandbox v2 · ≤16s · no Pre-Reg")
    print(f"seeds={SEEDS}")
    print("gate: ΔQ>0 ∧ H_Kante>ε ∧ Arm-C-Bruch")
    print("=" * 60)

    t0 = time.monotonic()
    rows = []
    for seed in SEEDS:
        cell = run_stateful_graph_cell(run_seed=seed)
        rows.append(cell)
        print(
            f"  seed={seed} ΔQ={cell['delta_q']}({cell['delta_q_pass']}) · "
            f"H={cell['h_edge']}({cell['h_pass']}) · "
            f"C-break={cell['arm_c_break']} "
            f"(anti B={cell['anti_b']} C={cell['anti_c']}) · "
            f"{'PASS' if cell['pass'] else 'FAIL'}"
        )

    elapsed = time.monotonic() - t0
    n_pass = sum(1 for r in rows if r["pass"])
    maj = n_pass >= 2
    budget_ok = elapsed <= BUDGET_S
    if not budget_ok:
        gate = "DISCARD_TIMEOUT"
    elif maj:
        gate = "PROTO_PASS"
    else:
        gate = "DISCARD"

    payload = {
        "schema": "stateful_graph_proto_v0",
        "sandbox": "prototypes/v2_stateful_graph",
        "not_a_pre_reg": True,
        "coupling_family_transfer": False,
        "gate_rule": "delta_Q > 0 AND H_edge > eps AND arm_C_break",
        "seeds": list(SEEDS),
        "elapsed_s": round(elapsed, 3),
        "budget_s": BUDGET_S,
        "budget_ok": budget_ok,
        "majority_pass": maj,
        "n_pass": n_pass,
        "gate": gate,
        "per_seed": rows,
        "next": (
            "DRAFT / Pre-Reg 01 allowed only if PROTO_PASS"
            if gate == "PROTO_PASS"
            else "discard — no Pre-Reg / no sweep / no further docs"
        ),
    }
    (HERE / "STATEFUL_GRAPH_PROTO.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    (HERE / "STATEFUL_GRAPH_PROTO_GATE.txt").write_text(
        f"gate={gate} elapsed={elapsed:.2f}s pass={n_pass}/3 budget_ok={budget_ok}\n",
        encoding="utf-8",
    )
    print("=" * 60)
    print(f"GATE: {gate}  ({elapsed:.2f}s / {BUDGET_S}s)")
    print("=" * 60)
    return 0 if gate == "PROTO_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
