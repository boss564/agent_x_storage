"""Baustein 5 tests: Wirtschafts-Simulation (event-log generation)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.wirtschaft.simulation import WirtschaftsSimulation


def test_simulation_produces_events_for_all_agents():
    events = WirtschaftsSimulation(ticks=60).run()
    assert len(events) == 9
    for evts in events.values():
        assert len(evts) > 0


def test_simulation_deterministic():
    assert WirtschaftsSimulation(ticks=60).run() == WirtschaftsSimulation(ticks=60).run()


def test_simulation_events_within_range():
    ticks = 60
    for evts in WirtschaftsSimulation(ticks=ticks).run().values():
        assert all(0 <= t < ticks for t in evts)


def test_freigabe_rearm_keeps_gas_alive():
    # long run with periodic Freigabe re-arm must not drain the agents
    sim = WirtschaftsSimulation(ticks=200, reset_freigaben_every=10)
    events = sim.run()
    assert all(not a.drained for a in sim.agents_by_id.values())
    assert all(len(e) > 0 for e in events.values())
