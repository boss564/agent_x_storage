"""Humanitarian stress study: 10 seeds x 3 stress types = 30 runs.

Pre-registered analysis (HUMANITAERE_LOGISTIK_PREREG.md):
  H1: ΔR = R_normal - R_stress > 0, one-sided Wilcoxon, alpha=0.01
  H2: Kruskal-Wallis across the 3 stress types, p<0.05
  H3: ΔQuote > 0 and/or ΔRT > 0, one-sided Wilcoxon, alpha=0.01
"""
import json
import math
import os
import statistics
import sys
from dataclasses import dataclass
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.humanitarian.simulation import HumanitarianStressSimulation
from agents_b2g.humanitarian.ooda_evaluator import evaluate_h0

ALPHA = 0.01
N_SEEDS = 10
STRESS_TYPES = ["hub_verlust", "nachbeben", "komm_kollaps"]
DURATION = 4320.0
T_WARMUP = 60.0
T_STRESS = 1440.0
BURN_IN = 60.0
COUPLING = 0.50


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
    quote_normal: float
    quote_stress: float
    delta_quote: float
    rt_normal: float
    rt_stress: float
    delta_rt: float


def run_one(seed: int, stress_type: str) -> StressRunResult:
    sim = HumanitarianStressSimulation(
        seed=seed, duration_s=DURATION, coupling=COUPLING,
        t_warmup=T_WARMUP, t_stress=T_STRESS, burn_in=BURN_IN,
        stress_type=stress_type,
    )
    result = sim.run()
    res_normal = evaluate_h0(result["normal"], alpha=ALPHA)
    res_stress = evaluate_h0(result["stress"], alpha=ALPHA)
    eff_normal = sim.compute_efficiency(T_WARMUP, T_STRESS)
    eff_stress = sim.compute_efficiency(T_STRESS + BURN_IN, DURATION)
    r_n = res_normal.get("r_observed", 0.0)
    r_s = res_stress.get("r_observed", 0.0)
    return StressRunResult(
        seed=seed, stress_type=stress_type,
        r_normal=r_n, p_normal=res_normal.get("p_value", 1.0),
        status_normal=res_normal.get("status", "UNKNOWN"),
        r_stress=r_s, p_stress=res_stress.get("p_value", 1.0),
        status_stress=res_stress.get("status", "UNKNOWN"),
        delta_r=r_n - r_s,
        quote_normal=eff_normal["quote"],
        quote_stress=eff_stress["quote"],
        delta_quote=eff_normal["quote"] - eff_stress["quote"],
        rt_normal=eff_normal["mean_rt"],
        rt_stress=eff_stress["mean_rt"],
        delta_rt=eff_stress["mean_rt"] - eff_normal["mean_rt"],
    )


