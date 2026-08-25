"""W39-A5-S3 — score integrity hits using registered blocking threshold."""

from __future__ import annotations

from agents_b2g.ethical_boundary.config import (
    ETHICAL_BLOCKING_SEVERITY_THRESHOLD,
    OFFENSIVE_MARKER_REGISTRY,
)
from agents_b2g.ethical_boundary.subagents.integrity.types import IntegrityDetectionHit
from agents_b2g.ethical_boundary.types import (
    ViolationRecord,
    ViolationSeverity,
    ViolationType,
)


class ViolationSeverityScorer:
    subagent_id = "W39-A5-S3"

    def score(self, hits: tuple[IntegrityDetectionHit, ...]) -> tuple[ViolationRecord, ...]:
        records: list[ViolationRecord] = []
        seen: set[tuple[str, str]] = set()
        for hit in hits:
            key = (hit.marker, hit.detector_id, hit.message)
            dedupe_key = (key[0], key[2])
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            severity_value = self._severity_for_hit(hit)
            records.append(
                ViolationRecord(
                    violation_type=hit.violation_type,
                    severity=ViolationSeverity(severity_value),
                    source_agent="IntegrityViolationDetector",
                    message=hit.message,
                    evidence={
                        **dict(hit.evidence),
                        "marker": hit.marker,
                        "detector_id": hit.detector_id,
                        "registry_version": OFFENSIVE_MARKER_REGISTRY.version,
                        "blocking_threshold": ETHICAL_BLOCKING_SEVERITY_THRESHOLD,
                        "charter_ref": OFFENSIVE_MARKER_REGISTRY.charter_refs.get(
                            hit.marker, "§1.0.E"
                        ),
                    },
                )
            )
        return tuple(records)

    @staticmethod
    def _severity_for_hit(hit: IntegrityDetectionHit) -> int:
        if hit.marker in OFFENSIVE_MARKER_REGISTRY.markers:
            return max(hit.severity_hint, ETHICAL_BLOCKING_SEVERITY_THRESHOLD)
        if hit.violation_type in {
            ViolationType.OFFENSIVE_EXECUTION,
            ViolationType.PROFIT_EXTRACTION,
        }:
            return max(hit.severity_hint, ETHICAL_BLOCKING_SEVERITY_THRESHOLD)
        return hit.severity_hint
