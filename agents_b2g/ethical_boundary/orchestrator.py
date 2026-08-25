"""Agent 9 — EthicalBoundaryOrchestrator (Wave 39 root).

All eight enforcement agents implemented — Vierfach-Sperre complete.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from agents_b2g.ethical_boundary.agents import make_response
from agents_b2g.diagnostic.types import BlockCause
from agents_b2g.ethical_boundary.config import (
    EthicalBoundaryConfig,
    EthicalBoundaryConfigError,
)
from agents_b2g.ethical_boundary.defensive_scope_certifier import DefensiveScopeCertifier
from agents_b2g.ethical_boundary.boundary_violation_reporter import BoundaryViolationReporter
from agents_b2g.ethical_boundary.audit_trail_agent import AuditTrailAgent
from agents_b2g.ethical_boundary.audit_trail_writer import AuditTrailWriter
from agents_b2g.ethical_boundary.charter_enforcer_agent import CharterEnforcerAgent
from agents_b2g.ethical_boundary.ethical_assertion_agent import EthicalAssertionAgent
from agents_b2g.ethical_boundary.logging_utils import JSONLogger, _safe_call
from agents_b2g.ethical_boundary.integrity_violation_detector import IntegrityViolationDetector
from agents_b2g.ethical_boundary.prereg_firewall_agent import PreRegFirewallAgent
from agents_b2g.ethical_boundary.subagents.certifier.types import CertificationContext
from agents_b2g.ethical_boundary.scope_enforcer_agent import ScopeEnforcerAgent
from agents_b2g.ethical_boundary.types import (
    EthicalBoundaryEnvelope,
    EthicalBoundaryException,
    EthicalVerdict,
    ViolationObservation,
    ViolationRecord,
    ViolationSeverity,
    ViolationType,
    attach_scope_flag,
    blocked_envelope,
    certified_envelope,
    merge_violations,
    should_block,
    validate_ethical_envelope,
    violations_to_observations,
)


class EthicalBoundaryOrchestrator:
    """Root orchestrator — coordinates agents 1–8, emits EthicalBoundaryEnvelope."""

    agent_name = "EthicalBoundaryOrchestrator"

    def __init__(self, user_id: str = "wave39", config: EthicalBoundaryConfig | None = None):
        self.user_id = user_id
        self.config = config or EthicalBoundaryConfig.load()
        self.logger = JSONLogger(self.agent_name, user_id)
        self._charter_version = self._read_charter_version(self.config.charter_path)
        self.scope_enforcer = ScopeEnforcerAgent(user_id)
        self.ethical_assertion = EthicalAssertionAgent(user_id)
        self.prereg_firewall = PreRegFirewallAgent(user_id, config=self.config)
        self.audit_trail = AuditTrailAgent(user_id, config=self.config)
        self.charter_enforcer = CharterEnforcerAgent(user_id, config=self.config)
        self.integrity_detector = IntegrityViolationDetector(user_id, config=self.config)
        self.violation_reporter = BoundaryViolationReporter(user_id, config=self.config)
        self.scope_certifier = DefensiveScopeCertifier(user_id, config=self.config)
        self._validated_prereg_hashes: dict[str, str] = {}
        self._prereg_stage_passed = False
        self._charter_stage_passed = False
        self._audit_writer: AuditTrailWriter | None = None
        self._wave28_observations: tuple[ViolationObservation, ...] = ()

    @staticmethod
    def _read_charter_version(charter_path: Path) -> str:
        text = charter_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("**Version:**"):
                return line.split(":", 1)[1].strip().split()[0]
        return "1.0"

    def enforce(
        self,
        payload: Mapping[str, Any],
        *,
        job_id: str,
        wave38_gate_context: Mapping[str, Any] | None = None,
    ) -> EthicalBoundaryEnvelope:
        """Run ethical boundary pipeline — fail-closed default."""
        return self._enforce_inner(payload, job_id=job_id, wave38_gate_context=wave38_gate_context)

    def run(
        self,
        payload: Mapping[str, Any],
        job_id: str,
        *,
        wave38_gate_context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Standard agent envelope wrapper around enforce()."""
        return _safe_call(
            self.logger,
            self.agent_name,
            self._run_envelope,
            payload,
            job_id,
            wave38_gate_context,
        )

    def _run_envelope(
        self,
        payload: Mapping[str, Any],
        job_id: str,
        wave38_gate_context: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        envelope = self.enforce(
            payload,
            job_id=job_id,
            wave38_gate_context=wave38_gate_context,
        )
        violations = validate_ethical_envelope(envelope)
        if violations:
            scope = envelope.scope
            blocked = blocked_envelope(
                job_id=job_id,
                scope=scope,
                violations=(
                    ViolationRecord(
                        violation_type=ViolationType.PIPELINE_FAULT,
                        severity=ViolationSeverity.critical(),
                        source_agent=self.agent_name,
                        message="; ".join(violations),
                    ),
                ),
                charter_version=self._charter_version,
            )
            envelope = blocked
        status = "blocked" if envelope.status == EthicalVerdict.BLOCKED else "completed"
        return make_response(
            status,  # type: ignore[arg-type]
            job_id,
            artifacts=[
                {
                    "type": "ethical_boundary_envelope",
                    "format": "json",
                    "metadata": envelope.to_dict(),
                }
            ],
            logs=[f"ethical_status={envelope.status.value}"],
        )

    def _enforce_inner(
        self,
        payload: Mapping[str, Any],
        *,
        job_id: str,
        wave38_gate_context: Mapping[str, Any] | None,
    ) -> EthicalBoundaryEnvelope:
        _ = wave38_gate_context
        scope = attach_scope_flag({}, attached_by=self.agent_name)
        violations: list[ViolationRecord] = []

        try:
            self._audit_writer = None
            self._wave28_observations = ()
            self._prereg_stage_passed = False
            self._charter_stage_passed = False
            prereg_result = self.prereg_firewall.enforce(payload, job_id=job_id)
            violations.extend(prereg_result.violations)
            self._validated_prereg_hashes = dict(prereg_result.validated_hashes)
            self._prereg_stage_passed = not prereg_result.violations

            scope_result = self.scope_enforcer.enforce(payload, job_id=job_id)
            scope = scope_result.scope
            scoped_payload = scope_result.scoped_payload
            violations.extend(scope_result.violations)
            if self._should_block_now(violations, scope, job_id):
                return self._blocked(scope, job_id, violations)

            assertion_result = self.ethical_assertion.assert_non_extraction(
                scoped_payload,
                scope=scope,
            )
            violations.extend(assertion_result.violations)

            if self._should_block_now(violations, scope, job_id):
                return self._blocked(scope, job_id, violations)

            audit_result = self.audit_trail.begin_audit(
                scoped_payload,
                job_id=job_id,
                completed_stages=(
                    "PreRegFirewallAgent",
                    "ScopeEnforcerAgent",
                    "EthicalAssertionAgent",
                ),
                prior_violation_count=len(violations),
                prereg_hash_keys=tuple(sorted(self._validated_prereg_hashes.keys())),
            )
            violations.extend(audit_result.violations)
            self._audit_writer = audit_result.writer
            if self._should_block_now(violations, scope, job_id):
                return self._blocked(scope, job_id, violations)

            charter_result = self.charter_enforcer.enforce(
                scoped_payload,
                job_id=job_id,
                audit_writer=self._audit_writer,
                expected_charter_version=self._charter_version,
            )
            violations.extend(charter_result.violations)
            self._charter_stage_passed = not charter_result.violations
            if self._should_block_now(violations, scope, job_id):
                return self._blocked(scope, job_id, violations)

            integrity_result = self.integrity_detector.enforce(
                scoped_payload,
                job_id=job_id,
                audit_writer=self._audit_writer,
            )
            violations.extend(integrity_result.violations)
            if self._should_block_now(violations, scope, job_id):
                return self._blocked(scope, job_id, violations)

            report_result = self.violation_reporter.enforce(
                merge_violations(tuple(violations)),
                job_id=job_id,
                audit_writer=self._audit_writer,
            )
            violations.extend(report_result.violations)
            self._wave28_observations = report_result.report.wave28_observations
            if self._should_block_now(violations, scope, job_id):
                return self._blocked(scope, job_id, violations)

            merged = merge_violations(tuple(violations))
            if should_block(merged):
                return self._blocked(scope, job_id, violations)

            cert_context = CertificationContext(
                prior_violations=merged,
                prereg_validated_hashes=self._prereg_hashes(),
                charter_version=self._charter_version,
                prereg_stage_passed=self._prereg_stage_passed,
                charter_stage_passed=self._charter_stage_passed,
                completed_stages=(
                    "PreRegFirewallAgent",
                    "ScopeEnforcerAgent",
                    "EthicalAssertionAgent",
                    "AuditTrailAgent",
                    "CharterEnforcerAgent",
                    "IntegrityViolationDetector",
                    "BoundaryViolationReporter",
                ),
            )
            cert_result = self.scope_certifier.certify(
                scoped_payload,
                scope=scope,
                job_id=job_id,
                context=cert_context,
                audit_writer=self._audit_writer,
            )
            if cert_result.violations:
                merged = merge_violations(merged, cert_result.violations)
                return self._blocked(scope, job_id, list(merged))

            if not cert_result.certificate_id:
                return self._blocked(
                    scope,
                    job_id,
                    list(
                        merge_violations(
                            merged,
                            (
                                ViolationRecord(
                                    violation_type=ViolationType.PIPELINE_FAULT,
                                    severity=ViolationSeverity.critical(),
                                    source_agent=self.agent_name,
                                    message="CERTIFIED path missing certificate_id",
                                ),
                            ),
                        )
                    ),
                )

            envelope = certified_envelope(
                job_id=job_id,
                scope=scope,
                charter_version=self._charter_version,
                prereg_hashes=self._prereg_hashes(),
                certificate_id=cert_result.certificate_id,
            )
            return envelope

        except EthicalBoundaryConfigError as exc:
            return blocked_envelope(
                job_id=job_id,
                scope=scope,
                violations=(
                    ViolationRecord(
                        violation_type=ViolationType.CONFIG_INTEGRITY,
                        severity=ViolationSeverity.critical(),
                        source_agent=self.agent_name,
                        message=str(exc),
                    ),
                ),
                charter_version=self._charter_version,
            )
        except EthicalBoundaryException as exc:
            return blocked_envelope(
                job_id=job_id,
                scope=scope,
                violations=(exc.to_violation_record(),),
                charter_version=self._charter_version,
            )
        except Exception as exc:
            return blocked_envelope(
                job_id=job_id,
                scope=scope,
                violations=(
                    ViolationRecord(
                        violation_type=ViolationType.PIPELINE_FAULT,
                        severity=ViolationSeverity.critical(),
                        source_agent=self.agent_name,
                        message=f"unexpected pipeline fault: {exc}",
                    ),
                ),
                charter_version=self._charter_version,
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _should_block_now(
        self,
        violations: list[ViolationRecord],
        scope: Any,
        job_id: str,
    ) -> bool:
        _ = scope, job_id
        return should_block(merge_violations(tuple(violations)))

    def _blocked(
        self,
        scope: Any,
        job_id: str,
        violations: list[ViolationRecord],
    ) -> EthicalBoundaryEnvelope:
        merged = merge_violations(tuple(violations))
        observations = (
            self._wave28_observations
            if self._wave28_observations
            else violations_to_observations(merged)
        )
        return EthicalBoundaryEnvelope(
            status=EthicalVerdict.BLOCKED,
            job_id=job_id,
            scope=scope,
            violations=merged,
            prereg_hashes=self._prereg_hashes(),
            charter_version=self._charter_version,
            certified_at=None,
            block_cause=BlockCause.ETHICAL_BOUNDARY,
            wave28_observations=observations,
        )

    def _log_audit_stage(self, stage: str, event: str, details: Mapping[str, Any] | None = None) -> None:
        if self._audit_writer is None:
            return
        self._audit_writer.log_event(stage=stage, event=event, details=details or {})

    def _prereg_hashes(self) -> dict[str, str]:
        """Return Agent-1-validated WORM hashes — not ad-hoc runtime generation."""
        if self._validated_prereg_hashes:
            return dict(self._validated_prereg_hashes)
        return {}

    def build_wave28_observations(
        self,
        envelope: EthicalBoundaryEnvelope,
    ) -> tuple[dict[str, Any], ...]:
        """Deskriptive-only observations for Wave 28 — no action fields."""
        return tuple(o.to_dict() for o in violations_to_observations(envelope.violations))
