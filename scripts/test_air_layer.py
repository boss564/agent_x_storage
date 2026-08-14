#!/usr/bin/env python3
"""Air-layer fault-injection tests — soft-finality state machine + cache.

Covers the Commit 1.5 hardening matrix: attestation, idempotency, anchor,
rollback/compensation, cache TTL eviction, and illegal transitions.

Usage:
  python3 scripts/test_air_layer.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.air.base import (
    AttestationEnvelope,
    FinalityState,
    FinalityTier,
)
from agents.air import A03SoftFinalityVerifier


def _envelope(tx_hash="tx1", signer="A02", epoch=0, seq=0) -> AttestationEnvelope:
    return AttestationEnvelope(
        tx_hash=tx_hash,
        state_root="a" * 32,
        tier=FinalityTier.SPECULATIVE,
        signer=signer,
        ts=time.time_ns(),
        expiry=time.time_ns() + 2_000_000_000,
        epoch=epoch,
        seq=seq,
    )


def run() -> int:
    checks = []
    v = A03SoftFinalityVerifier(ttl_s=0.05, max_entries=100)

    # 1. Attestation → SOFT_FINAL
    checks.append(("Attestation → SOFT_FINAL",
                   v.attest(_envelope("tx1")) == FinalityState.SOFT_FINAL))

    # 2. Double-submit → idempotent (same state, no double effect)
    s2 = v.attest(_envelope("tx1"))
    checks.append(("Double-submit idempotent",
                   s2 == FinalityState.SOFT_FINAL and v.stats()["cached_roots"] == 1))

    # 3. Anchor → ANCHORED
    checks.append(("Anchor → ANCHORED", v.anchor("tx1") == FinalityState.ANCHORED))

    # 4. Illegal transition (ANCHORED → ROLLED_BACK) rejected
    checks.append(("Illegal ANCHORED→ROLLED_BACK rejected",
                   v.invalidate("tx1") == FinalityState.ANCHORED))

    # 5. Rollback → COMPENSATED
    v.attest(_envelope("tx2"))
    v.invalidate("tx2")
    checks.append(("Rollback → COMPENSATED",
                   v.compensate("tx2") == FinalityState.COMPENSATED))

    # 6. Unauthorized signer → ROLLED_BACK
    checks.append(("Unauthorized signer → ROLLED_BACK",
                   v.attest(_envelope("tx3", signer="MALLORY")) == FinalityState.ROLLED_BACK))

    # 7. Cache TTL expiry → eviction (degrade L1→L0)
    v.attest(_envelope("tx4", epoch=0, seq=0))
    time.sleep(0.07)  # > ttl_s (0.05)
    checks.append(("Cache TTL eviction", v.cache_get(0, 0) is None))

    # 8. Evict ≠ Rollback (state stays SOFT_FINAL)
    checks.append(("Evict ≠ Rollback (state stays SOFT_FINAL)",
                   v._states.get("tx4") == FinalityState.SOFT_FINAL))

    all_pass = all(ok for _, ok in checks)
    for name, ok in checks:
        print(f"  {'✅' if ok else '❌'} {name}")
    passed = sum(1 for _, ok in checks if ok)
    failed = sum(1 for _, ok in checks if not ok)
    print(f"\n  ERGEBNIS: {passed} passed, {failed} failed ({len(checks)} total)")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(run())
