"""CI simulation: normal-operation (H0) and stress injectors (H1/H2).

Stress scenarios are opt-in via `stress_type` on CIStressSimulation.
Windows:
  - [t_warmup, t_stress] -> normal operation -> R_normal
  - [t_stress + burn_in, t_end] -> stress phase -> R_stress
Degradation metric: ΔR = R_normal - R_stress (positive = degradation).
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional

from agents_b2g.ci.unit_base import CIUnit, UnitState
from agents_b2g.ci.agents import build_ci_swarm

TWO_PI = 2 * math.pi


def phase_pull(phase: float, target: float, strength: float) -> float:
    delta = target - phase
    delta = ((delta + math.pi) % TWO_PI) - math.pi
    return (phase + strength * delta) % TWO_PI


class CINormalSimulation:
    """H0 gate: normal operation only, continuous phase sampling after warmup."""

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
        if (self.t >= self.t_warmup
                and (self.t - self._last_sample_t) >= self.sample_interval):
            self._last_sample_t = self.t
            for uid, u in self.units.items():
                last = self.phase_records[uid][-1] if self.phase_records[uid] else 0.0
                self.phase_records[uid].append(
                    u.ooda_phase if u.state in (UnitState.OPERATIONAL, UnitState.DEGRADED)
                    else last)

    def _send(self, sender: CIUnit, target_id: str, msg_type: str, payload):
        if sender.state == UnitState.OUT_OF_SERVICE:
            return None
        msg = sender.send(target_id, msg_type, payload)
        if msg is None:
            return None
        msg["sender_phase"] = sender.ooda_phase
        self.transit.append((self.t + self.dt, msg))
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
        if unit.unit_class == "A":
            cc = self._find_capability("incident_command")
            if cc:
                self._send(unit, cc, "sensor_data", {"reading": self.rng.random()})
        elif unit.unit_class == "B":
            cc = self._find_capability("incident_command")
            if cc:
                self._send(unit, cc, "status", {"health": unit.health_score})
        elif unit.unit_class == "C":
            if unit.capability == "incident_command":
                for uid, u in self.units.items():
                    if u.unit_class == "B":
                        self._send(unit, uid, "control_command", {"cmd": "adjust"})
            elif unit.capability == "logistics":
                sensors = [uid for uid, u in self.units.items() if u.unit_class == "A"]
                if sensors:
                    self._send(unit, sensors[unit.cycles_completed % len(sensors)],
                               "logistics", {"resupply": True})
            elif unit.capability == "maintenance":
                acts = [uid for uid, u in self.units.items() if u.unit_class == "B"]
                if acts:
                    self._send(unit, acts[unit.cycles_completed % len(acts)],
                               "maintenance", {"health_check": True})


class CIStressSimulation:
    def __init__(self, seed: int = 42, duration_s: float = 600.0, dt: float = 1.0,
                 coupling: float = 0.30, t_warmup: float = 60.0,
                 t_stress: float = 300.0, burn_in: float = 30.0,
                 stress_type: Optional[str] = None,
                 sample_interval: float = 1.0):
        self.rng = random.Random(seed)
        self.stress_rng = random.Random(seed + 999999)  # separate stress stream
        self.duration_s = duration_s
        self.dt = dt
        self.coupling = coupling
        self.t_warmup = t_warmup
        self.t_stress = t_stress
        self.burn_in = burn_in
        self.stress_type = stress_type  # None | "blackout" | "cyber" | "naturkatastrophe"
        self.sample_interval = sample_interval
        self.units: Dict[str, CIUnit] = build_ci_swarm()
        for u in self.units.values():
            u._last_act_cycle = -1
            u._stressed = False
        self.t = 0.0
        self.transit: List[tuple] = []
        self.delivered_count = 0
        self.phase_normal: Dict[str, List[float]] = {uid: [] for uid in self.units}
        self.phase_stress: Dict[str, List[float]] = {uid: [] for uid in self.units}
        self._last_sample_normal = -1.0
        self._last_sample_stress = -1.0
        self._stress_injected = False

    def run(self) -> Dict[str, Dict[str, List[float]]]:
        while self.t < self.duration_s:
            self.step()
        return {"normal": self.phase_normal, "stress": self.phase_stress}

    def step(self) -> None:
        self.t += self.dt
        if not self._stress_injected and self.t >= self.t_stress:
            self._inject_stress()
            self._stress_injected = True
        for u in self.units.values():
            u.advance_ooda(self.dt, self.t)
        self._deliver()
        for u in self.units.values():
            if u.cycles_completed > u._last_act_cycle:
                u._last_act_cycle = u.cycles_completed
                self._unit_act(u)
        if self.t_warmup <= self.t < self.t_stress:
            if (self.t - self._last_sample_normal) >= self.sample_interval:
                self._last_sample_normal = self.t
                for uid, u in self.units.items():
                    last = self.phase_normal[uid][-1] if self.phase_normal[uid] else 0.0
                    self.phase_normal[uid].append(
                        u.ooda_phase if u.state in (UnitState.OPERATIONAL, UnitState.DEGRADED)
                        else last)
        elif (self.stress_type is not None
              and self.t >= (self.t_stress + self.burn_in)):
            if (self.t - self._last_sample_stress) >= self.sample_interval:
                self._last_sample_stress = self.t
                for uid, u in self.units.items():
                    last = self.phase_stress[uid][-1] if self.phase_stress[uid] else 0.0
                    self.phase_stress[uid].append(
                        u.ooda_phase if u.state in (UnitState.OPERATIONAL, UnitState.DEGRADED)
                        else last)

    def _inject_stress(self) -> None:
        if self.stress_type is None:
            return
        if self.stress_type == "blackout":
            self._stress_blackout()
        elif self.stress_type == "cyber":
            self._stress_cyber()
        elif self.stress_type == "naturkatastrophe":
            self._stress_naturkatastrophe()

    def _stress_blackout(self) -> None:
        """Single Class-B actuator -> OUT_OF_SERVICE (stays offline)."""
        target = self.units.get("grid_controller")
        if target:
            target.state = UnitState.OUT_OF_SERVICE
            target._stressed = True

    def _stress_cyber(self) -> None:
        """Class-A sensor delivers manipulated data (offset + noise)."""
        target = self.units.get("infra_sensor")
        if target:
            target._stressed = True
            target._cyber_offset = 0.5
            target._cyber_noise = 0.1

    def _stress_naturkatastrophe(self) -> None:
        """Multiple agents degraded (increased failure rate, reduced efficiency)."""
        for uid in ("env_sensor", "water_valve"):
            u = self.units.get(uid)
            if u:
                u._stressed = True
                u.cycle_period_s *= 1.5

    def _send(self, sender: CIUnit, target_id: str, msg_type: str, payload):
        if sender.state == UnitState.OUT_OF_SERVICE:
            return None
        msg = sender.send(target_id, msg_type, payload)
        if msg is None:
            return None
        msg["sender_phase"] = sender.ooda_phase
        self.transit.append((self.t + self.dt, msg))
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
        if unit.unit_class == "A":
            cc = self._find_capability("incident_command")
            if cc:
                reading = self.rng.random()
                if getattr(unit, "_stressed", False) and hasattr(unit, "_cyber_offset"):
                    reading += unit._cyber_offset + self.stress_rng.uniform(
                        -unit._cyber_noise, unit._cyber_noise)
                self._send(unit, cc, "sensor_data", {"reading": reading})
        elif unit.unit_class == "B":
            cc = self._find_capability("incident_command")
            if cc:
                self._send(unit, cc, "status", {"health": unit.health_score})
        elif unit.unit_class == "C":
            if unit.capability == "incident_command":
                for uid, u in self.units.items():
                    if u.unit_class == "B":
                        self._send(unit, uid, "control_command", {"cmd": "adjust"})
            elif unit.capability == "logistics":
                sensors = [uid for uid, u in self.units.items() if u.unit_class == "A"]
                if sensors:
                    self._send(unit, sensors[unit.cycles_completed % len(sensors)],
                               "logistics", {"resupply": True})
            elif unit.capability == "maintenance":
                acts = [uid for uid, u in self.units.items() if u.unit_class == "B"]
                if acts:
                    self._send(unit, acts[unit.cycles_completed % len(acts)],
                               "maintenance", {"health_check": True})
