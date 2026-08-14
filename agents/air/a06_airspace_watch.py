"""A06 — Air-Space Watch (poison scan).

Continuous surveillance of the air layer for constraint-bloat poison
and anomalous envelopes — the direct counterpart to Chaos Fleet
injections (F07-F09). Thresholds mirror the mechanized/overwatch
pattern (score >= 0.7 -> neutralize).

Zero-sum law: every neutralization is booked through the BHO ledger
hook. No off-book destruction — the destroyed soft-final promise must
appear as a balanced journal entry (golden_books/ convention).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional, Protocol

from agents.air.finality_types import AttestationEnvelope


class PoisonKind(Enum):
    CONSTRAINT_BLOAT = "constraint_bloat"   # oversized legs / envelope
    EPOCH_DRIFT = "epoch_drift"             # envelope ahead of watch epoch
    REPLAY_STORM = "replay_storm"           # dedup key resurfacing later


class LedgerHook(Protocol):
    """Zero-sum booking interface (bound to golden_books/ in Step 4)."""

    def book_neutralization(self, dedup_key: str, state_root: str,
                            reason: str) -> None: ...


@dataclass
class WatchAlert:
    kind: PoisonKind
    dedup_key: str
    score: float
    detail: str
    ts: float


class AirspaceWatch:
    """Scans envelopes, scores poison, neutralizes with zero-sum booking."""

    BLOAT_SLOT_LIMIT = 64           # max legs per CAS request
    POISON_THRESHOLD = 0.7          # matches mechanized overwatch 0.7
    EPOCH_DRIFT_SCORE = 0.6
    REPLAY_STORM_SCORE = 0.7
    BLOAT_SCORE = 0.8

    def __init__(self, cache, ledger: Optional[LedgerHook] = None,
                 event_bus=None, metrics=None):
        self._cache = cache
        self._ledger = ledger
        self._bus = event_bus
        self._metrics = metrics
        self._quarantine: Dict[str, WatchAlert] = {}
        self._seen_dedup: Dict[str, int] = {}   # dedup_key -> last epoch
        self._epoch = 0
        self._alert_hooks: List[Callable[[WatchAlert], None]] = []

    def set_epoch(self, epoch: int) -> None:
        self._epoch = epoch

    def register_alert_hook(self, hook: Callable[[WatchAlert], None]) -> None:
        """Register a downstream actuator (A07 neutralizer) for detected alerts."""
        self._alert_hooks.append(hook)

    # -- scan ---------------------------------------------------------

    def scan_envelope(self, env: AttestationEnvelope,
                      slot_count: int = 0) -> Optional[WatchAlert]:
        """Score one envelope. Returns an alert iff poison threshold is
        crossed; neutralization happens inline (fail-fast)."""
        score = 0.0
        kinds: List[PoisonKind] = []

        if slot_count > self.BLOAT_SLOT_LIMIT:
            score += self.BLOAT_SCORE
            kinds.append(PoisonKind.CONSTRAINT_BLOAT)

        if env.epoch > self._epoch:
            score += self.EPOCH_DRIFT_SCORE
            kinds.append(PoisonKind.EPOCH_DRIFT)

        prior_epoch = self._seen_dedup.get(env.dedup_key)
        if prior_epoch is not None and env.epoch > prior_epoch + 1:
            score += self.REPLAY_STORM_SCORE
            kinds.append(PoisonKind.REPLAY_STORM)
        self._seen_dedup[env.dedup_key] = env.epoch

        if score < self.POISON_THRESHOLD:
            return None

        # Most specific signal wins (checked last).
        kind = kinds[-1]
        alert = WatchAlert(
            kind=kind, dedup_key=env.dedup_key, score=score,
            detail=",".join(k.value for k in kinds), ts=time.time(),
        )
        self._neutralize(alert, env)
        return alert

    # -- neutralization -----------------------------------------------

    def _neutralize(self, alert: WatchAlert, env: AttestationEnvelope) -> None:
        # 1. Invalidate cache entry (fires A03 rollback hooks).
        self._cache.invalidate(env.dedup_key,
                               reason=f"poison:{alert.kind.value}")
        # 2. Quarantine record for D02 forensic repair.
        self._quarantine[env.dedup_key] = alert
        # 3. Zero-sum booking: destroyed promise must hit the ledger.
        if self._ledger is not None:
            self._ledger.book_neutralization(
                dedup_key=env.dedup_key,
                state_root=env.state_root,
                reason=alert.kind.value,
            )
        if self._metrics is not None:
            self._metrics.inc("air_watch_poison_detected_total",
                              labels={"kind": alert.kind.value})
            self._metrics.inc("air_watch_neutralized_total")
        if self._bus is not None:
            self._bus.publish("agentx.air.watch.alert", {
                "kind": alert.kind.value,
                "dedup_key": alert.dedup_key,
                "score": alert.score,
                "epoch": env.epoch,
            })
        # 4. Notify registered actuators (A07 neutralizer).
        for hook in self._alert_hooks:
            hook(alert)

    def quarantine_size(self) -> int:
        return len(self._quarantine)

    def quarantined(self, dedup_key: str) -> Optional[WatchAlert]:
        return self._quarantine.get(dedup_key)
