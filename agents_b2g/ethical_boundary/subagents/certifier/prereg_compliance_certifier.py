"""W39-A8-S5 — reference Agent 1 Pre-Reg outcome (no re-validation)."""

from __future__ import annotations

from typing import Mapping

from agents_b2g.ethical_boundary.types import ViolationRecord, ViolationSeverity, ViolationType


class PreRegComplianceCertifier:
    subagent_id = "W39-A8-S5"

    def certify(
        self,
        *,
        prereg_stage_passed: bool,
        validated_hashes: Mapping[str, str],
    ) -> tuple[ViolationRecord, ...]:
        if not prereg_stage_passed:
            return (
                ViolationRecord(
                    violation_type=ViolationType.CONFIG_INTEGRITY,
                    severity=ViolationSeverity.critical(),
                    source_agent="DefensiveScopeCertifier",
                    message="certification failed: PreRegFirewallAgent did not pass",
                    evidence={"certifier": self.subagent_id},
                ),
            )

        if not validated_hashes:
            return (
                ViolationRecord(
                    violation_type=ViolationType.CONFIG_INTEGRITY,
                    severity=ViolationSeverity.critical(),
                    source_agent="DefensiveScopeCertifier",
                    message="certification failed: no Agent-1 validated pre-reg hashes",
                    evidence={"certifier": self.subagent_id},
                ),
            )

        return ()
