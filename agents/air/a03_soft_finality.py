#!/usr/bin/env python3
"""A03 — soft-finality attestation: state machine + versioned cache.

Two layers:
  - A03SoftFinalityVerifier (legacy, uses base.py types) — kept for the
    AirCoordinator fast-path wiring.
  - SoftFinalityEngine (refined, Commit 1.5) — the authoritative attestation
    engine with DedupKey idempotency, escalation, and CAS-conflict handling.
"""

import time
from typing import Any, Dict, Optional, Tuple

from .base import AirInterceptorAgent
from .base import AttestationEnvelope as LegacyEnvelope
from .base import FinalityState as LegacyState
from .base import FINALITY_TRANSITIONS
from .finality_types import (
    AttestationEnvelope,
    FinalityState,
    FinalityTier,
    build_dedup_key,
)
from .soft_finality_cache import SoftFinalityCache


# ── Legacy verifier (AirCoordinator fast-path) ─────────────────────────────

class A03SoftFinalityVerifier(AirInterceptorAgent):
    """Attests envelopes (SOFT_FINAL) and tracks their finality lifecycle."""

    def __init__(self, ttl_s: float = 1.0, max_entries: int = 10_000):
        super().__init__("A03")
        self.ttl_s = ttl_s
        self.max_entries = max_entries
        self._states: Dict[str, LegacyState] = {}
        self._cache: Dict[Tuple[int, int], LegacyEnvelope] = {}
        self._cache_ts: Dict[Tuple[int, int], float] = {}
        self._order: list = []

    def _transition(self, tx_hash: str, new_state: LegacyState) -> bool:
        cur = self._states.get(tx_hash, LegacyState.RECEIVED)
        if new_state not in FINALITY_TRANSITIONS.get(cur, set()):
            return False
        self._states[tx_hash] = new_state
        return True

    def attest(self, envelope: LegacyEnvelope) -> LegacyState:
        tx_hash = envelope.tx_hash
        cur = self._states.get(tx_hash, LegacyState.RECEIVED)
        if cur in (LegacyState.SOFT_FINAL, LegacyState.ANCHORED):
            return cur
        if envelope.signer != "A02":
            self._states[tx_hash] = LegacyState.ROLLED_BACK
            return LegacyState.ROLLED_BACK
        if not self._transition(tx_hash, LegacyState.VERIFIED):
            return cur
        if not self._transition(tx_hash, LegacyState.SOFT_FINAL):
            return cur
        self._cache_put((envelope.epoch, envelope.seq), envelope)
        self.intercept_count += 1
        return LegacyState.SOFT_FINAL

    def anchor(self, tx_hash: str) -> LegacyState:
        self._transition(tx_hash, LegacyState.ANCHORED)
        return self._states.get(tx_hash, LegacyState.RECEIVED)

    def invalidate(self, tx_hash: str) -> LegacyState:
        if self._transition(tx_hash, LegacyState.ROLLED_BACK):
            self._cache_remove_by_tx(tx_hash)
        return self._states.get(tx_hash, LegacyState.RECEIVED)

    def compensate(self, tx_hash: str) -> LegacyState:
        self._transition(tx_hash, LegacyState.COMPENSATED)
        return self._states.get(tx_hash, LegacyState.RECEIVED)

    def _cache_put(self, key, envelope) -> None:
        self._evict_expired()
        self._cache[key] = envelope
        self._cache_ts[key] = time.time()
        if key in self._order:
            self._order.remove(key)
        self._order.append(key)
        while len(self._cache) > self.max_entries:
            oldest = self._order.pop(0)
            self._cache.pop(oldest, None)
            self._cache_ts.pop(oldest, None)

    def cache_get(self, epoch: int, seq: int) -> Optional[LegacyEnvelope]:
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
            "soft_final": sum(1 for s in self._states.values() if s == LegacyState.SOFT_FINAL),
            "anchored": sum(1 for s in self._states.values() if s == LegacyState.ANCHORED),
            "rolled_back": sum(1 for s in self._states.values() if s == LegacyState.ROLLED_BACK),
            "compensated": sum(1 for s in self._states.values() if s == LegacyState.COMPENSATED),
        }


