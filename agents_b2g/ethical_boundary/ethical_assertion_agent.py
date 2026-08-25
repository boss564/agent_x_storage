"""Agent 2 — EthicalAssertionAgent (Wave 39).

Consumes ScopeFlag from Agent 3 — does not attach or re-validate scope logic duplicatively.
Runs NonExtractionAssertion against receiver metadata under established scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agents_b2g.ethical_boundary.agents import make_response
from agents_b2g.ethical_boundary.config import (
    EthicalBoundaryConfig,
    OFFENSIVE_MARKER_REGISTRY,
)
from agents_b2g.ethical_boundary.logging_utils import JSONLogger, _safe_call
from agents_b2g.ethical_boundary.types import (
    NonExtractionAssertion,
    ScopeFlag,
    SCOPE_DEFENSIVE,
    ViolationRecord,
    ViolationSeverity,
    ViolationType,
    check_non_extraction,
)


@dataclass(frozen=True)
class EthicalAssertionResult:
    violations: tuple[ViolationRecord, ...]
    assertion_ran: bool


class EthicalAssertionAgent:
    """Stage 2 — NonExtractionAssertion (requires Agent 3 scope)."""

    agent_name = "EthicalAssertionAgent"

    def __init__(self, user_id: str = "wave39"):
        self.user_id = user_id
        self.logger = JSONLogger(self.agent_name, user_id)
        self.config = EthicalBoundaryConfig.load()

    def run(
        self,
        scoped_payload: Mapping[str, Any],
        job_id: str,
        *,
        scope: ScopeFlag,
    ) -> dict[str, Any]:
        return _safe_call(
            self.logger,
            self.agent_name,
            self._run_inner,
            scoped_payload,
            job_id,
            scope,
        )

    def assert_non_extraction(
        self,
        scoped_payload: Mapping[str, Any],
        *,
        scope: ScopeFlag,
    ) -> EthicalAssertionResult:
        """Direct API — scope must come from ScopeEnforcerAgent."""
        return self._assert(scoped_payload, scope=scope)

    def _run_inner(
        self,
        scoped_payload: Mapping[str, Any],
        job_id: str,
        scope: ScopeFlag,
    ) -> dict[str, Any]:
        result = self._assert(scoped_payload, scope=scope)
        status = "blocked" if result.violations else "completed"
        return make_response(
            status,  # type: ignore[arg-type]
            job_id,
            artifacts=[
                {
                    "type": "ethical_assertion_result",
                    "assertion_ran": result.assertion_ran,
                    "violation_count": len(result.violations),
                    "marker_registry_version": OFFENSIVE_MARKER_REGISTRY.version,
                }
            ],
            logs=[
                f"assertion_ran={result.assertion_ran}",
                f"violations={len(result.violations)}",
            ],
        )

    def _assert(
        self,
        scoped_payload: Mapping[str, Any],
        *,
        scope: ScopeFlag,
    ) -> EthicalAssertionResult:
        violations: list[ViolationRecord] = []

        if scope.scope != SCOPE_DEFENSIVE:
            violations.append(
                ViolationRecord(
                    violation_type=ViolationType.ASSERTION_FAILURE,
                    severity=ViolationSeverity.critical(),
                    source_agent=self.agent_name,
                    message="assertion refused: scope is not DEFENSIVE_CAUSAL_GROUNDING",
                    evidence={"scope": scope.to_dict()},
                )
            )
            return EthicalAssertionResult(violations=tuple(violations), assertion_ran=False)

        if scoped_payload.get("scope") != SCOPE_DEFENSIVE:
            violations.append(
                ViolationRecord(
                    violation_type=ViolationType.SCOPE_TAMPER,
                    severity=ViolationSeverity.critical(),
                    source_agent=self.agent_name,
                    message="scoped payload missing defensive scope from Agent 3",
                )
            )
            return EthicalAssertionResult(violations=tuple(violations), assertion_ran=False)

        meta = scoped_payload.get("receiver_metadata") or scoped_payload.get("metadata")
        if not meta:
            return EthicalAssertionResult(violations=(), assertion_ran=False)

        assertion = NonExtractionAssertion(
            receiver_id=str(meta.get("receiver_id", "unknown")),
            allowed_purposes=tuple(
                str(p) for p in (meta.get("allowed_purposes") or ("RISK_MANAGEMENT",))
            ),
            metadata=meta,
        )
        hit = check_non_extraction(assertion)
        if hit:
            violations.append(hit)

        exec_calls = scoped_payload.get("execution_calls") or []
        for call in exec_calls:
            purpose = str(call.get("purpose", "")).upper()
            if purpose in OFFENSIVE_MARKER_REGISTRY.markers:
                violations.append(
                    ViolationRecord(
                        violation_type=ViolationType.OFFENSIVE_EXECUTION,
                        severity=ViolationSeverity.critical(),
                        source_agent=self.agent_name,
                        message=f"offensive execution purpose in assertion path: {purpose}",
                        evidence={
                            **dict(call),
                            "charter_ref": OFFENSIVE_MARKER_REGISTRY.charter_refs.get(
                                purpose, "§1.0.E"
                            ),
                        },
                    )
                )

        return EthicalAssertionResult(
            violations=tuple(violations),
            assertion_ran=True,
        )
