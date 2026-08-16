"""Hebel 1 — Evaluator redundancy: structural + runtime assertions.

Pre-reg: docs/HEBEL1_EVALUATOR_REDUNDANZ_PREREG.md

Finding: strictness is set but never read; all nine evaluators apply
abs(delta) <= 0.01. Pairwise disagreement ≡ 0 by construction.
Routing is 1-of-9 (StickySelector), not fan-out.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.protocol import AgentMessage, PayloadType
from agents_b2g.emergence.partner_select import StickySelector

# Import archetypes from the demo (source of EVALUATOR_PROFILES + EvaluatorAgent)
from scripts.demo_producer_cluster import (
    EVALUATOR_PROFILES,
    EvaluatorAgent,
    create_agent,
)


STRICTNESS_VALUES = [p[2] for p in EVALUATOR_PROFILES]  # decision_bias → strictness


def _verdict_from_amounts(net: float, tax: float, ret: float, gross: float) -> bool:
    """The actual rule used in EvaluatorAgent.act (strictness deliberately unused)."""
    delta = round(gross - (net + tax + ret), 10)
    return abs(delta) <= 0.01


def test_nine_distinct_evaluator_profiles():
    assert len(EVALUATOR_PROFILES) == 9
    ids = [p[0] for p in EVALUATOR_PROFILES]
    assert len(set(ids)) == 9
    assert "E01-bho-checker" in ids and "E09-tax-auditor" in ids


def test_strictness_does_not_affect_verdict():
    """Structural: verdict is pure function of amounts; strictness unused."""
    cases = [
        (100.0, 19.0, 0.0, 119.0),      # delta = 0.0
        (100.0, 19.0, 0.0, 119.005),    # delta = 0.005
        (100.0, 19.0, 0.0, 119.01),     # delta = 0.01 (boundary)
        (100.0, 19.0, 0.0, 119.02),     # delta = 0.02
    ]
    for net, tax, ret, gross in cases:
        verdicts = set()
        for _s in STRICTNESS_VALUES:
            holds = _verdict_from_amounts(net, tax, ret, gross)
            verdicts.add(holds)
        assert len(verdicts) == 1, f"disagreement at gross={gross}"


def test_strictness_is_dead_config_on_evaluator_agent():
    """Runtime: EvaluatorAgent.act ignores agent.strictness."""
    cases = [
        # (net, tax, ret, gross, expect_pass)
        (80.0, 15.0, 5.0, 100.0, True),    # delta = 0
        (83.0, 15.0, 5.0, 100.0, False),   # delta = -3 (inflated-style)
        (80.0, 15.0, 5.0, 100.005, True),  # |delta| = 0.005 <= 0.01
        (80.0, 15.0, 5.0, 100.02, False),  # |delta| = 0.02 > 0.01
    ]
    for net, tax, ret, gross, expect_pass in cases:
        outcomes = []
        for profile in EVALUATOR_PROFILES:
            agent = create_agent(profile, "evaluator", orch=None)
            assert hasattr(agent, "strictness")
            assert agent.strictness == profile[2]
            agent.inbox.append(AgentMessage(
                sender="P01-test",
                receiver=agent.id,
                payload_type=PayloadType.OFFER,
                content={
                    "contract_id": "TEST-001",
                    "gross_amount": gross,
                    "net_amount": net,
                    "tax_amount": tax,
                    "retention_amount": ret,
                    "inflated": not expect_pass,
                },
            ))
            agent.act()
            passed = agent.checks_passed == 1 and agent.checks_failed == 0
            failed = agent.checks_failed == 1 and agent.checks_passed == 0
            assert passed or failed
            outcomes.append(passed)
        assert len(set(outcomes)) == 1, (
            f"strictness-dependent disagreement at gross={gross}: {outcomes}"
        )
        assert outcomes[0] is expect_pass


def test_routing_is_one_of_nine_not_fanout():
    """Zusatzbefund: StickySelector delivers each OFFER to exactly one evaluator."""
    evaluators = [create_agent(p, "evaluator", orch=None) for p in EVALUATOR_PROFILES]
    sticky = StickySelector(threshold=8)
    recv_load = {e.id: 0 for e in evaluators}

    def _load(a):
        return recv_load.get(a.id, 0) + len(a.inbox)

    chosen = sticky.select("P01-constructor", "evaluator", evaluators, _load)
    assert chosen is not None
    assert chosen in evaluators
    msg = AgentMessage(
        sender="P01-constructor",
        receiver="evaluator",
        payload_type=PayloadType.OFFER,
        content={
            "contract_id": "P01-0001",
            "gross_amount": 100.0,
            "net_amount": 80.0,
            "tax_amount": 15.0,
            "retention_amount": 5.0,
            "inflated": False,
        },
    )
    chosen.inbox.append(msg)
    recipients = sum(1 for e in evaluators if e.inbox)
    assert recipients == 1
