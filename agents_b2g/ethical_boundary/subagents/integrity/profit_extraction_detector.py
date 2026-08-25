"""W39-A5-S2 — detect profit extraction via output execution routes."""

from __future__ import annotations

from typing import Any, Mapping

from agents_b2g.ethical_boundary.config import OFFENSIVE_MARKER_REGISTRY
from agents_b2g.ethical_boundary.subagents.integrity.types import (
    ExecutionCallRecord,
    IntegrityDetectionHit,
)
from agents_b2g.ethical_boundary.types import ViolationType

_PROFIT_MARKERS = frozenset(
    {
        "PROFIT_EXTRACTION",
        "MEV_EXTRACTION",
        "GAIN_ROUTING",
    }
)


class ProfitExtractionDetector:
    subagent_id = "W39-A5-S2"

    def detect(
        self,
        payload: Mapping[str, Any],
        calls: tuple[ExecutionCallRecord, ...],
    ) -> tuple[IntegrityDetectionHit, ...]:
        hits: list[IntegrityDetectionHit] = []

        if payload.get("uses_causal_signal_for_profit") is True:
            hits.append(
                IntegrityDetectionHit(
                    marker="PROFIT_EXTRACTION",
                    detector_id=self.subagent_id,
                    message="causal signal routed for profit extraction",
                    violation_type=ViolationType.PROFIT_EXTRACTION,
                    evidence={"charter_ref": OFFENSIVE_MARKER_REGISTRY.charter_refs.get(
                        "PROFIT_EXTRACTION", "§1.0.E(e)"
                    )},
                )
            )

        output_use = payload.get("output_signal_usage")
        if isinstance(output_use, Mapping):
            purpose = str(output_use.get("purpose", "")).upper()
            if purpose in _PROFIT_MARKERS:
                hits.append(
                    IntegrityDetectionHit(
                        marker=purpose,
                        detector_id=self.subagent_id,
                        message=f"output signal usage targets profit: {purpose}",
                        violation_type=ViolationType.PROFIT_EXTRACTION,
                        evidence=dict(output_use),
                    )
                )

        for call in calls:
            if call.purpose in _PROFIT_MARKERS:
                hits.append(
                    IntegrityDetectionHit(
                        marker=call.purpose,
                        detector_id=self.subagent_id,
                        message=(
                            f"profit extraction execution call in {call.source_field}"
                            f"[{call.index}]: {call.purpose}"
                        ),
                        violation_type=ViolationType.PROFIT_EXTRACTION,
                        evidence={
                            **dict(call.raw),
                            "source_field": call.source_field,
                            "charter_ref": OFFENSIVE_MARKER_REGISTRY.charter_refs.get(
                                call.purpose, "§1.0.E(e)"
                            ),
                        },
                    )
                )

        return tuple(hits)
