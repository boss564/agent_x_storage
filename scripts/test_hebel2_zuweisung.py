"""Tests for Hebel 2 assignment logic and evaluation."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.hebel2_assignment import (
    EVALUATOR_IDS,
    assign_status_quo,
    assign_null_model,
    assign_treatment,
    load_balance_metric,
    inbox_depth_from_agent,
)
from scripts.eval_hebel2_zuweisung import run_trial, evaluate
from scripts.demo_producer_cluster import create_agent, EVALUATOR_PROFILES


def test_status_quo_deterministic():
    a = assign_status_quo("TX-123", EVALUATOR_IDS)
    b = assign_status_quo("TX-123", EVALUATOR_IDS)
    assert a == b


def test_status_quo_distributes_across_evaluators():
    targets = set(assign_status_quo(f"TX-{i}", EVALUATOR_IDS) for i in range(100))
    assert len(targets) > 1


def test_null_model_uniform_distribution():
    rng = random.Random(1)
    targets = set(assign_null_model("TX-x", EVALUATOR_IDS, rng) for _ in range(200))
    assert len(targets) == len(EVALUATOR_IDS)


def test_treatment_picks_least_loaded():
    state = {
        "E01-bho-checker": {"inbox_depth": 5},
        "E02-z3-prover": {"inbox_depth": 1},
        "E03-gobd-auditor": {"inbox_depth": 3},
    }
    for eid in EVALUATOR_IDS:
        if eid not in state:
            state[eid] = {"inbox_depth": 10}
    target = assign_treatment("TX-x", EVALUATOR_IDS, state)
    assert target == "E02-z3-prover"


def test_treatment_tie_break_deterministic():
    state = {eid: {"inbox_depth": 0} for eid in EVALUATOR_IDS}
    a = assign_treatment("TX-x", EVALUATOR_IDS, state)
    b = assign_treatment("TX-x", EVALUATOR_IDS, state)
    assert a == b


def test_load_balance_metric_perfect_balance():
    load = {eid: 10 for eid in EVALUATOR_IDS}
    assert abs(load_balance_metric(load)) < 1e-9


def test_load_balance_metric_imbalanced():
    load = {eid: 0 for eid in EVALUATOR_IDS}
    load["E01-bho-checker"] = 100
    assert load_balance_metric(load) > 0


def test_real_agent_inbox_depth_field():
    """Adaptionsstelle: BaseAgent.inbox is a list → depth = len(inbox)."""
    agent = create_agent(EVALUATOR_PROFILES[0], "evaluator", orch=None)
    assert inbox_depth_from_agent(agent) == 0
    agent.inbox.append({"dummy": True})
    assert inbox_depth_from_agent(agent) == 1


def test_evaluate_treatment_beats_null_when_inbox_accumulates():
    """With inbox_depth updates, least-loaded treatment beats random (proxy)."""
    trials = {"status_quo": [], "null_model": [], "treatment": []}
    txs = [f"TX-{i}" for i in range(100)]
    for strategy in trials:
        for seed in range(30):
            trials[strategy].append(run_trial(strategy, txs, seed))
    result = evaluate(trials)
    assert result["verdict"] == "POSITIVBEFUND"
    assert result["delta_treatment_vs_null"] >= 0.05


def test_stateless_treatment_degenerates_to_tie_break():
    """If inbox never grows, treatment always picks the same id (tie-break)."""
    from scripts.hebel2_assignment import assign_treatment
    state = {eid: {"inbox_depth": 0} for eid in EVALUATOR_IDS}
    targets = [assign_treatment(f"TX-{i}", EVALUATOR_IDS, state) for i in range(50)]
    assert len(set(targets)) == 1
    assert targets[0] == min(EVALUATOR_IDS)  # (0, eid) tie-break


def test_full_pipeline_runs():
    tx_rng = random.Random(1)
    transactions = [f"TX-{tx_rng.randint(0, 999999):06d}" for _ in range(200)]
    trials = {"status_quo": [], "null_model": [], "treatment": []}
    for strategy in trials:
        for seed in range(5):
            trials[strategy].append(run_trial(strategy, transactions, seed))
    result = evaluate(trials)
    assert result["verdict"] in ("POSITIVBEFUND", "NEGATIVBEFUND", "INCONCLUSIVE")
