"""Rescue density study (Option B): does coordination scale with interaction density?

Pre-registered design:
  - 10 seeds x 4 density levels (mean_interval_s in {15, 25, 40, 70}) = 40 runs
  - Same parameter set otherwise: duration=600, dt=1, coupling=0.30, alpha=0.01
  - Per run: R, p, detected, assigned, served, msgs
  - Primary analysis: Spearman R ~ log(1/interval), one-sided, alpha=0.01
  - Secondary: Kruskal-Wallis across the 4 levels (omnibus)
  - Secondary variant: same grid with enable_clearance=True (RoE impact at scale)

Outcome is reported honestly, whether it confirms or falsifies the density hypothesis.
"""
from __future__ import annotations

import json
import math
import os
import statistics
import sys
from dataclasses import dataclass
from typing import Dict, List

# Allow `python3 scripts/study_rescue_density.py` from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.rescue.simulation import RescueSimulation

SEEDS = list(range(10))
INTERVALS = [15.0, 25.0, 40.0, 70.0]     # seconds between damage reports
DURATION = 600.0
DT = 1.0
COUPLING = 0.30
ALPHA = 0.01


@dataclass
class RunResult:
    seed: int
    interval_s: float
    enable_clearance: bool
    detected: int
    assigned: int
    served: int
    messages: int
    r: float
    p: float
    status: str


def run_one(seed: int, interval_s: float, enable_clearance: bool) -> RunResult:
    # ClearanceGate must be created in __init__ (setting the flag later is a no-op)
    sim = RescueSimulation(seed=seed, duration_s=DURATION, dt=DT,
                           coupling=COUPLING, enable_clearance=enable_clearance)
    # override the scenario generator's mean interval (independent RNG stream)
    sim.scenario.mean_interval_s = interval_s
    report = sim.run()
    coord = report["coordination"]
    cons = report["conservation"]
    return RunResult(
        seed=seed,
        interval_s=interval_s,
        enable_clearance=enable_clearance,
        detected=cons["detected"],
        assigned=cons["assigned"],
        served=cons["served"],
        messages=report["messages_delivered"],
        r=float(coord.get("r_observed", 0.0)),
        p=float(coord.get("p_value", 1.0)),
        status=str(coord.get("status")),
    )


def spearman(x: List[float], y: List[float]) -> tuple:
    """Spearman rank correlation with a one-sided p-value (H1: rho>0).

    Uses the t-approximation for n>=10. Returns (rho, p_one_sided).
    """
    n = len(x)
    assert n == len(y) and n >= 10

    def rank(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j < n - 1 and v[order[j]] == v[order[j + 1]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx = rank(x); ry = rank(y)
    mx = statistics.mean(rx); my = statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if dx == 0 or dy == 0:
        return 0.0, 1.0
    rho = num / (dx * dy)
    # Exact |ρ|=1: t → ∞; handle before division by (1−ρ²)
    if rho >= 1.0 - 1e-12:
        return 1.0, 0.0
    if rho <= -1.0 + 1e-12:
        return -1.0, 1.0

    # t-approximation → normal CDF for one-sided H1: ρ>0
    t_stat = rho * math.sqrt((n - 2) / (1.0 - rho * rho))
    z = t_stat / math.sqrt(1.0 + t_stat * t_stat / (n - 2)) if n > 30 else t_stat

    def phi_cdf(z: float) -> float:
        """Standard normal CDF Φ(z) via Abramowitz–Stegun 7.1.26."""
        if z < 0:
            return 1.0 - phi_cdf(-z)
        p = 0.3275911
        a1, a2, a3, a4, a5 = (0.254829592, -0.284496736, 1.421413741,
                               -1.453152027, 1.061405429)
        tt = 1.0 / (1.0 + p * z)
        poly = ((((a5 * tt + a4) * tt + a3) * tt + a2) * tt + a1) * tt
        return 1.0 - poly * math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)

    p_two = 2.0 * (1.0 - phi_cdf(abs(z)))
    p_one = p_two / 2.0 if rho > 0 else 1.0 - p_two / 2.0
    return rho, p_one


def kruskal_wallis(groups: List[List[float]]) -> float:
    """Kruskal-Wallis H-test omnibus p-value (chi2 approximation)."""
    flat = []
    for g in groups:
        flat.extend(g)
    n = len(flat)
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

    # conservative chi2 upper tail approximation
    def chi2_sf(x, df):
        # Wilson-Hilferty -> normal, then normal tail
        if x <= 0:
            return 1.0
        z = (((x / df) ** (1.0 / 3.0)) - (1.0 - 2.0 / (9.0 * df))) / math.sqrt(2.0 / (9.0 * df))
        # normal upper tail via Abramowitz-Stegun
        if z <= 0:
            return 0.5
        p = 0.3275911
        a1, a2, a3, a4, a5 = (0.254829592, -0.284496736, 1.421413741,
                               -1.453152027, 1.061405429)
        t = 1.0 / (1.0 + p * z)
        return 0.5 * (((((a5 * t + a4) * t + a3) * t + a2) * t + a1)
                      * t * math.exp(-z * z / 2.0))

    return chi2_sf(H, k - 1)


def analyze(results: List[RunResult]) -> Dict[str, object]:
    x = [math.log(1.0 / r.interval_s) for r in results]
    y = [r.r for r in results]
    rho, p_one = spearman(x, y)
    groups: Dict[float, List[float]] = {}
    for r in results:
        groups.setdefault(r.interval_s, []).append(r.r)
    group_order = [groups[i] for i in sorted(groups)]
    kw_p = kruskal_wallis(group_order)
    confirmed = (rho > 0 and p_one < ALPHA) and (kw_p < 0.05)
    return {
        "n_runs": len(results),
        "spearman_rho": round(rho, 4),
        "spearman_p_one_sided": round(p_one, 4),
        "kruskal_p": round(kw_p, 4),
        "alpha": ALPHA,
        "verdict": "CONFIRMED" if confirmed else "NOT_CONFIRMED",
        "interpretation": (
            "R steigt signifikant mit der Interaktionsdichte "
            "(Spearman + omnibus beide signifikant)."
            if confirmed else
            "Kein robuster Beleg für die Dichte-Hypothese."
        ),
        # per-level means for honest inspection (saturation / collapse)
        "mean_r_by_interval": {
            str(iv): round(statistics.mean(groups[iv]), 4)
            for iv in sorted(groups)
        },
        "mean_detected_by_interval": {
            str(iv): round(statistics.mean(
                [r.detected for r in results if r.interval_s == iv]), 1)
            for iv in sorted(groups)
        },
    }


def main():
    results: List[RunResult] = []
    for gate in (False, True):
        for interval in INTERVALS:
            for seed in SEEDS:
                results.append(run_one(seed, interval, gate))
                print(f"# done seed={seed} interval={interval} clearance={gate}",
                      file=sys.stderr, flush=True)
    base = [r for r in results if not r.enable_clearance]
    gate = [r for r in results if r.enable_clearance]
    a_base = analyze(base)
    a_gate = analyze(gate)
    out = {
        "design": {
            "seeds": len(SEEDS), "intervals_s": INTERVALS,
            "duration_s": DURATION, "coupling": COUPLING, "alpha": ALPHA,
        },
        "baseline": a_base,
        "with_clearance": a_gate,
        "runs": [
            {"seed": r.seed, "interval_s": r.interval_s,
             "clearance": r.enable_clearance,
             "detected": r.detected, "assigned": r.assigned, "served": r.served,
             "messages": r.messages, "r": r.r, "p": r.p, "status": r.status}
            for r in results
        ],
    }
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
