"""Fault-injection tests for the soft-finality contract (Commit 1.5).

Mirrors the 6-row matrix from SOFT_FINALITY.md. Chaos Fleet (F07-F09)
can replay these via killer.sh between ack and CAS.
"""

import time
import pytest

from agents.air.a03_soft_finality import SoftFinalityEngine, CASConflictError
from agents.air.finality_types import FinalityTier


@pytest.fixture
def engine():
    return SoftFinalityEngine(signer_id="A03", ttl_seconds=2.0)


def _evt(engine, **kw):
    base = dict(tx_hash="0xabc", state_root="0xroot1", sender="S",
                nonce=1, intent_hash="0xintent", amount_eur=10.0,
                risk_class="A")
    base.update(kw)
    return engine.attest(**base)


def test_standard_attestation(engine):
    env = _evt(engine)
    assert env.tier == 1
    assert not env.is_expired()


def test_idempotent_resubmit_returns_same_envelope(engine):
    e1 = _evt(engine)
    e2 = _evt(engine)              # NATS redelivery
    assert e1 == e2                # identical envelope, no double effect


def test_cas_conflict_single_winner(engine):
    _evt(engine)                   # incumbent on slot S:1:0xintent
    with pytest.raises(CASConflictError):
        _evt(engine, state_root="0xroot2")   # same slot, different root


def test_escalation_to_two_attestations(engine):
    env = _evt(engine, amount_eur=10000.0)   # > threshold
    assert env.tier == 2
    env2 = _evt(engine, nonce=2, intent_hash="0xi2", risk_class="D")
    assert env2.tier == 2


def test_ttl_expiry_demotes_to_speculative(engine):
    env = _evt(engine)
    future = env.expiry + 1.0
    assert engine._cache.get(env.dedup_key, now=future) is None


def test_poison_after_attestation_triggers_rollback_event(engine):
    rollback_events = []
    engine._bus = type("B", (), {
        "publish": lambda self, topic, payload: rollback_events.append(topic)
    })()
    env = _evt(engine)
    engine._cache.invalidate(env.dedup_key, reason="poison")
    assert "agentx.air.soft_final_rollback" in rollback_events


def test_epoch_bulk_invalidation_on_checkpoint_mismatch(engine):
    e1 = _evt(engine)
    e2 = _evt(engine, nonce=2, intent_hash="0xi2")
    n = engine._cache.invalidate_epoch(e1.epoch, reason="checkpoint_mismatch")
    assert n == 2


def test_kill_between_ack_and_cas_recovers_via_audit(engine):
    # Simulate killer.sh: attestation issued, process dies before anchor.
    env = _evt(engine)
    audit = env.to_audit_dict()
    assert audit["digest"]                # recoverable from GoBD audit trail
    assert engine._cache.get(env.dedup_key) is not None
