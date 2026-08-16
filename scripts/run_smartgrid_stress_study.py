"""Smart Grid stress study: 10 seeds x 3 stress types = 30 runs.

Pre-registered analysis (SMART_GRID_PREREG.md):
  H1 (Intersection-Union): H1a ΔR_grid<0 Wilcoxon α=0.01; H1b median ΔW≥0 + ≥7/10
  H2: Kruskal-Wallis on ΔR_grid across stress types, p<0.05
  H3: descriptive lever attribution
"""
import json
import math
import os
import statistics
import sys
from dataclasses import dataclass
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.smartgrid.simulation import SmartGridStressSimulation
from agents_b2g.smartgrid.ooda_evaluator import evaluate_h0

ALPHA = 0.01
N_SEEDS = 10
STRESS_TYPES = ["bewoelkung", "spitzenlast", "leitungsausfall"]
DURATION = 4320.0
T_WARMUP = 60.0
T_STRESS = 1440.0
BURN_IN = 60.0
GRID_COUPLING = 0.60


@dataclass
class StressRunResult:
    seed: int
    stress_type: str
    r_grid_normal: float
    p_grid_normal: float
    status_grid_normal: str
    r_grid_stress: float
    p_grid_stress: float
    status_grid_stress: str
    delta_r_grid: float
    w_dyn_normal: float
    w_dyn_stress: float
    delta_w_dyn: float


def run_one(seed: int, stress_type: str) -> StressRunResult:
    sim = SmartGridStressSimulation(
        seed=seed, duration_s=DURATION, grid_coupling=GRID_COUPLING,
        t_warmup=T_WARMUP, t_stress=T_STRESS, burn_in=BURN_IN,
        stress_type=stress_type,
    )
    result = sim.run()
    res_normal = evaluate_h0(result["normal"], alpha=ALPHA)
    res_stress = evaluate_h0(result["stress"], alpha=ALPHA)
    eff_normal = sim.compute_efficiency("normal")
    eff_stress = sim.compute_efficiency("stress")
    r_n = res_normal.get("r_observed", 0.0)
    r_s = res_stress.get("r_observed", 0.0)
    w_n = eff_normal["mean_w_dyn"]
    w_s = eff_stress["mean_w_dyn"]
    return StressRunResult(
        seed=seed, stress_type=stress_type,
        r_grid_normal=r_n, p_grid_normal=res_normal.get("p_value", 1.0),
        status_grid_normal=res_normal.get("status", "UNKNOWN"),
        r_grid_stress=r_s, p_grid_stress=res_stress.get("p_value", 1.0),
        status_grid_stress=res_stress.get("status", "UNKNOWN"),
        delta_r_grid=r_s - r_n,
        w_dyn_normal=w_n, w_dyn_stress=w_s, delta_w_dyn=w_s - w_n,
    )


def wilcoxon_one_sided(values: List[float], alternative: str = "less") -> tuple:
    """One-sided Wilcoxon signed-rank (CI-study form: ranks on |delta|, upper-tail)."""
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
    # less: large W-; greater: large W+
    w = w_neg if alternative == "less" else w_pos
    z = (w - mu) / sigma

    def norm_sf(z: float) -> float:
        return 0.5 * (1.0 - math.erf(z / math.sqrt(2)))

    return w, norm_sf(z)


