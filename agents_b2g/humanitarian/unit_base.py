"""Base class for humanitarian logistics units.

Resources: POL (fuel), COLD (cold-chain integrity), CAP (capacity), Battery.
Friction: every message/action consumes resources.
OODA cycle: each unit cycles at its own period (calibrated 3:1 spread).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

TWO_PI = 6.283185307179586


class UnitState(str, Enum):
    OPERATIONAL = "operational"
    STANDBY = "standby"              # resource below threshold, awaiting resupply
    DEGRADED = "degraded"            # reduced efficiency
    OUT_OF_SERVICE = "out_of_service"


@dataclass
class HumanitarianUnit:
    unit_id: str
    unit_class: str                       # "A" | "B" | "C"
    capability: str                       # routing key
    cycle_period_s: float                 # calibrated cycle time (sim-minutes)
    pol: float = 100.0                    # fuel
    cold: float = 100.0                   # cold-chain integrity
    cap: float = 100.0                    # free capacity
    battery: float = 100.0                # for UAV/SAR
    pol_drain_per_cycle: float = 0.02
    pol_cost_per_msg: float = 0.005
    state: UnitState = UnitState.OPERATIONAL
    ooda_phase: float = 0.0
    cycle_start_t: float = 0.0
    cycles_completed: int = 0
    inbox: List[Dict[str, Any]] = field(default_factory=list)
    outbox: List[Dict[str, Any]] = field(default_factory=list)
    log: List[Dict[str, Any]] = field(default_factory=list)

    def consume_pol(self, amount: float) -> bool:
        self.pol = max(0.0, self.pol - amount)
        if self.pol <= 0.0:
            self.state = UnitState.OUT_OF_SERVICE
            self._log("OUT_OF_POL")
            return False
        return True

    def send(self, target: str, msg_type: str, payload: Dict[str, Any]):
        if self.state == UnitState.OUT_OF_SERVICE:
            return None
        self.consume_pol(self.pol_cost_per_msg)
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
        if self.ooda_phase < prev:
            self.cycles_completed += 1
            self.cycle_start_t = t_now
            self._log("OODA_CYCLE")
        self.consume_pol(self.pol_drain_per_cycle * dt / self.cycle_period_s)

    def _log(self, event: str, data=None) -> None:
        self.log.append({"t": self.cycle_start_t, "event": event, "data": data or {}})
