"""W39-A4-S3 — SHA-256 hash chain for GoBD audit entries."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from agents_b2g.ethical_boundary.audit_constants import AUDIT_GENESIS_HASH


class AuditTrailHasher:
    subagent_id = "W39-A4-S3"

    genesis_hash = AUDIT_GENESIS_HASH

    def hash_entry(self, prev_hash: str, body: Mapping[str, Any]) -> str:
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
        material = f"{prev_hash}|{canonical}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def seal_entry(self, prev_hash: str, body: Mapping[str, Any]) -> dict[str, Any]:
        classified_body = dict(body)
        entry_hash = self.hash_entry(prev_hash, classified_body)
        return {
            **classified_body,
            "prev_hash": prev_hash,
            "entry_hash": entry_hash,
        }