def kruskal_wallis(groups: List[List[float]]) -> float:
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

    term = 0.0
    for gr in group_ranks:
        if not gr:
            continue
        r_bar = sum(gr) / len(gr)
        term += len(gr) * (r_bar - (n + 1) / 2.0) ** 2
    H = 12.0 / (n * (n + 1)) * term
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
    by_type: Dict[str, List[StressRunResult]] = {}
    for r in results:
        by_type.setdefault(r.stress_type, []).append(r)

    h1_results = {}
    for stype, runs in by_type.items():
        delta_r = [r.delta_r_grid for r in runs]
        delta_w = [r.delta_w_dyn for r in runs]
        w_r, p_r = wilcoxon_one_sided(delta_r, alternative="less")
        h1a_pass = p_r < ALPHA
        median_w = statistics.median(delta_w) if delta_w else 0.0
        n_nonneg = sum(1 for d in delta_w if d >= 0)
        h1b_pass = (median_w >= 0 and n_nonneg >= 7)
        h1_pass = h1a_pass and h1b_pass
        h1_results[stype] = {
            "mean_delta_r_grid": round(statistics.mean(delta_r) if delta_r else 0.0, 4),
            "wilcoxon_r_W": round(w_r, 2),
            "wilcoxon_r_p": round(p_r, 4),
            "h1a_status": "CONFIRMED" if h1a_pass else "NOT_CONFIRMED",
            "median_delta_w_dyn": round(median_w, 4),
            "n_seeds_w_dyn_geq_0": n_nonneg,
            "h1b_status": "CONFIRMED" if h1b_pass else "NOT_CONFIRMED",
            "h1_status": "CONFIRMED" if h1_pass else "NOT_CONFIRMED",
        }

    groups = [[r.delta_r_grid for r in by_type[st]] for st in STRESS_TYPES if st in by_type]
    kw_p = kruskal_wallis(groups) if len(groups) >= 2 else 1.0
    h2_status = "CONFIRMED" if kw_p < 0.05 else "NOT_CONFIRMED"

    h3_attribution = {
        "bewoelkung": "Schattenpreise + Speicher-Dispatch",
        "spitzenlast": "Flexibilitaet + Lastverschiebung",
        "leitungsausfall": "Hebb'sches Um-Routing + Curtailment",
    }

    return {
        "n_seeds": N_SEEDS,
        "n_stress_types": len(STRESS_TYPES),
        "h1_meta_stability": h1_results,
        "h2_distinguishability": {
            "kruskal_wallis_p": round(kw_p, 4),
            "h2_status": h2_status,
        },
        "h3_lever_attribution": h3_attribution,
        "runs": [
            {
                "seed": r.seed, "stress_type": r.stress_type,
                "r_grid_normal": r.r_grid_normal, "p_grid_normal": r.p_grid_normal,
                "status_grid_normal": r.status_grid_normal,
                "r_grid_stress": r.r_grid_stress, "p_grid_stress": r.p_grid_stress,
                "status_grid_stress": r.status_grid_stress,
                "delta_r_grid": r.delta_r_grid,
                "w_dyn_normal": r.w_dyn_normal, "w_dyn_stress": r.w_dyn_stress,
                "delta_w_dyn": r.delta_w_dyn,
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
            print(f"ΔR_grid={r.delta_r_grid:+.4f} ΔW_dyn={r.delta_w_dyn:+.4f}")
            results.append(r)

    analysis = analyze(results)
    print("\n" + "=" * 70)
    print("H1 META-STABILITY (Intersection-Union-Test, α=0.01):")
    for stype, h1 in analysis["h1_meta_stability"].items():
        print(f"  {stype:20s}:")
        print(f"    H1a (ΔR_grid<0): ΔR={h1['mean_delta_r_grid']:+.4f}  "
              f"p={h1['wilcoxon_r_p']:.4f}  -> {h1['h1a_status']}")
        print(f"    H1b (ΔW_dyn≥0): median={h1['median_delta_w_dyn']:+.4f}  "
              f"{h1['n_seeds_w_dyn_geq_0']}/10 seeds ≥0  -> {h1['h1b_status']}")
        print(f"    H1 (Konjunktion): {h1['h1_status']}")

    print("\nH2 DISTINGUISHABILITY (Kruskal-Wallis, p<0.05):")
    h2 = analysis["h2_distinguishability"]
    print(f"  Kruskal-Wallis p={h2['kruskal_wallis_p']:.4f}  -> {h2['h2_status']}")

    print("\nH3 LEVER ATTRIBUTION (deskriptiv):")
    for stype, lever in analysis["h3_lever_attribution"].items():
        print(f"  {stype:20s} -> {lever}")
    print("=" * 70)

    output_path = "smartgrid_stress_study_results.json"
    with open(output_path, "w") as f:
        json.dump(analysis, f, indent=2, default=str)
    print(f"\nFull results saved to {output_path}")


if __name__ == "__main__":
    main()
