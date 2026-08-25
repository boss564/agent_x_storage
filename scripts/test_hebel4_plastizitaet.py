"""Tests for Hebel 4 plasticity: Class-B waterfall + IUT helpers + seed streams."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.smartgrid.flex_dispatch import (
    PASSIVE_FLEX_FRACTION,
    WATERFALL_ORDER,
    flex_available_null,
    flex_available_treatment,
    run_waterfall,
)
from agents_b2g.smartgrid.simulation import SmartGridStressSimulation
from scripts.run_hebel4_plastizitaet_study import classify_h1


CAPS = {
    "battery_storage": 60.0,
    "ev_mobility": 40.0,
    "heat_pump": 30.0,
}


def test_waterfall_order_battery_before_ev():
    soc = {"battery_storage": 0.80, "ev_mobility": 0.60}
    # Small deficit: only battery should fire
    dispatch, residual, _ = run_waterfall(20.0, CAPS, soc)
    assert dispatch["battery_storage"] == 20.0
    assert dispatch["ev_mobility"] == 0.0
    assert dispatch["heat_pump"] == 0.0
    assert residual == 0.0


def test_waterfall_order_spills_to_ev_then_hp():
    soc = {"battery_storage": 0.80, "ev_mobility": 0.60}
    # Large deficit: battery full (60), then EV (0.7*40=28), then HP
    dispatch, residual, _ = run_waterfall(100.0, CAPS, soc)
    assert dispatch["battery_storage"] == 60.0
    assert abs(dispatch["ev_mobility"] - 28.0) < 1e-9
    assert abs(dispatch["heat_pump"] - 12.0) < 1e-9
    assert residual == 0.0


def test_full_cover_until_capacity_exhausted():
    soc = {"battery_storage": 0.80, "ev_mobility": 0.60}
    # Max Class-B ≈ 60+28+30 = 118
    dispatch, residual, _ = run_waterfall(200.0, CAPS, soc)
    assert abs(sum(dispatch.values()) - 118.0) < 1e-6
    assert abs(residual - 82.0) < 1e-6


def test_treatment_replaces_04_no_max():
    """Treatment flex is dispatch sum only — never max(0.4*cap, dispatch)."""
    assert abs(flex_available_null(CAPS) - PASSIVE_FLEX_FRACTION * 130.0) < 1e-9
    dispatch = {"battery_storage": 10.0, "ev_mobility": 0.0, "heat_pump": 0.0}
    assert flex_available_treatment(dispatch) == 10.0
    assert flex_available_treatment(dispatch) < flex_available_null(CAPS)


def test_null_act_passive_flex():
    sim = SmartGridStressSimulation(
        seed=1, duration_s=100.0, t_warmup=10.0, t_stress=50.0,
        burn_in=5.0, stress_type="leitungsausfall", plasticity=False,
    )
    for _ in range(20):
        sim.step()
    expected = PASSIVE_FLEX_FRACTION * sum(
        u.power_capacity for u in sim.units.values() if u.unit_class == "B"
    )
    assert abs(sim.last_flex_available - expected) < 1e-6


def test_treatment_dispatches_on_deficit():
    sim = SmartGridStressSimulation(
        seed=2, duration_s=200.0, t_warmup=10.0, t_stress=50.0,
        burn_in=5.0, stress_type="leitungsausfall", plasticity=True,
    )
    while sim.t < 80.0:
        sim.step()
    # After line failure, deficit should trigger some dispatch
    assert sim.last_deficit >= 0.0
    # At least one stress sample with dispatch, or current flex > 0 under deficit
    if sim.last_deficit > 1.0:
        assert sim.last_flex_available > 0.0


def test_leitungsausfall_injection():
    sim = SmartGridStressSimulation(
        seed=3, duration_s=100.0, t_warmup=5.0, t_stress=20.0,
        burn_in=1.0, stress_type="leitungsausfall", plasticity=False,
    )
    while sim.t < 25.0:
        sim.step()
    wind = [inv for iid, inv in sim._inverter_state.items() if "wind_turbine" in iid]
    assert wind
    assert all(inv["capacity_factor"] == 0.0 for inv in wind)
    assert all(inv["period"] == 100.0 for inv in wind)


def test_soc_floor():
    from agents_b2g.smartgrid.flex_dispatch import SOC_FLOOR
    soc = {"battery_storage": 0.105, "ev_mobility": 0.11}
    _, _, new_soc = run_waterfall(100.0, CAPS, soc)
    assert new_soc["battery_storage"] >= SOC_FLOOR - 1e-9


def test_iut_conjunction():
    # H1a only → NOT_CONFIRMED
    r = classify_h1(
        delta_r=[-0.2] * 10,
        delta_w=[-0.1] * 10,  # H1b fails
    )
    assert r["h1a_status"] == "CONFIRMED"
    assert r["h1b_status"] == "NOT_CONFIRMED"
    assert r["h1_status"] == "NOT_CONFIRMED"
    # Both → CONFIRMED
    r2 = classify_h1(
        delta_r=[-0.2] * 10,
        delta_w=[0.05] * 10,
    )
    assert r2["h1_status"] == "CONFIRMED"


def test_seed_streams_differ():
    """Different seeds must not be byte-identical (load / stress onset)."""
    a = SmartGridStressSimulation(
        seed=0, duration_s=2000.0, t_warmup=60.0, t_stress=1440.0,
        burn_in=60.0, stress_type="leitungsausfall", plasticity=False,
    )
    b = SmartGridStressSimulation(
        seed=1, duration_s=2000.0, t_warmup=60.0, t_stress=1440.0,
        burn_in=60.0, stress_type="leitungsausfall", plasticity=False,
    )
    assert a.t_stress != b.t_stress
    for _ in range(100):
        a.step()
        b.step()
    assert a.w_dyn_normal != b.w_dyn_normal


def test_waterfall_order_constant():
    assert WATERFALL_ORDER == ["battery_storage", "ev_mobility", "heat_pump"]
