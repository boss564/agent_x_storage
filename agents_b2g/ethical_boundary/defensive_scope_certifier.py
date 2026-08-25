"""Agent 8 — DefensiveScopeCertifier (Wave 39).

Positive gate: certifies defensive scope when all upstream stages passed.
References upstream outcomes — does not duplicate Agent 1/6 validation logic.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping

from agents_b2g.ethical_boundary.agents import make_response
from agents_b2g.ethical_boundary.audit_trail_writer import AuditTrailWriter
from agents_b2g.ethical_boundary.config import EthicalBoundaryConfig
from agents_b2g.ethical_boundary.logging_utils import JSONLogger, _safe_call
from agents_b2g.ethical_boundary.subagents.certifier import (
    AuditTrailCertifier,
    CharterComplianceCertifier,
    OutputCertifier,
    PreRegComplianceCertifier,
    ScopeFlagCertifier,
    ViolationAbsenceChecker,
)
from agents_b2g.ethical_boundary.subagents.certifier.types import CertificationContext
from agents_b2g.ethical_boundary.types import (
    ScopeFlag,
    ViolationRecord,
    ViolationSeverity,
    ViolationType,
)


@dataclass(frozen=True)
class DefensiveScopeCertificationResult:
    certified: bool
    violations: tuple[ViolationRecord, ...]
    certificate_id: str | None = None


class DefensiveScopeCertifier:
    """Stage 8 — positive certification gate for DEFENSIVE_CAUSAL_GROUNDING."""

    agent_name = "DefensiveScopeCertifier"

    def __init__(self, user_id: str = "wave39", config: EthicalBoundaryConfig | None = None):
        self.user_id = user_id
        self.config = config or EthicalBoundaryConfig.load()
        self.logger = JSONLogger(self.agent_name, user_id)
        self._scope_certifier = ScopeFlagCertifier()
        self._output_certifier = OutputCertifier()
        self._absence_checker = ViolationAbsenceChecker()
        self._audit_certifier = AuditTrailCertifier()
        self._prereg_certifier = PreRegComplianceCertifier()
        self._charter_certifier = CharterComplianceCertifier()

    def run(
        self,
        payload: Mapping[str, Any],
        job_id: str,
        *,
        scope: ScopeFlag,
        context: CertificationContext,
        audit_writer: AuditTrailWriter | None = None,
    ) -> dict[str, Any]:
        return _safe_call(
            self.logger,
            self.agent_name,
            self._run_inner,
            payload,
            job_id,
            scope,
            context,
            audit_writer,
        )

    def certify(
        self,
        payload: Mapping[str, Any],
        *,
        scope: ScopeFlag,
        job_id: str,
        context: CertificationContext,
        audit_writer: AuditTrailWriter | None = None,
    ) -> DefensiveScopeCertificationResult:
        return self._certify(
            payload,
            scope=scope,
            job_id=job_id,
            context=context,
            audit_writer=audit_writer,
        )

    def _run_inner(
        self,
        payload: Mapping[str, Any],
        job_id: str,
        scope: ScopeFlag,
        context: CertificationContext,
        audit_writer: AuditTrailWriter | None,
    ) -> dict[str, Any]:
        result = self._certify(
            payload,
            scope=scope,
            job_id=job_id,
            context=context,
            audit_writer=audit_writer,
        )
        status = "completed" if result.certified else "blocked"
        return make_response(
            status,  # type: ignore[arg-type]
            job_id,
            artifacts=[
                {
                    "type": "defensive_scope_certificate",
                    "certified": result.certified,
                    "certificate_id": result.certificate_id,
                    "violation_count": len(result.violations),
                }
            ],
            logs=[f"certified={result.certified}"],
        )

    def _certify(
        self,
        payload: Mapping[str, Any],
        *,
        scope: ScopeFlag,
        job_id: str,
        context: CertificationContext,
        audit_writer: AuditTrailWriter | None,
    ) -> DefensiveScopeCertificationResult:
        try:
            self._audit(audit_writer, event="certification_start", details={"job_id": job_id})

            hits: list[ViolationRecord] = []
            hits.extend(self._scope_certifier.certify(payload, scope=scope))
            hits.extend(self._output_certifier.certify(payload))
            hits.extend(self._absence_checker.certify(context.prior_violations))
            hits.extend(self._audit_certifier.certify(audit_writer))
            hits.extend(
                self._prereg_certifier.certify(
                    prereg_stage_passed=context.prereg_stage_passed,
                    validated_hashes=context.prereg_validated_hashes,
                )
            )
            hits.extend(
                self._charter_certifier.certify(
                    charter_stage_passed=context.charter_stage_passed,
                    charter_version=context.charter_version,
                )
            )

            if hits:
                self._audit(
                    audit_writer,
                    event="certification_failed",
                    details={"violation_count": len(hits)},
                )
                return DefensiveScopeCertificationResult(
                    certified=False,
                    violations=tuple(hits),
                )

            certificate_id = self._certificate_id(job_id, scope)
            self._audit(
                audit_writer,
                event="certification_pass",
                details={
                    "certificate_id": certificate_id,
                    "charter_version": context.charter_version,
                },
            )
            return DefensiveScopeCertificationResult(
                certified=True,
                violations=(),
                certificate_id=certificate_id,
            )

        except Exception as exc:
            self._audit(
                audit_writer,
                event="certification_fault",
                details={"error": str(exc)},
            )
            return DefensiveScopeCertificationResult(
                certified=False,
                violations=(
                    ViolationRecord(
                        violation_type=ViolationType.PIPELINE_FAULT,
                        severity=ViolationSeverity.critical(),
                        source_agent=self.agent_name,
                        message=f"DefensiveScopeCertifier fault: {exc}",
                    ),
                ),
            )

    @staticmethod
    def _certificate_id(job_id: str, scope: ScopeFlag) -> str:
        blob = f"{job_id}:{scope.content_hash}:{scope.attached_at}".encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    @staticmethod
    def _audit(
        audit_writer: AuditTrailWriter | None,
        *,
        event: str,
        details: Mapping[str, Any] | None,
    ) -> None:
        if audit_writer is None:
            return
        audit_writer.log_event(
            stage="DefensiveScopeCertifier",
            event=event,
            details=details or {},
        )
