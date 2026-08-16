"""Baustein 2 tests: Funktionsschranken / Gewaltenteilung."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.wirtschaft import KompetenzKlasse, WirtschaftAgent
from agents_b2g.wirtschaft.profiles import Aktion, WIRTSCHAFT_PROFILE, profil_fuer


def _agent(name, agent_id=None):
    a = WirtschaftAgent(agent_id or f"{name}-1")
    a.competence = profil_fuer(name)
    return a


# --- may(): default-deny ---

def test_may_exclusive_right():
    liq = _agent("liquidity")
    assert liq.may(Aktion.POOL_READ) is True
    assert liq.may(Aktion.TOKEN_TRANSFER) is True


def test_may_deficit_denied():
    liq = _agent("liquidity")
    assert liq.may(Aktion.COMPLIANCE_CHECK) is False
    assert liq.may(Aktion.RISK_ASSESS) is False


def test_may_unknown_action_denied():
    liq = _agent("liquidity")
    assert liq.may("some.random.action") is False


def test_may_no_profile_denied():
    a = WirtschaftAgent("noprof-1")
    assert a.may(Aktion.POOL_READ) is False


# --- Gewaltenteilung across the three classes ---

def test_class_a_cannot_check_compliance_or_risk():
    for name in ["liquidity", "treasury", "staking"]:
        a = _agent(name)
        assert a.may(Aktion.COMPLIANCE_CHECK) is False
        assert a.may(Aktion.RISK_ASSESS) is False


def test_class_b_cannot_assess_risk():
    for name in ["minter", "settlement", "paymaster"]:
        assert _agent(name).may(Aktion.RISK_ASSESS) is False


def test_class_c_approves_but_does_not_execute():
    ret = _agent("retention")
    assert ret.may(Aktion.TX_APPROVE) is True
    assert ret.may(Aktion.TX_EXECUTE) is False


def test_class_c_holds_no_liquidity_rights():
    for name in ["burn", "retention", "risk_auditor"]:
        a = _agent(name)
        assert a.may(Aktion.POOL_WRITE) is False
        assert a.may(Aktion.TOKEN_TRANSFER) is False


# --- execute(): routing decisions ---

def test_execute_allowed_right():
    assert _agent("liquidity").execute(Aktion.POOL_READ)["status"] == "executed"


def test_execute_deficit_delegates_to_governance():
    result = _agent("liquidity").execute(Aktion.COMPLIANCE_CHECK)
    assert result["status"] == "delegated"
    assert result["freigabe_request"]["target"] == \
        f"klasse.{KompetenzKlasse.GOVERNANCE.value}"


def test_execute_approval_required_right():
    result = _agent("minter").execute(Aktion.TOKEN_MINT)
    assert result["status"] == "freigabe_required"
    assert result["freigabe_request"]["target"] == \
        f"klasse.{KompetenzKlasse.GOVERNANCE.value}"


def test_execute_with_granted_freigabe():
    minter = _agent("minter")
    minter.grant_freigabe(Aktion.TOKEN_MINT)
    result = minter.execute(Aktion.TOKEN_MINT)
    assert result["status"] == "executed"
    assert result["mit_freigabe"] is True


def test_retention_delegates_execution_to_class_b():
    result = _agent("retention").execute(Aktion.TX_EXECUTE)
    assert result["status"] == "delegated"
    assert result["freigabe_request"]["target"] == \
        f"klasse.{KompetenzKlasse.AUSFUEHRUNG.value}"


def test_treasury_delegates_ledger_to_class_b():
    result = _agent("treasury").execute(Aktion.LEDGER_ANCHOR)
    assert result["status"] == "delegated"
    assert result["freigabe_request"]["target"] == \
        f"klasse.{KompetenzKlasse.AUSFUEHRUNG.value}"


# --- WORM logging of gate decisions ---

def test_gate_decisions_logged():
    liq = _agent("liquidity")
    liq.execute(Aktion.POOL_READ)          # executed
    liq.execute(Aktion.COMPLIANCE_CHECK)   # delegated
    actions = [e["action"] for e in liq.worm_log.entries]
    assert "EXECUTE" in actions
    assert "EXECUTE_DELEGATED" in actions
    assert liq.worm_log.verify_chain() is True


# --- profile isolation + completeness ---

def test_profiles_not_shared():
    p1, p2 = profil_fuer("liquidity"), profil_fuer("liquidity")
    p1.exklusive_rechte.append("injected")
    assert "injected" not in p2.exklusive_rechte


def test_all_nine_profiles_defined():
    expected = {"liquidity", "treasury", "staking", "minter", "settlement",
                "paymaster", "burn", "retention", "risk_auditor"}
    assert set(WIRTSCHAFT_PROFILE.keys()) == expected