def wilcoxon_one_sided(delta_r: List[float]) -> tuple:
    """One-sided Wilcoxon signed-rank test (H1: median > 0).

    Returns (W_statistic, p_value). Uses normal approximation for n>=10.
    W = sum of ranks of |delta| for positive deltas (large W => degradation).
    """
    vals = [d for d in delta_r if d != 0.0]
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
    mu = n * (n + 1) / 4.0
    sigma = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0)
    if sigma == 0:
        return w_pos, 1.0
    z = (w_pos - mu) / sigma

    def norm_sf(z: float) -> float:
        return 0.5 * (1.0 - math.erf(z / math.sqrt(2)))

    return w_pos, norm_sf(z)


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
        term = 0.0
        for gr in group_ranks:
            if not gr:
                continue
            r_bar = sum(gr) / len(gr)
            term += len(gr) * (r_bar - (n + 1) / 2.0) ** 2
        return 12.0 / (n * (n + 1)) * term

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
    by_type: Dict[str, List[StressRunResult]] = {}
    for r in results:
        by_type.setdefault(r.stress_type, []).append(r)

    h1_results = {}
    for stype, runs in by_type.items():
        deltas = [r.delta_r for r in runs]
        w, p = wilcoxon_one_sided(deltas)
        mean_delta = statistics.mean(deltas) if deltas else 0.0
        h1_results[stype] = {
            "mean_delta_r": round(mean_delta, 4),
            "wilcoxon_W": round(w, 2),
            "wilcoxon_p": round(p, 4),
            "h1_status": ("CONFIRMED" if (mean_delta > 0 and p < ALPHA)
                          else "NOT_CONFIRMED"),
        }

    groups = [[r.delta_r for r in by_type[st]] for st in STRESS_TYPES if st in by_type]
    kw_p = kruskal_wallis(groups) if len(groups) >= 2 else 1.0
    h2_status = "CONFIRMED" if kw_p < 0.05 else "NOT_CONFIRMED"

    h3_results = {}
    for stype, runs in by_type.items():
        delta_quotes = [r.delta_quote for r in runs]
        delta_rts = [r.delta_rt for r in runs]
        w_q, p_q = wilcoxon_one_sided(delta_quotes)
        w_rt, p_rt = wilcoxon_one_sided(delta_rts)
        mean_dq = statistics.mean(delta_quotes) if delta_quotes else 0.0
        mean_drt = statistics.mean(delta_rts) if delta_rts else 0.0
        h3_results[stype] = {
            "mean_delta_quote": round(mean_dq, 4),
            "quote_wilcoxon_p": round(p_q, 4),
            "mean_delta_rt": round(mean_drt, 2),
            "rt_wilcoxon_p": round(p_rt, 4),
            "h3_status": (
                "CONFIRMED"
                if ((mean_dq > 0 and p_q < ALPHA) or (mean_drt > 0 and p_rt < ALPHA))
                else "NOT_CONFIRMED"
            ),
        }

    return {
        "n_seeds": N_SEEDS,
        "n_stress_types": len(STRESS_TYPES),
        "h1_coordination_degradation": h1_results,
        "h2_distinguishability": {
            "kruskal_wallis_p": round(kw_p, 4),
            "h2_status": h2_status,
        },
        "h3_efficiency_degradation": h3_results,
        "runs": [
            {
                "seed": r.seed, "stress_type": r.stress_type,
                "r_normal": r.r_normal, "p_normal": r.p_normal,
                "status_normal": r.status_normal,
                "r_stress": r.r_stress, "p_stress": r.p_stress,
                "status_stress": r.status_stress,
                "delta_r": r.delta_r,
                "quote_normal": r.quote_normal, "quote_stress": r.quote_stress,
                "delta_quote": r.delta_quote,
                "rt_normal": r.rt_normal, "rt_stress": r.rt_stress,
                "delta_rt": r.delta_rt,
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
            print(f"ΔR={r.delta_r:+.4f} ΔQuote={r.delta_quote:+.4f} ΔRT={r.delta_rt:+.1f}")
            results.append(r)

    analysis = analyze(results)
    print("\n" + "=" * 70)
    print("H1 COORDINATION DEGRADATION (ΔR > 0, one-sided Wilcoxon, α=0.01):")
    for stype, h1 in analysis["h1_coordination_degradation"].items():
        print(f"  {stype:20s}: ΔR={h1['mean_delta_r']:+.4f}  "
              f"p={h1['wilcoxon_p']:.4f}  -> {h1['h1_status']}")

    print("\nH2 DISTINGUISHABILITY (Kruskal-Wallis, p<0.05):")
    h2 = analysis["h2_distinguishability"]
    print(f"  Kruskal-Wallis p={h2['kruskal_wallis_p']:.4f}  -> {h2['h2_status']}")

    print("\nH3 EFFICIENCY DEGRADATION (ΔQuote > 0 or ΔRT > 0, α=0.01):")
    for stype, h3 in analysis["h3_efficiency_degradation"].items():
        print(f"  {stype:20s}: ΔQuote={h3['mean_delta_quote']:+.4f} "
              f"(p={h3['quote_wilcoxon_p']:.4f})  "
              f"ΔRT={h3['mean_delta_rt']:+.1f} (p={h3['rt_wilcoxon_p']:.4f})  "
              f"-> {h3['h3_status']}")
    print("=" * 70)

    output_path = "hum_stress_study_results.json"
    with open(output_path, "w") as f:
        json.dump(analysis, f, indent=2, default=str)
    print(f"\nFull results saved to {output_path}")


if __name__ == "__main__":
    main()
