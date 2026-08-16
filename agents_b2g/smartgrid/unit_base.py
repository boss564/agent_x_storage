"""Base class for smart grid units.

OODA cycle per unit (calibrated, jitter +/-5%). Resources: power_capacity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

TWO_PI = 6.283185307179586


class UnitState(str, Enum):
    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    OUT_OF_SERVICE = "out_of_service"


@dataclass
class SmartGridUnit:
    unit_id: str
    unit_class: str                       # "A" | "B" | "C"
    capability: str                       # routing key
    cycle_period_s: float                 # calibrated cycle time (sim-minutes)
    power_capacity: float = 100.0         # max power output/input (kW)
    state: UnitState = UnitState.OPERATIONAL
    ooda_phase: float = 0.0
    cycle_start_t: float = 0.0
    cycles_completed: int = 0
    inbox: List[Dict[str, Any]] = field(default_factory=list)
    outbox: List[Dict[str, Any]] = field(default_factory=list)
    log: List[Dict[str, Any]] = field(default_factory=list)

    def advance_ooda(self, dt: float, t_now: float) -> None:
        if self.state == UnitState.OUT_OF_SERVICE:
            return
        prev = self.ooda_phase
        self.ooda_phase = (self.ooda_phase + TWO_PI * dt / self.cycle_period_s) % TWO_PI
        if self.ooda_phase < prev:
            self.cycles_completed += 1
            self.cycle_start_t = t_now

    def _log(self, event: str, data=None) -> None:
        self.log.append({"t": self.cycle_start_t, "event": event, "data": data or {}})
