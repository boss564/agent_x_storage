"""Unit tests for CI stress injectors (fast; no full 600s runs)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.ci.simulation import CIStressSimulation
from agents_b2g.ci.unit_base import UnitState


def test_blackout_stress_sets_unit_out_of_service():
    sim = CIStressSimulation(seed=1, duration_s=350.0, t_stress=300.0, stress_type="blackout")
    sim.run()
    assert sim.units["grid_controller"].state == UnitState.OUT_OF_SERVICE
    assert sim.units["grid_controller"]._stressed is True


def test_cyber_stress_sets_offset_and_noise():
    sim = CIStressSimulation(seed=1, duration_s=350.0, t_stress=300.0, stress_type="cyber")
    sim.run()
    sensor = sim.units["infra_sensor"]
    assert sensor._stressed is True
    assert hasattr(sensor, "_cyber_offset") and sensor._cyber_offset == 0.5
    assert hasattr(sensor, "_cyber_noise") and sensor._cyber_noise == 0.1


def test_naturkatastrophe_stress_degrades_multiple_units():
    sim = CIStressSimulation(seed=1, duration_s=350.0, t_stress=300.0,
                             stress_type="naturkatastrophe")
    sim.run()
    assert sim.units["env_sensor"]._stressed is True
    assert sim.units["water_valve"]._stressed is True
    # cycle period should be 1.5x original (5.0 * 1.5 = 7.5)
    assert abs(sim.units["env_sensor"].cycle_period_s - 7.5) < 0.01
    assert abs(sim.units["water_valve"].cycle_period_s - 7.5) < 0.01


def test_stress_trajectories_collected():
    sim = CIStressSimulation(seed=1, duration_s=400.0, t_warmup=60.0, t_stress=300.0,
                             burn_in=30.0, stress_type="blackout")
    trajectories = sim.run()
    assert len(trajectories["normal"]) == 9
    assert len(trajectories["stress"]) == 9
    assert len(trajectories["normal"]["infra_sensor"]) > 100
    assert len(trajectories["stress"]["infra_sensor"]) > 30


def test_no_stress_baseline():
    sim = CIStressSimulation(seed=1, duration_s=400.0, stress_type=None)
    trajectories = sim.run()
    assert all(len(v) == 0 for v in trajectories["stress"].values())
    assert all(len(v) > 0 for v in trajectories["normal"].values())
