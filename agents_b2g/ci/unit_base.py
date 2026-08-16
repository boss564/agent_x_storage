"""Base class for critical-infrastructure (CI) units.

Resources: energy (kWh), bandwidth (Mbit/s), health_score.
Friction: every transmitted message costs energy and bandwidth.
OODA cycle: each unit cycles at its own period (sensor fast, actuator mid, C2 slow).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

TWO_PI = 6.283185307179586


class UnitState(str, Enum):
    OPERATIONAL = "operational"
    STANDBY = "standby"              # energy below threshold, awaiting logistics
    DEGRADED = "degraded"            # bandwidth overloaded
    OUT_OF_SERVICE = "out_of_service"


@dataclass
class CIUnit:
    unit_id: str
    unit_class: str                       # "A" | "B" | "C"
    capability: str                       # routing key, e.g. "grid_control"
    cycle_period_s: float                 # sensor ~1-5s, actuator ~5s, C2 ~10s
    energy: float = 100.0
    bandwidth_usage: float = 0.0
    bandwidth_capacity: float = 100.0
    health_score: float = 1.0
    energy_drain_per_cycle: float = 0.02
    energy_cost_per_msg: float = 0.005
    bandwidth_cost_per_msg: float = 1.0
    energy_standby_threshold: float = 10.0
    bandwidth_throttle_threshold: float = 90.0
    state: UnitState = UnitState.OPERATIONAL
    ooda_phase: float = 0.0
    cycle_start_t: float = 0.0
    cycles_completed: int = 0
    inbox: List[Dict[str, Any]] = field(default_factory=list)
    outbox: List[Dict[str, Any]] = field(default_factory=list)
    log: List[Dict[str, Any]] = field(default_factory=list)

    def consume_energy(self, amount: float) -> bool:
        self.energy = max(0.0, self.energy - amount)
        if self.energy <= 0.0:
            self.state = UnitState.OUT_OF_SERVICE
            self._log("OUT_OF_ENERGY")
            return False
        if self.energy < self.energy_standby_threshold:
            self.state = UnitState.STANDBY
        return True

    def consume_bandwidth(self, amount: float) -> None:
        self.bandwidth_usage += amount
        if self.bandwidth_usage > self.bandwidth_throttle_threshold:
            self.state = UnitState.DEGRADED
            self._log("BANDWIDTH_OVERLOAD")

    def send(self, target: str, msg_type: str, payload: Dict[str, Any]):
        if self.state == UnitState.OUT_OF_SERVICE:
            return None
        self.consume_energy(self.energy_cost_per_msg)
        self.consume_bandwidth(self.bandwidth_cost_per_msg)
        msg = {"msg_id": str(uuid.uuid4()), "sender": self.unit_id,
               "target": target, "type": msg_type, "payload": payload,
               "t": self.cycle_start_t}
        self.outbox.append(msg)
        return msg

    def receive(self, msg: Dict[str, Any]) -> None:
        self.inbox.append(msg)

    def advance_ooda(self, dt: float, t_now: float) -> None:
        if self.state in (UnitState.OUT_OF_SERVICE, UnitState.STANDBY):
            return
        prev = self.ooda_phase
        self.ooda_phase = (self.ooda_phase + TWO_PI * dt / self.cycle_period_s) % TWO_PI
        if self.ooda_phase < prev:                 # phase wrapped -> cycle done
            self.cycles_completed += 1
            self.cycle_start_t = t_now
            self._log("OODA_CYCLE")
        self.consume_energy(self.energy_drain_per_cycle * dt / self.cycle_period_s)

    def _log(self, event: str, data=None) -> None:
        self.log.append({"t": self.cycle_start_t, "event": event, "data": data or {}})
