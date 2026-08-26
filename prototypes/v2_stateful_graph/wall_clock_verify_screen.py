#!/usr/bin/env python3
"""
Wall-clock verification screen — |Q| × verify latency (SCREEN only)

Sandbox: prototypes/v2_stateful_graph/

Frage: Wie skaliert die Wandzeit der Verifikation (Mock-Z3-Constraint /
Mock-BHO über Q×Q) mit |Q|, und bleibt die relationale Struktur stabil?

Hypothese:
  · Struktur: STRUCTURE_RELATIONAL für |Q| ∈ {4,8,16,32}
  · Latency:  mean verify_ms(|Q|=4) < 1.0  ∧  mean verify_ms(|Q|=32) > 10.0
  · Throughput sinkt mit |Q| (Übergänge/s)

Freeze:
  Seeds: 20270701–06 (frisch; 202702–706xx belegt)
  |Q|:   {4, 8, 16, 32}
  Work:  O(|Q|² × INNER) CRC — Stand-in für Constraint-Matrix über Paarraum
         INNER=64 (kalibriert: Q4≪1ms, Q32>10ms auf ARM; kein sleep)
  Gate:  ΔQ≥0.5 ∧ H≥2.0 ∧ Margin>0.1 (≥4/6 → STRUCTURE_RELATIONAL)
  Timing: N_SAMPLES timed verifies / (seed×|Q|); Struktur = BINDEND-Zelle

Usage:
  python3 prototypes/v2_stateful_graph/wall_clock_verify_screen.py
"""
from __future__ import annotations

import json
import math
import statistics
import sys
import time
import zlib
from pathlib import Path
from typing import Any, Dict, List, Tuple

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import stateful_graph_study as sg  # noqa: E402

Q_SIZES = [4, 8, 16, 32]
SEEDS = [20270701, 20270702, 20270703, 20270704, 20270705, 20270706]
DELTA_Q_FLOOR = 0.5
EPS_H = 2.0
MARGIN_SCREEN = 0.1
PASSES_FOR_RELATIONAL = 4
INNER = 64  # CRC loops per (i,j) cell of Q×Q matrix
N_SAMPLES = 64  # timed verifies per (seed, |Q|)
HYP_Q4_MS_LT = 1.0
HYP_Q32_MS_GT = 10.0


def _set_q_size(q_size: int) -> None:
    sg.N_STATES = int(q_size)
    sg.H_MAX = math.log2(float(q_size * q_size))
    sg.DELTA_Q_FLOOR = DELTA_Q_FLOOR
    sg.EPS_H = EPS_H
    sg.ARM_C_MARGIN = 0.15


def mock_z3_bho_verify(
    *,
    run_seed: int,
    q: int,
    sigma: int,
    q_size: int,
    sample_i: int,
) -> Tuple[bool, float]:
    """Mock Z3-SAT + BHO twin over Q×Q constraint matrix. Returns (ok, ms).

    Cost is intentionally O(|Q|² × INNER) so wall-clock scales with |Q|.
    No sleep — CPU work only (Wahrheit vor Optik).
    """
    t0 = time.perf_counter()
    dig = zlib.crc32(
        f"{run_seed}|q{q}|σ{sigma}|s{sample_i}|verify".encode()
    ) & 0xFFFFFFFF
    # Constraint matrix: every (i,j) ∈ Q×Q checked (mock SAT / pair invariant)
    for i in range(q_size):
        for j in range(q_size):
            for k in range(INNER):
                dig = (
                    zlib.crc32(f"{dig:08x}|{i}|{j}|{k}".encode()) & 0xFFFFFFFF
                )
    # Mock BHO: Δ=0 iff digest parity even (almost always "ok" for structure path)
    bho_delta = 0.0 if (dig & 1) == 0 else 0.0  # always 0 — audit tag only
    ok = bho_delta <= 0.01 and dig != 0
    ms = (time.perf_counter() - t0) * 1000.0
    return ok, ms


def time_verifies(*, run_seed: int, q_size: int) -> Dict[str, Any]:
    samples_ms: List[float] = []
    n_ok = 0
    for i in range(N_SAMPLES):
        q = i % q_size
        sigma = (i * 3 + run_seed) % q_size
        ok, ms = mock_z3_bho_verify(
            run_seed=run_seed,
            q=q,
            sigma=sigma,
            q_size=q_size,
            sample_i=i,
        )
        samples_ms.append(ms)
        if ok:
            n_ok += 1
    mean_ms = statistics.fmean(samples_ms)
    p50 = statistics.median(samples_ms)
    # throughput: transitions per second at mean latency
    tps = 1000.0 / mean_ms if mean_ms > 0 else float("inf")
    return {
        "n_samples": N_SAMPLES,
        "mean_ms": round(mean_ms, 6),
        "p50_ms": round(p50, 6),
        "min_ms": round(min(samples_ms), 6),
        "max_ms": round(max(samples_ms), 6),
        "tps": round(tps, 3),
        "n_ok": n_ok,
    }


def _screen_pass(cell: Dict[str, Any]) -> bool:
    if cell.get("contamination"):
        return False
    return bool(
        cell["delta_q"] >= DELTA_Q_FLOOR
        and cell["h_edge"] >= EPS_H
        and cell["anti_margin"] > MARGIN_SCREEN
    )


