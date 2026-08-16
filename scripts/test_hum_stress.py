"""Unit tests for humanitarian stress injectors."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.humanitarian.simulation import HumanitarianStressSimulation
from agents_b2g.humanitarian.unit_base import UnitState


def test_hub_verlust_stress():
    sim = HumanitarianStressSimulation(seed=1, duration_s=1500.0, t_stress=1440.0,
                                       stress_type="hub_verlust")
    sim.run()
    assert sim.units["forward_hub_agent"].state == UnitState.OUT_OF_SERVICE


def test_nachbeben_stress():
    sim = HumanitarianStressSimulation(seed=1, duration_s=1500.0, t_stress=1440.0,
                                       stress_type="nachbeben")
    sim.run()
    assert sim.units["thw_agent"].state == UnitState.DEGRADED
    assert sim.units["uav_agent"].state == UnitState.DEGRADED
    # Base 18/12 × jitter(0.9–1.1) × 1.5 → lower bound ~18×0.9×1.5=24.3 / 12×0.9×1.5=16.2
    assert sim.units["thw_agent"].cycle_period_s > 24.0
    assert sim.units["uav_agent"].cycle_period_s > 16.0


def test_komm_kollaps_stress():
    sim = HumanitarianStressSimulation(seed=1, duration_s=1500.0, t_stress=1440.0,
                                       stress_type="komm_kollaps")
    sim.run()
    for uid, u in sim.units.items():
        if u.unit_class == "A":
            assert u.pol_cost_per_msg > 0.01  # was 0.005
            assert u.pol_drain_per_cycle > 0.03  # was 0.02


def test_stress_trajectories_collected():
    sim = HumanitarianStressSimulation(seed=1, duration_s=1500.0, t_warmup=60.0,
                                       t_stress=1440.0, burn_in=60.0,
                                       stress_type="hub_verlust")
    result = sim.run()
    assert len(result["normal"]) == 9
    assert len(result["stress"]) == 9
    assert len(result["normal"]["sar_agent"]) > 100
    assert len(result["stress"]["sar_agent"]) > 0


def test_no_stress_baseline():
    sim = HumanitarianStressSimulation(seed=1, duration_s=1500.0, stress_type=None)
    result = sim.run()
    assert all(len(v) == 0 for v in result["stress"].values())
    assert all(len(v) > 0 for v in result["normal"].values())


def test_efficiency_tracking():
    sim = HumanitarianStressSimulation(seed=1, duration_s=500.0, t_warmup=60.0,
                                       t_stress=400.0, stress_type="hub_verlust")
    result = sim.run()
    assert "requests" in result
    eff_normal = sim.compute_efficiency(60.0, 400.0)
    eff_stress = sim.compute_efficiency(460.0, 500.0)
    assert eff_normal["n_requests"] >= 0
    assert eff_stress["n_requests"] >= 0
