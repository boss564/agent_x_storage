"""Normal-operation simulation for the CI swarm (H0 gate). NO stress injectors.

Runs the 9 CI agents exchanging messages (phase-pull coupling) and records the
OODA phase trajectories during the normal-operation window [t_warmup, duration].
"""
from __future__ import annotations

import math
import random
from typing import Dict, List

from agents_b2g.ci.unit_base import CIUnit, UnitState
from agents_b2g.ci.agents import build_ci_swarm

TWO_PI = 2 * math.pi


def phase_pull(phase: float, target: float, strength: float) -> float:
    delta = target - phase
    delta = ((delta + math.pi) % TWO_PI) - math.pi     # shortest arc
    return (phase + strength * delta) % TWO_PI


class CINormalSimulation:
    def __init__(self, seed: int = 42, duration_s: float = 600.0, dt: float = 1.0,
                 coupling: float = 0.30, t_warmup: float = 60.0,
                 sample_interval: float = 1.0):
        self.rng = random.Random(seed)
        self.duration_s = duration_s
        self.dt = dt
        self.coupling = coupling
        self.t_warmup = t_warmup
        self.sample_interval = sample_interval
        self.units: Dict[str, CIUnit] = build_ci_swarm()
        for u in self.units.values():
            u._last_act_cycle = -1
        self.t = 0.0
        self.transit: List[tuple] = []
        self.delivered_count = 0
        self.phase_records: Dict[str, List[float]] = {uid: [] for uid in self.units}
        self._last_sample_t = -1.0

    def run(self) -> Dict[str, List[float]]:
        while self.t < self.duration_s:
            self.step()
        return self.phase_records

    def step(self) -> None:
        self.t += self.dt
        for u in self.units.values():
            u.advance_ooda(self.dt, self.t)
        self._deliver()
        for u in self.units.values():
            if u.cycles_completed > u._last_act_cycle:
                u._last_act_cycle = u.cycles_completed
                self._unit_act(u)
        # sample phases during the normal-operation window
        if (self.t >= self.t_warmup
                and (self.t - self._last_sample_t) >= self.sample_interval):
            self._last_sample_t = self.t
            for uid, u in self.units.items():
                last = self.phase_records[uid][-1] if self.phase_records[uid] else 0.0
                # record live phase if cycling, else freeze last known phase
                self.phase_records[uid].append(
                    u.ooda_phase if u.state in (UnitState.OPERATIONAL, UnitState.DEGRADED)
                    else last)

    # --- messaging with phase-pull coupling ---

    def _send(self, sender: CIUnit, target_id: str, msg_type: str, payload):
        if sender.state == UnitState.OUT_OF_SERVICE:
            return None
        msg = sender.send(target_id, msg_type, payload)
        if msg is None:
            return None
        msg["sender_phase"] = sender.ooda_phase
        self.transit.append((self.t + self.dt, msg))      # 1-step propagation delay
        return msg

    def _deliver(self) -> None:
        still = []
        for deliver_at, msg in self.transit:
            if self.t < deliver_at:
                still.append((deliver_at, msg))
                continue
            target = self.units.get(msg["target"])
            if target is None or target.state == UnitState.OUT_OF_SERVICE:
                continue
            target.receive(msg)
            target.ooda_phase = phase_pull(target.ooda_phase,
                                           msg["sender_phase"], self.coupling)
            self.delivered_count += 1
        self.transit = still

    def _find_capability(self, capability: str):
        for u in self.units.values():
            if u.capability == capability and u.state != UnitState.OUT_OF_SERVICE:
                return u.unit_id
        return None

    def _unit_act(self, unit: CIUnit) -> None:
        if unit.state == UnitState.OUT_OF_SERVICE:
            return
        if unit.unit_class == "A":                        # sensors -> C2
            cc = self._find_capability("incident_command")
            if cc:
                self._send(unit, cc, "sensor_data", {"reading": self.rng.random()})
        elif unit.unit_class == "B":                      # actuators -> C2
            cc = self._find_capability("incident_command")
            if cc:
                self._send(unit, cc, "status", {"health": unit.health_score})
        elif unit.unit_class == "C":
            if unit.capability == "incident_command":     # C2 -> all actuators
                for uid, u in self.units.items():
                    if u.unit_class == "B":
                        self._send(unit, uid, "control_command", {"cmd": "adjust"})
            elif unit.capability == "logistics":          # logistics -> one sensor
                sensors = [uid for uid, u in self.units.items() if u.unit_class == "A"]
                if sensors:
                    self._send(unit, sensors[unit.cycles_completed % len(sensors)],
                               "logistics", {"resupply": True})
            elif unit.capability == "maintenance":        # maintenance -> one actuator
                acts = [uid for uid, u in self.units.items() if u.unit_class == "B"]
                if acts:
                    self._send(unit, acts[unit.cycles_completed % len(acts)],
                               "maintenance", {"health_check": True})
