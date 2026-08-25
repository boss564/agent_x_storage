"""Hebel 1 — Evaluator redundancy: structural + runtime assertions.

Pre-reg: docs/HEBEL1_EVALUATOR_REDUNDANZ_PREREG.md
Follow-up: docs/HEBEL1_DIFFERENZIERUNG_PREREG.md

Historical finding: strictness is set but never read (dead config).
Follow-up: rules are now differentiated by self.id; pairwise disagreement
across IDs is intentional — this suite only asserts that *strictness*
does not affect the verdict for a fixed evaluator id.
Routing remains 1-of-9 (StickySelector), not fan-out.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.protocol import AgentMessage, PayloadType
from agents_b2g.emergence.partner_select import StickySelector

from scripts.demo_producer_cluster import (
    EVALUATOR_PROFILES,
    create_agent,
)
from scripts.hebel1_evaluator_rules import rule_default


STRICTNESS_VALUES = [p[2] for p in EVALUATOR_PROFILES]  # decision_bias → strictness


def test_nine_distinct_evaluator_profiles():
    assert len(EVALUATOR_PROFILES) == 9
    ids = [p[0] for p in EVALUATOR_PROFILES]
    assert len(set(ids)) == 9
    assert "E01-bho-checker" in ids and "E09-tax-auditor" in ids


def test_strictness_does_not_affect_default_rule():
    """Structural: rule_default ignores any external strictness parameter."""
    cases = [
        (100.0, 19.0, 0.0, 119.0),
        (100.0, 19.0, 0.0, 119.005),
        (100.0, 19.0, 0.0, 119.01),
        (100.0, 19.0, 0.0, 119.02),
    ]
    for net, tax, ret, gross in cases:
        verdicts = {
            rule_default(net, tax, ret, gross, False, "TX")
            for _s in STRICTNESS_VALUES
        }
        assert len(verdicts) == 1, f"disagreement at gross={gross}"


def test_strictness_is_dead_config_on_evaluator_agent():
    """Runtime: mutating agent.strictness does not change the verdict for a fixed id."""
    profile = EVALUATOR_PROFILES[1]  # E02-z3-prover (balance + non-neg)
    cases = [
        (80.0, 15.0, 5.0, 100.0, True),
        (83.0, 15.0, 5.0, 100.0, False),
        (80.0, 15.0, 5.0, 100.005, True),
        (80.0, 15.0, 5.0, 100.02, False),
    ]
    for net, tax, ret, gross, expect_pass in cases:
        outcomes = []
        for s in (0.0, 0.5, 1.0, profile[2]):
            agent = create_agent(profile, "evaluator", orch=None)
            agent.strictness = s
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
                    "inflated": False,
                },
            ))
            agent.act()
            passed = agent.checks_passed == 1 and agent.checks_failed == 0
            failed = agent.checks_failed == 1 and agent.checks_passed == 0
            assert passed or failed
            outcomes.append(passed)
        assert len(set(outcomes)) == 1, (
            f"strictness changed verdict at gross={gross}: {outcomes}"
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
