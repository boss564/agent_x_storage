"""AirStack — final wiring of AirCoordinator + Schwärme 1-3 (Step 4).

Builds the complete object graph (A01-A09), implements A01's ingress
classification as AirStack.route, and enforces the air-layer
conservation law:

    Ingress = Completed + Forwarded + Fallback + Neutralized

— the air mirror of the 1M-Tsunami invariant (Ingested = Cleared +
Quarantined). An event is counted once (dedup-guarded) and must end in
exactly one terminal state.

Production deployments inject the real EventBus (event_bus.py); the
InProcessBus here keeps the stack testable and standalone-runnable.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Set

from agents.air.base import AirCoordinator
from agents.air.finality_types import AttestationEnvelope, build_dedup_key
from agents.air.a02_fastpath import FastPathInterceptor
from agents.air.a03_soft_finality import SoftFinalityEngine
from agents.air.a04_cas_coordinator import (
    CASCoordinator, CASRequest, CASSlotOp, CASResult, CASStatus,
)
from agents.air.a05_cas_bomber import CASBomber
from agents.air.a06_airspace_watch import AirspaceWatch
from agents.air.a07_inflight_neutralizer import InFlightNeutralizer, InFlightRegistry
from agents.air.a08_fallback_coordinator import FallbackCoordinator, FallbackReason
from agents.air.a09_awacs_datalink import AWACSDatalink
from agents.air.ledger import AirBHOLedger
from agents.air.metrics import MetricsRegistry

SURFACE_INGRESS_SUBJECT = "agentx.surface.ingress"


class InProcessBus:
    """Minimal pub/sub with the event_bus.py surface (publish/subscribe)."""

    def __init__(self):
        self._subs: Dict[str, list] = defaultdict(list)
        self.published: list = []

    def publish(self, topic: str, payload: dict) -> None:
        self.published.append((topic, payload))
        for cb in self._subs.get(topic, []):
            cb(payload)

    def subscribe(self, topic: str, cb: Callable[[dict], None]) -> None:
        self._subs[topic].append(cb)


@dataclass
class ConservationCounter:
    """Terminal-state accounting for the air layer."""

    ingress: int = 0
    completed: int = 0
    forwarded: int = 0
    fallback: int = 0
    neutralized: int = 0
    duplicates: int = 0

    @property
    def in_flight(self) -> int:
        return self.ingress - (
            self.completed + self.forwarded + self.fallback + self.neutralized
        )

    def is_settled(self) -> bool:
        return self.in_flight == 0

    def balance(self) -> dict:
        return {
            "ingress": self.ingress, "completed": self.completed,
            "forwarded": self.forwarded, "fallback": self.fallback,
            "neutralized": self.neutralized, "in_flight": self.in_flight,
            "duplicates": self.duplicates, "settled": self.is_settled(),
        }


class AirStack:
    """Fully wired air layer: routing, conservation, audit."""

    def __init__(self, signer_id: str = "air-0", bus=None, metrics=None,
                 ledger=None, ttl_seconds: float = 2.0, backend=None,
                 batch_size: int = 1024):
        self.metrics = metrics or MetricsRegistry()
        self.ledger = ledger or AirBHOLedger()
        self.bus = bus or InProcessBus()

        # Schwarm 1 (A01-A03)
        self.engine = SoftFinalityEngine(signer_id, ttl_seconds=ttl_seconds,
                                         event_bus=self.bus)
        self.fastpath = FastPathInterceptor(self.engine, metrics=self.metrics)

        # Schwarm 2 (A04-A06)
        self.cas = CASCoordinator(event_bus=self.bus, metrics=self.metrics)
        self.bomber = CASBomber(self.cas, backend=backend,
                                batch_size=batch_size, metrics=self.metrics,
                                event_bus=self.bus,
                                on_result=self._on_cas_result)

        # Schwarm 3 (A07-A09)
        self.registry = InFlightRegistry()
        self.watch = AirspaceWatch(self.engine._cache, ledger=self.ledger,
                                   event_bus=self.bus, metrics=self.metrics)
        self.neutralizer = InFlightNeutralizer(self.registry,
                                               self.engine._cache,
                                               ledger=self.ledger,
                                               event_bus=self.bus,
                                               metrics=self.metrics)
        self.fallback = FallbackCoordinator(event_bus=self.bus,
                                            metrics=self.metrics)
        self.datalink = AWACSDatalink(metrics=self.metrics)
        self.datalink.attach(self.bus)

        self.conservation = ConservationCounter()
        self._counted: Set[str] = set()              # ingress dedup guard
        self._cas_results: Dict[str, CASResult] = {}

        # Coordinator (legacy Commit-1 API) — optional; AirStack.route is authoritative.
        self.coordinator = AirCoordinator()

    # -- ingress routing (A01 classification) ----------------------------

    def route(self, event: dict) -> dict:
        kind = event.get("kind", "transfer")
        key = self._dedup_of(event, kind)
        if key is not None:
            if key in self._counted:
                self.conservation.duplicates += 1
                return {"route": "duplicate", "dedup_key": key}
            self._counted.add(key)
        self.conservation.ingress += 1
        self.metrics.inc("air_ingress_total")

        if kind == "cas_request":
            return self._route_cas(event)
        if kind == "payment_obligation" or event.get("hft"):
            return self._route_fastpath(event)
        return self._route_passthrough(event)

    def force_fastpath(self, event: dict) -> dict:
        event = dict(event)
        event.setdefault("kind", "payment_obligation")
        return self.route(event)

    def force_cas(self, event: dict) -> dict:
        event = dict(event)
        event["kind"] = "cas_request"
        return self.route(event)

    # -- path implementations ---------------------------------------------

    def _route_passthrough(self, event: dict) -> dict:
        self.conservation.forwarded += 1
        self.metrics.inc("air_ingress_routed_total", labels={"route": "forwarded"})
        return {"route": "forwarded", "subject": SURFACE_INGRESS_SUBJECT}

    def _route_fastpath(self, event: dict) -> dict:
        result = self.fastpath.handle_payment_obligation(event)
        if result["action"] == "FALLBACK_SURFACE":
            self.fallback.accept(event, FallbackReason.CAS_CONFLICT)
            self.conservation.fallback += 1
            return {"route": "fallback", "reason": "cas_conflict"}

        env: AttestationEnvelope = result["envelope"]
        self.registry.register(env)
        # Post-attestation scan: poison may ride along (drift/replay).
        alert = self.watch.scan_envelope(env,
                                         slot_count=int(event.get("slot_count", 0)))
        if alert is not None:
            report = self.neutralizer.neutralize(alert)
            self.conservation.neutralized += 1
            self.metrics.inc("air_ingress_routed_total",
                             labels={"route": "neutralized"})
            return {"route": "neutralized", "kind": alert.kind.value,
                    "compensation_id": report.compensation_id}

        self.metrics.inc("air_ingress_routed_total",
                         labels={"route": "soft_final"})
        return {"route": "soft_final", "dedup_key": env.dedup_key,
                "envelope_digest": env.digest(),
                "latency_us": result["latency_us"]}

    def _route_cas(self, event: dict) -> dict:
        slots = tuple(
            CASSlotOp(**s) if isinstance(s, dict) else s
            for s in event.get("slots", [])
        )
        # Pre-scan: constraint bloat never reaches the commit lock.
        if len(slots) > AirspaceWatch.BLOAT_SLOT_LIMIT:
            return self._neutralize_bloat(event, slot_count=len(slots))

        request = CASRequest(
            request_id=event["request_id"],
            slots=slots,
            source_dedup_key=self._dedup_of(event, "transfer") or event["request_id"],
            deadline=time.time() + float(event.get("deadline_s", 5.0)),
            epoch=int(event.get("epoch", 0)),
        )
        self.bomber.enqueue(request)
        if event.get("flush") or self.bomber.pending() >= self.bomber._batch_size:
            self.bomber.burst()

        result = self._cas_results.pop(event["request_id"], None)
        if result is None:
            return {"route": "cas_queued", "request_id": request.request_id,
                    "pending": self.bomber.pending()}
        if result.status is CASStatus.COMMITTED:
            return {"route": "cas_committed", "request_id": request.request_id,
                    "applied_slots": result.applied_slots}
        return {"route": "fallback", "reason": result.status.value,
                "request_id": request.request_id}

    def _neutralize_bloat(self, event: dict, slot_count: int) -> dict:
        """Attest-then-neutralize: runs the full A03->A06->A07 chain so
        both ledger legs (debit + credit) are booked uniformly."""
        env = self.engine.attest(
            tx_hash=event.get("tx_hash", f"bloat:{event.get('request_id', '?')}"),
            state_root=event.get("state_root", "0x" + "0" * 64),
            sender=event.get("sender", "unknown"),
            nonce=int(event.get("nonce", 0)),
            intent_hash=event.get("intent_hash", event.get("request_id", "?")),
            amount_eur=float(event.get("amount_eur", 0.0)),
            risk_class=event.get("risk_class", "A"),
        )
        self.registry.register(env)
        alert = self.watch.scan_envelope(env, slot_count=slot_count)
        if alert is None:                       # defensive: below threshold
            return {"route": "soft_final", "dedup_key": env.dedup_key}
        report = self.neutralizer.neutralize(alert)
        self.conservation.neutralized += 1
        self.metrics.inc("air_ingress_routed_total",
                         labels={"route": "neutralized"})
        return {"route": "neutralized", "kind": alert.kind.value,
                "compensation_id": report.compensation_id}

    # -- lifecycle hooks ----------------------------------------------------

    def confirm_anchor(self, dedup_key: str) -> bool:
        """L1 anchor confirmation (from D01 pipeline) -> HARD_FINAL."""
        if self.registry.get(dedup_key) is None:
            return False
        if not self.engine.anchor(dedup_key):
            return False
        self.registry.complete(dedup_key)
        self.conservation.completed += 1
        self.metrics.inc("air_ingress_routed_total", labels={"route": "anchored"})
        return True

    def flush_cas(self) -> list:
        """Force-burst the bomber queue (timer-driven in production)."""
        return self.bomber.burst()

    def handle_fallback_reply(self, event: dict) -> dict:
        """Surface rejected a fallback ticket -> retry/DLQ (A08)."""
        ticket_id = event.get("ticket_id")
        if not ticket_id:
            return {"route": "rejected", "reason": "missing_ticket_id"}
        ticket = self.fallback.retry(ticket_id)
        if ticket is None:
            return {"route": "rejected", "reason": "unknown_ticket"}
        if ticket.dead_lettered:
            return {"route": "dead_letter", "ticket_id": ticket_id}
        return {"route": "retry_scheduled", "ticket_id": ticket_id,
                "next_retry_at": ticket.next_retry_at}

    def _on_cas_result(self, result: CASResult) -> None:
        """CASBomber result hook: terminal-state bookkeeping."""
        self._cas_results[result.request_id] = result
        if result.status is CASStatus.COMMITTED:
            self.conservation.completed += 1
        else:
            reason = (FallbackReason.CAS_CONFLICT
                      if result.status is CASStatus.CONFLICT
                      else FallbackReason.CAS_TIMEOUT)
            self.fallback.accept({"request_id": result.request_id}, reason)
            self.conservation.fallback += 1

    # -- ops ------------------------------------------------------------------

    def health(self) -> dict:
        return {
            "status": "HALTED" if self.ledger.halted else "OK",
            "conservation": self.conservation.balance(),
            "inflight_active": self.registry.active_count(),
            "cas_pending": self.bomber.pending(),
            "datalink_chain": self.datalink.chain_length,
            "datalink_verified": self.datalink.verify(),
        }

    @staticmethod
    def _dedup_of(event: dict, kind: str) -> Optional[str]:
        if kind == "cas_request":
            return event.get("request_id")
        if all(k in event for k in ("sender", "nonce", "intent_hash")):
            return build_dedup_key(event["sender"], event["nonce"],
                                   event["intent_hash"]).render()
        return event.get("tx_hash")
