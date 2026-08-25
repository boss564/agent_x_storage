"""W39-A6-S1 — validate air-gap to profit systems (Charter §5)."""

from __future__ import annotations

from typing import Any, Mapping

from agents_b2g.ethical_boundary.config import CHARTER_PROFIT_SYSTEM_MARKERS
from agents_b2g.ethical_boundary.types import (
    ViolationRecord,
    ViolationSeverity,
    ViolationType,
)


class AirGapValidator:
    subagent_id = "W39-A6-S1"

    def validate(self, payload: Mapping[str, Any]) -> ViolationRecord | None:
        targets = payload.get("execution_targets") or payload.get("routing_targets") or []
        if isinstance(targets, str):
            targets = [targets]
        for target in targets:
            token = str(target).lower()
            for marker in CHARTER_PROFIT_SYSTEM_MARKERS:
                if marker in token:
                    return ViolationRecord(
                        violation_type=ViolationType.CHARTER_AIRGAP,
                        severity=ViolationSeverity.critical(),
                        source_agent="CharterEnforcerAgent",
                        message=f"charter air-gap violation: profit system reference {target!r}",
                        evidence={"target": str(target), "marker": marker},
                    )
        return None
