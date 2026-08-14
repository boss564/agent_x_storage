"""A07 — In-Flight Neutralizer.

Actuator of the neutralization chain. A06 (airspace watch) is the
sensor: it scores poison, invalidates the cache entry and books the
destruction leg. A07 acts on the in-flight registry: revokes the
attestation, removes the envelope from flight, books the compensation
leg and emits a compensation request toward D02 forensic repair
(agents_b2g.settlement).

Zero-sum split: A06 books destruction (debit), A07 books compensation
(credit). Both legs together keep the ledger balanced.

Idempotent: revoking the same dedup_key twice yields exactly one
compensation request.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional, Set

from agents.air.a06_airspace_watch import WatchAlert
from agents.air.finality_types import AttestationEnvelope


@dataclass
class NeutralizationReport:
    dedup_key: str
    revoked: bool
    compensation_id: Optional[str]
    reason: str
    ts: float


class InFlightRegistry:
    """Tracks envelopes between attestation and anchoring."""

    def __init__(self):
        self._active: Dict[str, AttestationEnvelope] = {}
        self._lock = threading.RLock()

    def register(self, env: AttestationEnvelope) -> None:
        with self._lock:
            self._active[env.dedup_key] = env

    def complete(self, dedup_key: str) -> Optional[AttestationEnvelope]:
        with self._lock:
            return self._active.pop(dedup_key, None)

    def get(self, dedup_key: str) -> Optional[AttestationEnvelope]:
        with self._lock:
            return self._active.get(dedup_key)

    def active_count(self) -> int:
        with self._lock:
            return len(self._active)


class InFlightNeutralizer:
    """Revokes in-flight envelopes and emits compensation requests."""

    def __init__(self, registry: InFlightRegistry, cache,
                 ledger=None, event_bus=None, metrics=None):
        self._registry = registry
        self._cache = cache
        self._ledger = ledger
        self._bus = event_bus
        self._metrics = metrics
        self._revoked: Set[str] = set()   # idempotency guard
        self._lock = threading.RLock()

    def neutralize(self, alert: WatchAlert,
                   now: Optional[float] = None) -> NeutralizationReport:
        now = now if now is not None else time.time()

        with self._lock:
            # Idempotent: second alert for the same key is a no-op.
            if alert.dedup_key in self._revoked:
                return NeutralizationReport(
                    dedup_key=alert.dedup_key, revoked=False,
                    compensation_id=None, reason="already_revoked", ts=now,
                )

            env = self._registry.get(alert.dedup_key)
            if env is None:
                # Anchored or unknown -> neutralization is too late.
                self._emit("neutralization.refused", {
                    "dedup_key": alert.dedup_key,
                    "kind": alert.kind.value,
                    "reason": "not_in_flight",
                })
                return NeutralizationReport(
                    dedup_key=alert.dedup_key, revoked=False,
                    compensation_id=None, reason="not_in_flight", ts=now,
                )

            # 1. Remove from flight, 2. mark revoked (idempotency).
            self._registry.complete(alert.dedup_key)
            self._revoked.add(alert.dedup_key)

        # 3. Belt-and-suspenders cache invalidation (A06 usually did it).
        self._cache.invalidate(alert.dedup_key,
                               reason=f"neutralized:{alert.kind.value}")

        # 4. Deterministic compensation id (idempotent by construction).
        compensation_id = f"comp:{alert.dedup_key}"

        # 5. Compensation leg -> ledger (credit against A06's debit).
        if self._ledger is not None:
            self._ledger.book_compensation(
                dedup_key=alert.dedup_key,
                compensation_id=compensation_id,
                reason=alert.kind.value,
            )

        # 6. Compensation request toward D02 forensic repair.
        self._emit("compensation.request", {
            "compensation_id": compensation_id,
            "dedup_key": alert.dedup_key,
            "state_root": env.state_root,
            "kind": alert.kind.value,
            "epoch": env.epoch,
        })
        self._emit("neutralized", {
            "dedup_key": alert.dedup_key,
            "kind": alert.kind.value,
            "score": alert.score,
        })

        if self._metrics is not None:
            self._metrics.inc("air_neutralizer_revoked_total",
                              labels={"kind": alert.kind.value})
            self._metrics.inc("air_neutralizer_compensations_total")
            self._metrics.set("air_inflight_active",
                              self._registry.active_count())

        return NeutralizationReport(
            dedup_key=alert.dedup_key, revoked=True,
            compensation_id=compensation_id,
            reason=alert.kind.value, ts=now,
        )

    def revoked_count(self) -> int:
        with self._lock:
            return len(self._revoked)

    def _emit(self, event: str, payload: dict) -> None:
        if self._bus is not None:
            self._bus.publish(f"agentx.air.{event}", payload)
