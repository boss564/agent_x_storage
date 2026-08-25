"""Agent 3 — ScopeEnforcerAgent (Wave 39).

Single source of truth for DEFENSIVE_CAUSAL_GROUNDING scope attach + immutability.
Agent 2 (EthicalAssertion) consumes the scope produced here — no duplicate validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agents_b2g.ethical_boundary.agents import make_response
from agents_b2g.ethical_boundary.config import EthicalBoundaryConfig
from agents_b2g.ethical_boundary.logging_utils import JSONLogger, _safe_call
from agents_b2g.ethical_boundary.types import (
    ScopeFlag,
    SCOPE_DEFENSIVE,
    ViolationRecord,
    ViolationSeverity,
    ViolationType,
    attach_scope_flag,
    validate_scope_immutable,
)


@dataclass(frozen=True)
class ScopeEnforcerResult:
    """Output contract for Agent 3 — consumed by Agent 2 and orchestrator."""

    scope: ScopeFlag
    scoped_payload: dict[str, Any]
    violations: tuple[ViolationRecord, ...]


class ScopeEnforcerAgent:
    """Stage 3 — attach, validate, propagate immutable scope flag."""

    agent_name = "ScopeEnforcerAgent"

    def __init__(self, user_id: str = "wave39"):
        self.user_id = user_id
        self.logger = JSONLogger(self.agent_name, user_id)
        self.config = EthicalBoundaryConfig.load()

    def run(
        self,
        payload: Mapping[str, Any],
        job_id: str,
        *,
        ethical_boundary_job_id: str | None = None,
    ) -> dict[str, Any]:
        return _safe_call(
            self.logger,
            self.agent_name,
            self._run_inner,
            payload,
            job_id,
            ethical_boundary_job_id,
        )

    def enforce(
        self,
        payload: Mapping[str, Any],
        *,
        job_id: str,
    ) -> ScopeEnforcerResult:
        """Direct API for orchestrator — returns structured result."""
        return self._enforce(payload, job_id=job_id)

    def _run_inner(
        self,
        payload: Mapping[str, Any],
        job_id: str,
        ethical_boundary_job_id: str | None,
    ) -> dict[str, Any]:
        result = self._enforce(payload, job_id=ethical_boundary_job_id or job_id)
        status = "blocked" if result.violations else "completed"
        return make_response(
            status,  # type: ignore[arg-type]
            job_id,
            artifacts=[
                {
                    "type": "scope_enforcer_result",
                    "scope": result.scope.to_dict(),
                    "scoped_payload_keys": list(result.scoped_payload.keys()),
                    "violation_count": len(result.violations),
                }
            ],
            logs=[f"scope={result.scope.scope}", f"violations={len(result.violations)}"],
        )

    def _enforce(self, payload: Mapping[str, Any], *, job_id: str) -> ScopeEnforcerResult:
        violations: list[ViolationRecord] = []

        if self.config.defensive_scope_mandatory not in ("true", "strict"):
            violations.append(
                ViolationRecord(
                    violation_type=ViolationType.CONFIG_INTEGRITY,
                    severity=ViolationSeverity.critical(),
                    source_agent=self.agent_name,
                    message="DEFENSIVE_SCOPE_MANDATORY invalid",
                )
            )

        scope = self._attach_scope(payload)
        scoped_payload = self._propagate_scope(dict(payload), scope, job_id)

        tamper = self._validate_immutable(scoped_payload, scope)
        if tamper:
            violations.append(tamper)

        injected = self._detect_pre_injection(payload)
        if injected:
            violations.append(injected)

        return ScopeEnforcerResult(
            scope=scope,
            scoped_payload=scoped_payload,
            violations=tuple(violations),
        )

    def _attach_scope(self, payload: Mapping[str, Any]) -> ScopeFlag:
        return attach_scope_flag(payload, attached_by=self.agent_name)

    def _propagate_scope(
        self,
        payload: dict[str, Any],
        scope: ScopeFlag,
        job_id: str,
    ) -> dict[str, Any]:
        payload["scope"] = scope.scope
        payload["ethical_boundary_job_id"] = job_id
        payload["scope_attached_by"] = scope.attached_by
        payload["scope_content_hash"] = scope.content_hash
        return payload

    def _validate_immutable(
        self,
        payload: Mapping[str, Any],
        scope: ScopeFlag,
    ) -> ViolationRecord | None:
        return validate_scope_immutable(payload, scope)

    def _detect_pre_injection(self, payload: Mapping[str, Any]) -> ViolationRecord | None:
        """Reject payloads that already carry a non-defensive scope before attach."""
        pre = payload.get("scope")
        if pre is None:
            return None
        if pre != SCOPE_DEFENSIVE:
            return ViolationRecord(
                violation_type=ViolationType.SCOPE_TAMPER,
                severity=ViolationSeverity.critical(),
                source_agent=self.agent_name,
                message=f"pre-injected scope rejected: {pre!r}",
                evidence={"scope": pre},
            )
        return None
