"""Hebel 2: evaluate assignment strategies against the prereg threshold.

Prereg (docs/HEBEL2_ZUWEISUNG_PREREG.md, 6c927bc2):
  - Null model: uniform random (NOT kappa=0)
  - IMPROVED:      delta >= +5% throughput proxy vs null model
  - WORSENED:      delta <= -5%
  - INCONCLUSIVE:  -5% < delta < +5%
"""

from __future__ import annotations

import json
import os
import random
import statistics
import sys
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.hebel2_assignment import (
    EVALUATOR_IDS, simulate_assignment, load_balance_metric,
)

IMPROVED_THRESHOLD = 0.05
WORSENED_THRESHOLD = -0.05
N_TRIALS = 30
N_TRANSACTIONS = 1000


def run_trial(strategy: str, transactions: List[str], seed: int) -> Dict:
    rng = random.Random(seed)
    state = {eid: {"inbox_depth": 0} for eid in EVALUATOR_IDS}
    load = simulate_assignment(strategy, transactions, EVALUATOR_IDS, rng, state)
    max_load = max(load.values()) if load else 1
    balance = load_balance_metric(load)
    return {
        "load": load,
        "max_load": max_load,
        "throughput_proxy": 1.0 / max_load if max_load > 0 else 1.0,
        "load_balance_cv": balance,
    }


def evaluate(trials_by_strategy: Dict[str, List[Dict]]) -> dict:
    null_tps = [t["throughput_proxy"] for t in trials_by_strategy["null_model"]]
    treat_tps = [t["throughput_proxy"] for t in trials_by_strategy["treatment"]]
    sq_tps = [t["throughput_proxy"] for t in trials_by_strategy["status_quo"]]

    mean_null = statistics.mean(null_tps)
    mean_treat = statistics.mean(treat_tps)
    mean_sq = statistics.mean(sq_tps)

    delta_treat_vs_null = (mean_treat - mean_null) / mean_null if mean_null > 0 else 0.0
    delta_sq_vs_null = (mean_sq - mean_null) / mean_null if mean_null > 0 else 0.0

    null_balance = statistics.mean(
        [t["load_balance_cv"] for t in trials_by_strategy["null_model"]])
    treat_balance = statistics.mean(
        [t["load_balance_cv"] for t in trials_by_strategy["treatment"]])
    sq_balance = statistics.mean(
        [t["load_balance_cv"] for t in trials_by_strategy["status_quo"]])

    if delta_treat_vs_null >= IMPROVED_THRESHOLD:
        verdict = "POSITIVBEFUND"
    elif delta_treat_vs_null <= WORSENED_THRESHOLD:
        verdict = "NEGATIVBEFUND"
    else:
        verdict = "INCONCLUSIVE"

    return {
        "verdict": verdict,
        "delta_treatment_vs_null": round(delta_treat_vs_null, 6),
        "delta_status_quo_vs_null": round(delta_sq_vs_null, 6),
        "mean_throughput_proxy": {
            "null_model": round(mean_null, 6),
            "treatment": round(mean_treat, 6),
            "status_quo": round(mean_sq, 6),
        },
        "load_balance_cv": {
            "null_model": round(null_balance, 6),
            "treatment": round(treat_balance, 6),
            "status_quo": round(sq_balance, 6),
        },
        "n_trials": N_TRIALS,
        "n_transactions_per_trial": N_TRANSACTIONS,
        "note": (
            "throughput_proxy = 1/max_load (assignment simulation). "
            "Treatment updates inbox_depth; status_quo/null do not in this model "
            "except via resulting load counts."
        ),
    }


def main(out_path: str = "hebel2_zuweisung_ergebnis.json") -> None:
    tx_rng = random.Random(42)
    transactions = [f"TX-{tx_rng.randint(0, 999999):06d}" for _ in range(N_TRANSACTIONS)]

    trials_by_strategy: Dict[str, List[Dict]] = {
        "status_quo": [], "null_model": [], "treatment": [],
    }
    for strategy in trials_by_strategy:
        for trial_seed in range(N_TRIALS):
            trials_by_strategy[strategy].append(
                run_trial(strategy, transactions, trial_seed)
            )

    result = evaluate(trials_by_strategy)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"VERDICT: {result['verdict']}")
    print(f"  Treatment vs Null: {result['delta_treatment_vs_null']:+.4f} "
          f"(Schwelle +/-5%)")
    print(f"  Status-quo vs Null (deskriptiv): "
          f"{result['delta_status_quo_vs_null']:+.4f}")
    print(f"  Last-Balance (CV, niedriger = besser):")
    print(f"    Null: {result['load_balance_cv']['null_model']:.4f} | "
          f"Treatment: {result['load_balance_cv']['treatment']:.4f} | "
          f"Status-quo: {result['load_balance_cv']['status_quo']:.4f}")


if __name__ == "__main__":
    main()
