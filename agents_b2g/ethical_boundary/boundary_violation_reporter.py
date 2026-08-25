"""Agent 7 — BoundaryViolationReporter (Wave 39).

Aggregates upstream ViolationRecords, ranks by severity, and escalates descriptively
to Wave 28 via ViolationObservation — no action fields permitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agents_b2g.ethical_boundary.agents import make_response
from agents_b2g.ethical_boundary.audit_trail_writer import AuditTrailWriter
from agents_b2g.ethical_boundary.config import EthicalBoundaryConfig
from agents_b2g.ethical_boundary.logging_utils import JSONLogger, _safe_call
from agents_b2g.ethical_boundary.subagents.reporter import (
    ViolationAggregator,
    ViolationEscalationManager,
    ViolationSeverityRanker,
)
from agents_b2g.ethical_boundary.subagents.reporter.types import AggregatedViolationReport
from agents_b2g.ethical_boundary.types import (
    ViolationObservation,
    ViolationRecord,
    ViolationSeverity,
    ViolationType,
)


@dataclass(frozen=True)
class BoundaryViolationReportResult:
    """Agent 7 output — faults only in violations; report carries aggregated view."""

    violations: tuple[ViolationRecord, ...]
    report: AggregatedViolationReport


class BoundaryViolationReporter:
    """Stage 7 — violation aggregation, ranking, and descriptive Wave 28 escalation."""

    agent_name = "BoundaryViolationReporter"

    def __init__(self, user_id: str = "wave39", config: EthicalBoundaryConfig | None = None):
        self.user_id = user_id
        self.config = config or EthicalBoundaryConfig.load()
        self.logger = JSONLogger(self.agent_name, user_id)
        self._aggregator = ViolationAggregator()
        self._ranker = ViolationSeverityRanker()
        self._escalator = ViolationEscalationManager()

    def run(
        self,
        violations: tuple[ViolationRecord, ...],
        job_id: str,
        *,
        audit_writer: AuditTrailWriter | None = None,
    ) -> dict[str, Any]:
        return _safe_call(
            self.logger,
            self.agent_name,
            self._run_inner,
            violations,
            job_id,
            audit_writer,
        )

    def enforce(
        self,
        violations: tuple[ViolationRecord, ...],
        *,
        job_id: str,
        audit_writer: AuditTrailWriter | None = None,
    ) -> BoundaryViolationReportResult:
        return self._enforce(violations, job_id=job_id, audit_writer=audit_writer)

    def _run_inner(
        self,
        violations: tuple[ViolationRecord, ...],
        job_id: str,
        audit_writer: AuditTrailWriter | None,
    ) -> dict[str, Any]:
        result = self._enforce(violations, job_id=job_id, audit_writer=audit_writer)
        status = "blocked" if result.violations else "completed"
        return make_response(
            status,  # type: ignore[arg-type]
            job_id,
            artifacts=[
                {
                    "type": "boundary_violation_report",
                    "violation_count": len(result.report.violations),
                    "observation_count": len(result.report.wave28_observations),
                    "summary": dict(result.report.summary),
                }
            ],
            logs=[f"faults={len(result.violations)}"],
        )

    def _enforce(
        self,
        violations: tuple[ViolationRecord, ...],
        *,
        job_id: str,
        audit_writer: AuditTrailWriter | None,
    ) -> BoundaryViolationReportResult:
        _ = job_id
        try:
            self._audit(
                audit_writer,
                event="violation_report_start",
                details={"input_count": len(violations)},
            )

            aggregated = self._aggregator.aggregate(violations)
            ranked = self._ranker.rank(aggregated)
            observations = self._escalator.escalate(ranked)
            summary = self._aggregator.summarize(aggregated)

            self._audit(
                audit_writer,
                event="violation_report_complete",
                details={
                    "aggregated_count": len(aggregated),
                    "observation_count": len(observations),
                    **summary,
                },
            )

            report = AggregatedViolationReport(
                violations=aggregated,
                ranked_violations=ranked,
                wave28_observations=observations,
                summary=summary,
            )
            return BoundaryViolationReportResult(violations=(), report=report)

        except Exception as exc:
            self._audit(
                audit_writer,
                event="violation_report_fault",
                details={"error": str(exc)},
            )
            return BoundaryViolationReportResult(
                violations=(
                    ViolationRecord(
                        violation_type=ViolationType.PIPELINE_FAULT,
                        severity=ViolationSeverity.critical(),
                        source_agent=self.agent_name,
                        message=f"BoundaryViolationReporter fault: {exc}",
                    ),
                ),
                report=AggregatedViolationReport(
                    violations=(),
                    ranked_violations=(),
                    wave28_observations=(),
                    summary={"fault": str(exc)},
                ),
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
            stage="BoundaryViolationReporter",
            event=event,
            details=details or {},
        )
