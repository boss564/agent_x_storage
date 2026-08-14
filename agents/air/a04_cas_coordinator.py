"""A04 — CAS Coordinator.

Coordinates transient Compare-And-Swap (CAS) operations on state slots.
Receives soft-final envelopes from A03 and applies multi-slot atomic
swaps: all-or-nothing. On conflict the loser is routed toward the
Surface fallback (A08, Step 3).

Hot path is lock-bounded and deterministic — no LLM, no network I/O.
Transient analog of the Consensus Engine: instead of a 3/4 validator
quorum, atomicity is guaranteed by validate-then-commit under a single
write lock.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple


class CASStatus(Enum):
    COMMITTED = "committed"
    CONFLICT = "conflict"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class CASSlotOp:
    """One leg of a CAS request: swap slot from expected to new root."""

    slot_key: str
    expected_root: str
    new_root: str


@dataclass(frozen=True)
class CASRequest:
    request_id: str
    slots: Tuple[CASSlotOp, ...]
    source_dedup_key: str
    deadline: float
    epoch: int


@dataclass
class CASResult:
    request_id: str
    status: CASStatus
    conflicting_slot: Optional[str] = None
    committed_at: Optional[float] = None
    applied_slots: int = 0


@dataclass
class SlotState:
    root: str
    holder: Optional[str] = None
    epoch: int = 0
    seq: int = 0


class CASCoordinator:
    """Atomic multi-slot CAS on the transient state table.

    Invariant: a request commits iff every leg's expected_root matches
    the current slot root at commit time. Partial application is
    impossible — all legs are validated before any slot is mutated.
    Roots move monotonically forward within an epoch (epoch flushes
    invalidate wholesale), so a failed compare never becomes valid again.
    """

    def __init__(self, event_bus=None, metrics=None):
        self._slots: Dict[str, SlotState] = {}
        self._seen: Dict[str, CASResult] = {}   # idempotency table
        self._lock = threading.RLock()
        self._bus = event_bus
        self._metrics = metrics
        self._seq = 0

    # -- slot table ---------------------------------------------------

    def seed_slot(self, slot_key: str, root: str, epoch: int = 0) -> None:
        with self._lock:
            self._slots[slot_key] = SlotState(root=root, epoch=epoch)

    def slot_root(self, slot_key: str) -> Optional[str]:
        with self._lock:
            s = self._slots.get(slot_key)
            return s.root if s else None

    # -- CAS ----------------------------------------------------------

    def submit(self, request: CASRequest, now: Optional[float] = None) -> CASResult:
        now = now if now is not None else time.time()

        if now > request.deadline:
            result = CASResult(request.request_id, CASStatus.TIMEOUT)
            self._record(request.request_id, result)
            self._observe("timeout")
            return result

        with self._lock:
            # Idempotent resubmit (NATS redelivery).
            prior = self._seen.get(request.request_id)
            if prior is not None:
                return prior

            # Validate phase: every leg must match.
            for op in request.slots:
                slot = self._slots.get(op.slot_key)
                current = slot.root if slot else None
                if current != op.expected_root:
                    result = CASResult(
                        request.request_id, CASStatus.CONFLICT,
                        conflicting_slot=op.slot_key,
                    )
                    self._seen[request.request_id] = result
                    self._observe("conflict")
                    self._emit("cas.conflict", {
                        "request_id": request.request_id,
                        "slot": op.slot_key,
                        "expected": op.expected_root,
                        "actual": current,
                    })
                    return result

            # Commit phase: apply all swaps atomically.
            self._seq += 1
            for op in request.slots:
                self._slots[op.slot_key] = SlotState(
                    root=op.new_root,
                    holder=request.source_dedup_key,
                    epoch=request.epoch,
                    seq=self._seq,
                )
            result = CASResult(
                request.request_id, CASStatus.COMMITTED,
                committed_at=now, applied_slots=len(request.slots),
            )
            self._seen[request.request_id] = result

        self._observe("committed")
        self._emit("cas.committed", {
            "request_id": request.request_id,
            "slots": len(request.slots),
            "source": request.source_dedup_key,
        })
        return result

    # -- helpers ------------------------------------------------------

    def _record(self, request_id: str, result: CASResult) -> None:
        with self._lock:
            self._seen.setdefault(request_id, result)

    def _observe(self, status: str) -> None:
        if self._metrics is not None:
            self._metrics.inc("air_cas_submitted_total",
                              labels={"status": status})

    def _emit(self, event: str, payload: dict) -> None:
        if self._bus is not None:
            self._bus.publish(f"agentx.air.{event}", payload)
