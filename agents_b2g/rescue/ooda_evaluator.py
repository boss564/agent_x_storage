"""OODA-Kuramoto coordination evaluator for the rescue swarm.

Measures whether units act in a coordinated OODA phase (closed
sensor-to-rescue loop). Null hypothesis: per-unit phase-offset shuffle
(analogous to IFI-Shuffle for point processes) -- NOT IAAFT, which can
artifact on periodic signals (lesson from the Wirtschafts-Schwarm dossier).
"""
from __future__ import annotations

import math
import random
from typing import Dict, List


def order_parameter(phases: Dict[str, float]) -> float:
    """Kuramoto R = |mean(exp(i*theta))| over unit phases."""
    if not phases:
        return 0.0
    re = sum(math.cos(p) for p in phases.values()) / len(phases)
    im = sum(math.sin(p) for p in phases.values()) / len(phases)
    return math.sqrt(re * re + im * im)


def evaluate_coordination(units: Dict[str, "RescueUnit"],
                          n_surrogates: int = 500,
                          alpha: float = 0.01,
                          seed: int = 42) -> Dict[str, object]:
    """Observed R vs. phase-offset-shuffle surrogates. Returns verdict."""
    phases = {uid: u.ooda_phase for uid, u in units.items()
              if u.state.value == "operational"}
    if len(phases) < 2:
        return {"status": "insufficient_units", "n": len(phases)}

    r_obs = order_parameter(phases)
    rng = random.Random(seed)
    two_pi = 2 * math.pi
    r_surr: List[float] = []
    for _ in range(n_surrogates):
        # preserve each unit's period, randomize relative phase offset
        shuffled = {uid: rng.uniform(0.0, two_pi) for uid in phases}
        r_surr.append(order_parameter(shuffled))

    # +1 Monte-Carlo correction (no p=0.0000 reporting)
    exceed = sum(1 for r in r_surr if r >= r_obs)
    p = (exceed + 1) / (n_surrogates + 1)
    coupled = p < alpha
    return {
        "r_observed": round(r_obs, 4),
        "p_value": round(p, 4),
        "n_units": len(phases),
        "n_surrogates": n_surrogates,
        "status": "COORDINATED" if coupled else "UNCOORDINATED",
        "verdict": ("echte Kohäsion (geschlossener Sensor-to-Rescue-Loop)"
                    if coupled else "zersplitterter Wirkverbund"),
    }
