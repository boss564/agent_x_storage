"""Agent 6 — CharterEnforcerAgent (Wave 39).

Charter §5 air-gap and §6 identity protection. Extracted from orchestrator inline
check_charter_airgap — orchestrator remains coordinating-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agents_b2g.ethical_boundary.agents import make_response
from agents_b2g.ethical_boundary.audit_trail_writer import AuditTrailWriter
from agents_b2g.ethical_boundary.config import EthicalBoundaryConfig
from agents_b2g.ethical_boundary.logging_utils import JSONLogger, _safe_call
from agents_b2g.ethical_boundary.subagents.charter import (
    AirGapValidator,
    CharterLoader,
    NameInheritanceChecker,
)
from agents_b2g.ethical_boundary.types import (
    ViolationRecord,
    ViolationSeverity,
    ViolationType,
)


@dataclass(frozen=True)
class CharterEnforcerResult:
    violations: tuple[ViolationRecord, ...]
    charter_version: str | None


class CharterEnforcerAgent:
    """Stage 6 — Charter air-gap + identity enforcement with audit trail."""

    agent_name = "CharterEnforcerAgent"

    def __init__(self, user_id: str = "wave39", config: EthicalBoundaryConfig | None = None):
        self.user_id = user_id
        self.config = config or EthicalBoundaryConfig.load()
        self.logger = JSONLogger(self.agent_name, user_id)
        self._air_gap = AirGapValidator()
        self._name_checker = NameInheritanceChecker()
        self._charter_loader = CharterLoader()

    def run(
        self,
        payload: Mapping[str, Any],
        job_id: str,
        *,
        audit_writer: AuditTrailWriter | None = None,
        expected_charter_version: str | None = None,
    ) -> dict[str, Any]:
        return _safe_call(
            self.logger,
            self.agent_name,
            self._run_inner,
            payload,
            job_id,
            audit_writer,
            expected_charter_version,
        )

    def enforce(
        self,
        payload: Mapping[str, Any],
        *,
        job_id: str,
        audit_writer: AuditTrailWriter | None = None,
        expected_charter_version: str | None = None,
    ) -> CharterEnforcerResult:
        return self._enforce(
            payload,
            job_id=job_id,
            audit_writer=audit_writer,
            expected_charter_version=expected_charter_version,
        )

    def _run_inner(
        self,
        payload: Mapping[str, Any],
        job_id: str,
        audit_writer: AuditTrailWriter | None,
        expected_charter_version: str | None,
    ) -> dict[str, Any]:
        result = self._enforce(
            payload,
            job_id=job_id,
            audit_writer=audit_writer,
            expected_charter_version=expected_charter_version,
        )
        status = "blocked" if result.violations else "completed"
        return make_response(
            status,  # type: ignore[arg-type]
            job_id,
            artifacts=[
                {
                    "type": "charter_enforcer_result",
                    "charter_version": result.charter_version,
                    "violation_count": len(result.violations),
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
        expected_charter_version: str | None,
    ) -> CharterEnforcerResult:
        _ = job_id
        violations: list[ViolationRecord] = []
        charter_version: str | None = None

        try:
            self._audit(
                audit_writer,
                event="charter_enforcement_start",
                details={"expected_charter_version": expected_charter_version},
            )

            loader_result = self._charter_loader.load(self.config.charter_path)
            if loader_result.error or loader_result.charter is None:
                violations.append(
                    ViolationRecord(
                        violation_type=ViolationType.CONFIG_INTEGRITY,
                        severity=ViolationSeverity.critical(),
                        source_agent=self._charter_loader.subagent_id,
                        message=loader_result.error or "charter load failed",
                        evidence={"path": str(self.config.charter_path)},
                    )
                )
                self._audit(
                    audit_writer,
                    event="charter_load_failed",
                    details={"error": loader_result.error},
                )
            else:
                charter_version = loader_result.charter.version
                self._audit(
                    audit_writer,
                    event="charter_loaded",
                    details={
                        "version": charter_version,
                        "path": str(loader_result.charter.path),
                    },
                )
                if (
                    expected_charter_version
                    and charter_version != expected_charter_version
                ):
                    violations.append(
                        ViolationRecord(
                            violation_type=ViolationType.CONFIG_INTEGRITY,
                            severity=ViolationSeverity.critical(),
                            source_agent=self._charter_loader.subagent_id,
                            message="charter version mismatch",
                            evidence={
                                "expected": expected_charter_version,
                                "actual": charter_version,
                            },
                        )
                    )

            self._audit(audit_writer, event="air_gap_check_start", details={})
            air_gap_hit = self._air_gap.validate(payload)
            if air_gap_hit:
                violations.append(air_gap_hit)
                self._audit(
                    audit_writer,
                    event="air_gap_violation",
                    details=dict(air_gap_hit.evidence),
                )
            else:
                self._audit(audit_writer, event="air_gap_check_pass", details={})

            self._audit(audit_writer, event="name_inheritance_check_start", details={})
            name_hits = self._name_checker.check(payload)
            if name_hits:
                violations.extend(name_hits)
                self._audit(
                    audit_writer,
                    event="name_inheritance_violation",
                    details={"count": len(name_hits)},
                )
            else:
                self._audit(audit_writer, event="name_inheritance_check_pass", details={})

            if not violations:
                self._audit(audit_writer, event="charter_enforcement_pass", details={})

            return CharterEnforcerResult(
                violations=tuple(violations),
                charter_version=charter_version,
            )

        except Exception as exc:
            self._audit(
                audit_writer,
                event="charter_enforcement_fault",
                details={"error": str(exc)},
            )
            return CharterEnforcerResult(
                violations=(
                    ViolationRecord(
                        violation_type=ViolationType.PIPELINE_FAULT,
                        severity=ViolationSeverity.critical(),
                        source_agent=self.agent_name,
                        message=f"CharterEnforcerAgent fault: {exc}",
                    ),
                ),
                charter_version=charter_version,
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
            stage="CharterEnforcerAgent",
            event=event,
            details=details or {},
        )
