"""Unit tests for the CI H0 building blocks (fast; the 10-seed gate is run_ci_h0.py)."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.ci.agents import build_ci_swarm
from agents_b2g.ci.simulation import CINormalSimulation, phase_pull
from agents_b2g.ci.ooda_evaluator import evaluate_h0


def test_swarm_has_nine_units_three_classes():
    swarm = build_ci_swarm()
    assert len(swarm) == 9
    assert {u.unit_class for u in swarm.values()} == {"A", "B", "C"}


def test_cycle_time_spread():
    swarm = build_ci_swarm()
    periods = sorted(u.cycle_period_s for u in swarm.values())
    assert periods[0] == 1.0 and periods[-1] == 10.0   # 10x spread as designed


def test_phase_pull_wraps():
    two_pi = 2 * math.pi
    assert abs(phase_pull(0.1, two_pi - 0.1, 1.0) - (two_pi - 0.1)) < 1e-6
    assert abs(phase_pull(1.0, 3.0, 0.0) - 1.0) < 1e-6


def test_evaluator_aligned_phases_coordinated():
    traj = {f"u{i}": [1.0, 1.0, 1.0, 1.0] for i in range(9)}   # identical phases
    res = evaluate_h0(traj, n_surrogates=200)
    assert res["r_observed"] > 0.99
    assert res["status"] == "COORDINATED"


def test_evaluator_random_phases_uncoordinated():
    import random
    rng = random.Random(7)
    traj = {f"u{i}": [rng.uniform(0, 2 * math.pi) for _ in range(50)] for i in range(9)}
    res = evaluate_h0(traj, n_surrogates=200)
    assert res["status"] == "UNCOORDINATED"


def test_normal_simulation_produces_trajectories():
    sim = CINormalSimulation(seed=1, duration_s=120.0, t_warmup=20.0)
    traj = sim.run()
    assert len(traj) == 9
    assert all(len(v) > 0 for v in traj.values())
    assert all(len(v) == len(next(iter(traj.values()))) for v in traj.values())
