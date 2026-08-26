#!/usr/bin/env python3
"""16s gate screen — event-driven strand (prototype only).

Gate: ΔR_i > 0  ∧  median |ρ| < 0.90
Fail A or B → DISCARD (no Pre-Reg, no sweep, minimal artifact).
Seeds 20261901–03 (post coupling-series lock).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "agents_b2g" / "emergence"))

from event_driven_proto import run_event_driven_cell  # noqa: E402

SEEDS = (20261901, 20261902, 20261903)
BUDGET_S = 16.0


def main() -> int:
    out_dir = (
        _PROJECT_ROOT
        / "agents_b2g"
        / "emergence"
        / "event_driven_proto_v0"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("EVENT-DRIVEN proto screen · ≤16s · no Pre-Reg")
    print(f"seeds={SEEDS} gate: ΔR_i>0 ∧ median|ρ|<0.90")
    print("=" * 60)

    t0 = time.monotonic()
    rows = []
    for seed in SEEDS:
        cell = run_event_driven_cell(run_seed=seed)
        rows.append(cell)
        print(
            f"  seed={seed} A={cell['layer_a_pass']} ρ={cell['median_abs_rho']} · "
            f"B={cell['layer_b_pass']} ΔR={cell['mean_delta_r']} · "
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
        "schema": "event_driven_proto_v0",
        "not_a_pre_reg": True,
        "strand": "1_event_driven",
        "gate_rule": "delta_R_i > 0 AND median_|rho| < 0.90",
        "seeds": list(SEEDS),
        "elapsed_s": round(elapsed, 3),
        "budget_s": BUDGET_S,
        "budget_ok": budget_ok,
        "majority_pass": maj,
        "n_pass": n_pass,
        "gate": gate,
        "per_seed": rows,
        "next": (
            "DRAFT allowed only if PROTO_PASS"
            if gate == "PROTO_PASS"
            else "discard — no Pre-Reg / no sweep / no further docs"
        ),
    }
    (out_dir / "EVENT_DRIVEN_PROTO.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    # Minimal one-liner result only (gate: no doc overhead on fail)
    line = (
        f"gate={gate} elapsed={elapsed:.2f}s "
        f"pass={n_pass}/3 budget_ok={budget_ok}\n"
    )
    (out_dir / "EVENT_DRIVEN_PROTO_GATE.txt").write_text(line, encoding="utf-8")

    print("=" * 60)
    print(f"GATE: {gate}  ({elapsed:.2f}s / {BUDGET_S}s)")
    print("=" * 60)
    return 0 if gate == "PROTO_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
