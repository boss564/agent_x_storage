"""Shared certification context — references upstream agent outcomes, no re-validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from agents_b2g.ethical_boundary.types import ViolationRecord


@dataclass(frozen=True)
class CertificationContext:
    """Upstream stage outcomes referenced by Agent 8 — not re-run."""

    prior_violations: tuple[ViolationRecord, ...]
    prereg_validated_hashes: Mapping[str, str]
    charter_version: str
    prereg_stage_passed: bool
    charter_stage_passed: bool
    completed_stages: tuple[str, ...] = field(default_factory=tuple)
