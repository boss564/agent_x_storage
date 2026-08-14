#!/usr/bin/env python3
"""A02 — fast-path: speculative pre-execution with soft-finality attestation.

Two layers:
  - A02FastpathHunter (legacy) — signs a speculative envelope for the
    AirCoordinator fast-path wiring.
  - FastPathInterceptor (refined, Commit 1.5) — routes through the
    SoftFinalityEngine and reports cache-hit metrics under the 200µs budget.
"""

import hashlib
import time
from typing import Any, Dict

from .base import AirInterceptorAgent
from .base import AttestationEnvelope as LegacyEnvelope
from .base import FinalityTier as LegacyTier
from .a03_soft_finality import SoftFinalityEngine, CASConflictError


# ── Legacy hunter (AirCoordinator fast-path) ───────────────────────────────

class A02FastpathHunter(AirInterceptorAgent):
    """Signs speculative attestations for the fast path."""

    def __init__(self):
        super().__init__("A02")

    def sign_attestation(self, event: Dict[str, Any]) -> LegacyEnvelope:
        event_id = event.get("id", "?")
        state_root = event.get("state_root") or hashlib.sha256(
            event_id.encode()
        ).hexdigest()[:32]
        tx_hash = event.get("tx_hash") or hashlib.sha256(
            f"TX:{event_id}".encode()
        ).hexdigest()
        now_ns = time.time_ns()
        self.intercept_count += 1
        return LegacyEnvelope(
            tx_hash=tx_hash,
            state_root=state_root,
            tier=LegacyTier.SPECULATIVE,
            signer=self.agent_id,
            ts=now_ns,
            expiry=now_ns + 2_000_000_000,
            epoch=event.get("epoch", 0),
            seq=event.get("seq", 0),
        )


# ── Refined FastPathInterceptor (Commit 1.5) ───────────────────────────────

class FastPathInterceptor:
    """A02 fast-path, routed through the SoftFinalityEngine."""

    def __init__(self, engine: SoftFinalityEngine, metrics=None):
        self._engine = engine
        self._metrics = metrics

    def handle_payment_obligation(self, event: dict) -> dict:
        """HFT / Zahlungspflicht -> Soft-Finality Fast-Path."""
        t0 = time.perf_counter_ns()
        try:
            env = self._engine.attest(
                tx_hash=event["tx_hash"],
                state_root=event["state_root"],
                sender=event["sender"],
                nonce=event["nonce"],
                intent_hash=event["intent_hash"],
                amount_eur=event.get("amount_eur", 0.0),
                risk_class=event.get("risk_class", "A"),
            )
            action = "SOFT_FINAL"
        except CASConflictError:
            action = "FALLBACK_SURFACE"   # CAS loser -> Surface
            env = None
        latency_us = (time.perf_counter_ns() - t0) / 1000.0

        if self._metrics is not None:
            self._metrics.observe("air_soft_final_latency_us", latency_us)
            self._metrics.inc("air_soft_final_attestations_total",
                              labels={"action": action})
        return {"action": action, "envelope": env, "latency_us": latency_us}
