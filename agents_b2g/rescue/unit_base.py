"""Base class for rescue units (civil protection).

Resources: power (battery/fuel), supplies (relief goods), comms_load.
Friction: every transmitted message costs comms budget; over the threshold
the unit risks network congestion (civilian analog of EM-signature risk).
OODA loop: each unit cycles Observe->Orient->Decide->Act at its own period.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class UnitState(str, Enum):
    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    RECHARGING = "recharging"
    OUT_OF_SERVICE = "out_of_service"


@dataclass
class RescueUnit:
    unit_id: str
    unit_class: str                       # "A" | "B" | "C"
    capability: str                       # routing key, e.g. "victim_rescue"
    ooda_period_s: float                  # individual OODA cycle time (seconds)
    power: float = 100.0                  # battery / fuel
    supplies: float = 100.0               # relief goods / consumables
    comms_budget: float = 100.0           # communication budget
    power_drain_per_cycle: float = 1.0
    supply_drain_per_action: float = 2.0
    comms_cost_per_msg: float = 0.5
    comms_threshold: float = 90.0         # congestion warning level
    state: UnitState = UnitState.OPERATIONAL
    ooda_phase: float = 0.0               # [0, 2*pi)
    cycle_start_t: float = 0.0
    cycles_completed: int = 0
    inbox: List[Dict[str, Any]] = field(default_factory=list)
    outbox: List[Dict[str, Any]] = field(default_factory=list)
    log: List[Dict[str, Any]] = field(default_factory=list)

    # --- resources ---

    def consume_power(self, amount: float) -> bool:
        self.power = max(0.0, self.power - amount)
        if self.power <= 0.0:
            self.state = UnitState.OUT_OF_SERVICE
            self._log("OUT_OF_POWER")
            return False
        return True

    def consume_supplies(self, amount: float) -> bool:
        if self.supplies < amount:
            self._log("LOW_SUPPLIES", {"need": amount, "have": self.supplies})
            return False
        self.supplies -= amount
        return True

    def recharge(self, amount: float) -> None:
        self.power = min(100.0, self.power + amount)
        if self.power > 0.0 and self.state in (UnitState.RECHARGING, UnitState.OUT_OF_SERVICE):
            self.state = UnitState.OPERATIONAL

    def resupply(self, amount: float) -> None:
        self.supplies = min(100.0, self.supplies + amount)

    # --- communication friction ---

    def send(self, target: str, msg_type: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send a message; costs comms budget. Overload -> degraded."""
        if self.state == UnitState.OUT_OF_SERVICE:
            return None
        self.comms_budget -= self.comms_cost_per_msg
        msg = {
            "msg_id": str(uuid.uuid4()),
            "sender": self.unit_id,
            "target": target,
            "type": msg_type,
            "payload": payload,
            "t": self.cycle_start_t,
        }
        self.outbox.append(msg)
        if self.comms_budget <= 0.0:
            self.state = UnitState.DEGRADED
            self._log("COMMS_OVERLOAD")
        return msg

    def receive(self, msg: Dict[str, Any]) -> None:
        self.inbox.append(msg)

    # --- OODA loop ---

    def advance_ooda(self, dt: float, t_now: float) -> None:
        """Advance the OODA phase by dt seconds."""
        if self.state == UnitState.OUT_OF_SERVICE:
            return
        prev = self.ooda_phase
        self.ooda_phase = (self.ooda_phase + 2 * 3.141592653589793 * dt / self.ooda_period_s) % (2 * 3.141592653589793)
        # detect cycle completion (phase wrapped)
        if self.ooda_phase < prev:
            self.cycles_completed += 1
            self.cycle_start_t = t_now
            self._log("OODA_CYCLE")
        self.consume_power(self.power_drain_per_cycle * dt / self.ooda_period_s)

    def ooda_step(self) -> str:
        """Return the current OODA step name from the phase."""
        frac = self.ooda_phase / (2 * 3.141592653589793)
        return ["OBSERVE", "ORIENT", "DECIDE", "ACT"][int(frac * 4) % 4]

    def _log(self, event: str, data: Optional[Dict[str, Any]] = None) -> None:
        self.log.append({"t": self.cycle_start_t, "event": event, "data": data or {}})
