"""OODA-Kuramoto evaluator for the CI swarm (phase-offset-shuffle null).

Null hypothesis: phase-offset-shuffle — each unit's recorded phase trajectory
is shifted by a random CONSTANT offset. This preserves each unit's period and
internal dynamics but randomizes the relative alignment between units.
NOT IAAFT (periodic-signal artifact lesson from the Wirtschafts/Rescue dossiers).
"""
from __future__ import annotations

import math
import random
from typing import Dict, List

TWO_PI = 2 * math.pi


def order_parameter(phases: Dict[str, float]) -> float:
    if not phases:
        return 0.0
    re = sum(math.cos(p) for p in phases.values()) / len(phases)
    im = sum(math.sin(p) for p in phases.values()) / len(phases)
    return math.sqrt(re * re + im * im)


def r_over_time(phase_trajectories: Dict[str, List[float]]) -> List[float]:
    units = list(phase_trajectories.keys())
    if len(units) < 2:
        return []
    n_t = len(phase_trajectories[units[0]])
    return [order_parameter({u: phase_trajectories[u][t] for u in units})
            for t in range(n_t)]


def evaluate_h0(phase_trajectories: Dict[str, List[float]],
                n_surrogates: int = 500, alpha: float = 0.01,
                seed: int = 42) -> Dict[str, object]:
    """Time-averaged R + phase-offset-shuffle significance (+1 correction)."""
    units = list(phase_trajectories.keys())
    if len(units) < 2:
        return {"status": "insufficient_units", "n": len(units)}
    n_t = len(phase_trajectories[units[0]])
    if n_t == 0:
        return {"status": "no_timepoints"}

    r_obs_series = r_over_time(phase_trajectories)
    r_obs = sum(r_obs_series) / len(r_obs_series)

    rng = random.Random(seed)
    r_surr = []
    for _ in range(n_surrogates):
        offsets = {u: rng.uniform(0, TWO_PI) for u in units}
        shifted = {u: [(p + offsets[u]) % TWO_PI for p in phase_trajectories[u]]
                   for u in units}
        rs = r_over_time(shifted)
        r_surr.append(sum(rs) / len(rs))

    exceed = sum(1 for r in r_surr if r >= r_obs)
    p = (exceed + 1) / (n_surrogates + 1)          # +1 correction, never p=0
    return {
        "r_observed": round(r_obs, 4),
        "p_value": round(p, 4),
        "n_units": len(units),
        "n_timepoints": n_t,
        "n_surrogates": n_surrogates,
        "status": "COORDINATED" if p < alpha else "UNCOORDINATED",
    }
