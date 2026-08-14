#!/usr/bin/env python3
"""P08 Audit Logger — tamper-evident hash-chained audit trail.

Every dismount and quarantine event produces a hash-chained entry:
    H_n = HMAC-SHA256(secret, H_{n-1} || event_type || agent_id || payload || t_ns)

No entry can be altered or deleted without breaking the chain, and the
HMAC secret is held only by the trusted auditor. The chain is verifiable
forward from the genesis hash.
"""

import hashlib
import hmac
import json
import time
from typing import Any, Dict, List, Optional


class P08AuditLogger:
    """Hash-chained audit logger for P08 security events."""

    def __init__(self, secret_key: bytes):
        self.secret_key = secret_key
        self.previous_hash = "GENESIS_BLOCK_P08_AUDIT_HASH_AGENT_X"
        self.entries: List[Dict[str, Any]] = []

    def log_event(self, event_type: str, agent_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        timestamp_ns = time.time_ns()
        payload_serialized = json.dumps(payload, sort_keys=True, default=str)
        data_to_hash = (
            f"{self.previous_hash}|{event_type}|{agent_id}|"
            f"{payload_serialized}|{timestamp_ns}"
        ).encode()
        current_hash = hmac.new(
            self.secret_key, data_to_hash, hashlib.sha256
        ).hexdigest()

        entry = {
            "sequence_hash": current_hash,
            "previous_hash": self.previous_hash,
            "event_type": event_type,
            "agent_id": agent_id,
            "timestamp_ns": timestamp_ns,
            "payload": payload,
        }
        self.entries.append(entry)
        self.previous_hash = current_hash
        return entry

    def verify_chain(self, start_from: int = 0) -> bool:
        """Verify the hash chain is unbroken from the genesis hash forward."""
        prev = "GENESIS_BLOCK_P08_AUDIT_HASH_AGENT_X"
        for i, entry in enumerate(self.entries):
            if i < start_from:
                continue
            if entry["previous_hash"] != prev:
                return False
            payload_serialized = json.dumps(entry["payload"], sort_keys=True, default=str)
            data = (
                f"{prev}|{entry['event_type']}|{entry['agent_id']}|"
                f"{payload_serialized}|{entry['timestamp_ns']}"
            ).encode()
            expected = hmac.new(self.secret_key, data, hashlib.sha256).hexdigest()
            if entry["sequence_hash"] != expected:
                return False
            prev = entry["sequence_hash"]
        return True

    def count(self) -> int:
        return len(self.entries)
