"""Versioned state-root cache for soft-finality (A02/A03).

Stores hash-chained state roots keyed by dedup_key, versioned by (epoch, seq).
Never stores raw payloads. Supports TTL expiry, explicit invalidation (poison /
redelivery / checkpoint mismatch), and CAS-conflict resolution.

Invariant: eviction != rollback. Evicting an entry drops the fast-path
acceleration, but the TX remains SOFT_FINAL until anchored or compensated.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, List, Optional

from agents.air.finality_types import AttestationEnvelope


@dataclass
class CacheEntry:
    envelope: AttestationEnvelope
    inserted_at: float
    invalidated: bool = False
    invalidate_reason: Optional[str] = None


class SoftFinalityCache:
    """LRU + TTL cache for soft-final state roots. Thread-safe."""

    def __init__(self, ttl_seconds: float = 2.0, max_entries: int = 4096):
        self._ttl = ttl_seconds
        self._max = max_entries
        self._store: "OrderedDict[str, CacheEntry]" = OrderedDict()
        self._lock = threading.RLock()
        # Hooks fired on invalidation (rollback coordinator, audit, ...).
        self._invalidation_hooks: List[Callable[[CacheEntry, str], None]] = []

    # -- registration -------------------------------------------------

    def register_invalidation_hook(
        self, hook: Callable[[CacheEntry, str], None]
    ) -> None:
        with self._lock:
            self._invalidation_hooks.append(hook)

    # -- hot path -----------------------------------------------------

    def get(self, dedup_key: str, now: Optional[float] = None
            ) -> Optional[AttestationEnvelope]:
        now = now if now is not None else time.time()
        with self._lock:
            entry = self._store.get(dedup_key)
            if entry is None or entry.invalidated:
                return None
            if entry.envelope.is_expired(now):
                # TTL lapse -> demote to speculative, drop from cache.
                self._store.pop(dedup_key, None)
                return None
            self._store.move_to_end(dedup_key)
            return entry.envelope

    def put(self, envelope: AttestationEnvelope, now: Optional[float] = None
            ) -> bool:
        """Insert or update. Returns True if this call won the slot.

        CAS semantics: if a live entry already exists for the same dedup_key
        with a different state_root, the newcomer loses and must fall back to
        Surface.
        """
        now = now if now is not None else time.time()
        with self._lock:
            existing = self._store.get(envelope.dedup_key)
            if existing is not None and not existing.invalidated:
                if not existing.envelope.is_expired(now):
                    if existing.envelope.state_root != envelope.state_root:
                        return False  # conflict on same slot: incumbent wins
                    return True       # idempotent resubmit of same envelope
            self._store[envelope.dedup_key] = CacheEntry(
                envelope=envelope, inserted_at=now
            )
            self._store.move_to_end(envelope.dedup_key)
            self._evict_if_needed()
            return True

    # -- invalidation -------------------------------------------------

    def invalidate(self, dedup_key: str, reason: str) -> bool:
        with self._lock:
            entry = self._store.get(dedup_key)
            if entry is None or entry.invalidated:
                return False
            entry.invalidated = True
            entry.invalidate_reason = reason
            hooks = list(self._invalidation_hooks)
        for hook in hooks:
            hook(entry, reason)
        return True

    def invalidate_epoch(self, epoch: int, reason: str) -> int:
        """Bulk-invalidate an epoch (checkpoint mismatch)."""
        with self._lock:
            keys = [
                k for k, v in self._store.items()
                if v.envelope.epoch == epoch and not v.invalidated
            ]
        for k in keys:
            self.invalidate(k, reason)
        return len(keys)

    # -- maintenance --------------------------------------------------

    def _evict_if_needed(self) -> None:
        while len(self._store) > self._max:
            self._store.popitem(last=False)

    def sweep_expired(self, now: Optional[float] = None) -> int:
        now = now if now is not None else time.time()
        with self._lock:
            expired = [
                k for k, v in self._store.items()
                if v.envelope.is_expired(now) or v.invalidated
            ]
            for k in expired:
                self._store.pop(k, None)
        return len(expired)

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)
