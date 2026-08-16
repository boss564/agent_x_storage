"""Unit tests for smart grid stress injectors."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.smartgrid.simulation import SmartGridStressSimulation


def test_bewoelkung_stress_reduces_pv_capacity():
    sim = SmartGridStressSimulation(seed=1, duration_s=1500.0, t_stress=1440.0,
                                    stress_type="bewoelkung")
    sim.run()
    for inv_id, inv in sim._inverter_state.items():
        if "pv_prosumer" in inv_id:
            assert inv["capacity_factor"] == 0.1


def test_spitzenlast_stress_increases_load():
    sim = SmartGridStressSimulation(seed=1, duration_s=1500.0, t_stress=1440.0,
                                    stress_type="spitzenlast", base_load=100.0)
    sim.run()
    assert sim.base_load == 150.0


def test_leitungsausfall_stress_isolates_wind():
    sim = SmartGridStressSimulation(seed=1, duration_s=1500.0, t_stress=1440.0,
                                    stress_type="leitungsausfall")
    sim.run()
    for inv_id, inv in sim._inverter_state.items():
        if "wind_turbine" in inv_id:
            assert inv["capacity_factor"] == 0.0
            assert inv["period"] == 100.0


def test_stress_trajectories_collected():
    sim = SmartGridStressSimulation(seed=1, duration_s=1500.0, t_warmup=60.0,
                                    t_stress=1440.0, burn_in=60.0,
                                    stress_type="bewoelkung")
    result = sim.run()
    assert len(result["normal"]) == 9
    assert len(result["stress"]) == 9
    assert len(result["normal"]["pv_prosumer_inv0"]) > 100
    assert len(result["stress"]["pv_prosumer_inv0"]) > 0


def test_no_stress_baseline():
    sim = SmartGridStressSimulation(seed=1, duration_s=1500.0, stress_type=None)
    result = sim.run()
    assert all(len(v) == 0 for v in result["stress"].values())
    assert all(len(v) > 0 for v in result["normal"].values())


def test_w_dyn_tracking():
    sim = SmartGridStressSimulation(seed=1, duration_s=500.0, t_warmup=60.0,
                                    t_stress=400.0, stress_type="bewoelkung")
    sim.run()
    eff_normal = sim.compute_efficiency("normal")
    eff_stress = sim.compute_efficiency("stress")
    assert eff_normal["n_samples"] > 0
    assert eff_stress["n_samples"] > 0
    assert 0.0 <= eff_normal["mean_w_dyn"] <= 1.0
    assert 0.0 <= eff_stress["mean_w_dyn"] <= 1.0
