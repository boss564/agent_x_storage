"""Tests for the TIER-2a efficiency evaluation logic (synthetic data only)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.eval_tier2a_effizienz import (
    KAPPA_VALUES,
    compute_delta,
    classify_delta,
    sign_consistency_required,
    evaluate_sweep,
)


def make_runs(kappa, throughput, n_seeds=5):
    return [
        {
            "kappa": kappa,
            "epsilon": 0.0,
            "seed": s,
            "ticks": 1000,
            "n_messages": int(throughput * 1000),
            "throughput_msg_per_tick": throughput,
        }
        for s in range(n_seeds)
    ]


def build_sweep(tp_by_kappa):
    return {k: make_runs(k, tp_by_kappa[k]) for k in KAPPA_VALUES}


def test_compute_delta():
    assert abs(compute_delta(100.0, 110.0) - 0.10) < 1e-9
    assert abs(compute_delta(100.0, 90.0) - (-0.10)) < 1e-9
    assert abs(compute_delta(100.0, 100.0)) < 1e-9


def test_classify_delta():
    assert classify_delta(0.10) == "VERBESSERT"
    assert classify_delta(0.05) == "VERBESSERT"
    assert classify_delta(-0.05) == "VERSCHLECHTERT"
    assert classify_delta(-0.10) == "VERSCHLECHTERT"
    assert classify_delta(0.02) == "KEINE_KLARE_WIRKUNG"
    assert classify_delta(-0.02) == "KEINE_KLARE_WIRKUNG"


def test_sign_consistency_required():
    assert sign_consistency_required(4) == 3
    assert sign_consistency_required(3) == 2


def test_positivbefund_all_improved():
    sweep = build_sweep({
        0.0: 100.0, 0.25: 110.0, 0.5: 110.0, 1.0: 110.0, 2.0: 110.0,
    })
    result = evaluate_sweep(sweep)
    assert result["verdict"] == "POSITIVBEFUND"
    assert result["sign_consistency"]["met"] is True


def test_negativbefund_all_worsened():
    sweep = build_sweep({
        0.0: 100.0, 0.25: 90.0, 0.5: 90.0, 1.0: 90.0, 2.0: 90.0,
    })
    result = evaluate_sweep(sweep)
    assert result["verdict"] == "NEGATIVBEFUND"


def test_inconclusive_no_clear_effect():
    sweep = build_sweep({
        0.0: 100.0, 0.25: 101.0, 0.5: 101.0, 1.0: 101.0, 2.0: 101.0,
    })
    result = evaluate_sweep(sweep)
    assert result["verdict"] == "INCONCLUSIVE"


def test_inconclusive_mixed_effects():
    sweep = build_sweep({
        0.0: 100.0, 0.25: 110.0, 0.5: 110.0, 1.0: 90.0, 2.0: 90.0,
    })
    result = evaluate_sweep(sweep)
    assert result["verdict"] == "INCONCLUSIVE"


def test_inconclusive_insufficient_runs():
    sweep = {k: make_runs(k, 110.0, n_seeds=2) for k in KAPPA_VALUES}
    result = evaluate_sweep(sweep)
    assert result["verdict"] == "INCONCLUSIVE"
    assert "duenne Datenbasis" in result["reason"]


def test_positivbefund_requires_no_worsening():
    sweep = build_sweep({
        0.0: 100.0, 0.25: 110.0, 0.5: 110.0, 1.0: 110.0, 2.0: 90.0,
    })
    result = evaluate_sweep(sweep)
    assert result["verdict"] == "INCONCLUSIVE"
