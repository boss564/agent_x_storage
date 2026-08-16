"""A05 — CAS Bomber (GPU burst).

Batches CAS requests and fires them in bursts, mirroring the B2G
GPU-Burst pattern (57.6k-172.8k TX per evaluation). Deterministic:
results are backend-independent — GPU and CPU evaluation of the same
ordered batch yield identical outcomes. The backend accelerates the
compare step only; the coordinator owns the swap and thus atomicity.

Conflict shortcut: legs that already fail prevalidation are routed to
fallback without touching the commit lock. Safe because slot roots are
monotonic within an epoch (see CASCoordinator).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional, Protocol

from agents.air.a04_cas_coordinator import (
    CASCoordinator, CASRequest, CASResult, CASStatus,
)


class ComputeBackend(Protocol):
    """Backend abstraction: GPU burst or CPU fallback."""

    name: str

    def prevalidate_batch(self, requests: List[CASRequest],
                          coordinator: CASCoordinator) -> List[bool]:
        """Per-request leg-validity verdicts. Must be a pure function of
        (requests, slot table) — no side effects, no reordering."""
        ...


class CPUBackend:
    name = "cpu"

    def prevalidate_batch(self, requests, coordinator):
        return [
            all(coordinator.slot_root(op.slot_key) == op.expected_root
                for op in req.slots)
            for req in requests
        ]


class GPUBurstBackend:
    """CUDA burst kernel stub. The kernel vectorizes the compare across
    the batch; semantics are identical to the CPU path (determinism
    invariant). Real kernel binding lands with the services/ GPU pool."""

    name = "gpu"

    def __init__(self, device: int = 0):
        self.device = device
        self._fallback = CPUBackend()

    def prevalidate_batch(self, requests, coordinator):
        return self._fallback.prevalidate_batch(requests, coordinator)


@dataclass
class BurstReport:
    batch_size: int
    committed: int
    conflicts: int
    timeouts: int
    shortcut_conflicts: int
    latency_us: float
    backend: str


class CASBomber:
    """Collects CAS requests and fires them in batch_size-sized bursts."""

    def __init__(self, coordinator: CASCoordinator,
                 backend: Optional[ComputeBackend] = None,
                 batch_size: int = 1024,
                 metrics=None, event_bus=None,
                 on_result=None):
        self._coordinator = coordinator
        self._backend = backend or CPUBackend()
        self._batch_size = batch_size
        self._metrics = metrics
        self._bus = event_bus
        self._on_result = on_result
        self._queue: List[CASRequest] = []

    def enqueue(self, request: CASRequest) -> None:
        self._queue.append(request)

    def pending(self) -> int:
        return len(self._queue)

    def burst(self, now: Optional[float] = None) -> List[BurstReport]:
        """Fire all queued requests in batch_size-sized bursts."""
        reports = []
        while self._queue:
            batch = self._queue[: self._batch_size]
            self._queue = self._queue[self._batch_size:]
            reports.append(self._fire(batch, now))
        return reports

    def _fire(self, batch: List[CASRequest],
              now: Optional[float] = None) -> BurstReport:
        t0 = time.perf_counter_ns()
        verdicts = self._backend.prevalidate_batch(batch, self._coordinator)

        results: List[CASResult] = []
        shortcuts = 0
        for req, ok in zip(batch, verdicts):
            if ok:
                results.append(self._coordinator.submit(req, now=now))
            else:
                # Stale roots never become valid again within the epoch:
                # skip the commit lock, route straight to fallback.
                shortcuts += 1
                results.append(CASResult(req.request_id, CASStatus.CONFLICT))

        if self._on_result is not None:
            for result in results:
                self._on_result(result)

        latency_us = (time.perf_counter_ns() - t0) / 1000.0
        report = BurstReport(
            batch_size=len(batch),
            committed=sum(r.status is CASStatus.COMMITTED for r in results),
            conflicts=sum(r.status is CASStatus.CONFLICT for r in results),
            timeouts=sum(r.status is CASStatus.TIMEOUT for r in results),
            shortcut_conflicts=shortcuts,
            latency_us=latency_us,
            backend=self._backend.name,
        )
        if self._metrics is not None:
            self._metrics.observe("air_cas_batch_size", report.batch_size)
            self._metrics.observe("air_cas_burst_latency_us", latency_us)
        if self._bus is not None:
            self._bus.publish("agentx.air.cas.burst", {
                "batch_size": report.batch_size,
                "committed": report.committed,
                "conflicts": report.conflicts,
                "shortcuts": shortcuts,
                "latency_us": latency_us,
                "backend": report.backend,
            })
        return report
