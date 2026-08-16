"""Unit tests for the humanitarian H0 building blocks (fast; no full 1440-min runs)."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.humanitarian.agents import build_humanitarian_swarm, HUM_CYCLE_TIMES
from agents_b2g.humanitarian.simulation import HumanitarianNormalSimulation, phase_pull
from agents_b2g.humanitarian.ooda_evaluator import evaluate_h0


def test_swarm_has_nine_units_three_classes():
    swarm = build_humanitarian_swarm()
    assert len(swarm) == 9
    assert {u.unit_class for u in swarm.values()} == {"A", "B", "C"}


def test_cycle_time_spread_3_to_1():
    periods = sorted(HUM_CYCLE_TIMES.values())
    assert periods[0] == 10 and periods[-1] == 30   # 3:1 spread per prereg


def test_jitter_applied_and_varies_across_seeds():
    """Different seeds must produce different initial phases / cycle times."""
    sim_a = HumanitarianNormalSimulation(seed=1, duration_s=10.0)
    sim_b = HumanitarianNormalSimulation(seed=2, duration_s=10.0)
    phases_a = [u.ooda_phase for u in sim_a.units.values()]
    phases_b = [u.ooda_phase for u in sim_b.units.values()]
    assert phases_a != phases_b   # jitter varies across seeds


def test_jitter_deterministic_per_seed():
    """Same seed must produce identical jitter (reproducible)."""
    sim_a = HumanitarianNormalSimulation(seed=5, duration_s=10.0)
    sim_b = HumanitarianNormalSimulation(seed=5, duration_s=10.0)
    periods_a = sorted(u.cycle_period_s for u in sim_a.units.values())
    periods_b = sorted(u.cycle_period_s for u in sim_b.units.values())
    assert periods_a == periods_b


def test_jitter_within_10_percent():
    """Cycle-time jitter must stay within +/-10% of the calibrated value."""
    sim = HumanitarianNormalSimulation(seed=3, duration_s=10.0)
    for uid, u in sim.units.items():
        base = HUM_CYCLE_TIMES[uid]
        assert base * 0.9 <= u.cycle_period_s <= base * 1.1


def test_phase_pull_wraps():
    two_pi = 2 * math.pi
    assert abs(phase_pull(0.1, two_pi - 0.1, 1.0) - (two_pi - 0.1)) < 1e-6
    assert abs(phase_pull(1.0, 3.0, 0.0) - 1.0) < 1e-6


def test_evaluator_aligned_phases_coordinated():
    traj = {f"u{i}": [1.0, 1.0, 1.0, 1.0] for i in range(9)}
    res = evaluate_h0(traj, n_surrogates=200)
    assert res["r_observed"] > 0.99
    assert res["status"] == "COORDINATED"


def test_simulation_produces_trajectories():
    sim = HumanitarianNormalSimulation(seed=1, duration_s=200.0, t_warmup=50.0)
    traj = sim.run()
    assert len(traj) == 9
    assert all(len(v) > 0 for v in traj.values())


def test_all_agents_receive_messages():
    """Every agent must receive at least one message (phase-pull participation)."""
    sim = HumanitarianNormalSimulation(seed=1, duration_s=200.0, t_warmup=50.0)
    sim.run()
    for uid, u in sim.units.items():
        assert len(u.inbox) > 0, f"{uid} receives no messages (phase never pulled)"
