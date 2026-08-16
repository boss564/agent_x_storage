"""The 9 smart grid agents across 3 classes.

Class A (Erzeugung): phase matters for R_grid.
Class B (Flexibilitaet), Class C (Netz-Guardians).
Calibrated cycle times, ~3:1 spread (CI lesson).
"""

from __future__ import annotations

from agents_b2g.smartgrid.unit_base import SmartGridUnit


SMARTGRID_CYCLE_TIMES = {
    # Class A — Erzeugung (phase matters for R_grid)
    "pv_prosumer": 3,
    "wind_turbine": 4,
    "chp_agent": 5,
    # Class B — Flexibilitaet
    "battery_storage": 6,
    "ev_mobility": 8,
    "heat_pump": 7,
    # Class C — Netz-Guardians
    "transformer": 9,
    "curtailment": 10,
    "grid_quality": 8,
}

POWER_CAPACITIES = {
    "pv_prosumer": 50.0,
    "wind_turbine": 80.0,
    "chp_agent": 100.0,
    "battery_storage": 60.0,
    "ev_mobility": 40.0,
    "heat_pump": 30.0,
    "transformer": 0.0,
    "curtailment": 0.0,
    "grid_quality": 0.0,
}


def build_smartgrid_swarm() -> dict:
    """Instantiate the 9-agent smart grid swarm. Returns {unit_id: SmartGridUnit}."""
    specs = [
        ("pv_prosumer", "A", "pv_generation"),
        ("wind_turbine", "A", "wind_generation"),
        ("chp_agent", "A", "chp_generation"),
        ("battery_storage", "B", "battery_flexibility"),
        ("ev_mobility", "B", "ev_flexibility"),
        ("heat_pump", "B", "thermal_flexibility"),
        ("transformer", "C", "voltage_control"),
        ("curtailment", "C", "feed_in_management"),
        ("grid_quality", "C", "grid_monitoring"),
    ]
    return {uid: SmartGridUnit(unit_id=uid, unit_class=cls, capability=cap,
                               cycle_period_s=SMARTGRID_CYCLE_TIMES[uid],
                               power_capacity=POWER_CAPACITIES[uid])
            for uid, cls, cap in specs}
