"""W39-A5-S4 — detect offensive liquidations (not defensive risk analysis)."""

from __future__ import annotations

from typing import Any, Mapping

from agents_b2g.ethical_boundary.config import OFFENSIVE_MARKER_REGISTRY
from agents_b2g.ethical_boundary.subagents.integrity.types import (
    ExecutionCallRecord,
    IntegrityDetectionHit,
)
from agents_b2g.ethical_boundary.types import ViolationType


class OffensiveLiquidationDetector:
    subagent_id = "W39-A5-S4"

    def detect(
        self,
        payload: Mapping[str, Any],
        calls: tuple[ExecutionCallRecord, ...],
    ) -> tuple[IntegrityDetectionHit, ...]:
        hits: list[IntegrityDetectionHit] = []

        mode = str(payload.get("liquidation_mode", "")).lower()
        if mode == "offensive":
            hits.append(
                IntegrityDetectionHit(
                    marker="OFFENSIVE_LIQUIDATION",
                    detector_id=self.subagent_id,
                    message="payload declares offensive liquidation mode",
                    violation_type=ViolationType.OFFENSIVE_EXECUTION,
                    evidence={"liquidation_mode": mode},
                )
            )

        for call in calls:
            if call.purpose == "OFFENSIVE_LIQUIDATION":
                hits.append(
                    IntegrityDetectionHit(
                        marker=call.purpose,
                        detector_id=self.subagent_id,
                        message=(
                            f"offensive liquidation call in {call.source_field}"
                            f"[{call.index}]"
                        ),
                        violation_type=ViolationType.OFFENSIVE_EXECUTION,
                        evidence={
                            **dict(call.raw),
                            "source_field": call.source_field,
                            "charter_ref": OFFENSIVE_MARKER_REGISTRY.charter_refs.get(
                                call.purpose, "§1.0.E(d)"
                            ),
                        },
                    )
                )

        return tuple(hits)
