"""Agent 4 — AuditTrailAgent (Wave 39).

GoBD-WORM JSONL audit infrastructure with hash chain. Provides AuditTrailWriter
for downstream stages 5–8. Fail-closed when audit is not writable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agents_b2g.ethical_boundary.agents import make_response
from agents_b2g.ethical_boundary.audit_constants import AUDIT_PURPOSE_OBSERVATION_AND_DEFENSE
from agents_b2g.ethical_boundary.audit_trail_writer import (
    AuditTrailWriter,
    AuditTrailWriterFactory,
)
from agents_b2g.ethical_boundary.subagents.audit.worm_writer import AuditWriteError
from agents_b2g.ethical_boundary.config import EthicalBoundaryConfig
from agents_b2g.ethical_boundary.logging_utils import JSONLogger, _safe_call
from agents_b2g.ethical_boundary.types import (
    ViolationRecord,
    ViolationSeverity,
    ViolationType,
)


@dataclass(frozen=True)
class AuditTrailResult:
    violations: tuple[ViolationRecord, ...]
    writer: AuditTrailWriter | None
    entries_written: int


class AuditTrailAgent:
    """Stage 4 — GoBD audit trail + writer injection for stages 5–8."""

    agent_name = "AuditTrailAgent"

    def __init__(self, user_id: str = "wave39", config: EthicalBoundaryConfig | None = None):
        self.user_id = user_id
        self.config = config or EthicalBoundaryConfig.load()
        self.logger = JSONLogger(self.agent_name, user_id)
        self._factory = AuditTrailWriterFactory(
            data_root=self.config.data_root,
            user_id=user_id,
        )

    def run(
        self,
        payload: Mapping[str, Any],
        job_id: str,
        *,
        completed_stages: tuple[str, ...] = (),
        prior_violation_count: int = 0,
    ) -> dict[str, Any]:
        return _safe_call(
            self.logger,
            self.agent_name,
            self._run_inner,
            payload,
            job_id,
            completed_stages,
            prior_violation_count,
        )

    def begin_audit(
        self,
        payload: Mapping[str, Any],
        *,
        job_id: str,
        completed_stages: tuple[str, ...],
        prior_violation_count: int = 0,
        prereg_hash_keys: tuple[str, ...] = (),
    ) -> AuditTrailResult:
        return self._begin_audit(
            payload,
            job_id=job_id,
            completed_stages=completed_stages,
            prior_violation_count=prior_violation_count,
            prereg_hash_keys=prereg_hash_keys,
        )

    def _run_inner(
        self,
        payload: Mapping[str, Any],
        job_id: str,
        completed_stages: tuple[str, ...],
        prior_violation_count: int,
    ) -> dict[str, Any]:
        result = self._begin_audit(
            payload,
            job_id=job_id,
            completed_stages=completed_stages,
            prior_violation_count=prior_violation_count,
        )
        status = "blocked" if result.violations else "completed"
        return make_response(
            status,  # type: ignore[arg-type]
            job_id,
            artifacts=[
                {
                    "type": "audit_trail_result",
                    "entries_written": result.entries_written,
                    "audit_path": (
                        str(result.writer.audit_path) if result.writer is not None else None
                    ),
                    "purpose": AUDIT_PURPOSE_OBSERVATION_AND_DEFENSE,
                    "violation_count": len(result.violations),
                }
            ],
            logs=[f"entries_written={result.entries_written}"],
        )

    def _begin_audit(
        self,
        payload: Mapping[str, Any],
        *,
        job_id: str,
        completed_stages: tuple[str, ...],
        prior_violation_count: int,
        prereg_hash_keys: tuple[str, ...] = (),
    ) -> AuditTrailResult:
        _ = payload
        try:
            writer = self._factory.open(job_id)
            writer.log_event(
                stage=self.agent_name,
                event="pipeline_audit_start",
                details={
                    "completed_stages": list(completed_stages),
                    "prior_violation_count": prior_violation_count,
                    "prereg_hash_keys": list(prereg_hash_keys),
                },
            )
            for stage_name in completed_stages:
                writer.log_event(
                    stage=stage_name,
                    event="stage_completed",
                    details={"job_id": job_id},
                )
            ok, err = writer.verify_chain()
            if not ok:
                return AuditTrailResult(
                    violations=(
                        ViolationRecord(
                            violation_type=ViolationType.AUDIT_INTEGRITY,
                            severity=ViolationSeverity.critical(),
                            source_agent=self.agent_name,
                            message=f"audit hash chain verification failed: {err}",
                        ),
                    ),
                    writer=None,
                    entries_written=0,
                )
            return AuditTrailResult(
                violations=(),
                writer=writer,
                entries_written=writer.entries_written,
            )
        except (AuditWriteError, OSError) as exc:
            return AuditTrailResult(
                violations=(
                    ViolationRecord(
                        violation_type=ViolationType.PIPELINE_FAULT,
                        severity=ViolationSeverity.critical(),
                        source_agent=self.agent_name,
                        message=f"audit trail not writable: {exc}",
                        evidence={"job_id": job_id},
                    ),
                ),
                writer=None,
                entries_written=0,
            )
        except Exception as exc:
            return AuditTrailResult(
                violations=(
                    ViolationRecord(
                        violation_type=ViolationType.PIPELINE_FAULT,
                        severity=ViolationSeverity.critical(),
                        source_agent=self.agent_name,
                        message=f"AuditTrailAgent fault: {exc}",
                    ),
                ),
                writer=None,
                entries_written=0,
            )
