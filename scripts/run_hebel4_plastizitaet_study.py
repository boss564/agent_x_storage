"""Hebel 4 plasticity study: Class-B dispatch vs stub null.

Pre-reg: docs/HEBEL4_PLASTIZITAET_PREREG.md
Spec:    docs/HEBEL4_PLASTIZITAET_SPEC.md

Verdict ONLY on leitungsausfall × treatment (IUT H1a ∧ H1b).
bewoelkung / spitzenlast: descriptive under treatment.
Null × leitungsausfall: replication expected NOT_CONFIRMED.
"""

from __future__ import annotations

import json
import math
import os
import statistics
import sys
from dataclasses import dataclass
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.smartgrid.flex_dispatch import PASSIVE_FLEX_FRACTION
from agents_b2g.smartgrid.simulation import SmartGridStressSimulation
from agents_b2g.smartgrid.ooda_evaluator import evaluate_h0

ALPHA = 0.01
N_SEEDS = 10
DURATION = 4320.0
T_WARMUP = 60.0
T_STRESS = 1440.0
BURN_IN = 60.0
GRID_COUPLING = 0.60
VERDICT_STRESS = "leitungsausfall"
DESCRIPTIVE_STRESSES = ["bewoelkung", "spitzenlast"]


@dataclass
class RunResult:
    seed: int
    stress_type: str
    plasticity: bool
    delta_r_grid: float
    delta_w_dyn: float
    w_dyn_normal: float
    w_dyn_stress: float
    r_grid_normal: float
    r_grid_stress: float
    mean_dispatch_kw: float
    t_stress_effective: float


def wilcoxon_one_sided(values: List[float], alternative: str = "less") -> tuple:
    vals = [d for d in values if d != 0.0]
    n = len(vals)
    if n < 10:
        return 0.0, 1.0
    ordered = sorted(range(n), key=lambda i: abs(vals[i]))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n - 1 and abs(vals[ordered[j]]) == abs(vals[ordered[j + 1]]):
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[ordered[k]] = avg
        i = j + 1
    w_pos = sum(ranks[i] for i in range(n) if vals[i] > 0)
    w_neg = sum(ranks[i] for i in range(n) if vals[i] < 0)
    mu = n * (n + 1) / 4.0
    sigma = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0)
    if sigma == 0:
        return (w_neg if alternative == "less" else w_pos), 1.0
    w = w_neg if alternative == "less" else w_pos
    z = (w - mu) / sigma

    def norm_sf(zv: float) -> float:
        return 0.5 * (1.0 - math.erf(zv / math.sqrt(2)))

    return w, norm_sf(z)


def classify_h1(delta_r: List[float], delta_w: List[float]) -> dict:
    """IUT: H1 CONFIRMED iff H1a AND H1b."""
    w_r, p_r = wilcoxon_one_sided(delta_r, alternative="less")
    h1a = p_r < ALPHA
    median_w = statistics.median(delta_w) if delta_w else 0.0
    n_nonneg = sum(1 for d in delta_w if d >= 0)
    h1b = median_w >= 0 and n_nonneg >= 7
    return {
        "mean_delta_r_grid": round(statistics.mean(delta_r) if delta_r else 0.0, 6),
        "wilcoxon_r_W": round(w_r, 2),
        "wilcoxon_r_p": round(p_r, 6),
        "h1a_status": "CONFIRMED" if h1a else "NOT_CONFIRMED",
        "median_delta_w_dyn": round(median_w, 6),
        "n_seeds_w_dyn_geq_0": n_nonneg,
        "h1b_status": "CONFIRMED" if h1b else "NOT_CONFIRMED",
        "h1_status": "CONFIRMED" if (h1a and h1b) else "NOT_CONFIRMED",
        "delta_r": [round(x, 6) for x in delta_r],
        "delta_w": [round(x, 6) for x in delta_w],
    }


def run_one(seed: int, stress_type: str, plasticity: bool) -> RunResult:
    sim = SmartGridStressSimulation(
        seed=seed, duration_s=DURATION, grid_coupling=GRID_COUPLING,
        t_warmup=T_WARMUP, t_stress=T_STRESS, burn_in=BURN_IN,
        stress_type=stress_type, plasticity=plasticity,
    )
    result = sim.run()
    res_n = evaluate_h0(result["normal"], alpha=ALPHA)
    res_s = evaluate_h0(result["stress"], alpha=ALPHA)
    w_n = sim.compute_efficiency("normal")["mean_w_dyn"]
    w_s = sim.compute_efficiency("stress")["mean_w_dyn"]
    r_n = res_n.get("r_observed", 0.0)
    r_s = res_s.get("r_observed", 0.0)
    return RunResult(
        seed=seed, stress_type=stress_type, plasticity=plasticity,
        delta_r_grid=r_s - r_n, delta_w_dyn=w_s - w_n,
        w_dyn_normal=w_n, w_dyn_stress=w_s,
        r_grid_normal=r_n, r_grid_stress=r_s,
        mean_dispatch_kw=float(result.get("mean_dispatch_kw", 0.0)),
        t_stress_effective=float(result.get("t_stress_effective", T_STRESS)),
    )


