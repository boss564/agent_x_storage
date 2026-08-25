"""W39-A8-S3 — certify no open violations remain from stages 1–7."""

from __future__ import annotations

from agents_b2g.ethical_boundary.types import (
    ViolationRecord,
    ViolationSeverity,
    ViolationType,
    should_block,
)


class ViolationAbsenceChecker:
    subagent_id = "W39-A8-S3"

    def certify(
        self,
        prior_violations: tuple[ViolationRecord, ...],
    ) -> tuple[ViolationRecord, ...]:
        if not prior_violations:
            return ()

        blocking = [v for v in prior_violations if v.is_auto_block() or should_block((v,))]
        if blocking:
            return (
                ViolationRecord(
                    violation_type=ViolationType.ASSERTION_FAILURE,
                    severity=ViolationSeverity.critical(),
                    source_agent="DefensiveScopeCertifier",
                    message="certification failed: open violations from upstream stages",
                    evidence={
                        "open_count": len(prior_violations),
                        "blocking_count": len(blocking),
                        "certifier": self.subagent_id,
                    },
                ),
            )

        return (
            ViolationRecord(
                violation_type=ViolationType.ASSERTION_FAILURE,
                severity=ViolationSeverity.critical(),
                source_agent="DefensiveScopeCertifier",
                message="certification failed: non-blocking violations still open",
                evidence={
                    "open_count": len(prior_violations),
                    "certifier": self.subagent_id,
                },
            ),
        )
