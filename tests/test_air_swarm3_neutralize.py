"""Tests for Schwarm 3 (A07-A09): in-flight neutralization with
zero-sum compensation, fallback conservation, GoBD hash-chain audit."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # for agents_air_testkit

import pytest

from agents_air_testkit import MockBus, MockLedger

from agents.air.finality_types import AttestationEnvelope
from agents.air.a06_airspace_watch import AirspaceWatch, PoisonKind, WatchAlert
from agents.air.a07_inflight_neutralizer import (
    InFlightNeutralizer, InFlightRegistry,
)
from agents.air.a08_fallback_coordinator import FallbackCoordinator, FallbackReason
from agents.air.a09_awacs_datalink import AWACSDatalink


def _env(dedup="S:1:0xi", epoch=0):
    return AttestationEnvelope(
        tx_hash="0xabc", state_root="0xroot", tier=1, signer="A03",
        ts=time.time(), expiry=time.time() + 2.0, epoch=epoch, seq=1,
        dedup_key=dedup,
    )


def _alert(dedup="S:1:0xi"):
    return WatchAlert(kind=PoisonKind.CONSTRAINT_BLOAT, dedup_key=dedup,
                      score=0.8, detail="constraint_bloat", ts=time.time())


# -- A07: neutralization ------------------------------------------------

@pytest.fixture
def neutralizer_setup():
    registry = InFlightRegistry()
    ledger = MockLedger()
    bus = MockBus()

    class _Cache:   # minimal stub of SoftFinalityCache
        def __init__(self):
            self.invalidated = []

        def invalidate(self, key, reason):
            self.invalidated.append((key, reason))
            return True

    cache = _Cache()
    neutralizer = InFlightNeutralizer(registry, cache, ledger=ledger,
                                      event_bus=bus)
    return registry, cache, ledger, bus, neutralizer


def test_neutralize_revokes_and_compensates(neutralizer_setup):
    registry, cache, ledger, bus, neu = neutralizer_setup
    env = _env()
    registry.register(env)
    report = neu.neutralize(_alert())
    assert report.revoked is True
    assert report.compensation_id == "comp:S:1:0xi"
    assert registry.active_count() == 0
    assert ("S:1:0xi", "neutralized:constraint_bloat") in cache.invalidated
    assert "agentx.air.compensation.request" in bus.topics
    assert ledger.is_balanced()          # A06 debit + A07 credit = 0


def test_neutralize_is_idempotent(neutralizer_setup):
    registry, _, ledger, bus, neu = neutralizer_setup
    registry.register(_env())
    first = neu.neutralize(_alert())
    second = neu.neutralize(_alert())
    assert first.revoked is True
    assert second.revoked is False
    assert second.reason == "already_revoked"
    assert ledger.compensation_count() == 1   # exactly one credit leg


def test_neutralize_refuses_anchored_envelope(neutralizer_setup):
    _, _, _, bus, neu = neutralizer_setup
    # Not registered -> already anchored or unknown.
    report = neu.neutralize(_alert(dedup="S:9:anchored"))
    assert report.revoked is False
    assert report.reason == "not_in_flight"
    assert "agentx.air.neutralization.refused" in bus.topics


# -- A08: fallback + conservation ----------------------------------------

def test_cas_loser_routed_to_surface():
    bus = MockBus()
    fb = FallbackCoordinator(event_bus=bus)
    ticket = fb.accept({"tx": "0x1"}, FallbackReason.CAS_CONFLICT)
    assert ticket.attempts == 1
    routed = bus.payloads("agentx.air.fallback.routed")[0]
    assert routed["subject"] == "agentx.surface.fallback"
    assert routed["reason"] == "cas_conflict"


def test_dead_letter_after_max_attempts():
    fb = FallbackCoordinator()
    ticket = fb.accept({"tx": "0x2"}, FallbackReason.TTL_EXPIRY)
    now = time.time()
    # 2 retries -> attempts=3 (not yet dead)
    for i in range(2):
        ticket = fb.retry(ticket.ticket_id, now=now + 4000 * (i + 1))
        assert ticket is not None
        assert not ticket.dead_lettered
    # 3rd retry -> attempts=4 > MAX_ATTEMPTS(3) -> dead letter
    ticket = fb.retry(ticket.ticket_id, now=now + 20000)
    assert ticket.dead_lettered is True
    # Backoff capped at 1 h (Wave 7 DLQ).
    fb2 = FallbackCoordinator()
    t2 = fb2.accept({"tx": "0x3"}, FallbackReason.CAPACITY_SHED)
    fb2.retry(t2.ticket_id, now=now)
    assert fb2._tickets[t2.ticket_id].next_retry_at <= now + 3600.0


def test_conservation_invariant_holds():
    fb = FallbackCoordinator()
    for _ in range(100):
        fb.mark_ingress()
    for _ in range(97):
        fb.mark_completed()           # finalized in the air layer
    for _ in range(3):
        fb.accept({"tx": "x"}, FallbackReason.CAS_CONFLICT)
    balance = fb.conservation_balance()
    assert balance["holds"] is True
    assert balance["delta"] == 0      # 100 = 97 + 3


# -- A09: GoBD hash chain ---------------------------------------------------

def test_hash_chain_records_and_verifies():
    dl = AWACSDatalink()
    dl.record("agentx.air.cas.committed", {"request_id": "r1"})
    dl.record("agentx.air.watch.alert", {"kind": "constraint_bloat"})
    assert dl.chain_length == 3       # genesis + 2 events
    assert dl.verify() is True


def test_hash_chain_detects_tampering():
    dl = AWACSDatalink()
    dl.record("agentx.air.cas.committed", {"request_id": "r1"})
    dl.record("agentx.air.neutralized", {"dedup_key": "S:1:0xi"})
    # Auditor scenario: someone alters a historical payload.
    dl._records[1]["payload"]["request_id"] = "r999"
    assert dl.verify() is False


def test_gobd_export_writes_jsonl_and_certificate(tmp_path):
    dl = AWACSDatalink()
    dl.record("agentx.air.soft_final_attested", {"dedup_key": "S:1:0xi"})
    target = str(tmp_path / "air_audit.jsonl")
    report = dl.export(target)
    assert report.records == 2
    assert report.tail_hash == dl.tail_hash
    import json
    import os
    assert os.path.exists(target)
    assert os.path.exists(report.certificate_path)
    lines = open(target).read().strip().split("\n")
    assert len(lines) == 2
    cert = json.load(open(report.certificate_path))
    assert cert["algorithm"] == "SHA3-256"
    assert cert["records"] == 2
