"""W39-A6-S2 — name and identity inheritance checks (Charter §6)."""

from __future__ import annotations

from typing import Any, Mapping

from agents_b2g.ethical_boundary.types import (
    ViolationRecord,
    ViolationSeverity,
    ViolationType,
)

AGENT_X_NAME_TOKENS: tuple[str, ...] = ("agent x", "agent-x", "agent_x")

NAME_SURFACE_FIELDS: tuple[str, ...] = (
    "product_name",
    "brand",
    "system_name",
    "display_name",
)


class NameInheritanceChecker:
    subagent_id = "W39-A6-S2"

    def check(self, payload: Mapping[str, Any]) -> tuple[ViolationRecord, ...]:
        violations: list[ViolationRecord] = []

        if payload.get("claims_agent_x_identity") is True and not payload.get(
            "charter_acknowledged"
        ):
            violations.append(
                ViolationRecord(
                    violation_type=ViolationType.CHARTER_AIRGAP,
                    severity=ViolationSeverity.critical(),
                    source_agent=self.subagent_id,
                    message="name inheritance: Agent X identity claimed without charter acknowledgment",
                    evidence={"charter_ref": "§6"},
                )
            )

        if payload.get("uses_prereg_seal") is True and not payload.get("charter_acknowledged"):
            violations.append(
                ViolationRecord(
                    violation_type=ViolationType.CHARTER_AIRGAP,
                    severity=ViolationSeverity.critical(),
                    source_agent=self.subagent_id,
                    message="pre-reg seal use without charter acknowledgment",
                    evidence={"charter_ref": "§6"},
                )
            )

        for field in NAME_SURFACE_FIELDS:
            value = payload.get(field)
            if not value:
                continue
            lowered = str(value).lower()
            if any(token in lowered for token in AGENT_X_NAME_TOKENS):
                if payload.get("defensive_only") is not True:
                    violations.append(
                        ViolationRecord(
                            violation_type=ViolationType.CHARTER_AIRGAP,
                            severity=ViolationSeverity.critical(),
                            source_agent=self.subagent_id,
                            message=f"name inheritance: offensive Agent X reference in {field}",
                            evidence={"field": field, "value": str(value), "charter_ref": "§6"},
                        )
                    )

        return tuple(violations)
