"""Stufe-A v2 lock tests: thinning, sign counting, majority, borderline.

No live JSONL peek of v2 outcomes. Synthetic files only.
"""
from __future__ import annotations

import json
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bridge_stufe_a_config import N_TESTS, WINDOW_START_UTC
from bridge_stufe_a_stats import benjamini_hochberg
from bridge_stufe_a_v2_config import (
    BORDERLINE_K,
    BRIDGE_STUFE_A_V2_SEED,
    DEFINITIVE_MIN,
    MAJORITY_MIN,
    N_DRAWS,
)
from bridge_stufe_a_v2_stats import (
    aggregate_draw_labels,
    control_surrogate_rng,
    count_cte_hits,
    count_hawkes_hits,
    draw_effect_present,
    exact_n_subset,
    hawkes_hit,
    thinning_rng,
    treatment_rng,
    v2_verdict,
)


def test_frozen_v2_constants():
    assert N_DRAWS == 21
    assert N_DRAWS % 2 == 1
    assert MAJORITY_MIN == 11
    assert BORDERLINE_K == frozenset({10, 11, 12})
    assert DEFINITIVE_MIN == 13
    assert BRIDGE_STUFE_A_V2_SEED == 20260818
    assert N_TESTS == 248


def test_exact_n_subset_is_sorted_subset_without_replacement():
    times = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0]
    rng = random.Random(1)
    kept = exact_n_subset(times, 4, rng)
    assert len(kept) == 4
    assert kept == sorted(kept)
    assert len(set(kept)) == 4
    assert set(kept).issubset(set(times))


def test_exact_n_full_copy_when_n_equals():
    times = [3.0, 1.0, 2.0]
    kept = exact_n_subset(times, 3, random.Random(0))
    assert kept == [1.0, 2.0, 3.0]


def test_exact_n_raises_if_control_shorter():
    try:
        exact_n_subset([1.0, 2.0], 3, random.Random(0))
    except ValueError as exc:
        assert "N*" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_thinning_not_uniform_in_window():
    src = open("scripts/bridge_stufe_a_v2_stats.py", encoding="utf-8").read()
    assert "without replacement" in src
    assert "Uniform(window" not in src
    pipe = open("scripts/bridge_stufe_a_v2_pipeline.py", encoding="utf-8").read()
    assert "exact_n_subset" in pipe


def test_rng_streams_are_separated():
    thin0 = [thinning_rng(0).random() for _ in range(8)]
    surr0 = [control_surrogate_rng(0).random() for _ in range(8)]
    treat = [treatment_rng().random() for _ in range(8)]
    thin1 = [thinning_rng(1).random() for _ in range(8)]
    assert thin0 != surr0
    assert thin0 != treat
    assert surr0 != treat
    assert thin0 != thin1
    assert thinning_rng(0).sample(range(50), 10) != thinning_rng(1).sample(range(50), 10)


def test_hawkes_hit_requires_positive_gamma():
    assert hawkes_hit(True, 0.1) is True
    assert hawkes_hit(True, 0.0) is False
    assert hawkes_hit(True, -0.4) is False
    assert hawkes_hit(False, 1.2) is False


def test_sign_conjunction_is_counting_rule_not_family_reduction():
    tests = [
        {"pair": "treatment", "metric": "hawkes", "bh_reject": True, "observed": -0.2},
        {"pair": "treatment", "metric": "hawkes", "bh_reject": True, "observed": 0.3},
        {"pair": "treatment", "metric": "cte", "bh_reject": True, "observed": 0.0},
        {"pair": "control", "metric": "hawkes", "bh_reject": True, "observed": -1.0},
        {"pair": "control", "metric": "cte", "bh_reject": False, "observed": 0.01},
    ]
    assert count_hawkes_hits(tests, "treatment") == 1
    assert count_cte_hits(tests, "treatment") == 1
    assert count_hawkes_hits(tests, "control") == 0
    assert count_cte_hits(tests, "control") == 0
    assert len(tests) == 5
    reject = benjamini_hochberg([0.001, 0.02, 0.04, 0.2, 0.9], q=0.05)
    assert len(reject) == 5


