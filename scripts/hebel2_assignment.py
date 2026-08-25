"""Hebel 2: Assignment strategies for the nine evaluators.

Three strategies compared against the prereg:
  - status_quo: hash(contract_id) % 9  (current production-style shard)
  - null_model: uniform random over the 9 evaluators
  - treatment:  state-aware assignment (shortest inbox / lowest load)

The treatment can only outperform the null model if evaluators carry state
(inbox depth, pending load). If evaluators are stateless, all three strategies
are equivalent and the result is INCONCLUSIVE by construction.
"""

from __future__ import annotations

import hashlib
import random
from typing import Dict, List, Optional


EVALUATOR_IDS = [
    "E01-bho-checker", "E02-z3-prover", "E03-gobd-auditor",
    "E04-compliance", "E05-iot-verifier", "E06-qes-validator",
    "E07-geofence", "E08-fraud-detector", "E09-tax-auditor",
]


def inbox_depth_from_agent(agent) -> int:
    """Real BaseAgent field: inbox is a list → depth = len(inbox)."""
    return len(getattr(agent, "inbox", []) or [])


def assign_status_quo(contract_id: str, evaluator_ids: List[str]) -> str:
    """Current shard behavior: hash(contract_id) % 9. Ignores evaluator state."""
    h = int(hashlib.sha256(contract_id.encode()).hexdigest(), 16)
    return evaluator_ids[h % len(evaluator_ids)]


def assign_null_model(contract_id: str, evaluator_ids: List[str],
                      rng: random.Random) -> str:
    """Null model: uniform random over the 9 evaluators."""
    return rng.choice(evaluator_ids)


def assign_treatment(contract_id: str, evaluator_ids: List[str],
                     state: Dict[str, dict]) -> str:
    """State-aware: pick evaluator with shortest inbox_depth.

    Real agents: use inbox_depth_from_agent(agent) when building `state`.
    Simulated trials update inbox_depth on each assignment.
    """
    def sort_key(eid: str):
        depth = state.get(eid, {}).get("inbox_depth", 0)
        return (depth, eid)
    return min(evaluator_ids, key=sort_key)


def simulate_assignment(strategy: str, transactions: List[str],
                        evaluator_ids: List[str],
                        rng: random.Random,
                        state: Optional[Dict[str, dict]] = None) -> Dict[str, int]:
    """Assign all transactions; return load distribution."""
    load = {eid: 0 for eid in evaluator_ids}
    state = state or {eid: {"inbox_depth": 0} for eid in evaluator_ids}

    for contract_id in transactions:
        if strategy == "status_quo":
            target = assign_status_quo(contract_id, evaluator_ids)
        elif strategy == "null_model":
            target = assign_null_model(contract_id, evaluator_ids, rng)
        elif strategy == "treatment":
            target = assign_treatment(contract_id, evaluator_ids, state)
            state[target]["inbox_depth"] = state[target].get("inbox_depth", 0) + 1
        else:
            raise ValueError(f"unknown strategy: {strategy}")
        load[target] += 1

    return load


def load_balance_metric(load: Dict[str, int]) -> float:
    """Coefficient of variation (std/mean). Lower = more balanced."""
    values = list(load.values())
    if not values or sum(values) == 0:
        return 0.0
    mean = sum(values) / len(values)
    if mean == 0:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return (variance ** 0.5) / mean
