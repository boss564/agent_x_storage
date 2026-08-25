"""Shared integrity detection hit — scored by ViolationSeverityScorer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from agents_b2g.ethical_boundary.types import ViolationType


@dataclass(frozen=True)
class ExecutionCallRecord:
    """Normalized execution-call view for output-side integrity checks."""

    purpose: str
    raw: Mapping[str, Any]
    source_field: str
    index: int


@dataclass(frozen=True)
class IntegrityDetectionHit:
    marker: str
    detector_id: str
    message: str
    violation_type: ViolationType
    evidence: Mapping[str, Any] = field(default_factory=dict)
    severity_hint: int = 100
