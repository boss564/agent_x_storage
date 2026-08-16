"""Tests for the rescue coordination module."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.rescue import (
    build_rescue_swarm, IncidentCoordinator,
    evaluate_coordination, order_parameter,
)
from agents_b2g.rescue.unit_base import UnitState


def test_swarm_has_nine_units_three_classes():
    swarm = build_rescue_swarm()
    assert len(swarm) == 9
    classes = {u.unit_class for u in swarm.values()}
    assert classes == {"A", "B", "C"}


def test_damage_to_rescue_loop_conservation():
    swarm = build_rescue_swarm()
    coord = IncidentCoordinator()
    for u in swarm.values():
        coord.add_unit(u)
    area = coord.report_damage("area_north", "severe", victims=5, t=0.0)
    res = coord.allocate(area)
    assert res["status"] == "dispatched"
    coord.serve(res)
    check = coord.conservation_check()
    assert check["conserved"] is True
    assert check["detected"] == 5 and check["served"] == 5


def test_class_separation_no_field_action_in_class_c():
    swarm = build_rescue_swarm()
    coord = IncidentCoordinator()
    for u in swarm.values():
        coord.add_unit(u)
    # class C units must not be selectable as rescuers
    rescuers = coord.units_by_capability("victim_rescue")
    assert all(u.unit_class == "B" for u in rescuers)


def test_resource_friction_drains_and_degrades():
    swarm = build_rescue_swarm()
    unit = swarm["search_rescue"]
    unit.comms_budget = 0.4
    for i in range(3):
        unit.send("incident_cmd", "status", {"i": i})
    assert unit.state == UnitState.DEGRADED  # comms overload


def test_coordination_evaluator_structure():
    swarm = build_rescue_swarm()
    # advance all units to the SAME phase -> should read as coordinated
    for u in swarm.values():
        u.ooda_phase = 1.0
    result = evaluate_coordination(swarm)
    assert result["status"] == "COORDINATED"
    assert result["r_observed"] > 0.99
    assert result["p_value"] >= 0.0  # +1 correction, never exactly 0


def test_random_phases_uncoordinated():
    import math, random
    swarm = build_rescue_swarm()
    rng = random.Random(7)
    for u in swarm.values():
        u.ooda_phase = rng.uniform(0.0, 2 * math.pi)
    result = evaluate_coordination(swarm, n_surrogates=2000, alpha=0.01)
    # random phases should NOT be flagged as coordinated
    assert result["status"] == "UNCOORDINATED"


if __name__ == "__main__":
    for fn in [test_swarm_has_nine_units_three_classes,
               test_damage_to_rescue_loop_conservation,
               test_class_separation_no_field_action_in_class_c,
               test_resource_friction_drains_and_degrades,
               test_coordination_evaluator_structure,
               test_random_phases_uncoordinated]:
        fn()
        print(f"PASS {fn.__name__}")
