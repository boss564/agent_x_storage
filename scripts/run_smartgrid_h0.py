"""Smart Grid H0 gate: 10 seeds, normal operation, R_grid + W_dyn measurement validity.

Pre-registered rule (SMART_GRID_PREREG.md):
  H0a: R_grid above phase-offset-shuffle null (p < alpha=0.01) in >= 7/10 seeds.
  H0b: W_dyn in valid range (0 < W_dyn <= 1) and varies with simulation dynamics.
  H0 PASSES if H0a AND H0b.  NOT an R->1 test.
"""
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.smartgrid.simulation import SmartGridNormalSimulation
from agents_b2g.smartgrid.ooda_evaluator import evaluate_h0

ALPHA = 0.01
N_SEEDS = 10
GATE_THRESHOLD = 7
W_DYN_STD_THRESHOLD = 0.005


def run_h0_gate(n_seeds: int = N_SEEDS, duration_s: float = 1440.0,
                grid_coupling: float = 0.60):
    print(f"CONFIG: smart grid H0 | grid_coupling={grid_coupling} | alpha={ALPHA} | "
          f"gate>={GATE_THRESHOLD}/{n_seeds} | jitter=+/-5% | lambda=0")
    r_grid_significant = 0
    w_dyn_valid = 0
    for seed in range(n_seeds):
        sim = SmartGridNormalSimulation(seed=seed, duration_s=duration_s,
                                        grid_coupling=grid_coupling)
        gen_phases = sim.run()
        res = evaluate_h0(gen_phases, alpha=ALPHA)
        r_sig = res.get("status") == "COORDINATED"
        if r_sig:
            r_grid_significant += 1
        w = sim.w_dyn_records
        w_ok = (len(w) > 0 and all(0.0 <= x <= 1.0 for x in w)
                and statistics.stdev(w) > W_DYN_STD_THRESHOLD)
        if w_ok:
            w_dyn_valid += 1
        print(f"seed={seed:2d}  R_grid={res.get('r_observed')}  p={res.get('p_value')}  "
              f"{'COORD' if r_sig else 'UNCOORD'}  "
              f"W_dyn_mean={statistics.mean(w):.3f}  W_dyn_std={statistics.stdev(w):.4f}  "
              f"{'VALID' if w_ok else 'INVALID'}")
    h0a = r_grid_significant >= GATE_THRESHOLD
    h0b = w_dyn_valid >= GATE_THRESHOLD
    print(f"\nH0a (R_grid above null): {r_grid_significant}/{n_seeds} ({'PASS' if h0a else 'FAIL'})")
    print(f"H0b (W_dyn valid+varying): {w_dyn_valid}/{n_seeds} ({'PASS' if h0b else 'FAIL'})")
    print(f"H0 GATE: {'PASSES -> proceed to stress study' if (h0a and h0b) else 'FAILS -> DESIGN STOP, recalibrate'}")
    return h0a and h0b


if __name__ == "__main__":
    run_h0_gate()
