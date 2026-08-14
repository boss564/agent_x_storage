"""A09 — AWACS Datalink (GoBD audit export).

Consumes the frozen agentx.air.* event schema and writes a GoBD-compliant
hash-chained audit trail — the air-layer mirror of the ground-side WORM
archives (compliance/gobd_integrity_checker, finale/audit_trail D2).

Chain rule: h_i = SHA3-256(h_{i-1} || canonical(event_i)).
Tampering with any record breaks verification. Export is append-only
JSONL plus a chain certificate. SHA3 per Wave 33 convention.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

GENESIS_HASH = "0" * 64

# Frozen event schema — do not extend without a contract revision.
FROZEN_TOPICS = (
    "agentx.air.soft_final_attested",
    "agentx.air.hard_final_anchored",
    "agentx.air.soft_final_rollback",
    "agentx.air.cas.committed",
    "agentx.air.cas.conflict",
    "agentx.air.cas.burst",
    "agentx.air.watch.alert",
    "agentx.air.neutralized",
    "agentx.air.compensation.request",
    "agentx.air.fallback.routed",
    "agentx.air.fallback.deadletter",
)


@dataclass
class ExportReport:
    path: str
    records: int
    head_hash: str
    tail_hash: str
    certificate_path: str


class AWACSDatalink:
    """Hash-chained audit sink for all air-layer events."""

    def __init__(self, metrics=None):
        self._metrics = metrics
        self._records: List[Dict] = []
        self._tail = GENESIS_HASH
        # Genesis record anchors the chain to deployment time.
        self.record("agentx.air.datalink.genesis", {"schema": "1.0"})

    # -- recording ------------------------------------------------------

    def record(self, topic: str, payload: dict,
               ts: Optional[float] = None) -> str:
        """Append one event. Returns the new tail hash."""
        ts = ts if ts is not None else time.time()
        event = {"topic": topic, "ts": round(ts, 6), "payload": payload}
        digest = self._hash(self._tail, event)
        event["prev_hash"] = self._tail
        event["hash"] = digest
        self._records.append(event)
        self._tail = digest
        if self._metrics is not None:
            self._metrics.inc("air_datalink_events_total",
                              labels={"topic": topic})
            self._metrics.set("air_datalink_chain_length",
                              len(self._records))
        return digest

    def attach(self, bus) -> None:
        """Subscribe to all frozen topics on the EventBus."""
        for topic in FROZEN_TOPICS:
            bus.subscribe(topic, lambda payload, t=topic:
                          self.record(t, payload))

    # -- verification ----------------------------------------------------

    def verify(self) -> bool:
        """Recompute the whole chain. Any tampering breaks it."""
        prev = GENESIS_HASH
        for event in self._records:
            check = {k: v for k, v in event.items()
                     if k not in ("prev_hash", "hash")}
            if event["prev_hash"] != prev:
                return False
            if event["hash"] != self._hash(prev, check):
                return False
            prev = event["hash"]
        return prev == self._tail

    # -- export ------------------------------------------------------------

    def export(self, path: str) -> ExportReport:
        """Write JSONL + chain certificate (append-only, WORM-style)."""
        with open(path, "w", encoding="utf-8") as fh:
            for event in self._records:
                fh.write(json.dumps(event, sort_keys=True,
                                    separators=(",", ":")) + "\n")
        cert_path = path + ".cert"
        cert = {
            "schema": "1.0",
            "records": len(self._records),
            "head_hash": self._records[0]["hash"],
            "tail_hash": self._tail,
            "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                         time.gmtime()),
            "algorithm": "SHA3-256",
        }
        with open(cert_path, "w", encoding="utf-8") as fh:
            json.dump(cert, fh, indent=2)
        return ExportReport(
            path=path, records=len(self._records),
            head_hash=self._records[0]["hash"], tail_hash=self._tail,
            certificate_path=cert_path,
        )

    # -- accessors ----------------------------------------------------------

    @property
    def chain_length(self) -> int:
        return len(self._records)

    @property
    def tail_hash(self) -> str:
        return self._tail

    # -- internals -------------------------------------------------------------

    @staticmethod
    def _hash(prev: str, event: dict) -> str:
        canonical = json.dumps(event, sort_keys=True, separators=(",", ":"))
        return hashlib.sha3_256((prev + canonical).encode("utf-8")).hexdigest()
