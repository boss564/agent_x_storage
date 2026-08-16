"""Einsatzregeln / infrastructure clearance gate for the rescue swarm.

Civilian analog of Rules of Engagement: a Search-and-Rescue unit (class B)
may NOT enter a structurally unsafe area until class C (incident command)
issues an infrastructure clearance, informed by an independent structural
assessment (class B infra_repair).

Gewaltenteilung enforced:
- The responder (B) cannot self-authorize entry.
- Only the command element (C) can issue clearance.
- Clearance requires a structural assessment; unstable areas are denied.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict


class HazardLevel(str, Enum):
    SAFE = "safe"
    UNSAFE = "unsafe"


class ClearanceStatus(str, Enum):
    CLEAR = "clear"
    BLOCKED = "blocked"
    ASSESSING = "assessing"


class ClearanceGate:
    def __init__(self) -> None:
        self.hazard: Dict[str, HazardLevel] = {}
        self.status: Dict[str, ClearanceStatus] = {}
        self.assessments: Dict[str, Dict[str, Any]] = {}
        self.clearance_log = []

    def register_area(self, area_id: str, hazard: HazardLevel) -> None:
        self.hazard[area_id] = hazard
        self.status[area_id] = (ClearanceStatus.BLOCKED
                                if hazard == HazardLevel.UNSAFE
                                else ClearanceStatus.CLEAR)

    def is_cleared(self, area_id: str) -> bool:
        return self.status.get(area_id, ClearanceStatus.CLEAR) == ClearanceStatus.CLEAR

    def is_blocked(self, area_id: str) -> bool:
        return self.status.get(area_id) == ClearanceStatus.BLOCKED

    def begin_assessment(self, area_id: str, assessor_id: str) -> None:
        self.status[area_id] = ClearanceStatus.ASSESSING
        self.assessments.setdefault(area_id, {})["assessor"] = assessor_id

    def record_assessment(self, area_id: str, stable: bool) -> None:
        self.assessments.setdefault(area_id, {})["result"] = "stable" if stable else "unstable"

    def assessment_result(self, area_id: str):
        return self.assessments.get(area_id, {}).get("result")

    def issue_clearance(self, area_id: str, issuer_id: str, issuer_class: str) -> bool:
        """Only class C may issue clearance; unstable areas are denied."""
        if issuer_class != "C":
            return False
        if self.assessment_result(area_id) == "unstable":
            return False
        self.status[area_id] = ClearanceStatus.CLEAR
        self.clearance_log.append({"area": area_id, "issuer": issuer_id,
                                   "assessment": self.assessment_result(area_id)})
        return True

    def stats(self) -> Dict[str, int]:
        return {
            "areas": len(self.status),
            "cleared": sum(1 for s in self.status.values() if s == ClearanceStatus.CLEAR),
            "blocked": sum(1 for s in self.status.values() if s == ClearanceStatus.BLOCKED),
            "assessing": sum(1 for s in self.status.values() if s == ClearanceStatus.ASSESSING),
            "clearances_issued": len(self.clearance_log),
        }
