"""W39-A8-S2 — certify output-side fields remain defensive."""

from __future__ import annotations

from typing import Any, Mapping

from agents_b2g.ethical_boundary.config import OFFENSIVE_MARKER_REGISTRY
from agents_b2g.ethical_boundary.types import ViolationRecord, ViolationSeverity, ViolationType

_OUTPUT_FIELDS: tuple[str, ...] = (
    "execution_calls",
    "output_execution_calls",
    "audit_execution_calls",
    "routed_outputs",
)


class OutputCertifier:
    subagent_id = "W39-A8-S2"

    def certify(self, payload: Mapping[str, Any]) -> tuple[ViolationRecord, ...]:
        violations: list[ViolationRecord] = []

        if payload.get("uses_causal_signal_for_profit") is True:
            violations.append(self._hit("uses_causal_signal_for_profit"))

        if payload.get("sandwich_bundle") is True:
            violations.append(self._hit("sandwich_bundle"))

        mode = str(payload.get("liquidation_mode", "")).lower()
        if mode == "offensive":
            violations.append(self._hit("liquidation_mode=offensive"))

        output_use = payload.get("output_signal_usage")
        if isinstance(output_use, Mapping):
            purpose = str(output_use.get("purpose", "")).upper()
            if purpose in OFFENSIVE_MARKER_REGISTRY.markers:
                violations.append(
                    ViolationRecord(
                        violation_type=ViolationType.ASSERTION_FAILURE,
                        severity=ViolationSeverity.critical(),
                        source_agent="DefensiveScopeCertifier",
                        message=f"certification failed: offensive output signal usage ({purpose})",
                        evidence={"purpose": purpose, "certifier": self.subagent_id},
                    )
                )

        for field in _OUTPUT_FIELDS:
            raw_items = payload.get(field)
            if raw_items is None:
                continue
            if isinstance(raw_items, Mapping):
                raw_items = [raw_items]
            if not isinstance(raw_items, (list, tuple)):
                continue
            for index, item in enumerate(raw_items):
                if not isinstance(item, Mapping):
                    continue
                purpose = str(item.get("purpose") or item.get("action") or "").upper()
                if purpose in OFFENSIVE_MARKER_REGISTRY.markers:
                    violations.append(
                        ViolationRecord(
                            violation_type=ViolationType.ASSERTION_FAILURE,
                            severity=ViolationSeverity.critical(),
                            source_agent="DefensiveScopeCertifier",
                            message=(
                                f"certification failed: offensive output in {field}[{index}]"
                                f" ({purpose})"
                            ),
                            evidence={
                                "field": field,
                                "index": index,
                                "purpose": purpose,
                                "certifier": self.subagent_id,
                            },
                        )
                    )

        return tuple(violations)

    def _hit(self, detail: str) -> ViolationRecord:
        return ViolationRecord(
            violation_type=ViolationType.ASSERTION_FAILURE,
            severity=ViolationSeverity.critical(),
            source_agent="DefensiveScopeCertifier",
            message=f"certification failed: non-defensive output ({detail})",
            evidence={"detail": detail, "certifier": self.subagent_id},
        )
