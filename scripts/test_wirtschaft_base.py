"""Baustein 1 tests: Wirtschaftsagenten foundation."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal

import pytest

from agents_b2g.wirtschaft import (
    KompetenzKlasse, KompetenzProfil, StateKeeper, GasFrictionMonitor,
    WormLog, CryptoModule, MessageBus, WirtschaftAgent,
)


# --- StateKeeper --------------------------------------------------------

def test_statekeeper_credit_debit_balance():
    sk = StateKeeper({})
    sk.credit("EURe", "100.50")
    assert sk.balance("EURe") == Decimal("100.50")
    sk.debit("EURe", "40.25")
    assert sk.balance("EURe") == Decimal("60.25")


def test_statekeeper_insufficient_balance_raises():
    sk = StateKeeper({})
    sk.credit("EURe", "10")
    with pytest.raises(ValueError):
        sk.debit("EURe", "20")


def test_statekeeper_initial_balances():
    sk = StateKeeper({}, initial_balances={"AGX": "500"})
    assert sk.balance("AGX") == Decimal("500")


# --- GasFrictionMonitor ---------------------------------------------------

def test_gas_deduction_and_drain():
    drained = []
    gm = GasFrictionMonitor(tank_capacity=3.0, g_tx=1.0,
                            on_depleted=lambda: drained.append(True))
    assert gm.deduct() is True    # gas -> 2
    assert gm.deduct() is True    # gas -> 1
    assert gm.deduct() is True    # gas -> 0, drain fires, message still allowed
    assert gm.drained is True
    assert drained == [True]
    assert gm.deduct() is False   # already drained


def test_gas_refuel_clears_drain():
    gm = GasFrictionMonitor(tank_capacity=2.0, g_tx=1.0)
    gm.deduct(); gm.deduct()
    assert gm.drained is True
    gm.refuel(1.0)
    assert gm.drained is False
    assert gm.deduct() is True


# --- WormLog -------------------------------------------------------------

def test_wormlog_chain_verifies():
    log = WormLog()
    log.append("A", {"x": 1})
    log.append("B", {"y": 2})
    assert log.verify_chain() is True
    assert len(log) == 2


def test_wormlog_tamper_detected():
    log = WormLog()
    log.append("A", {"x": 1})
    log.append("B", {"y": 2})
    log._entries[0]["payload"] = {"x": 999}   # tamper
    assert log.verify_chain() is False


# --- CryptoModule ---------------------------------------------------------

def test_crypto_digest_and_sign():
    cm = CryptoModule(enabled=True)
    d = cm.digest({"a": 1})
    assert d is not None and len(d) == 64
    assert cm.sign({"a": 1}) == d   # Baustein 1 fallback = digest


def test_crypto_disabled():
    cm = CryptoModule(enabled=False)
    assert cm.digest({"a": 1}) is None
    assert cm.sign({"a": 1}) is None


# --- MessageBus ------------------------------------------------------------

def test_messagebus_topic_and_publish():
    mb = MessageBus("liquidity-1")
    assert mb.topic("settlement-1", "request") == \
        "agent.liquidity-1.settlement-1.request"
    env = mb.publish("settlement-1", {"amt": 5}, kind="request")
    assert env["target"] == "settlement-1"
    assert env["kind"] == "request"
    assert len(mb.published) == 1


# --- WirtschaftAgent composition -------------------------------------------

def test_wirtschaft_agent_send_deducts_gas_and_logs():
    a = WirtschaftAgent("liq-1", klasse=KompetenzKlasse.KAPITAL,
                        gas_tank=5.0, g_tx=1.0)
    env = a.send("settle-1", {"amt": 10})
    assert env is not None
    assert a.gas_monitor.gas == 4.0
    assert env["digest"] is not None and env["signature"] is not None
    actions = [e["action"] for e in a.worm_log.entries]
    assert "SEND" in actions
    assert a.worm_log.verify_chain() is True


def test_wirtschaft_agent_drain_blocks_send():
    a = WirtschaftAgent("liq-2", gas_tank=1.0, g_tx=1.0)
    assert a.send("x", {}) is not None   # spends the last gas, drains
    assert a.drained is True
    assert a.send("x", {}) is None       # blocked
    actions = [e["action"] for e in a.worm_log.entries]
    assert "GAS_DEPLETED" in actions
    assert "SEND_BLOCKED_DRAIN" in actions


def test_wirtschaft_agent_competence_slot():
    a = WirtschaftAgent("gov-1", klasse=KompetenzKlasse.GOVERNANCE)
    assert isinstance(a.competence, KompetenzProfil)
    assert a.competence.klasse == KompetenzKlasse.GOVERNANCE
    assert a.competence.exklusive_rechte == []   # filled in Baustein 2


def test_wirtschaft_agent_tick_logs():
    class _Demo(WirtschaftAgent):
        def decide(self):
            return "noop"

        def act(self):
            return []

    a = _Demo("tick-1")
    a.tick({})
    actions = [e["action"] for e in a.worm_log.entries]
    assert "TICK" in actions
    assert a.worm_log.verify_chain() is True


def test_wirtschaft_agent_to_dict():
    a = WirtschaftAgent("t-1", initial_balances={"EURe": "10"})
    d = a.to_dict()
    assert d["balances"]["EURe"] == "10"
    assert d["drained"] is False
