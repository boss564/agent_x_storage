"""Hebel 1 Follow-up: disagreement rate measurement.

Replays each transaction to all nine evaluators (fan-out) and computes the
pairwise disagreement rate. Also detects dead rules (always-PASS).

This is a MEASUREMENT harness, not a production routing change. Production
routing stays 1-of-9 (StickySelector); the measurement replays each TX to
all nine so pairwise disagreement is well-defined.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from scripts.hebel1_evaluator_rules import EVALUATOR_RULES

EVALUATOR_IDS = list(EVALUATOR_RULES.keys())

# Prereg thresholds (frozen)
THRESHOLD_NOT_EFFECTIVE = 0.01
THRESHOLD_PARTIAL = 0.10
THRESHOLD_GOOD = 0.30


def evaluate_all(transaction: dict) -> Dict[str, bool]:
    """Run a single transaction through all nine rules. Returns verdicts."""
    net = transaction.get("net", 0.0)
    tax = transaction.get("tax", 0.0)
    ret = transaction.get("ret", 0.0)
    gross = transaction.get("gross", 0.0)
    inflated = transaction.get("inflated", False)
    contract_id = transaction.get("contract_id", "")
    return {
        eid: rule(net, tax, ret, gross, inflated, contract_id)
        for eid, rule in EVALUATOR_RULES.items()
    }


def pairwise_disagreement_rate(all_verdicts: List[Dict[str, bool]]) -> float:
    """Mean over all transactions and all C(9,2)=36 pairs of the indicator
    verdict_i != verdict_j."""
    if not all_verdicts:
        return 0.0
    total_disagreements = 0
    total_comparisons = 0
    for verdicts in all_verdicts:
        for i in range(len(EVALUATOR_IDS)):
            for j in range(i + 1, len(EVALUATOR_IDS)):
                if verdicts[EVALUATOR_IDS[i]] != verdicts[EVALUATOR_IDS[j]]:
                    total_disagreements += 1
                total_comparisons += 1
    if total_comparisons == 0:
        return 0.0
    return total_disagreements / total_comparisons


def detect_dead_rules(all_verdicts: List[Dict[str, bool]]) -> Dict[str, int]:
    """Count how many transactions each rule FAILs. A rule that FAILs zero
    transactions is effectively always-PASS (dead differentiation)."""
    fail_counts = {eid: 0 for eid in EVALUATOR_IDS}
    for verdicts in all_verdicts:
        for eid, verdict in verdicts.items():
            if not verdict:
                fail_counts[eid] += 1
    return fail_counts


def classify(rate: float) -> str:
    """Classify the disagreement rate against the prereg thresholds."""
    if rate < THRESHOLD_NOT_EFFECTIVE:
        return "NICHT_WIRKSAM"
    if rate < THRESHOLD_PARTIAL:
        return "TEILWEISE_WIRKSAM"
    if rate <= THRESHOLD_GOOD:
        return "GUT_WIRKSAM"
    return "KONSISTENZ_WARNUNG"


def measure(transactions: List[dict], out_path: Optional[str] = None) -> dict:
    """Run the full measurement over a list of transactions."""
    all_verdicts = [evaluate_all(tx) for tx in transactions]
    rate = pairwise_disagreement_rate(all_verdicts)
    fail_counts = detect_dead_rules(all_verdicts)
    dead_rules = [eid for eid, count in fail_counts.items() if count == 0]

    result = {
        "n_transactions": len(transactions),
        "pairwise_disagreement_rate": round(rate, 6),
        "classification": classify(rate),
        "fail_counts_per_rule": fail_counts,
        "dead_rules_always_pass": dead_rules,
        "n_dead_rules": len(dead_rules),
    }
    if out_path:
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
    return result
