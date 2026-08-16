"""IncidentCoordinator: victim-detection -> dispatch -> resupply loop.

Civilian analog of a fire-direction loop, but for rescue:
damage reports come in, the command element allocates rescue tasks,
response units execute, logistics resupplies. No unit can close the loop alone.
"""
from __future__ import annotations

from typing import Any, Dict, List

from agents_b2g.rescue.unit_base import RescueUnit, UnitState


class IncidentCoordinator:
    """Routes by capability with class separation (Gewaltenteilung).

    Class A detects, class B responds, class C commands/resupplies.
    Routing is deterministic (crc32 tie-break) to keep runs reproducible.
    """

    def __init__(self) -> None:
        self.units: Dict[str, RescueUnit] = {}
        self.victims: List[Dict[str, Any]] = []
        self.assignments: List[Dict[str, Any]] = []
        self.detected = 0
        self.assigned = 0
        self.served = 0

    def add_unit(self, unit: RescueUnit) -> None:
        self.units[unit.unit_id] = unit

    def units_by_capability(self, capability: str) -> List[RescueUnit]:
        out = [u for u in self.units.values()
               if u.capability == capability and u.state == UnitState.OPERATIONAL]
        # deterministic tie-break: highest power first, then crc32 of unit_id
        import zlib
        out.sort(key=lambda u: (-u.power, zlib.crc32(u.unit_id.encode())))
        return out

    def report_damage(self, area_id: str, severity: str, victims: int, t: float) -> Dict[str, Any]:
        """A detection (class A) reports a damage area with victims."""
        rec = {"area_id": area_id, "severity": severity, "victims": victims,
               "t": t, "status": "detected"}
        self.victims.append(rec)
        self.detected += victims
        return rec

    def allocate(self, area: Dict[str, Any]) -> Dict[str, Any]:
        """Command element (class C) allocates a rescue unit (class B)."""
        rescuers = self.units_by_capability("victim_rescue")
        if not rescuers:
            return {"status": "no_rescuer_available", "area": area["area_id"]}
        unit = rescuers[0]
        if not unit.consume_supplies(unit.supply_drain_per_action):
            return {"status": "rescuer_low_supplies", "area": area["area_id"]}
        area["status"] = "assigned"
        self.assigned += area["victims"]
        assignment = {"area": area["area_id"], "unit": unit.unit_id,
                      "victims": area["victims"]}
        self.assignments.append(assignment)
        return {"status": "dispatched", **assignment}

    def serve(self, assignment: Dict[str, Any]) -> Dict[str, Any]:
        """Response unit (class B) completes the rescue -> served."""
        self.served += assignment["victims"]
        return {"status": "served", **assignment}

    def conservation_check(self) -> Dict[str, Any]:
        """Conservation invariant: detected = assigned + pending; served <= assigned."""
        pending = self.detected - self.assigned
        ok = (self.served <= self.assigned <= self.detected) and pending >= 0
        return {
            "detected": self.detected,
            "assigned": self.assigned,
            "served": self.served,
            "pending": pending,
            "conserved": ok,
        }
