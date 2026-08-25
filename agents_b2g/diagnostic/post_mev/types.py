"""Post-MEV types — additive envelopes; never mutates DiagnosticSignalEnvelope."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Mapping


class PostMEVStatus(str, Enum):
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"


class PostMEVBlockCause(str, Enum):
    PRE_REG_MUTATION_ATTEMPT = "PRE_REG_MUTATION_ATTEMPT"
    TRIGGER_MISSING = "TRIGGER_MISSING"
    ENVELOPE_TAMPER = "ENVELOPE_TAMPER"
    PIPELINE_FAULT = "PIPELINE_FAULT"


class ReconcileVerdict(str, Enum):
    AMENDMENT_PROPOSED = "AMENDMENT_PROPOSED"
    NO_AMENDMENT = "NO_AMENDMENT"
    BLOCKED = "BLOCKED"


GENESIS_AMENDMENT_PREV = "0" * 64


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_hex(payload: str | bytes | Mapping[str, Any] | list[Any]) -> str:
    if isinstance(payload, (dict, list)):
        raw = json.dumps(payload, sort_keys=True, default=str).encode()
    elif isinstance(payload, str):
        raw = payload.encode()
    else:
        raw = bytes(payload)
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class AmendmentEntry:
    amendment_id: str
    original_pre_reg_hash: str
    amendment_payload: dict[str, Any]
    prev_amendment_hash: str
    amendment_hash: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "amendment_id": self.amendment_id,
            "original_pre_reg_hash": self.original_pre_reg_hash,
            "amendment_payload": self.amendment_payload,
            "prev_amendment_hash": self.prev_amendment_hash,
            "amendment_hash": self.amendment_hash,
            "created_at": self.created_at,
        }

    @staticmethod
    def build(
        *,
        amendment_id: str,
        original_pre_reg_hash: str,
        amendment_payload: dict[str, Any],
        prev_amendment_hash: str = GENESIS_AMENDMENT_PREV,
    ) -> AmendmentEntry:
        created = utc_now_iso()
        material = {
            "amendment_id": amendment_id,
            "original_pre_reg_hash": original_pre_reg_hash,
            "amendment_payload": amendment_payload,
            "prev_amendment_hash": prev_amendment_hash,
            "created_at": created,
        }
        digest = sha256_hex(material)
        return AmendmentEntry(
            amendment_id=amendment_id,
            original_pre_reg_hash=original_pre_reg_hash,
            amendment_payload=amendment_payload,
            prev_amendment_hash=prev_amendment_hash,
            amendment_hash=digest,
            created_at=created,
        )


@dataclass(frozen=True)
class PostMEVDiagnosticEnvelope:
    """Additive post-gatekeeper annotation — never replaces DiagnosticSignalEnvelope."""

    status: PostMEVStatus
    job_id: str
    trigger: Literal["mev_tail_completed"] = "mev_tail_completed"
    gatekeeper_envelope_hash: str = ""
    consistency_ok: bool = False
    quarantined_count: int = 0
    amendments: tuple[AmendmentEntry, ...] = ()
    reconcile_verdict: str = ReconcileVerdict.NO_AMENDMENT.value
    block_cause: str | None = None
    pm_results: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "job_id": self.job_id,
            "trigger": self.trigger,
            "gatekeeper_envelope_hash": self.gatekeeper_envelope_hash,
            "consistency_ok": self.consistency_ok,
            "quarantined_count": self.quarantined_count,
            "amendments": [a.to_dict() for a in self.amendments],
            "reconcile_verdict": self.reconcile_verdict,
            "block_cause": self.block_cause,
            "pm_results": self.pm_results,
        }
