"""Smoke tests for AstroCore KuramotoEvaluator (fast surrogate counts)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from astrocore.emergence_evaluator import KuramotoEvaluator


def _synced_logs(n_agents=5, n_events=40, period=10.0, jitter=0.05, seed=1):
    rng = np.random.default_rng(seed)
    base = np.arange(n_events) * period + 100.0
    logs = {}
    for i in range(n_agents):
        logs[f"a{i}"] = (base + rng.normal(0, jitter, n_events)).tolist()
    return logs


def _independent_logs(n_agents=5, n_events=40, seed=2):
    rng = np.random.default_rng(seed)
    logs = {}
    for i in range(n_agents):
        logs[f"a{i}"] = sorted(rng.uniform(0, 400, n_events).tolist())
    return logs


def test_synced_r_higher_than_independent():
    sync = KuramotoEvaluator(_synced_logs(), n_time_bins=200)
    indep = KuramotoEvaluator(_independent_logs(), n_time_bins=200)
    assert sync.compute_observed_mean_R() > indep.compute_observed_mean_R()


def test_significance_api_returns_status():
    # Tiny surrogate budget — API smoke only, not production α-power.
    ev = KuramotoEvaluator(_synced_logs(), n_time_bins=100)
    p, status = ev.run_significance_test(n_surrogates=5, alpha=0.01)
    assert 0.0 <= p <= 1.0
    assert status in ("EMERGENCE_PASSED", "EMERGENCE_FAILED")


def test_empty_logs_raise():
    import pytest
    with pytest.raises(ValueError):
        KuramotoEvaluator({"a": [], "b": []})