def test_cte_hit_has_no_positive_hurdle():
    tests = [{"pair": "treatment", "metric": "cte", "bh_reject": True, "observed": 0.0}]
    assert count_cte_hits(tests, "treatment") == 1


def test_per_draw_effect_is_full_iut():
    n = {"treat_eth": 200, "treat_gnosis": 200, "ctrl_eth": 200, "ctrl_arbitrum": 200}
    pos = v2_verdict(
        n_events=n,
        driver_coverage=0.9,
        n_sig_hawkes_treat=1,
        n_sig_cte_treat=1,
        n_sig_hawkes_ctrl=0,
        n_sig_cte_ctrl=0,
    )
    assert pos == "V2_POSITIVBEFUND"
    assert draw_effect_present(pos) is True
    hawkes_only = v2_verdict(
        n_events=n,
        driver_coverage=0.9,
        n_sig_hawkes_treat=2,
        n_sig_cte_treat=0,
        n_sig_hawkes_ctrl=0,
        n_sig_cte_ctrl=0,
    )
    assert hawkes_only == "V2_DISSOZIIERT"
    assert draw_effect_present(hawkes_only) is False
    ctrl_hit = v2_verdict(
        n_events=n,
        driver_coverage=0.9,
        n_sig_hawkes_treat=1,
        n_sig_cte_treat=1,
        n_sig_hawkes_ctrl=0,
        n_sig_cte_ctrl=1,
    )
    assert ctrl_hit == "V2_UNSPEZIFISCH"
    assert draw_effect_present(ctrl_hit) is False


def test_v2_verdict_other_labels():
    n = {"treat_eth": 200, "treat_gnosis": 200, "ctrl_eth": 200, "ctrl_arbitrum": 200}
    assert (
        v2_verdict(
            n_events=n,
            driver_coverage=0.9,
            n_sig_hawkes_treat=0,
            n_sig_cte_treat=0,
            n_sig_hawkes_ctrl=0,
            n_sig_cte_ctrl=0,
        )
        == "V2_NEGATIVBEFUND"
    )
    assert (
        v2_verdict(
            n_events={"treat_eth": 10, "treat_gnosis": 200, "ctrl_eth": 200, "ctrl_arbitrum": 200},
            driver_coverage=0.99,
            n_sig_hawkes_treat=5,
            n_sig_cte_treat=5,
            n_sig_hawkes_ctrl=0,
            n_sig_cte_ctrl=0,
        )
        == "V2_INCONCLUSIVE"
    )


def _labels(pos: int, other: str, n: int = 21) -> list[str]:
    rest = n - pos
    return ["V2_POSITIVBEFUND"] * pos + [other] * rest


def test_majority_13_is_definitive():
    agg = aggregate_draw_labels(_labels(13, "V2_UNSPEZIFISCH"))
    assert agg["majority_label"] == "V2_POSITIVBEFUND"
    assert agg["confirmatory_verdict"] == "V2_POSITIVBEFUND"
    assert agg["k_star"] == 13
    assert agg["borderline"] is False
    assert agg["definitive"] is True
    assert agg["n_effect_present"] == 13


def test_majority_11_is_borderline_not_definitive():
    agg = aggregate_draw_labels(_labels(11, "V2_UNSPEZIFISCH"))
    assert agg["majority_label"] == "V2_POSITIVBEFUND"
    assert agg["confirmatory_verdict"] == "V2_UNSPEZIFISCH"
    assert agg["borderline"] is True
    assert agg["definitive"] is False


def test_majority_12_is_borderline_not_definitive():
    agg = aggregate_draw_labels(_labels(12, "V2_NEGATIVBEFUND"))
    assert agg["majority_label"] == "V2_POSITIVBEFUND"
    assert agg["confirmatory_verdict"] == "V2_UNSPEZIFISCH"
    assert agg["borderline"] is True


