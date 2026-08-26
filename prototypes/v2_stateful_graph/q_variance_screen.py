#!/usr/bin/env python3
"""
|Q|-Variance Screening — STRUCTURE_RELATIONAL across state-space sizes

|Q| ∈ {4, 8, 16, 32}

SCREEN only (kein Pre-Reg · keine BINDEND-Wiederholung von Studie 1).
Mechanik = `stateful_graph_study.py` (Warmup=32 · Measure=80 · H über Paare ·
F10 Arm-A σ=crc · true vs π Partner), nur `N_STATES` variiert.

Seeds: 20270401–06 (frisch; 202702xx = Studie 1; ≤20270199 gesperrt)

Screen-Gate (bewusst lockerer Margin als BINDEND 0,15):
  ΔQ ≥ 0.5  ∧  H_Kante ≥ 2.0 bit  ∧  Margin > 0.1

Usage (cwd = repo root):
  python3 prototypes/v2_stateful_graph/q_variance_screen.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import stateful_graph_study as sg  # noqa: E402

Q_SIZES = [4, 8, 16, 32]
SEEDS = [20270401, 20270402, 20270403, 20270404, 20270405, 20270406]

DELTA_Q_FLOOR = 0.5
EPS_H = 2.0
MARGIN_SCREEN = 0.1  # screen; BINDEND study uses 0.15
PASSES_FOR_RELATIONAL = 4  # of 6


def _set_q_size(q_size: int) -> None:
    sg.N_STATES = int(q_size)
    sg.H_MAX = math.log2(float(q_size * q_size))
    sg.DELTA_Q_FLOOR = DELTA_Q_FLOOR
    sg.EPS_H = EPS_H
    # Keep study margin constant for arm_c_break flag; screen uses MARGIN_SCREEN
    sg.ARM_C_MARGIN = 0.15


def _screen_pass(cell: Dict[str, Any]) -> bool:
    if cell.get("contamination"):
        return False
    return bool(
        cell["delta_q"] >= DELTA_Q_FLOOR
        and cell["h_edge"] >= EPS_H
        and cell["anti_margin"] > MARGIN_SCREEN
    )


def run_q_variance_screen() -> Dict[str, Any]:
    print("|Q|-Variance Screening (BINDEND mechanics · SCREEN seeds)")
    print("=" * 88)
    print(
        f"{'|Q|':<6} {'Seed':<12} {'ΔQ_B':<8} {'H_B':<8} "
        f"{'anti_B':<8} {'anti_C':<8} {'Margin':<8} {'PASS':<6}"
    )
    print("-" * 88)

    results: List[Dict[str, Any]] = []

    for q_size in Q_SIZES:
        _set_q_size(q_size)
        for seed in SEEDS:
            cell = sg.run_stateful_graph_study_cell(run_seed=seed)
            passed = _screen_pass(cell)
            row = {
                "seed": seed,
                "Q_size": q_size,
                "h_max": sg.H_MAX,
                "cell": cell,
                "screen_pass": passed,
            }
            results.append(row)
            flag = "PASS" if passed else "FAIL"
            print(
                f"{q_size:<6} {seed:<12} {cell.get('delta_q', float('nan')):<8.3f} "
                f"{cell.get('h_edge', float('nan')):<8.3f} "
                f"{cell.get('anti_b', float('nan')):<8.3f} "
                f"{cell.get('anti_c', float('nan')):<8.3f} "
                f"{cell.get('anti_margin', float('nan')):<8.3f} "
                f"{flag:<6}"
            )
        print()

    print("=" * 88)
    print("Summary by |Q|:")
    print(
        f"{'|Q|':<6} {'Passes':<10} {'Avg Margin':<12} {'Avg H_B':<10} "
        f"{'H_max':<8} {'Verdict':<25}"
    )
    print("-" * 88)

    summary: List[Dict[str, Any]] = []
    for q_size in Q_SIZES:
        q_rows = [r for r in results if r["Q_size"] == q_size]
        n_pass = sum(1 for r in q_rows if r["screen_pass"])
        avg_margin = sum(r["cell"]["anti_margin"] for r in q_rows) / len(q_rows)
        avg_h = sum(r["cell"]["h_edge"] for r in q_rows) / len(q_rows)
        h_max = math.log2(float(q_size * q_size))
        verdict = (
            "STRUCTURE_RELATIONAL"
            if n_pass >= PASSES_FOR_RELATIONAL
            else "STRUCTURE_BREAKS"
        )
        summary.append(
            {
                "Q_size": q_size,
                "n_pass": n_pass,
                "n": len(q_rows),
                "avg_margin": round(avg_margin, 6),
                "avg_h_edge": round(avg_h, 6),
                "h_max": h_max,
                "verdict": verdict,
            }
        )
        print(
            f"{q_size:<6} {n_pass}/6{'':<6} {avg_margin:<12.3f} "
            f"{avg_h:<10.3f} {h_max:<8.1f} {verdict:<25}"
        )

    # Restore study defaults so import side-effects don't stick
    _set_q_size(4)

    payload = {
        "screen": "q_variance",
        "mechanics": "stateful_graph_study.py (BINDEND F0–F10)",
        "gate": {
            "delta_q": DELTA_Q_FLOOR,
            "h_edge": EPS_H,
            "margin": MARGIN_SCREEN,
            "note": "Margin screen >0.1; BINDEND study ≥0.15",
        },
        "seeds": SEEDS,
        "Q_sizes": Q_SIZES,
        "summary": summary,
        "results": [
            {
                "seed": r["seed"],
                "Q_size": r["Q_size"],
                "h_max": r["h_max"],
                "screen_pass": r["screen_pass"],
                "delta_q": r["cell"].get("delta_q"),
                "h_edge": r["cell"].get("h_edge"),
                "anti_b": r["cell"].get("anti_b"),
                "anti_c": r["cell"].get("anti_c"),
                "anti_margin": r["cell"].get("anti_margin"),
                "triad_bindend_margin_015": r["cell"].get("triad"),
            }
            for r in results
        ],
    }

    out = _HERE / "q_variance_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"\nResults saved to: {out}")
    return payload


if __name__ == "__main__":
    run_q_variance_screen()
