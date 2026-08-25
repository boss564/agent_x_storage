"""W39-A5-S5 — detect sandwich / frontrun / backrun execution bundles."""

from __future__ import annotations

from typing import Any, Mapping

from agents_b2g.ethical_boundary.config import OFFENSIVE_MARKER_REGISTRY
from agents_b2g.ethical_boundary.subagents.integrity.types import (
    ExecutionCallRecord,
    IntegrityDetectionHit,
)
from agents_b2g.ethical_boundary.types import ViolationType

_SANDWICH_MARKERS = frozenset({"SANDWICH_ATTACK", "FRONTRUNNING", "BACKRUNNING"})


class SandwichAttackDetector:
    subagent_id = "W39-A5-S5"

    def detect(
        self,
        payload: Mapping[str, Any],
        calls: tuple[ExecutionCallRecord, ...],
    ) -> tuple[IntegrityDetectionHit, ...]:
        hits: list[IntegrityDetectionHit] = []

        if payload.get("sandwich_bundle") is True:
            hits.append(
                IntegrityDetectionHit(
                    marker="SANDWICH_ATTACK",
                    detector_id=self.subagent_id,
                    message="payload declares sandwich execution bundle",
                    violation_type=ViolationType.OFFENSIVE_EXECUTION,
                    evidence={"sandwich_bundle": True},
                )
            )

        purposes = {call.purpose for call in calls if call.purpose}
        if "SANDWICH_ATTACK" in purposes:
            for call in calls:
                if call.purpose == "SANDWICH_ATTACK":
                    hits.append(
                        IntegrityDetectionHit(
                            marker=call.purpose,
                            detector_id=self.subagent_id,
                            message=(
                                f"sandwich attack call in {call.source_field}[{call.index}]"
                            ),
                            violation_type=ViolationType.OFFENSIVE_EXECUTION,
                            evidence={
                                **dict(call.raw),
                                "source_field": call.source_field,
                                "charter_ref": OFFENSIVE_MARKER_REGISTRY.charter_refs.get(
                                    call.purpose, "§1.0.E(c)"
                                ),
                            },
                        )
                    )

        if {"FRONTRUNNING", "BACKRUNNING"}.issubset(purposes):
            hits.append(
                IntegrityDetectionHit(
                    marker="SANDWICH_ATTACK",
                    detector_id=self.subagent_id,
                    message="frontrunning + backrunning bundle detected",
                    violation_type=ViolationType.OFFENSIVE_EXECUTION,
                    evidence={"purposes": sorted(purposes & _SANDWICH_MARKERS)},
                )
            )

        for call in calls:
            if call.purpose in {"FRONTRUNNING", "BACKRUNNING"} and call.purpose != "SANDWICH_ATTACK":
                if not any(h.marker == call.purpose for h in hits):
                    hits.append(
                        IntegrityDetectionHit(
                            marker=call.purpose,
                            detector_id=self.subagent_id,
                            message=(
                                f"MEV execution call in {call.source_field}[{call.index}]: "
                                f"{call.purpose}"
                            ),
                            violation_type=ViolationType.OFFENSIVE_EXECUTION,
                            evidence={
                                **dict(call.raw),
                                "source_field": call.source_field,
                                "charter_ref": OFFENSIVE_MARKER_REGISTRY.charter_refs.get(
                                    call.purpose, "§1.0.E(b)"
                                ),
                            },
                        )
                    )

        return tuple(hits)