def test_leading_10_is_borderline_without_majority():
    labels = ["V2_POSITIVBEFUND"] * 10 + ["V2_UNSPEZIFISCH"] * 9 + ["V2_NEGATIVBEFUND"] * 2
    agg = aggregate_draw_labels(labels)
    assert agg["majority_label"] == "V2_UNSPEZIFISCH"
    assert agg["confirmatory_verdict"] == "V2_UNSPEZIFISCH"
    assert agg["k_star"] == 10
    assert agg["borderline"] is True
    assert agg["definitive"] is False


def test_split_is_unspezifisch_not_borderline():
    labels = ["V2_POSITIVBEFUND"] * 7 + ["V2_UNSPEZIFISCH"] * 7 + ["V2_NEGATIVBEFUND"] * 7
    agg = aggregate_draw_labels(labels)
    assert agg["majority_label"] == "V2_UNSPEZIFISCH"
    assert agg["confirmatory_verdict"] == "V2_UNSPEZIFISCH"
    assert agg["k_star"] == 7
    assert agg["borderline"] is False
    assert len(agg["leading_labels"]) == 3


def test_tie_at_10_is_split_not_borderline():
    labels = ["V2_POSITIVBEFUND"] * 10 + ["V2_UNSPEZIFISCH"] * 10 + ["V2_NEGATIVBEFUND"]
    agg = aggregate_draw_labels(labels)
    assert agg["majority_label"] == "V2_UNSPEZIFISCH"
    assert agg["borderline"] is False
    assert agg["k_star"] == 10


def test_definitive_unspezifisch_is_allowed():
    labels = ["V2_UNSPEZIFISCH"] * 15 + ["V2_POSITIVBEFUND"] * 6
    agg = aggregate_draw_labels(labels)
    assert agg["majority_label"] == "V2_UNSPEZIFISCH"
    assert agg["confirmatory_verdict"] == "V2_UNSPEZIFISCH"
    assert agg["definitive"] is True
    assert agg["borderline"] is False


def test_no_pooled_bh_in_aggregation():
    src = open("scripts/bridge_stufe_a_v2_stats.py", encoding="utf-8").read()
    assert "No pooled BH" in src
    pipe = open("scripts/bridge_stufe_a_v2_pipeline.py", encoding="utf-8").read()
    assert "benjamini_hochberg" in pipe
    assert "for d in range(n_draws):" in pipe


def test_pipeline_inconclusive_short_circuit():
    from bridge_stufe_a_v2_pipeline import run_pipeline

    start = int(WINDOW_START_UTC.timestamp())
    d = tempfile.mkdtemp()

    def write_events(name, n):
        path = os.path.join(d, name)
        with open(path, "w", encoding="utf-8") as fh:
            for i in range(n):
                fh.write(json.dumps({"blockTime": start + 120 + i * 10, "txHash": f"0x{i}"}) + "\n")
        return path

    def write_drivers(name):
        path = os.path.join(d, name)
        with open(path, "w", encoding="utf-8") as fh:
            for i in range(10):
                fh.write(
                    json.dumps(
                        {
                            "timestamp": start + i * 60,
                            "gas_price_gwei": 1.0,
                            "btc_price_usd": 100.0,
                            "cex_volume_usd": 1.0,
                        }
                    )
                    + "\n"
                )
        return path

    result = run_pipeline(
        bridge_eth=write_events("be.jsonl", 10),
        bridge_gnosis=write_events("bg.jsonl", 10),
        uniswap_eth=write_events("ue.jsonl", 50),
        uniswap_arb=write_events("ua.jsonl", 50),
        drivers_path=write_drivers("drv.jsonl"),
        n_surrogates=2,
        n_draws=3,
        allow_smoke=True,
    )
    assert result["skipped_compute"] is True
    assert result["confirmatory_run"] is False
    assert result["n_draws"] == 3
    assert result["confirmatory_verdict"] == "V2_UNSPEZIFISCH"
    assert all(row["label"] == "V2_INCONCLUSIVE" for row in result["draws"])


def main() -> int:
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except Exception as exc:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {exc!r}")
    print(f"RESULT {len(tests) - failed}/{len(tests)}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
