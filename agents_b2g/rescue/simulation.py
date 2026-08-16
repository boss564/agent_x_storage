"""Full simulation loop for the rescue swarm (civil protection).

Coordination EMERGES from interaction, it is never imposed:
- Units act when their own OODA cycle completes.
- Actionable messages nudge the recipient's OODA phase toward the
  sender's send-phase (pulse coupling). No global clock, no shared field.
- Resource depletion forces real resupply dependencies between classes.
- Scenario damage reports arrive at non-periodic (exponential) intervals,
  deliberately avoiding the fixed-cadence drive that produced the IAAFT
  periodicity artifact documented in docs/WIRTSCHAFTS_SCHWARM_DOSSIER.md.
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional

from agents_b2g.rescue.unit_base import RescueUnit, UnitState
from agents_b2g.rescue.coordinator import IncidentCoordinator
from agents_b2g.rescue.agents import build_rescue_swarm
from agents_b2g.rescue.ooda_evaluator import evaluate_coordination
from agents_b2g.rescue.clearance import ClearanceGate, HazardLevel, ClearanceStatus

TWO_PI = 2.0 * math.pi


def phase_pull(phase: float, target: float, strength: float) -> float:
    """Pull `phase` toward `target` along the shortest arc (Kuramoto-style)."""
    delta = target - phase
    delta = ((delta + math.pi) % TWO_PI) - math.pi   # wrap to [-pi, pi]
    return (phase + strength * delta) % TWO_PI


class ScenarioGenerator:
    """Damage reports at varied, non-periodic intervals."""

    def __init__(self, rng: random.Random, mean_interval_s: float = 25.0,
                 victims_lo: int = 1, victims_hi: int = 6):
        self.rng = rng
        self.mean_interval_s = mean_interval_s
        self.victims_lo = victims_lo
        self.victims_hi = victims_hi
        self._next_at = 0.0
        self._area_seq = 0

    def maybe_report(self, t: float) -> Optional[Dict[str, Any]]:
        if t < self._next_at:
            return None
        # exponential interval -> non-periodic drive
        self._next_at = t + self.rng.expovariate(1.0 / self.mean_interval_s)
        self._area_seq += 1
        severity = self.rng.choice(["minor", "moderate", "severe"])
        if severity == "severe" and self.rng.random() < 0.6:
            hazard = "unsafe"
        elif severity == "moderate" and self.rng.random() < 0.25:
            hazard = "unsafe"
        else:
            hazard = "safe"
        return {
            "area_id": f"area_{self._area_seq:03d}",
            "severity": severity,
            "victims": self.rng.randint(self.victims_lo, self.victims_hi),
            "hazard": hazard,
            "t": t,
        }


class RescueSimulation:
    def __init__(self, seed: int = 42, duration_s: float = 600.0, dt: float = 1.0,
                 coupling: float = 0.30, resupply_threshold: float = 30.0,
                 resupply_amount: float = 60.0, work_cycles: int = 3,
                 enable_clearance: bool = False, assess_stable_p: float = 0.85):
        self.rng = random.Random(seed)
        self.duration_s = duration_s
        self.dt = dt
        self.coupling = coupling
        self.resupply_threshold = resupply_threshold
        self.resupply_amount = resupply_amount
        self.work_cycles = work_cycles
        self.enable_clearance = enable_clearance
        self.clearance_gate = ClearanceGate() if enable_clearance else None
        self.assess_stable_p = assess_stable_p
        self._assessment_queue: List[str] = []

        self.units: Dict[str, RescueUnit] = build_rescue_swarm()
        self.coordinator = IncidentCoordinator()
        for u in self.units.values():
            self.coordinator.add_unit(u)
            u._last_act_cycle = -1                      # OODA-act bookkeeping

        self.scenario = ScenarioGenerator(self.rng)
        self.t = 0.0
        self.transit: List[tuple] = []                  # (deliver_at, msg)
        self.delivered_count = 0
        self.undetected: List[Dict[str, Any]] = []      # reports awaiting detection
        self.active_tasks: Dict[str, Dict[str, Any]] = {}
        self.resupply_requests: set = set()

    # --- main loop ---

    def run(self) -> Dict[str, Any]:
        while self.t < self.duration_s:
            self.step()
        return self.report()

    def step(self) -> None:
        self.t += self.dt
        for u in self.units.values():                   # 1) advance OODA phases
            u.advance_ooda(self.dt, self.t)
        rep = self.scenario.maybe_report(self.t)        # 2) scenario injection
        if rep:
            self.undetected.append(rep)
        self._deliver()                                 # 3) deliver + phase-pull
        for u in self.units.values():                   # 4) act on completed cycles
            if u.cycles_completed > u._last_act_cycle:
                u._last_act_cycle = u.cycles_completed
                self._unit_act(u)

    # --- messaging with emergent coupling ---

    def _send(self, sender: RescueUnit, target_id: str,
              msg_type: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if sender.state != UnitState.OPERATIONAL:
            return None
        msg = sender.send(target_id, msg_type, payload)
        if msg is None:
            return None
        msg["sender_phase"] = sender.ooda_phase          # snapshot for phase-pull
        self.transit.append((self.t + self.dt, msg))     # 1-step propagation delay
        return msg

    def _deliver(self) -> None:
        still: List[tuple] = []
        for deliver_at, msg in self.transit:
            if self.t < deliver_at:
                still.append((deliver_at, msg))
                continue
            target = self.units.get(msg["target"])
            if target is None or target.state == UnitState.OUT_OF_SERVICE:
                continue                                  # dropped (denied environment)
            target.receive(msg)
            # emergent coupling: recipient pulled toward sender's send-phase
            target.ooda_phase = phase_pull(target.ooda_phase,
                                           msg["sender_phase"], self.coupling)
            self.delivered_count += 1
            self._route_message(target, msg)
        self.transit = still

    def _route_message(self, recipient: RescueUnit, msg: Dict[str, Any]) -> None:
        if msg["type"] == "resupply_request" and recipient.capability == "resupply":
            self.resupply_requests.add(msg["sender"])

    def _find_capability(self, capability: str) -> Optional[str]:
        for u in self.units.values():
            if u.capability == capability and u.state == UnitState.OPERATIONAL:
                return u.unit_id
        return None

    # --- class-specific behaviour on OODA cycle completion ---

    def _unit_act(self, unit: RescueUnit) -> None:
        if unit.state != UnitState.OPERATIONAL:
            return
        if unit.unit_class == "A":
            self._act_detect(unit)
        elif unit.unit_class == "B":
            self._act_rescue(unit)
        else:
            self._act_command(unit)

    def _act_detect(self, unit: RescueUnit) -> None:
        if not self.undetected:
            return
        rep = self.undetected.pop(0)
        self.coordinator.report_damage(rep["area_id"], rep["severity"],
                                       rep["victims"], self.t)
        if self.clearance_gate is not None:
            self.clearance_gate.register_area(rep["area_id"],
                                              HazardLevel(rep.get("hazard", "safe")))
            if self.clearance_gate.is_blocked(rep["area_id"]):
                self._assessment_queue.append(rep["area_id"])
        cmd = self._find_capability("incident_command")
        if cmd:
            self._send(unit, cmd, "damage_report",
                       {"area": rep["area_id"], "victims": rep["victims"]})

    def _act_rescue(self, unit: RescueUnit) -> None:
        if self.clearance_gate is not None and unit.capability == "route_clearing":
            self._do_assessment(unit)
        if unit.supplies < self.resupply_threshold:
            log = self._find_capability("resupply")
            if log:
                self._send(unit, log, "resupply_request", {"supplies": unit.supplies})
        task = self.active_tasks.get(unit.unit_id)
        if not task:
            return
        if unit.supplies < unit.supply_drain_per_action:
            return
        unit.consume_supplies(unit.supply_drain_per_action)
        task["work_left"] -= 1
        if task["work_left"] <= 0:
            self.coordinator.serve(task["assignment"])
            cmd = self._find_capability("incident_command")
            if cmd:
                self._send(unit, cmd, "task_report",
                           {"area": task["assignment"]["area"],
                            "served": task["assignment"]["victims"]})
            del self.active_tasks[unit.unit_id]

    def _do_assessment(self, unit: RescueUnit) -> None:
        if not self._assessment_queue:
            return
        area_id = self._assessment_queue[0]
        status = self.clearance_gate.status.get(area_id)
        if status not in (ClearanceStatus.BLOCKED, ClearanceStatus.ASSESSING):
            self._assessment_queue.pop(0)          # already cleared
            return
        self.clearance_gate.begin_assessment(area_id, unit.unit_id)
        stable = self.rng.random() < self.assess_stable_p
        self.clearance_gate.record_assessment(area_id, stable)
        cmd = self._find_capability("incident_command")
        if cmd:
            self._send(unit, cmd, "assessment_report",
                       {"area": area_id, "stable": stable})
        if stable:
            self._assessment_queue.pop(0)
        # unstable -> stays in queue, re-assessed next cycle (shoring work)

    def _act_command(self, unit: RescueUnit) -> None:
        if unit.capability == "incident_command":
            # 1) clearance for assessed-stable areas (only C can issue)
            if self.clearance_gate is not None:
                for area_id in list(self.clearance_gate.status):
                    if (self.clearance_gate.status[area_id] == ClearanceStatus.ASSESSING
                            and self.clearance_gate.assessment_result(area_id) == "stable"):
                        self.clearance_gate.issue_clearance(area_id, unit.unit_id, "C")
            # 2) allocate detected areas, respecting the clearance gate
            for area in self.coordinator.victims:
                if area["status"] != "detected":
                    continue
                area_id = area["area_id"]
                if (self.clearance_gate is not None
                        and not self.clearance_gate.is_cleared(area_id)):
                    continue                       # unsafe -> no SAR entry yet
                res = self.coordinator.allocate(area)
                if res.get("status") == "dispatched":
                    self.active_tasks[res["unit"]] = {
                        "assignment": res, "work_left": self.work_cycles,
                    }
                    self._send(unit, res["unit"], "task_assignment",
                               {"area": area_id, "victims": area["victims"]})
        elif unit.capability == "resupply":
            for uid in list(self.resupply_requests):
                target = self.units.get(uid)
                if target and target.state != UnitState.OUT_OF_SERVICE:
                    target.resupply(self.resupply_amount)
                    target.recharge(self.resupply_amount)
                    self._send(unit, uid, "resupply_delivered",
                               {"amount": self.resupply_amount})
                self.resupply_requests.discard(uid)
        elif unit.capability == "comms_relay":
            for u in self.units.values():                 # restore degraded units
                if u.state == UnitState.DEGRADED:
                    u.comms_budget = min(100.0, u.comms_budget + 20.0)
                    u.state = UnitState.OPERATIONAL

    # --- report ---

    def report(self) -> Dict[str, Any]:
        conservation = self.coordinator.conservation_check()
        coordination = evaluate_coordination(self.units)
        operational = sum(1 for u in self.units.values()
                          if u.state == UnitState.OPERATIONAL)
        report = {
            "t": self.t,
            "conservation": conservation,
            "coordination": coordination,
            "units_operational": operational,
            "units_total": len(self.units),
            "messages_delivered": self.delivered_count,
            "active_tasks": len(self.active_tasks),
            "summary": (f"detected={conservation['detected']} "
                        f"assigned={conservation['assigned']} "
                        f"served={conservation['served']} | "
                        f"coordination={coordination.get('status')} "
                        f"(R={coordination.get('r_observed')}, "
                        f"p={coordination.get('p_value')}) | "
                        f"operational={operational}/{len(self.units)}"),
        }
        report["clearance"] = (self.clearance_gate.stats()
                               if self.clearance_gate is not None else None)
        return report
