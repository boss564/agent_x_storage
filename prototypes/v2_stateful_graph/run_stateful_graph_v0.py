#!/usr/bin/env python3
"""Stateful Graph v0 — Spot + Sweep (BINDEND).

Seeds: Spot 20270201 · Sweep 20270201–06
Proto seeds ≤20270199 locked.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from stateful_graph_study import (  # noqa: E402
    majority_verdict,
    run_stateful_graph_study_cell,
)

SPOT_SEED = 20270201
SWEEP_SEEDS = tuple(range(20270201, 20270207))
OUT_DIR = HERE / "runs" / "stateful_graph_v0"


def _print_cell(tag: str, cell: dict) -> None:
    if cell.get("contamination"):
        print(f"  {tag} CONTAMINATION seed={cell.get('run_seed')}")
        return
    print(
        f"  {tag} seed={cell['run_seed']} "
        f"ΔQ={cell['delta_q']:.4f}({'Y' if cell['delta_q_pass'] else 'N'}) "
        f"H={cell['h_edge']:.4f}({'Y' if cell['h_pass'] else 'N'}) "
        f"anti A/B/C={cell['anti_a']:.3f}/{cell['anti_b']:.3f}/{cell['anti_c']:.3f} "
        f"margin={cell['anti_margin']:.3f} "
        f"A-sanity={'Y' if cell['arm_a_sanity'] else 'N'} "
        f"triad={'PASS' if cell['triad'] else 'FAIL'}"
    )


def run_spot() -> dict:
    print("=" * 64)
    print("STATEFUL_GRAPH_v0 SPOT · seed=20270201")
    print("Gate B-triad + Arm-A sanity (ΔQ≥0.5 ∧ H≥2.0)")
    print("=" * 64)
    cell = run_stateful_graph_study_cell(run_seed=SPOT_SEED)
    _print_cell("SPOT", cell)
    ok = bool(
        cell.get("triad")
        and cell.get("arm_a_sanity")
        and not cell.get("contamination")
    )
    label = "SPOT_PASS" if ok else "SIGNAL_BLIND"
    print(f"SPOT: {label}")
    return {"label": label, "ok": ok, "cell": cell}


def run_sweep() -> dict:
    print("=" * 64)
    print("STATEFUL_GRAPH_v0 SWEEP · seeds=20270201–06")
    print("=" * 64)
    t0 = time.monotonic()
    cells = []
    for seed in SWEEP_SEEDS:
        cell = run_stateful_graph_study_cell(run_seed=seed)
        cells.append(cell)
        _print_cell("SWEEP", cell)
    elapsed = time.monotonic() - t0
    maj = majority_verdict(cells)
    print("-" * 64)
    print(
        f"VERDICT: {maj['verdict']} · triad {maj['n_triad']}/{maj['n']} · "
        f"§1.1 break {maj['n_arm_c_break']}/{maj['n']} · {elapsed:.3f}s"
    )
    return {
        "elapsed_s": round(elapsed, 3),
        "majority": maj,
        "cells": cells,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "mode",
        choices=("spot", "sweep", "all"),
        nargs="?",
        default="all",
    )
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    payload: dict = {
        "schema": "stateful_graph_v0",
        "prereg": "docs/STATEFUL_GRAPH_v0_PREREG.md",
        "sandbox": "prototypes/v2_stateful_graph",
        "coupling_family_transfer": False,
        "spot_seed": SPOT_SEED,
        "sweep_seeds": list(SWEEP_SEEDS),
    }

    spot = None
    if args.mode in ("spot", "all"):
        spot = run_spot()
        payload["spot"] = {
            "label": spot["label"],
            "ok": spot["ok"],
            "cell": spot["cell"],
        }
        (OUT_DIR / "SPOT.json").write_text(
            json.dumps(payload["spot"], indent=2) + "\n", encoding="utf-8"
        )
        if not spot["ok"]:
            (OUT_DIR / "VERDICT.txt").write_text(
                "SIGNAL_BLIND\n", encoding="utf-8"
            )
            print("Sweep gesperrt — Spot FAIL")
            return 1

    if args.mode in ("sweep", "all"):
        if args.mode == "sweep":
            # still require spot integrity if running sweep alone
            spot_chk = run_stateful_graph_study_cell(run_seed=SPOT_SEED)
            if not (
                spot_chk.get("triad") and spot_chk.get("arm_a_sanity")
            ):
                print("Sweep abort: spot triad/A-sanity would fail")
                return 1
        sweep = run_sweep()
        payload["sweep"] = {
            "elapsed_s": sweep["elapsed_s"],
            "majority": sweep["majority"],
            "cells": sweep["cells"],
        }
        (OUT_DIR / "SWEEP.json").write_text(
            json.dumps(payload["sweep"], indent=2) + "\n", encoding="utf-8"
        )
        verdict = sweep["majority"]["verdict"]
        (OUT_DIR / "VERDICT.txt").write_text(verdict + "\n", encoding="utf-8")
        (OUT_DIR / "SUMMARY.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        return 0 if verdict == "STRUCTURE_RELATIONAL" else 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
