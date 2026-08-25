"""W39-A8-S6 — reference Agent 6 Charter outcome (no re-validation)."""

from __future__ import annotations

from agents_b2g.ethical_boundary.types import ViolationRecord, ViolationSeverity, ViolationType


class CharterComplianceCertifier:
    subagent_id = "W39-A8-S6"

    def certify(
        self,
        *,
        charter_stage_passed: bool,
        charter_version: str,
    ) -> tuple[ViolationRecord, ...]:
        if not charter_version:
            return (
                ViolationRecord(
                    violation_type=ViolationType.CHARTER_AIRGAP,
                    severity=ViolationSeverity.critical(),
                    source_agent="DefensiveScopeCertifier",
                    message="certification failed: charter version missing",
                    evidence={"certifier": self.subagent_id},
                ),
            )

        if not charter_stage_passed:
            return (
                ViolationRecord(
                    violation_type=ViolationType.CHARTER_AIRGAP,
                    severity=ViolationSeverity.critical(),
                    source_agent="DefensiveScopeCertifier",
                    message="certification failed: CharterEnforcerAgent did not pass",
                    evidence={
                        "charter_version": charter_version,
                        "certifier": self.subagent_id,
                    },
                ),
            )

        return ()
