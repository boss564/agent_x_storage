"""Shared reporter contracts — aggregated violation report metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from agents_b2g.ethical_boundary.types import ViolationObservation, ViolationRecord


@dataclass(frozen=True)
class AggregatedViolationReport:
    """Consolidated violation report produced by Agent 7."""

    violations: tuple[ViolationRecord, ...]
    ranked_violations: tuple[ViolationRecord, ...]
    wave28_observations: tuple[ViolationObservation, ...]
    summary: Mapping[str, Any] = field(default_factory=dict)
