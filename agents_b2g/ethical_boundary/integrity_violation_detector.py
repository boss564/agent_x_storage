"""Agent 5 — IntegrityViolationDetector (Wave 39).

Output-side integrity detection: offensive execution calls, profit extraction,
sandwich/MEV patterns. Consumes execution metadata and audit context; references
OFFENSIVE_MARKER_REGISTRY only — no local marker lists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agents_b2g.ethical_boundary.agents import make_response
from agents_b2g.ethical_boundary.audit_trail_writer import AuditTrailWriter
from agents_b2g.ethical_boundary.config import EthicalBoundaryConfig, OFFENSIVE_MARKER_REGISTRY
from agents_b2g.ethical_boundary.logging_utils import JSONLogger, _safe_call
from agents_b2g.ethical_boundary.subagents.integrity import (
    ExecutionCallAnalyzer,
    OffensiveLiquidationDetector,
    ProfitExtractionDetector,
    SandwichAttackDetector,
    ViolationSeverityScorer,
)
from agents_b2g.ethical_boundary.types import (
    ViolationRecord,
    ViolationSeverity,
    ViolationType,
)


@dataclass(frozen=True)
class IntegrityViolationResult:
    violations: tuple[ViolationRecord, ...]
    execution_calls_analyzed: int


class IntegrityViolationDetector:
    """Stage 5 — offensive output execution detection with audit trail."""

    agent_name = "IntegrityViolationDetector"

    def __init__(self, user_id: str = "wave39", config: EthicalBoundaryConfig | None = None):
        self.user_id = user_id
        self.config = config or EthicalBoundaryConfig.load()
        self.logger = JSONLogger(self.agent_name, user_id)
        self._analyzer = ExecutionCallAnalyzer()
        self._profit_detector = ProfitExtractionDetector()
        self._liquidation_detector = OffensiveLiquidationDetector()
        self._sandwich_detector = SandwichAttackDetector()
        self._scorer = ViolationSeverityScorer()

    def run(
        self,
        payload: Mapping[str, Any],
        job_id: str,
        *,
        audit_writer: AuditTrailWriter | None = None,
    ) -> dict[str, Any]:
        return _safe_call(
            self.logger,
            self.agent_name,
            self._run_inner,
            payload,
            job_id,
            audit_writer,
        )

    def enforce(
        self,
        payload: Mapping[str, Any],
        *,
        job_id: str,
        audit_writer: AuditTrailWriter | None = None,
    ) -> IntegrityViolationResult:
        return self._enforce(payload, job_id=job_id, audit_writer=audit_writer)

    def _run_inner(
        self,
        payload: Mapping[str, Any],
        job_id: str,
        audit_writer: AuditTrailWriter | None,
    ) -> dict[str, Any]:
        result = self._enforce(payload, job_id=job_id, audit_writer=audit_writer)
        status = "blocked" if result.violations else "completed"
        return make_response(
            status,  # type: ignore[arg-type]
            job_id,
            artifacts=[
                {
                    "type": "integrity_violation_result",
                    "execution_calls_analyzed": result.execution_calls_analyzed,
                    "violation_count": len(result.violations),
                    "marker_registry_version": OFFENSIVE_MARKER_REGISTRY.version,
                }
            ],
            logs=[f"violations={len(result.violations)}"],
        )

    def _enforce(
        self,
        payload: Mapping[str, Any],
        *,
        job_id: str,
        audit_writer: AuditTrailWriter | None,
    ) -> IntegrityViolationResult:
        _ = job_id
        try:
            self._audit(
                audit_writer,
                event="integrity_detection_start",
                details={"registry_version": OFFENSIVE_MARKER_REGISTRY.version},
            )

            calls = self._analyzer.analyze(payload)
            self._audit(
                audit_writer,
                event="execution_calls_analyzed",
                details={"count": len(calls), "sources": list({c.source_field for c in calls})},
            )

            hits = []
            hits.extend(self._profit_detector.detect(payload, calls))
            hits.extend(self._liquidation_detector.detect(payload, calls))
            hits.extend(self._sandwich_detector.detect(payload, calls))

            violations = self._scorer.score(tuple(hits))

            if violations:
                self._audit(
                    audit_writer,
                    event="integrity_violation_detected",
                    details={
                        "count": len(violations),
                        "markers": [v.evidence.get("marker") for v in violations],
                    },
                )
            else:
                self._audit(audit_writer, event="integrity_detection_pass", details={})

            return IntegrityViolationResult(
                violations=violations,
                execution_calls_analyzed=len(calls),
            )

        except Exception as exc:
            self._audit(
                audit_writer,
                event="integrity_detection_fault",
                details={"error": str(exc)},
            )
            return IntegrityViolationResult(
                violations=(
                    ViolationRecord(
                        violation_type=ViolationType.PIPELINE_FAULT,
                        severity=ViolationSeverity.critical(),
                        source_agent=self.agent_name,
                        message=f"IntegrityViolationDetector fault: {exc}",
                    ),
                ),
                execution_calls_analyzed=0,
            )

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
            stage="IntegrityViolationDetector",
            event=event,
            details=details or {},
        )
