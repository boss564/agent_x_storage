#!/usr/bin/env python3
"""
|Q|=2 Boundary Screen — Grenzfall-Ergänzung zur |Q|-Varianz

SCREEN only (kein Pre-Reg). Mechanik = `stateful_graph_study.py` BINDEND
(Warmup=32 · Measure=80 · H über Paare · F10 · true vs π).

Nur neuer Datenpunkt: |Q|=2 (nicht Wiederholung von {4,8,16,32} /
Commit 01846061).

Hypothese (falsifizierbar): Bei |Q|=2 bricht die relationale Trennung
(monotoner Gleichlauf / Kollision) — Verdict STRUCTURE_BREAKS.

Hinweis: H_max = log2(|Q|²) = 2.0 bit — Gate H≥2.0 verlangt Sättigung.

Seeds: 20270501–06
Gate:  ΔQ ≥ 0.5 ∧ H ≥ 2.0 ∧ Margin > 0.1  (≥4/6 → STRUCTURE_RELATIONAL)

Usage:
  python3 prototypes/v2_stateful_graph/q2_boundary_screen.py
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

Q_SIZE = 2
SEEDS = [20270501, 20270502, 20270503, 20270504, 20270505, 20270506]

DELTA_Q_FLOOR = 0.5
EPS_H = 2.0
MARGIN_SCREEN = 0.1
PASSES_FOR_RELATIONAL = 4


def _set_q_size(q_size: int) -> None:
    sg.N_STATES = int(q_size)
    sg.H_MAX = math.log2(float(q_size * q_size))
    sg.DELTA_Q_FLOOR = DELTA_Q_FLOOR
    sg.EPS_H = EPS_H
    sg.ARM_C_MARGIN = 0.15


def _screen_pass(cell: Dict[str, Any]) -> bool:
    if cell.get("contamination"):
        return False
    return bool(
        cell["delta_q"] >= DELTA_Q_FLOOR
        and cell["h_edge"] >= EPS_H
        and cell["anti_margin"] > MARGIN_SCREEN
    )


def run_q2_boundary_screen() -> Dict[str, Any]:
    _set_q_size(Q_SIZE)
    h_max = sg.H_MAX

    print("|Q|=2 Boundary Screen (Grenzfall · BINDEND mechanics)")
    print("=" * 80)
    print(f"H_max={h_max:.1f} bit  Gate: ΔQ≥{DELTA_Q_FLOOR} ∧ H≥{EPS_H} ∧ Margin>{MARGIN_SCREEN}")
    print(f"Seeds: {SEEDS}")
    print("-" * 80)
    print(
        f"{'Seed':<12} {'ΔQ_B':<8} {'H_B':<8} {'anti_B':<8} "
        f"{'anti_C':<8} {'Margin':<8} {'PASS':<6}"
    )
    print("-" * 80)

    rows: List[Dict[str, Any]] = []
    for seed in SEEDS:
        cell = sg.run_stateful_graph_study_cell(run_seed=seed)
        passed = _screen_pass(cell)
        rows.append({"seed": seed, "cell": cell, "screen_pass": passed})
        print(
            f"{seed:<12} {cell.get('delta_q', float('nan')):<8.3f} "
            f"{cell.get('h_edge', float('nan')):<8.3f} "
            f"{cell.get('anti_b', float('nan')):<8.3f} "
            f"{cell.get('anti_c', float('nan')):<8.3f} "
            f"{cell.get('anti_margin', float('nan')):<8.3f} "
            f"{'PASS' if passed else 'FAIL':<6}"
        )

    n_pass = sum(1 for r in rows if r["screen_pass"])
    avg_margin = sum(r["cell"]["anti_margin"] for r in rows) / len(rows)
    avg_h = sum(r["cell"]["h_edge"] for r in rows) / len(rows)
    avg_dq = sum(r["cell"]["delta_q"] for r in rows) / len(rows)

    if n_pass >= PASSES_FOR_RELATIONAL:
        verdict = "STRUCTURE_RELATIONAL"
        hypothesis = "HYPOTHESIS_FALSIFIED"  # expected break did not happen
    else:
        verdict = "STRUCTURE_BREAKS"
        hypothesis = "HYPOTHESIS_CONFIRMED"  # break as predicted

    # Restore study default
    _set_q_size(4)

    print("-" * 80)
    print(
        f"Passes: {n_pass}/6  Avg ΔQ={avg_dq:.3f}  Avg H={avg_h:.3f}  "
        f"Avg Margin={avg_margin:.3f}"
    )
    print(f"Verdict: {verdict}  ({hypothesis})")

    payload = {
        "screen": "q2_boundary",
        "Q_size": Q_SIZE,
        "h_max": h_max,
        "mechanics": "stateful_graph_study.py (BINDEND F0–F10)",
        "extends": "q_variance_screen.py / commit 01846061 (|Q|∈{4,8,16,32})",
        "hypothesis": (
            "At |Q|=2 relational separation breaks (collision / monotone lockstep)"
        ),
        "hypothesis_result": hypothesis,
        "gate": {
            "delta_q": DELTA_Q_FLOOR,
            "h_edge": EPS_H,
            "margin": MARGIN_SCREEN,
            "passes_needed": PASSES_FOR_RELATIONAL,
        },
        "seeds": SEEDS,
        "n_pass": n_pass,
        "avg_delta_q": round(avg_dq, 6),
        "avg_h_edge": round(avg_h, 6),
        "avg_margin": round(avg_margin, 6),
        "verdict": verdict,
        "results": [
            {
                "seed": r["seed"],
                "screen_pass": r["screen_pass"],
                "delta_q": r["cell"].get("delta_q"),
                "h_edge": r["cell"].get("h_edge"),
                "anti_b": r["cell"].get("anti_b"),
                "anti_c": r["cell"].get("anti_c"),
                "anti_margin": r["cell"].get("anti_margin"),
            }
            for r in rows
        ],
    }

    out = _HERE / "q2_boundary_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"\nResults: {out}")
    return payload


if __name__ == "__main__":
    run_q2_boundary_screen()
