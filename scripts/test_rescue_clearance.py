"""Tests for the rescue clearance gate (Einsatzregeln / Freigaben)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.rescue.clearance import ClearanceGate, HazardLevel, ClearanceStatus
from agents_b2g.rescue.simulation import RescueSimulation


def test_gate_only_class_c_can_clear():
    g = ClearanceGate()
    g.register_area("a1", HazardLevel.UNSAFE)
    g.begin_assessment("a1", "infra_repair")
    g.record_assessment("a1", True)
    # the responder (B) must NOT be able to self-authorize entry
    assert g.issue_clearance("a1", "search_rescue", "B") is False
    assert g.issue_clearance("a1", "incident_cmd", "C") is True
    assert g.is_cleared("a1") is True


def test_gate_denies_unstable_area():
    g = ClearanceGate()
    g.register_area("a2", HazardLevel.UNSAFE)
    g.begin_assessment("a2", "infra_repair")
    g.record_assessment("a2", False)
    assert g.issue_clearance("a2", "incident_cmd", "C") is False
    assert g.is_cleared("a2") is False


def test_safe_area_cleared_by_default():
    g = ClearanceGate()
    g.register_area("a3", HazardLevel.SAFE)
    assert g.is_cleared("a3") is True


def test_clearance_disabled_by_default():
    assert RescueSimulation(seed=1, duration_s=50.0).clearance_gate is None


def test_clearance_sim_conservation():
    report = RescueSimulation(seed=42, duration_s=600.0,
                              enable_clearance=True, assess_stable_p=0.95).run()
    c = report["conservation"]
    assert c["conserved"] is True
    assert c["detected"] >= c["assigned"] >= c["served"] >= 0


def test_clearance_sim_accounts_all_areas():
    report = RescueSimulation(seed=42, duration_s=600.0,
                              enable_clearance=True, assess_stable_p=0.95).run()
    cl = report["clearance"]
    assert cl is not None and cl["areas"] > 0
    assert cl["cleared"] + cl["blocked"] + cl["assessing"] == cl["areas"]
    assert cl["clearances_issued"] <= cl["cleared"]


def test_clearance_sim_issues_at_least_one_clearance():
    report = RescueSimulation(seed=42, duration_s=800.0,
                              enable_clearance=True, assess_stable_p=0.95).run()
    assert report["clearance"]["cleared"] >= 1


def test_clearance_sim_deterministic():
    r1 = RescueSimulation(seed=7, duration_s=400.0,
                          enable_clearance=True, assess_stable_p=0.95).run()
    r2 = RescueSimulation(seed=7, duration_s=400.0,
                          enable_clearance=True, assess_stable_p=0.95).run()
    assert r1["clearance"] == r2["clearance"]
    assert r1["conservation"] == r2["conservation"]
