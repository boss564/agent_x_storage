#!/usr/bin/env python3
"""A03 Soft-Finality Verifikator — attests envelopes and manages the finality state machine.

Manages a versioned state-root cache keyed by (epoch, seq) with TTL + LRU
eviction and invalidation hooks. Core invariant (see SOFT_FINALITY.md): every
SOFT_FINAL event ends either ANCHORED or COMPENSATED — never dangling.
"""

import time
from typing import Any, Dict, Optional, Tuple

from .base import (
    AirInterceptorAgent,
    AttestationEnvelope,
    FinalityState,
    FINALITY_TRANSITIONS,
)


class A03SoftFinalityVerifier(AirInterceptorAgent):
    """Attests envelopes (SOFT_FINAL) and tracks their finality lifecycle."""

    def __init__(self, ttl_s: float = 1.0, max_entries: int = 10_000):
        super().__init__("A03")
        self.ttl_s = ttl_s
        self.max_entries = max_entries
        self._states: Dict[str, FinalityState] = {}          # tx_hash → state
        self._cache: Dict[Tuple[int, int], AttestationEnvelope] = {}  # (epoch, seq) → envelope
        self._cache_ts: Dict[Tuple[int, int], float] = {}              # (epoch, seq) → inserted_at
        self._order: list = []                               # LRU order

    # ── State machine ──────────────────────────────────────────────────────

    def _transition(self, tx_hash: str, new_state: FinalityState) -> bool:
        cur = self._states.get(tx_hash, FinalityState.RECEIVED)
        if new_state not in FINALITY_TRANSITIONS.get(cur, set()):
            return False
        self._states[tx_hash] = new_state
        return True

    def attest(self, envelope: AttestationEnvelope) -> FinalityState:
        """Verify signer + cache state-root → SOFT_FINAL (idempotent)."""
        tx_hash = envelope.tx_hash
        cur = self._states.get(tx_hash, FinalityState.RECEIVED)
        if cur in (FinalityState.SOFT_FINAL, FinalityState.ANCHORED):
            return cur  # idempotent ack — NATS redelivery returns the same state

        # Reject unauthorized signers (production: verify TEE/ECDSA signature).
        if envelope.signer != "A02":
            self._states[tx_hash] = FinalityState.ROLLED_BACK
            return FinalityState.ROLLED_BACK

        if not self._transition(tx_hash, FinalityState.VERIFIED):
            return cur
        if not self._transition(tx_hash, FinalityState.SOFT_FINAL):
            return cur
        self._cache_put((envelope.epoch, envelope.seq), envelope)
        self.intercept_count += 1
        return FinalityState.SOFT_FINAL

    def anchor(self, tx_hash: str) -> FinalityState:
        """SOFT_FINAL → ANCHORED (L1 anchor confirmed)."""
        self._transition(tx_hash, FinalityState.ANCHORED)
        return self._states.get(tx_hash, FinalityState.RECEIVED)

    def invalidate(self, tx_hash: str) -> FinalityState:
        """Poison found / checkpoint mismatch → ROLLED_BACK + cache removal."""
        if self._transition(tx_hash, FinalityState.ROLLED_BACK):
            self._cache_remove_by_tx(tx_hash)
        return self._states.get(tx_hash, FinalityState.RECEIVED)

    def compensate(self, tx_hash: str) -> FinalityState:
        """ROLLED_BACK → COMPENSATED (economic compensation applied)."""
        self._transition(tx_hash, FinalityState.COMPENSATED)
        return self._states.get(tx_hash, FinalityState.RECEIVED)

    # ── Versioned cache (TTL + LRU) ────────────────────────────────────────

    def _cache_put(self, key: Tuple[int, int], envelope: AttestationEnvelope) -> None:
        self._evict_expired()
        self._cache[key] = envelope
        self._cache_ts[key] = time.time()
        if key in self._order:
            self._order.remove(key)
        self._order.append(key)
        while len(self._cache) > self.max_entries:  # LRU eviction — evict ≠ rollback
            oldest = self._order.pop(0)
            self._cache.pop(oldest, None)
            self._cache_ts.pop(oldest, None)

    def cache_get(self, epoch: int, seq: int) -> Optional[AttestationEnvelope]:
        """Return the cached envelope if still within TTL; else degrade (L1→L0)."""
        key = (epoch, seq)
        env = self._cache.get(key)
        if env is None:
            return None
        if time.time() - self._cache_ts[key] > self.ttl_s:
            self._cache.pop(key, None)
            self._cache_ts.pop(key, None)
            self._order.remove(key)
            return None
        return env

    def _evict_expired(self) -> None:
        now = time.time()
        for key in list(self._cache_ts):
            if now - self._cache_ts[key] > self.ttl_s:
                self._cache.pop(key, None)
                self._cache_ts.pop(key, None)
                self._order.remove(key)

    def _cache_remove_by_tx(self, tx_hash: str) -> None:
        for key in list(self._cache):
            if self._cache[key].tx_hash == tx_hash:
                self._cache.pop(key, None)
                self._cache_ts.pop(key, None)
                self._order.remove(key)

    def stats(self) -> Dict[str, Any]:
        return {
            **super().stats(),
            "cached_roots": len(self._cache),
            "soft_final": sum(1 for s in self._states.values() if s == FinalityState.SOFT_FINAL),
            "anchored": sum(1 for s in self._states.values() if s == FinalityState.ANCHORED),
            "rolled_back": sum(1 for s in self._states.values() if s == FinalityState.ROLLED_BACK),
            "compensated": sum(1 for s in self._states.values() if s == FinalityState.COMPENSATED),
        }