# ── Refined SoftFinalityEngine (Commit 1.5) ────────────────────────────────

# Escalation thresholds (env-configurable later).
ESCALATION_AMOUNT_EUR = 5000.0   # > this -> 2 attestations
ESCALATION_RISK_CLASS = "D"      # >= this -> 2 attestations


class SoftFinalityEngine:
    """Tier + attestation logic for A03. Wraps the versioned cache and
    enforces the state machine + idempotency + rollback invariant."""

    def __init__(self, signer_id: str, ttl_seconds: float = 2.0, event_bus=None):
        self._signer = signer_id
        self._ttl = ttl_seconds
        self._cache = SoftFinalityCache(ttl_seconds=ttl_seconds)
        self._bus = event_bus
        self._epoch = 0
        self._seq = 0
        # Rollback hook -> D02 Forensic Repair (agents_b2g.settlement).
        self._cache.register_invalidation_hook(self._on_invalidation)

    # -- attestation --------------------------------------------------

    def attest(self, tx_hash: str, state_root: str, sender: str,
               nonce: int, intent_hash: str, amount_eur: float = 0.0,
               risk_class: str = "A") -> AttestationEnvelope:
        """Issue (or idempotently return) the soft-finality envelope."""
        dedup = build_dedup_key(sender, nonce, intent_hash).render()
        now = time.time()
        self._seq += 1

        # Idempotent: return existing live envelope if the root matches;
        # a different root on the same slot is a CAS conflict.
        existing = self._cache.get(dedup, now=now)
        if existing is not None:
            if existing.state_root != state_root:
                raise CASConflictError(dedup)
            return existing

        tier = self._required_attestations(amount_eur, risk_class)
        env = AttestationEnvelope(
            tx_hash=tx_hash, state_root=state_root, tier=tier,
            signer=self._signer, ts=now, expiry=now + self._ttl,
            epoch=self._epoch, seq=self._seq, dedup_key=dedup,
        )
        won = self._cache.put(env, now=now)
        if not won:
            # CAS conflict on slot -> caller must fall back to Surface.
            raise CASConflictError(dedup)
        self._emit("soft_final_attested", env)
        return env

    def _required_attestations(self, amount_eur: float,
                               risk_class: str) -> int:
        """Escalation rule: single attestation by default, 2 when the amount
        or risk class crosses a threshold."""
        if amount_eur > ESCALATION_AMOUNT_EUR or risk_class >= ESCALATION_RISK_CLASS:
            return 2
        return 1

    # -- anchoring / rollback ----------------------------------------

    def anchor(self, dedup_key: str) -> bool:
        """Promote to HARD_FINAL (L1 anchor confirmed)."""
        env = self._cache.get(dedup_key)
        if env is None:
            return False
        self._cache.invalidate(dedup_key, reason="anchored")
        self._emit("hard_final_anchored", env)
        return True

    def _on_invalidation(self, entry, reason: str) -> None:
        """Fired by cache. On poison/rollback (not anchor) we must emit a
        compensating signal toward D02 Forensic Repair + AWACS audit."""
        if reason == "anchored":
            return
        self._emit("soft_final_rollback", entry.envelope, reason=reason)

    def advance_epoch(self) -> None:
        """Epoch flush: closes the rollback window for prior entries."""
        self._epoch += 1
        self._seq = 0

    def _emit(self, event: str, env: AttestationEnvelope, **extra) -> None:
        if self._bus is not None:
            payload = env.to_audit_dict()
            payload.update(extra)
            self._bus.publish(f"agentx.air.{event}", payload)


class CASConflictError(RuntimeError):
    """Raised when two fast-paths race on the same dedup slot."""
