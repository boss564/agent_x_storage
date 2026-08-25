"""W39-A8-S1 — verify DEFENSIVE_CAUSAL_GROUNDING scope flag integrity."""

from __future__ import annotations

from typing import Any, Mapping

from agents_b2g.ethical_boundary.types import (
    ScopeFlag,
    SCOPE_DEFENSIVE,
    ViolationRecord,
    ViolationSeverity,
    ViolationType,
    validate_scope_immutable,
)


class ScopeFlagCertifier:
    subagent_id = "W39-A8-S1"

    def certify(
        self,
        payload: Mapping[str, Any],
        *,
        scope: ScopeFlag,
    ) -> tuple[ViolationRecord, ...]:
        violations: list[ViolationRecord] = []

        if payload.get("scope") != SCOPE_DEFENSIVE:
            violations.append(
                ViolationRecord(
                    violation_type=ViolationType.SCOPE_TAMPER,
                    severity=ViolationSeverity.critical(),
                    source_agent="DefensiveScopeCertifier",
                    message="certification failed: defensive scope flag missing or wrong",
                    evidence={
                        "expected_scope": SCOPE_DEFENSIVE,
                        "actual_scope": payload.get("scope"),
                        "certifier": self.subagent_id,
                    },
                )
            )

        tamper = validate_scope_immutable(payload, scope)
        if tamper is not None:
            violations.append(tamper)

        return tuple(violations)
