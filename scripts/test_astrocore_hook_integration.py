"""P2 tests: astrocore_hook ↔ emergence_adapter integration."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.astrocore_hook import AstrocoreHookClient
from agents_b2g.wirtschaft.emergence_adapter import (
    evaluate_emergence,
    _fetch_astrocore_signal,
)


def test_hook_client_synthetic_envelope():
    client = AstrocoreHookClient(neo4j_uri=None, strict=False)
    env = client.analyze_liquidations()
    assert env["data_provenance"] == "synthetic"
    assert env["verdict"] == "SYNTHETIC_ONLY"
    assert env["analysis"]["n_events"] == 1000
    sig = client.to_evaluator_signal(env)
    assert sig["verdict"] == "SYNTHETIC_ONLY"
    assert 0.0 <= sig["R"] <= 1.0


def test_fetch_astrocore_signal_disabled():
    assert _fetch_astrocore_signal(use_astrocore_hook=False) is None


def test_evaluate_emergence_hook_off_unchanged():
    base = evaluate_emergence(ticks=100, n_surrogates=50, use_astrocore_hook=False)
    assert base.astrocore is None
    assert base.verdict in ("COUPLED", "NO_COUPLING")


def test_evaluate_emergence_hook_on_attaches_signal():
    result = evaluate_emergence(ticks=100, n_surrogates=50, use_astrocore_hook=True)
    assert result.astrocore is not None
    assert result.astrocore.verdict == "SYNTHETIC_ONLY"
    assert result.astrocore.data_provenance == "synthetic"
    assert result.astrocore.n_events == 1000
    assert "astrocore=" in result.summary()


if __name__ == "__main__":
    test_hook_client_synthetic_envelope()
    test_fetch_astrocore_signal_disabled()
    test_evaluate_emergence_hook_off_unchanged()
    test_evaluate_emergence_hook_on_attaches_signal()
    print("OK: test_astrocore_hook_integration 4/4")
