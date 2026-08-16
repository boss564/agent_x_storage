"""Tests for the full rescue simulation loop."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.rescue.simulation import RescueSimulation, phase_pull


def test_simulation_runs_and_reports():
    report = RescueSimulation(seed=42, duration_s=300.0).run()
    assert report["units_total"] == 9
    assert report["t"] >= 300.0
    assert "conservation" in report and "coordination" in report


def test_conservation_invariant_holds():
    c = RescueSimulation(seed=42, duration_s=300.0).run()["conservation"]
    assert c["conserved"] is True
    assert c["detected"] >= c["assigned"] >= c["served"] >= 0


def test_messages_actually_flow():
    report = RescueSimulation(seed=42, duration_s=300.0).run()
    assert report["messages_delivered"] > 0


def test_deterministic_with_seed():
    r1 = RescueSimulation(seed=7, duration_s=200.0).run()
    r2 = RescueSimulation(seed=7, duration_s=200.0).run()
    assert r1["conservation"] == r2["conservation"]
    assert r1["messages_delivered"] == r2["messages_delivered"]


def test_both_seeds_conserve():
    for seed in (1, 2):
        c = RescueSimulation(seed=seed, duration_s=200.0).run()["conservation"]
        assert c["conserved"] is True


def test_coordination_result_wellformed():
    coord = RescueSimulation(seed=42, duration_s=300.0).run()["coordination"]
    assert coord.get("status") in ("COORDINATED", "UNCOORDINATED", "insufficient_units")
    if "r_observed" in coord:
        assert 0.0 <= coord["r_observed"] <= 1.0
        assert 0.0 <= coord["p_value"] <= 1.0


def test_units_survive_with_resupply():
    report = RescueSimulation(seed=42, duration_s=400.0).run()
    assert report["units_operational"] >= 1


def test_phase_pull_wraps_correctly():
    two_pi = 2 * math.pi
    # full-strength pull lands exactly on target across the 0/2pi wrap
    assert abs(phase_pull(0.1, two_pi - 0.1, 1.0) - (two_pi - 0.1)) < 1e-6
    # zero-strength pull leaves phase unchanged
    assert abs(phase_pull(1.0, 3.0, 0.0) - 1.0) < 1e-6
