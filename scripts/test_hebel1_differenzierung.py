"""Tests for Hebel 1 Follow-up: differentiated rules + disagreement measurement."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.hebel1_evaluator_rules import EVALUATOR_RULES
from scripts.hebel1_disagreement_measurement import (
    evaluate_all, measure,
)


def make_tx(net=100.0, tax=19.0, ret=5.0, gross=124.0,
            inflated=False, contract_id="TX-001"):
    return {"net": net, "tax": tax, "ret": ret, "gross": gross,
            "inflated": inflated, "contract_id": contract_id}


def test_nine_rules_registered():
    assert len(EVALUATOR_RULES) == 9


def test_normal_invoice_passes_all():
    """A clean, balanced invoice (19% VAT, 5% retention) passes all nine."""
    verdicts = evaluate_all(make_tx())
    assert all(verdicts.values()), f"Expected all PASS, got {verdicts}"


def test_strict_zero_sum_fails_on_small_delta():
    """E01 (strict zero-sum) fails on a small non-zero delta; E02 passes."""
    verdicts = evaluate_all(make_tx(gross=124.005))  # delta = 0.005
    assert verdicts["E01-bho-checker"] is False
    assert verdicts["E02-z3-prover"] is True


def test_inflated_invoice_fails_fraud_detector_only():
    """E08 (fraud-detector) fails on inflated; others (balanced) pass."""
    verdicts = evaluate_all(make_tx(inflated=True))
    assert verdicts["E08-fraud-detector"] is False
    assert verdicts["E01-bho-checker"] is True


def test_negative_amount_fails_z3():
    """E02 (z3-prover) fails on a negative amount."""
    verdicts = evaluate_all(make_tx(net=-10.0, gross=14.0))  # delta = 0
    assert verdicts["E02-z3-prover"] is False


def test_high_tax_rate_splits_compliance_and_auditor():
    """25% tax: E04 (0-30%) passes, E09 (0-20%) fails."""
    verdicts = evaluate_all(make_tx(net=100.0, tax=25.0, ret=5.0, gross=130.0))
    assert verdicts["E04-compliance"] is True
    assert verdicts["E09-tax-auditor"] is False


def test_high_retention_fails_iot():
    """15% retention: E05 (<=10%) fails."""
    verdicts = evaluate_all(make_tx(net=100.0, tax=19.0, ret=20.0, gross=139.0))
    assert verdicts["E05-iot-verifier"] is False


def test_disagreement_on_mixed_batch():
    """A diverse batch produces non-zero disagreement."""
    txs = [
        make_tx(),
        make_tx(gross=124.005),
        make_tx(inflated=True),
        make_tx(net=100.0, tax=25.0, ret=5.0, gross=130.0),
    ]
    result = measure(txs)
    assert result["pairwise_disagreement_rate"] > 0.0


def test_identical_normal_batch_zero_disagreement():
    """Identical normal invoices produce zero disagreement (NICHT_WIRKSAM)."""
    result = measure([make_tx() for _ in range(10)])
    assert result["pairwise_disagreement_rate"] == 0.0
    assert result["classification"] == "NICHT_WIRKSAM"


def test_dead_rule_detection_flags_never_failing():
    """On all-normal data, rules that never FAIL are flagged as dead."""
    result = measure([make_tx() for _ in range(10)])
    assert result["n_dead_rules"] == 9


def test_act_uses_registry_by_id():
    """EvaluatorAgent.act looks up rule via self.id (not hardcoded delta)."""
    from scripts.demo_producer_cluster import EvaluatorAgent
    from agents_b2g.protocol import AgentMessage, PayloadType

    agent = EvaluatorAgent("E08-fraud-detector")
    agent.inbox.append(AgentMessage(
        sender="P01", receiver=agent.id,
        payload_type=PayloadType.OFFER,
        content={
            "contract_id": "P01-0001",
            "gross_amount": 124.0,
            "net_amount": 100.0,
            "tax_amount": 19.0,
            "retention_amount": 5.0,
            "inflated": True,
        },
    ))
    msgs = agent.act()
    # E08 rejects inflated → alert, no BHO_PROOF
    assert not any(m.payload_type == PayloadType.BHO_PROOF for m in msgs)
    assert agent.checks_failed == 1
