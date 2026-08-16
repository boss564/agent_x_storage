"""Baustein 3 tests: 9 agents + distributed Freigabe/Delegation flows."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.wirtschaft import KompetenzKlasse, Aktion
from agents_b2g.wirtschaft.agents import AGENT_CLASSES, create_agent
from agents_b2g.wirtschaft.schwarm import build_schwarm


def test_all_nine_agents_created_with_profiles():
    for name in AGENT_CLASSES:
        agent = create_agent(name)
        assert agent.competence is not None
        assert agent.competence.klasse is not None


def test_agents_compose_their_subagents():
    liq = create_agent("liquidity")
    assert hasattr(liq, "pool_manager") and hasattr(liq, "gas_bank")
    ret = create_agent("retention")
    assert hasattr(ret, "compliance_engine") and hasattr(ret, "policy_store")


def test_subagent_bound_to_parent():
    liq = create_agent("liquidity")
    assert liq.pool_manager.parent is liq


def test_class_assignments():
    assert create_agent("liquidity").competence.klasse == KompetenzKlasse.KAPITAL
    assert create_agent("minter").competence.klasse == KompetenzKlasse.AUSFUEHRUNG
    assert create_agent("retention").competence.klasse == KompetenzKlasse.GOVERNANCE


# --- distributed Freigabe flow ---

def test_approval_flow_grant():
    schwarm, agents = build_schwarm()
    result = schwarm.execute(agents["minter"].id, Aktion.TOKEN_MINT)
    assert result["status"] == "executed"
    assert result["mit_freigabe"] is True


def test_approval_flow_deny():
    schwarm, agents = build_schwarm()
    agents["retention"].compliance_engine.policy.deny(Aktion.TOKEN_MINT)
    result = schwarm.execute(agents["minter"].id, Aktion.TOKEN_MINT)
    assert result["status"] == "freigabe_denied"


def test_compliance_engine_grant_and_deny():
    ret = create_agent("retention")
    verdict = ret.compliance_engine.check({"aktion": Aktion.TOKEN_MINT, "requester": "minter-1"})
    assert verdict["decision"] == "GRANT"
    ret.compliance_engine.policy.deny(Aktion.TOKEN_MINT)
    verdict = ret.compliance_engine.check({"aktion": Aktion.TOKEN_MINT, "requester": "minter-1"})
    assert verdict["decision"] == "DENY"


# --- delegation flow ---

def test_delegation_compliance_to_governance():
    schwarm, agents = build_schwarm()
    result = schwarm.execute(agents["liquidity"].id, Aktion.COMPLIANCE_CHECK)
    assert result["status"] == "delegated"
    assert result["delegated_to"] == agents["retention"].id
    assert result["delegated_result"]["status"] == "executed"


def test_retention_delegates_execution_to_settlement():
    schwarm, agents = build_schwarm()
    result = schwarm.execute(agents["retention"].id, Aktion.TX_EXECUTE)
    assert result["status"] == "delegated"
    assert result["delegated_to"] == agents["settlement"].id


def test_gewaltenteilung_a_cannot_compliance_directly():
    liq = create_agent("liquidity")
    assert liq.may(Aktion.COMPLIANCE_CHECK) is False


def test_schwarm_unknown_agent():
    schwarm, _ = build_schwarm()
    assert schwarm.execute("ghost-1", Aktion.POOL_READ)["status"] == "unknown_agent"
