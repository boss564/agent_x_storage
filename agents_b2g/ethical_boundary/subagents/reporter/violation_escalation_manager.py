"""W39-A7-S3 — descriptive Wave 28 escalation (ViolationObservation only)."""

from __future__ import annotations

import hashlib
import json

from agents_b2g.ethical_boundary.types import (
    ViolationObservation,
    ViolationRecord,
    utc_now_iso,
)


class ViolationEscalationManager:
    subagent_id = "W39-A7-S3"

    _FORBIDDEN_KEYS = frozenset(
        {"execute", "respond", "countermeasure", "action", "route"}
    )

    def escalate(
        self,
        violations: tuple[ViolationRecord, ...],
    ) -> tuple[ViolationObservation, ...]:
        observations: list[ViolationObservation] = []
        for record in violations:
            observation = ViolationObservation(
                signature=self._signature(record),
                severity=record.severity,
                timestamp_utc=utc_now_iso(),
                source_agent=record.source_agent,
            )
            payload = observation.to_dict()
            if self._FORBIDDEN_KEYS.intersection(payload.keys()):
                raise ValueError("ViolationObservation must not carry action fields")
            observations.append(observation)
        return tuple(observations)

    @staticmethod
    def _signature(record: ViolationRecord) -> str:
        blob = json.dumps(record.to_dict(), sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()
