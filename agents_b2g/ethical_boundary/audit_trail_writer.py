"""Shared GoBD WORM audit trail writer — injected into Wave 39 stages 5–8."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from agents_b2g.ethical_boundary.audit_constants import AUDIT_GENESIS_HASH
from agents_b2g.ethical_boundary.subagents.audit import (
    AuditTrailHasher,
    GoBDLogClassifier,
    WORMWriter,
)
from agents_b2g.ethical_boundary.subagents.audit.worm_writer import AuditWriteError


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AuditTrailWriteResult:
    entry_hash: str
    line_number: int


class AuditTrailWriter:
    """Central append-only audit infrastructure for ethical boundary pipeline."""

    def __init__(
        self,
        *,
        job_id: str,
        user_id: str,
        audit_path: Path,
    ):
        self.job_id = job_id
        self.user_id = user_id
        self.audit_path = audit_path
        self._classifier = GoBDLogClassifier()
        self._hasher = AuditTrailHasher()
        self._worm = WORMWriter(audit_path)
        self._entries_written = 0

    @property
    def entries_written(self) -> int:
        return self._entries_written

    @property
    def last_hash(self) -> str:
        return self._worm.last_entry_hash(genesis=AUDIT_GENESIS_HASH)

    def log_event(
        self,
        *,
        stage: str,
        event: str,
        details: Mapping[str, Any] | None = None,
    ) -> AuditTrailWriteResult:
        prev_hash = self._worm.last_entry_hash(genesis=AUDIT_GENESIS_HASH)
        body = self._classifier.classify(
            {
                "timestamp_utc": utc_now_iso(),
                "job_id": self.job_id,
                "user_id": self.user_id,
                "stage": stage,
                "event": event,
                "details": dict(details or {}),
            }
        )
        sealed = self._hasher.seal_entry(prev_hash, body)
        append_result = self._worm.append_entry(sealed)
        self._entries_written += 1
        return AuditTrailWriteResult(
            entry_hash=append_result.entry_hash,
            line_number=append_result.line_number,
        )

    def verify_chain(self) -> tuple[bool, str | None]:
        return self._worm.verify_chain(genesis=AUDIT_GENESIS_HASH)


class AuditTrailWriterFactory:
    """Creates job-scoped writers under {data_root}/{user_id}/ethical_boundary/audit/."""

    def __init__(self, *, data_root: Path, user_id: str):
        self.data_root = data_root
        self.user_id = user_id

    def open(self, job_id: str) -> AuditTrailWriter:
        safe_job = job_id.replace("/", "_")
        audit_dir = self.data_root / self.user_id / "ethical_boundary" / "audit"
        path = audit_dir / f"{safe_job}.jsonl"
        return AuditTrailWriter(job_id=job_id, user_id=self.user_id, audit_path=path)


__all__ = [
    "AuditTrailWriter",
    "AuditTrailWriterFactory",
    "AuditTrailWriteResult",
]
