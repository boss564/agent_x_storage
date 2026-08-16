"""IFI-Shuffle cross-check for the Wirtschafts-Schwarm COUPLED result (Baustein 5).

Uses the same event-based phase estimator and IFI-shuffle null as
agents_b2g/emergence/measure.py (firing_phase / surrogate_ifi_shuffle /
kuramoto_r_nan), with Monte-Carlo +1 correction.

This is the natural null for point processes; IAAFT (AstroCore primary path)
preserves the power spectrum and can be confounded by the simulation's
fixed natural frequencies (2/3/4).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from agents_b2g.wirtschaft.simulation import WirtschaftsSimulation
from agents_b2g.emergence.measure import (
    firing_phase,
    kuramoto_r_nan,
    surrogate_ifi_shuffle,
)


def cross_check(ticks: int = 200, n_surrogates: int = 500,
                seed: int = 42, min_firings: int = 3, alpha: float = 0.01):
    sim = WirtschaftsSimulation(ticks=ticks)
    events = sim.run()
    logs = {
        aid: np.asarray(ts, dtype=float)
        for aid, ts in events.items()
        if len(ts) >= min_firings
    }
    if len(logs) < 2:
        raise ValueError(f"fewer than 2 agents with ≥{min_firings} events")

    # Simulation ticks are 0-indexed; match event timestamps on the grid
    t_grid = np.arange(0, ticks, dtype=float)
    agent_fts = list(logs.values())

    phases_rows = []
    for ft in agent_fts:
        th = firing_phase(ft, t_grid)
        if th is not None:
            phases_rows.append(th)
    if len(phases_rows) < 2:
        raise ValueError("phase matrix < 2 agents")

    _, r_obs = kuramoto_r_nan(np.array(phases_rows, dtype=float))
    if not np.isfinite(r_obs):
        raise ValueError("r_obs undefined (insufficient phase overlap)")

    rng = np.random.default_rng(seed)
    r_surr = np.empty(n_surrogates)
    for s in range(n_surrogates):
        ph = []
        for ft in agent_fts:
            th = surrogate_ifi_shuffle(ft, t_grid, rng)
            if th is None:
                th = np.full(len(t_grid), np.nan)
            ph.append(th)
        _, r_s = kuramoto_r_nan(np.array(ph, dtype=float))
        r_surr[s] = r_s if np.isfinite(r_s) else 0.0

    p = float((np.sum(r_surr >= r_obs) + 1) / (n_surrogates + 1))
    verdict = "COUPLED" if p < alpha else "NO_COUPLING"
    print(
        f"IFI-Shuffle: r_obs={r_obs:.3f}  p={p:.4f}  "
        f"surr_mean={float(np.nanmean(r_surr)):.3f}  "
        f"agents={len(agent_fts)}  ({verdict} vs IFI-Shuffle)"
    )
    return float(r_obs), p, verdict


if __name__ == "__main__":
    cross_check()
