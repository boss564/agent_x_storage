"""Tests for Schwarm 2 (A04-A06): CAS atomicity, burst determinism,
poison neutralization with zero-sum booking."""

import time
import pytest

from agents.air.a03_soft_finality import SoftFinalityEngine
from agents.air.a04_cas_coordinator import (
    CASCoordinator, CASRequest, CASSlotOp, CASStatus,
)
from agents.air.a05_cas_bomber import CASBomber, CPUBackend, GPUBurstBackend
from agents.air.a06_airspace_watch import AirspaceWatch, PoisonKind
from agents.air.finality_types import AttestationEnvelope


@pytest.fixture
def cas():
    c = CASCoordinator()
    c.seed_slot("ledger:head", "0xr0")
    c.seed_slot("pool:usdc", "0rp0")
    return c


def _req(rid, slots, deadline=None):
    return CASRequest(
        request_id=rid, slots=tuple(slots),
        source_dedup_key=f"S:1:{rid}",
        deadline=deadline or time.time() + 5.0, epoch=0,
    )


# -- A04: atomicity ---------------------------------------------------

def test_single_slot_commit(cas):
    req = _req("r1", [CASSlotOp("ledger:head", "0xr0", "0xr1")])
    res = cas.submit(req)
    assert res.status is CASStatus.COMMITTED
    assert cas.slot_root("ledger:head") == "0xr1"


def test_multi_slot_all_or_nothing(cas):
    # Second leg has a stale expected root -> nothing may be applied.
    req = _req("r2", [
        CASSlotOp("ledger:head", "0xr0", "0xr1"),
        CASSlotOp("pool:usdc", "0xSTALE", "0xp1"),
    ])
    res = cas.submit(req)
    assert res.status is CASStatus.CONFLICT
    assert res.conflicting_slot == "pool:usdc"
    assert cas.slot_root("ledger:head") == "0xr0"   # untouched


def test_idempotent_resubmit(cas):
    req = _req("r3", [CASSlotOp("ledger:head", "0xr0", "0xr1")])
    first = cas.submit(req)
    second = cas.submit(req)      # NATS redelivery
    assert first is second


def test_deadline_timeout(cas):
    req = _req("r4", [CASSlotOp("ledger:head", "0xr0", "0xr1")],
               deadline=time.time() - 1.0)
    assert cas.submit(req).status is CASStatus.TIMEOUT


# -- A05: burst determinism ------------------------------------------

def test_burst_backend_determinism(cas):
    def run(backend):
        c2 = CASCoordinator()
        c2.seed_slot("ledger:head", "0xr0")
        bomber = CASBomber(c2, backend=backend, batch_size=512)
        for i in range(1024):
            c2.seed_slot(f"s:{i}", f"0x{i:04d}")
            bomber.enqueue(_req(
                f"b{i}", [CASSlotOp(f"s:{i}", f"0x{i:04d}", f"0xn{i:04d}")],
            ))
        return [(r.committed, r.conflicts) for r in bomber.burst()]

    assert run(CPUBackend()) == run(GPUBurstBackend())


def test_burst_shortcut_skips_stale_roots(cas):
    bomber = CASBomber(cas, batch_size=16)
    bomber.enqueue(_req("ok", [CASSlotOp("ledger:head", "0xr0", "0xr1")]))
    bomber.enqueue(_req("stale", [CASSlotOp("pool:usdc", "0xWRONG", "0xp1")]))
    report = bomber.burst()[0]
    assert report.committed == 1
    assert report.shortcut_conflicts == 1


# -- A06: poison + zero-sum ------------------------------------------

class MockLedger:
    def __init__(self):
        self.entries = []

    def book_neutralization(self, dedup_key, state_root, reason):
        # Double-entry: destruction on one side, quarantine liability
        # on the other -> sum stays zero.
        self.entries.append((dedup_key, +1.0, reason))
        self.entries.append((dedup_key, -1.0, "quarantine_liability"))


def _env(dedup="S:1:0xi", epoch=0):
    return AttestationEnvelope(
        tx_hash="0xabc", state_root="0xroot", tier=1, signer="A03",
        ts=time.time(), expiry=time.time() + 2.0, epoch=epoch, seq=1,
        dedup_key=dedup,
    )


def test_watch_detects_constraint_bloat():
    engine = SoftFinalityEngine(signer_id="A03")
    ledger = MockLedger()
    watch = AirspaceWatch(engine._cache, ledger=ledger)
    env = _env()
    alert = watch.scan_envelope(env, slot_count=128)   # > limit 64
    assert alert is not None
    assert alert.kind is PoisonKind.CONSTRAINT_BLOAT
    assert watch.quarantine_size() == 1


def test_watch_neutralization_books_zero_sum():
    engine = SoftFinalityEngine(signer_id="A03")
    ledger = MockLedger()
    watch = AirspaceWatch(engine._cache, ledger=ledger)
    env = _env()
    watch.scan_envelope(env, slot_count=128)
    # Cache entry invalidated (rollback hooks fire downstream).
    assert engine._cache.get(env.dedup_key) is None
    # Zero-sum law: ledger entries net to zero.
    assert sum(amount for _, amount, _ in ledger.entries) == 0.0


def test_watch_detects_replay_storm():
    engine = SoftFinalityEngine(signer_id="A03")
    watch = AirspaceWatch(engine._cache)
    watch.scan_envelope(_env(epoch=0))     # first sighting, benign
    alert = watch.scan_envelope(_env(epoch=3))   # resurfaces 3 epochs later
    assert alert is not None
    assert alert.kind is PoisonKind.REPLAY_STORM