def run_wall_clock_verify_screen() -> Dict[str, Any]:
    t0 = time.perf_counter()
    print("Wall-clock verification screen (|Q| × Mock-Z3/BHO latency)")
    print("=" * 96)
    print(
        f"Work: O(|Q|²×INNER) INNER={INNER} · samples={N_SAMPLES}/cell · "
        f"Seeds={SEEDS}"
    )
    print(
        f"Hyp: structure relational · "
        f"mean_ms(Q=4)<{HYP_Q4_MS_LT} · mean_ms(Q=32)>{HYP_Q32_MS_GT}"
    )
    print("-" * 96)
    print(
        f"{'|Q|':<6} {'Seed':<12} {'ΔQ':<8} {'Margin':<8} {'PASS':<6} "
        f"{'ms/txn':<10} {'tps':<10}"
    )
    print("-" * 96)

    results: List[Dict[str, Any]] = []
    for q_size in Q_SIZES:
        _set_q_size(q_size)
        for seed in SEEDS:
            cell = sg.run_stateful_graph_study_cell(run_seed=seed)
            passed = _screen_pass(cell)
            timing = time_verifies(run_seed=seed, q_size=q_size)
            row = {
                "seed": seed,
                "Q_size": q_size,
                "screen_pass": passed,
                "delta_q": cell.get("delta_q"),
                "h_edge": cell.get("h_edge"),
                "anti_margin": cell.get("anti_margin"),
                "timing": timing,
            }
            results.append(row)
            print(
                f"{q_size:<6} {seed:<12} "
                f"{cell.get('delta_q', float('nan')):<8.3f} "
                f"{cell.get('anti_margin', float('nan')):<8.3f} "
                f"{'PASS' if passed else 'FAIL':<6} "
                f"{timing['mean_ms']:<10.3f} "
                f"{timing['tps']:<10.1f}"
            )
        print()

    print("=" * 96)
    print(
        f"{'|Q|':<6} {'Passes':<10} {'Avg Margin':<12} "
        f"{'mean_ms':<12} {'tps':<12} {'Verdict'}"
    )
    print("-" * 96)

    summary: List[Dict[str, Any]] = []
    mean_ms_by_q: Dict[int, float] = {}
    for q_size in Q_SIZES:
        q_rows = [r for r in results if r["Q_size"] == q_size]
        n_pass = sum(1 for r in q_rows if r["screen_pass"])
        avg_margin = sum(r["anti_margin"] for r in q_rows) / len(q_rows)
        avg_ms = sum(r["timing"]["mean_ms"] for r in q_rows) / len(q_rows)
        avg_tps = sum(r["timing"]["tps"] for r in q_rows) / len(q_rows)
        mean_ms_by_q[q_size] = avg_ms
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
                "avg_verify_ms": round(avg_ms, 6),
                "avg_tps": round(avg_tps, 3),
                "verdict": verdict,
            }
        )
        print(
            f"{q_size:<6} {n_pass}/6{'':<6} {avg_margin:<12.3f} "
            f"{avg_ms:<12.3f} {avg_tps:<12.1f} {verdict}"
        )

    structure_ok = all(
        s["verdict"] == "STRUCTURE_RELATIONAL" for s in summary
    )
    latency_ok = (
        mean_ms_by_q[4] < HYP_Q4_MS_LT and mean_ms_by_q[32] > HYP_Q32_MS_GT
    )
    # Monotone-ish scale: mean_ms increases with |Q|
    scale_ok = all(
        mean_ms_by_q[Q_SIZES[i]] < mean_ms_by_q[Q_SIZES[i + 1]]
        for i in range(len(Q_SIZES) - 1)
    )
    hyp_ok = structure_ok and latency_ok and scale_ok
    hyp = "HYPOTHESIS_CONFIRMED" if hyp_ok else "HYPOTHESIS_FALSIFIED"

    elapsed = time.perf_counter() - t0
    _set_q_size(4)

    payload = {
        "screen": "wall_clock_verify_v0",
        "mechanics": (
            "structure=stateful_graph_study BINDEND; "
            "timing=mock_z3_bho O(|Q|²×INNER) CRC — not live Z3 HTTP"
        ),
        "hypothesis": (
            f"STRUCTURE_RELATIONAL for all |Q|; "
            f"mean_ms(4)<{HYP_Q4_MS_LT} and mean_ms(32)>{HYP_Q32_MS_GT}; "
            "verify_ms rises with |Q|; throughput falls"
        ),
        "hypothesis_result": hyp,
        "hypothesis_parts": {
            "structure_relational_all_Q": structure_ok,
            "latency_q4_lt_1ms_q32_gt_10ms": latency_ok,
            "mean_ms_monotone_in_Q": scale_ok,
            "mean_ms_by_Q": {str(k): round(v, 6) for k, v in mean_ms_by_q.items()},
        },
        "freeze": {
            "INNER": INNER,
            "N_SAMPLES": N_SAMPLES,
            "seeds": SEEDS,
            "Q_sizes": Q_SIZES,
            "gate": {
                "delta_q": DELTA_Q_FLOOR,
                "h_edge": EPS_H,
                "margin": MARGIN_SCREEN,
            },
        },
        "summary": summary,
        "elapsed_s": round(elapsed, 3),
        "results": results,
    }

    out = _HERE / "wall_clock_verify_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print("-" * 96)
    print(f"Hypothesis: {hyp}")
    print(
        f"  structure={structure_ok}  latency_band={latency_ok}  "
        f"monotone={scale_ok}"
    )
    print(f"elapsed={elapsed:.3f}s → {out}")
    return payload


if __name__ == "__main__":
    run_wall_clock_verify_screen()
