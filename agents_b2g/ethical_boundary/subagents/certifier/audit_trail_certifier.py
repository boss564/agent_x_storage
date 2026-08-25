"""W39-A8-S4 — verify audit trail hash chain consistency."""

from __future__ import annotations

from agents_b2g.ethical_boundary.audit_trail_writer import AuditTrailWriter
from agents_b2g.ethical_boundary.types import ViolationRecord, ViolationSeverity, ViolationType


class AuditTrailCertifier:
    subagent_id = "W39-A8-S4"

    def certify(
        self,
        audit_writer: AuditTrailWriter | None,
    ) -> tuple[ViolationRecord, ...]:
        if audit_writer is None:
            return (
                ViolationRecord(
                    violation_type=ViolationType.AUDIT_INTEGRITY,
                    severity=ViolationSeverity.critical(),
                    source_agent="DefensiveScopeCertifier",
                    message="certification failed: audit trail writer unavailable",
                    evidence={"certifier": self.subagent_id},
                ),
            )

        ok, err = audit_writer.verify_chain()
        if ok:
            return ()

        return (
            ViolationRecord(
                violation_type=ViolationType.AUDIT_INTEGRITY,
                severity=ViolationSeverity.critical(),
                source_agent="DefensiveScopeCertifier",
                message=f"certification failed: audit chain invalid ({err})",
                evidence={"error": err, "certifier": self.subagent_id},
            ),
        )
