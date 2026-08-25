"""W39-A7-S2 — rank violations by severity and type priority."""

from __future__ import annotations

from agents_b2g.ethical_boundary.types import ViolationRecord, ViolationType

_TYPE_PRIORITY: dict[ViolationType, int] = {
    ViolationType.PIPELINE_FAULT: 0,
    ViolationType.PREREG_NEGATION: 1,
    ViolationType.CONFIG_INTEGRITY: 2,
    ViolationType.AUDIT_INTEGRITY: 3,
    ViolationType.SCOPE_TAMPER: 4,
    ViolationType.CHARTER_AIRGAP: 5,
    ViolationType.PROFIT_EXTRACTION: 6,
    ViolationType.OFFENSIVE_EXECUTION: 7,
    ViolationType.ASSERTION_FAILURE: 8,
}


class ViolationSeverityRanker:
    subagent_id = "W39-A7-S2"

    def rank(self, violations: tuple[ViolationRecord, ...]) -> tuple[ViolationRecord, ...]:
        return tuple(
            sorted(
                violations,
                key=lambda v: (
                    -v.severity.value,
                    _TYPE_PRIORITY.get(v.violation_type, 99),
                    v.violation_type.value,
                    v.source_agent,
                    v.message,
                ),
            )
        )