def summarize_arm(runs: List[RunResult]) -> dict:
    return classify_h1(
        [r.delta_r_grid for r in runs],
        [r.delta_w_dyn for r in runs],
    )


def main() -> None:
    results: List[RunResult] = []

    # Core: leitungsausfall × {null, treatment}
    for plasticity in (False, True):
        label = "treatment" if plasticity else "null"
        for seed in range(N_SEEDS):
            print(f"leitungsausfall {label} seed={seed}...", end=" ", flush=True)
            r = run_one(seed, VERDICT_STRESS, plasticity)
            print(f"ΔR={r.delta_r_grid:+.4f} ΔW={r.delta_w_dyn:+.4f} "
                  f"dispatch={r.mean_dispatch_kw:.1f} t_stress={r.t_stress_effective:.1f}")
            results.append(r)

    # Descriptive: bewoelkung / spitzenlast under treatment only
    for stype in DESCRIPTIVE_STRESSES:
        for seed in range(N_SEEDS):
            print(f"{stype} treatment seed={seed}...", end=" ", flush=True)
            r = run_one(seed, stype, True)
            print(f"ΔR={r.delta_r_grid:+.4f} ΔW={r.delta_w_dyn:+.4f}")
            results.append(r)

    null_runs = [r for r in results
                 if r.stress_type == VERDICT_STRESS and not r.plasticity]
    treat_runs = [r for r in results
                  if r.stress_type == VERDICT_STRESS and r.plasticity]

    null_h1 = summarize_arm(null_runs)
    treat_h1 = summarize_arm(treat_runs)
    verdict = "WIRKSAM" if treat_h1["h1_status"] == "CONFIRMED" else "NICHT_WIRKSAM"

    descriptive = {}
    for stype in DESCRIPTIVE_STRESSES:
        runs = [r for r in results if r.stress_type == stype and r.plasticity]
        descriptive[stype] = {
            **summarize_arm(runs),
            "mean_dispatch_kw": round(
                statistics.mean([r.mean_dispatch_kw for r in runs]), 4
            ),
            "note": "deskriptiv — kein Verdict",
        }

    out = {
        "passive_flex_fraction": PASSIVE_FLEX_FRACTION,
        "verdict_stress": VERDICT_STRESS,
        "verdict": verdict,
        "leitungsausfall": {
            "null": {
                **null_h1,
                "mean_dispatch_kw": 0.0,
                "note": "replication arm — expected NOT_CONFIRMED",
            },
            "treatment": {
                **treat_h1,
                "mean_dispatch_kw": round(
                    statistics.mean([r.mean_dispatch_kw for r in treat_runs]), 4
                ),
            },
        },
        "descriptive_treatment": descriptive,
        "notes": [
            "IUT: H1a AND H1b",
            "0.4 stub caveat: POSITIV vs stub baseline, not realistic flex model",
            "step-synchronous dispatch (not OODA-gated)",
            "generalization: verdict only leitungsausfall",
            "consciously deferred: shadow prices / Hebb / active inference",
            "seed streams: seed+1 gen, +5555 load, +7777 jitter, +999999 stress onset ±30",
            "waterfall: battery→EV→HP (reaction time × degradation cost)",
            "full deficit cover per step while capacity remains",
        ],
        "runs": [
            {
                "seed": r.seed, "stress_type": r.stress_type,
                "plasticity": r.plasticity,
                "delta_r_grid": round(r.delta_r_grid, 6),
                "delta_w_dyn": round(r.delta_w_dyn, 6),
                "mean_dispatch_kw": round(r.mean_dispatch_kw, 4),
                "t_stress_effective": round(r.t_stress_effective, 2),
            }
            for r in results
        ],
    }

    print("\n" + "=" * 70)
    print("HEBEL 4 — Leitungsausfall NULL:")
    print(f"  H1a: ΔR={null_h1['mean_delta_r_grid']:+.4f} p={null_h1['wilcoxon_r_p']:.4f}"
          f" → {null_h1['h1a_status']}")
    print(f"  H1b: median ΔW={null_h1['median_delta_w_dyn']:+.4f} "
          f"{null_h1['n_seeds_w_dyn_geq_0']}/10 → {null_h1['h1b_status']}")
    print(f"  H1:  {null_h1['h1_status']}")
    print("HEBEL 4 — Leitungsausfall TREATMENT:")
    print(f"  H1a: ΔR={treat_h1['mean_delta_r_grid']:+.4f} p={treat_h1['wilcoxon_r_p']:.4f}"
          f" → {treat_h1['h1a_status']}")
    print(f"  H1b: median ΔW={treat_h1['median_delta_w_dyn']:+.4f} "
          f"{treat_h1['n_seeds_w_dyn_geq_0']}/10 → {treat_h1['h1b_status']}")
    print(f"  H1:  {treat_h1['h1_status']}")
    print(f"\nVERDICT: {verdict}")
    for stype, d in descriptive.items():
        print(f"\nDeskriptiv {stype} (treatment): ΔR={d['mean_delta_r_grid']:+.4f} "
              f"median ΔW={d['median_delta_w_dyn']:+.4f} "
              f"dispatch={d['mean_dispatch_kw']:.1f}")
    print("=" * 70)

    path = "hebel4_plastizitaet_ergebnis.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {path}")


if __name__ == "__main__":
    main()
