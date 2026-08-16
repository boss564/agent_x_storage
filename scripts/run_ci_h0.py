"""CI H0 gate: 10 seeds, normal operation, R via phase-offset-shuffle.

Pre-registered rule (CI_RESILIENZ_STUDIE_PREREG.md):
  H0 passes if >= 7/10 seeds show significant R (p < alpha=0.01).
  H0 fails -> DESIGN STOP, no stress spend.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.ci.simulation import CINormalSimulation
from agents_b2g.ci.ooda_evaluator import evaluate_h0

ALPHA = 0.01
N_SEEDS = 10
GATE_THRESHOLD = 7


def run_h0_gate(n_seeds: int = N_SEEDS, duration_s: float = 600.0,
                coupling: float = 0.30):
    significant = 0
    for seed in range(n_seeds):
        sim = CINormalSimulation(seed=seed, duration_s=duration_s, coupling=coupling)
        trajectories = sim.run()
        res = evaluate_h0(trajectories, alpha=ALPHA)
        if res.get("status") == "COORDINATED":
            significant += 1
        print(f"seed={seed:2d}  R={res.get('r_observed')}  "
              f"p={res.get('p_value')}  {res.get('status')}")
    gate_passed = significant >= GATE_THRESHOLD
    print(f"\nH0 GATE: {significant}/{n_seeds} coordinated "
          f"(threshold {GATE_THRESHOLD}/{n_seeds})")
    print(f"H0 {'PASSES -> proceed to stress study' if gate_passed else 'FAILS -> DESIGN STOP, no stress spend'}")
    return gate_passed


if __name__ == "__main__":
    run_h0_gate()
