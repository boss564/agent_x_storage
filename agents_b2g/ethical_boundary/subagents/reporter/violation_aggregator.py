"""W39-A7-S1 — aggregate ViolationRecords from all upstream pipeline stages."""

from __future__ import annotations

from collections import Counter
from typing import Any

from agents_b2g.ethical_boundary.types import ViolationRecord, merge_violations


class ViolationAggregator:
    subagent_id = "W39-A7-S1"

    def aggregate(
        self,
        violations: tuple[ViolationRecord, ...],
    ) -> tuple[ViolationRecord, ...]:
        merged = merge_violations(violations)
        return merged

    def summarize(self, violations: tuple[ViolationRecord, ...]) -> dict[str, Any]:
        by_source = Counter(v.source_agent for v in violations)
        by_type = Counter(v.violation_type.value for v in violations)
        return {
            "total": len(violations),
            "by_source_agent": dict(sorted(by_source.items())),
            "by_violation_type": dict(sorted(by_type.items())),
        }
