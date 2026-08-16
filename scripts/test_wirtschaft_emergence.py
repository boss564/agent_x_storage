"""Baustein 5b tests: Wirtschafts-Schwarm -> Kuramoto evaluation.

The verdict (COUPLED / NO_COUPLING) is an OPEN measurement; these tests
verify the adapter's structure and determinism, not a specific outcome.
Small ticks/n_surrogates keep the suite fast.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.wirtschaft.emergence_adapter import (
    EmergenceResult, run_simulation_logs, evaluate_emergence,
)

TICKS = 100
N_SURR = 50


def test_simulation_logs_format():
    logs = run_simulation_logs(ticks=TICKS)
    assert isinstance(logs, dict)
    assert len(logs) == 9                      # all agents produce >=2 events
    for ts in logs.values():
        assert isinstance(ts, list)
        assert all(isinstance(t, float) for t in ts)
        assert len(ts) >= 2
        assert ts == sorted(ts)                # chronological


def test_emergence_result_structure():
    r = evaluate_emergence(ticks=TICKS, n_surrogates=N_SURR)
    assert isinstance(r, EmergenceResult)
    assert 0.0 <= r.mean_r <= 1.0
    assert 0.0 <= r.p_value <= 1.0
    assert r.status in ("EMERGENCE_PASSED", "EMERGENCE_FAILED")
    assert r.verdict in ("COUPLED", "NO_COUPLING")
    assert r.coupled == (r.status == "EMERGENCE_PASSED")
    assert r.n_agents == 9
    assert r.n_events > 0


def test_emergence_mean_r_deterministic():
    # events are deterministic -> observed mean_r must be reproducible
    a = evaluate_emergence(ticks=TICKS, n_surrogates=N_SURR)
    b = evaluate_emergence(ticks=TICKS, n_surrogates=N_SURR)
    assert a.mean_r == b.mean_r
    assert a.n_events == b.n_events


def test_summary_string():
    r = evaluate_emergence(ticks=TICKS, n_surrogates=N_SURR)
    s = r.summary()
    assert "verdict=" in s and "mean_r=" in s and "p=" in s
