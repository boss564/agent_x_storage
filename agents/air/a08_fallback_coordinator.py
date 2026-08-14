"""A08 — Fallback Coordinator.

Catches everything the air layer cannot finalize itself: CAS conflicts
and timeouts (A04/A05 losers), TTL lapses (Commit 1.5 demotion),
fast-path rejections and capacity shedding. Routes events back to the
Surface layer (C01-C09 NATS queue-group workers) with bounded retries
and dead-lettering.

Retry/backoff mirrors Wave 7 DeadLetterHandlerAgent: exponential
10 s - 1 h, max 3 attempts before dead letter.

Conservation invariant (1M-Tsunami pattern):
    AirIngress = AirCompleted + FallbackReturned
No event may vanish silently between the layers.
"""

from __future__ import annotations

import itertools
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

# NATS subject mapping (wired in Step 4):
SURFACE_FALLBACK_SUBJECT = "agentx.surface.fallback"


class FallbackReason(Enum):
    CAS_CONFLICT = "cas_conflict"
    CAS_TIMEOUT = "cas_timeout"
    TTL_EXPIRY = "ttl_expiry"
    FASTPATH_REJECT = "fastpath_reject"
    CAPACITY_SHED = "capacity_shed"


@dataclass
class FallbackTicket:
    ticket_id: str
    event: dict
    reason: FallbackReason
    attempts: int = 0
    next_retry_at: float = 0.0
    dead_lettered: bool = False


class FallbackCoordinator:
    """Routes air-layer rejects back to Surface; guards conservation."""

    MAX_ATTEMPTS = 3
    BACKOFF_BASE_S = 10.0        # Wave 7 DLQ: 10 s ...
    BACKOFF_CAP_S = 3600.0       # ... to 1 h

    def __init__(self, event_bus=None, metrics=None):
        self._bus = event_bus
        self._metrics = metrics
        self._ids = itertools.count(1)
        self._tickets: Dict[str, FallbackTicket] = {}
        # Conservation counters.
        self._ingress = 0
        self._completed = 0
        self._returned = 0

    # -- conservation bookkeeping --------------------------------------

    def mark_ingress(self) -> None:
        self._ingress += 1

    def mark_completed(self) -> None:
        """Event finalized in the air layer (anchored / CAS committed)."""
        self._completed += 1

    def conservation_balance(self) -> dict:
        """Ingress = Completed + Returned (1M-Tsunami invariant)."""
        return {
            "ingress": self._ingress,
            "completed": self._completed,
            "returned": self._returned,
            "delta": self._ingress - (self._completed + self._returned),
            "holds": self._ingress == self._completed + self._returned,
        }

    # -- fallback handling ---------------------------------------------

    def accept(self, event: dict, reason: FallbackReason,
               now: Optional[float] = None) -> FallbackTicket:
        """Accept a reject and route it to Surface immediately."""
        now = now if now is not None else time.time()
        ticket = FallbackTicket(
            ticket_id=f"fb-{next(self._ids):08d}",
            event=event, reason=reason, attempts=1,
        )
        self._tickets[ticket.ticket_id] = ticket
        self._returned += 1
        self._route(ticket)
        if self._metrics is not None:
            self._metrics.inc("air_fallback_total",
                              labels={"reason": reason.value})
        return ticket

    def retry(self, ticket_id: str,
              now: Optional[float] = None) -> Optional[FallbackTicket]:
        """Surface rejected the event again. Bounded retry + backoff;
        dead letter after MAX_ATTEMPTS."""
        now = now if now is not None else time.time()
        ticket = self._tickets.get(ticket_id)
        if ticket is None or ticket.dead_lettered:
            return None

        ticket.attempts += 1
        if ticket.attempts > self.MAX_ATTEMPTS:
            ticket.dead_lettered = True
            self._emit("fallback.deadletter", {
                "ticket_id": ticket.ticket_id,
                "reason": ticket.reason.value,
                "attempts": ticket.attempts,
            })
            if self._metrics is not None:
                self._metrics.inc("air_fallback_deadletter_total")
            return ticket

        delay = min(self.BACKOFF_BASE_S * (2 ** (ticket.attempts - 2)),
                    self.BACKOFF_CAP_S)
        ticket.next_retry_at = now + delay
        if self._metrics is not None:
            self._metrics.inc("air_fallback_retry_scheduled_total")
        return ticket

    def due_tickets(self, now: Optional[float] = None) -> List[FallbackTicket]:
        """Tickets whose backoff has elapsed (re-route to Surface)."""
        now = now if now is not None else time.time()
        due = [
            t for t in self._tickets.values()
            if not t.dead_lettered and t.attempts > 1
            and t.next_retry_at <= now
        ]
        for t in due:
            self._route(t)
        return due

    # -- helpers --------------------------------------------------------

    def _route(self, ticket: FallbackTicket) -> None:
        self._emit("fallback.routed", {
            "ticket_id": ticket.ticket_id,
            "subject": SURFACE_FALLBACK_SUBJECT,
            "reason": ticket.reason.value,
            "attempt": ticket.attempts,
            "event": ticket.event,
        })

    def _emit(self, event: str, payload: dict) -> None:
        if self._bus is not None:
            self._bus.publish(f"agentx.air.{event}", payload)
