"""CI stress study: 10 seeds x 3 stress types = 30 runs.

Pre-registered analysis (CI_RESILIENZ_STUDIE_PREREG.md):
  H1 (Degradation): ΔR = R_normal - R_stress > 0, one-sided Wilcoxon, alpha=0.01
  H2 (Distinguishability): Kruskal-Wallis across the 3 stress types, p<0.05
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

from agents_b2g.ci.simulation import CIStressSimulation
from agents_b2g.ci.ooda_evaluator import evaluate_h0

ALPHA = 0.01
N_SEEDS = 10
STRESS_TYPES = ["blackout", "cyber", "naturkatastrophe"]
DURATION = 600.0
T_WARMUP = 60.0
T_STRESS = 300.0
BURN_IN = 30.0
COUPLING = 0.30


@dataclass
class StressRunResult:
    seed: int
    stress_type: str
    r_normal: float
    p_normal: float
    status_normal: str
    r_stress: float
    p_stress: float
    status_stress: str
    delta_r: float


def run_one(seed: int, stress_type: str) -> StressRunResult:
    sim = CIStressSimulation(seed=seed, duration_s=DURATION, coupling=COUPLING,
                             t_warmup=T_WARMUP, t_stress=T_STRESS, burn_in=BURN_IN,
                             stress_type=stress_type)
    trajectories = sim.run()
    res_normal = evaluate_h0(trajectories["normal"], alpha=ALPHA)
    res_stress = evaluate_h0(trajectories["stress"], alpha=ALPHA)
    r_n = float(res_normal.get("r_observed", 0.0))
    r_s = float(res_stress.get("r_observed", 0.0))
    return StressRunResult(
        seed=seed, stress_type=stress_type,
        r_normal=r_n, p_normal=float(res_normal.get("p_value", 1.0)),
        status_normal=str(res_normal.get("status", "UNKNOWN")),
        r_stress=r_s, p_stress=float(res_stress.get("p_value", 1.0)),
        status_stress=str(res_stress.get("status", "UNKNOWN")),
        delta_r=r_n - r_s,
    )


def wilcoxon_one_sided(delta_r: List[float]) -> tuple:
    """One-sided Wilcoxon signed-rank test (H1: median > 0).

    Returns (W_statistic, p_value). Uses normal approximation for n>=10.
    W = sum of ranks of |delta| for positive deltas (large W => degradation).
    """
    # drop exact zeros (standard signed-rank practice)
    vals = [d for d in delta_r if d != 0.0]
    n = len(vals)
    if n < 10:
        return 0.0, 1.0
    ordered = sorted(range(n), key=lambda i: abs(vals[i]))
    # average ranks for ties on |delta|
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
    # one-sided H1: median > 0 → large W+; use upper-tail on W+
    mu = n * (n + 1) / 4.0
    sigma = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0)
    if sigma == 0:
        return w_pos, 1.0
    z = (w_pos - mu) / sigma

    def norm_sf(z: float) -> float:
        """P(Z > z) for standard normal."""
        return 0.5 * (1.0 - math.erf(z / math.sqrt(2)))

    p = norm_sf(z)  # upper tail: evidence for W+ larger than null
    return w_pos, p


def kruskal_wallis(groups: List[List[float]]) -> float:
    """Kruskal-Wallis H-test omnibus p-value (chi2 approximation)."""
    flat = []
    for g in groups:
        flat.extend(g)
    n = len(flat)
    if n == 0:
        return 1.0
    order = sorted(range(n), key=lambda i: flat[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n - 1 and flat[order[j]] == flat[order[j + 1]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    offsets = [0]
    for g in groups:
        offsets.append(offsets[-1] + len(g))
    group_ranks = [ranks[offsets[k]:offsets[k + 1]] for k in range(len(groups))]

    def h_stat():
        n_tot = n
        term = 0.0
        for gr in group_ranks:
            if not gr:
                continue
            r_bar = sum(gr) / len(gr)
            term += len(gr) * (r_bar - (n_tot + 1) / 2.0) ** 2
        return 12.0 / (n_tot * (n_tot + 1)) * term

    H = h_stat()
    k = len(groups)

    def chi2_sf(x, df):
        if x <= 0:
            return 1.0
        z = (((x / df) ** (1.0 / 3.0)) - (1.0 - 2.0 / (9.0 * df))) / math.sqrt(2.0 / (9.0 * df))

        def norm_sf(z):
            if z <= 0:
                return 0.5
            p = 0.3275911
            a1, a2, a3, a4, a5 = (0.254829592, -0.284496736, 1.421413741,
                                   -1.453152027, 1.061405429)
            t = 1.0 / (1.0 + p * z)
            return 0.5 * (((((a5 * t + a4) * t + a3) * t + a2) * t + a1)
                          * t * math.exp(-z * z / 2.0))

        return norm_sf(z)

    return chi2_sf(H, k - 1)


def analyze(results: List[StressRunResult]) -> Dict[str, object]:
    by_type: Dict[str, List[float]] = {}
    for r in results:
        by_type.setdefault(r.stress_type, []).append(r.delta_r)

    h1_results = {}
    for stype, deltas in by_type.items():
        w, p = wilcoxon_one_sided(deltas)
        mean_delta = statistics.mean(deltas) if deltas else 0.0
        h1_results[stype] = {
            "mean_delta_r": round(mean_delta, 4),
            "wilcoxon_W": round(w, 2),
            "wilcoxon_p": round(p, 4),
            "h1_status": ("CONFIRMED" if (mean_delta > 0 and p < ALPHA)
                          else "NOT_CONFIRMED"),
        }

    groups = [by_type[st] for st in STRESS_TYPES if st in by_type]
    kw_p = kruskal_wallis(groups) if len(groups) >= 2 else 1.0
    h2_status = "CONFIRMED" if kw_p < 0.05 else "NOT_CONFIRMED"

    return {
        "n_seeds": N_SEEDS,
        "n_stress_types": len(STRESS_TYPES),
        "h1_degradation": h1_results,
        "h2_distinguishability": {
            "kruskal_wallis_p": round(kw_p, 4),
            "h2_status": h2_status,
        },
        "runs": [
            {
                "seed": r.seed, "stress_type": r.stress_type,
                "r_normal": r.r_normal, "p_normal": r.p_normal,
                "status_normal": r.status_normal,
                "r_stress": r.r_stress, "p_stress": r.p_stress,
                "status_stress": r.status_stress,
                "delta_r": r.delta_r,
            }
            for r in results
        ],
    }


def main():
    results: List[StressRunResult] = []
    for seed in range(N_SEEDS):
        for stype in STRESS_TYPES:
            print(f"Running seed={seed} stress={stype}...", end=" ", flush=True)
            r = run_one(seed, stype)
            print(f"ΔR={r.delta_r:+.4f}")
            results.append(r)

    analysis = analyze(results)
    print("\n" + "=" * 70)
    print("H1 DEGRADATION (ΔR > 0, one-sided Wilcoxon, α=0.01):")
    for stype, h1 in analysis["h1_degradation"].items():
        print(f"  {stype:20s}: ΔR={h1['mean_delta_r']:+.4f}  "
              f"p={h1['wilcoxon_p']:.4f}  -> {h1['h1_status']}")

    print("\nH2 DISTINGUISHABILITY (Kruskal-Wallis, p<0.05):")
    h2 = analysis["h2_distinguishability"]
    print(f"  Kruskal-Wallis p={h2['kruskal_wallis_p']:.4f}  -> {h2['h2_status']}")
    print("=" * 70)

    output_path = "ci_stress_study_results.json"
    with open(output_path, "w") as f:
        json.dump(analysis, f, indent=2, default=str)
    print(f"\nFull results saved to {output_path}")


if __name__ == "__main__":
    main()
