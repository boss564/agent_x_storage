"""Unit tests for the smart grid H0 building blocks (fast; no full 1440-min runs)."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.smartgrid.agents import build_smartgrid_swarm, SMARTGRID_CYCLE_TIMES
from agents_b2g.smartgrid.simulation import SmartGridNormalSimulation, phase_pull
from agents_b2g.smartgrid.ooda_evaluator import evaluate_h0


def test_swarm_has_nine_units_three_classes():
    swarm = build_smartgrid_swarm()
    assert len(swarm) == 9
    assert {u.unit_class for u in swarm.values()} == {"A", "B", "C"}


def test_generators_are_class_a():
    swarm = build_smartgrid_swarm()
    gens = {u.unit_id for u in swarm.values() if u.unit_class == "A"}
    assert gens == {"pv_prosumer", "wind_turbine", "chp_agent"}


def test_cycle_time_spread():
    periods = sorted(SMARTGRID_CYCLE_TIMES.values())
    assert periods[0] == 3 and periods[-1] == 10


def test_jitter_varies_across_seeds():
    a = SmartGridNormalSimulation(seed=1, duration_s=10.0)
    b = SmartGridNormalSimulation(seed=2, duration_s=10.0)
    assert sorted(u.ooda_phase for u in a.units.values()) != \
           sorted(u.ooda_phase for u in b.units.values())


def test_jitter_within_5_percent():
    sim = SmartGridNormalSimulation(seed=3, duration_s=10.0)
    for uid, u in sim.units.items():
        base = SMARTGRID_CYCLE_TIMES[uid]
        assert base * 0.95 <= u.cycle_period_s <= base * 1.05


def test_phase_pull_wraps():
    two_pi = 2 * math.pi
    assert abs(phase_pull(0.1, two_pi - 0.1, 1.0) - (two_pi - 0.1)) < 1e-6
    assert abs(phase_pull(1.0, 3.0, 0.0) - 1.0) < 1e-6


def test_simulation_produces_generator_phases_and_w_dyn():
    sim = SmartGridNormalSimulation(seed=1, duration_s=200.0, t_warmup=50.0)
    phases = sim.run()
    assert len(phases) == 9                      # 3 agents x 3 inverters
    assert all(len(v) > 0 for v in phases.values())
    assert len(sim.w_dyn_records) > 0
    assert all(0.0 <= x <= 1.0 for x in sim.w_dyn_records)


def test_r_grid_evaluator_aligned_phases():
    traj = {f"gen{i}": [1.0, 1.0, 1.0, 1.0] for i in range(3)}
    res = evaluate_h0(traj, n_surrogates=200)
    assert res["r_observed"] > 0.99
    assert res["status"] == "COORDINATED"
