"""Normal-operation simulation for the humanitarian swarm (H0 gate). NO stress.

Key difference from the CI simulation: JITTER is part of the design, not a
caveat. Two pre-registered jitter sources give the 10 seeds real replication
variance:
  - Initial phase: uniform(0, 2*pi) per agent per seed.
  - Cycle-time jitter: +/-10% per agent (fixed per agent per seed).

This is the methodological improvement over the CI study's byte-identical seeds.
"""
from __future__ import annotations

import math
import random
from typing import Dict, List

from agents_b2g.humanitarian.unit_base import HumanitarianUnit, UnitState
from agents_b2g.humanitarian.agents import build_humanitarian_swarm

TWO_PI = 2 * math.pi


def phase_pull(phase: float, target: float, strength: float) -> float:
    delta = target - phase
    delta = ((delta + math.pi) % TWO_PI) - math.pi
    return (phase + strength * delta) % TWO_PI


class HumanitarianNormalSimulation:
    def __init__(self, seed: int = 42, duration_s: float = 1440.0, dt: float = 1.0,
                 coupling: float = 0.30, t_warmup: float = 60.0,
                 sample_interval: float = 1.0):
        self.rng = random.Random(seed)
        self.jitter_rng = random.Random(seed + 7777)   # separate jitter stream
        self.duration_s = duration_s
        self.dt = dt
        self.coupling = coupling
        self.t_warmup = t_warmup
        self.sample_interval = sample_interval
        self.units: Dict[str, HumanitarianUnit] = build_humanitarian_swarm()
        # Pre-registered jitter: initial phase + cycle-time +/-10%, per agent per seed.
        for u in self.units.values():
            u.ooda_phase = self.jitter_rng.uniform(0, TWO_PI)
            u.cycle_period_s = u.cycle_period_s * (1.0 + self.jitter_rng.uniform(-0.1, 0.1))
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
        if self.t >= self.t_warmup and (self.t - self._last_sample_t) >= self.sample_interval:
            self._last_sample_t = self.t
            for uid, u in self.units.items():
                last = self.phase_records[uid][-1] if self.phase_records[uid] else 0.0
                self.phase_records[uid].append(
                    u.ooda_phase if u.state in (UnitState.OPERATIONAL, UnitState.DEGRADED)
                    else last)

    def _send(self, sender: HumanitarianUnit, target_id: str, msg_type: str, payload):
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

    def _unit_act(self, unit: HumanitarianUnit) -> None:
        if unit.state == UnitState.OUT_OF_SERVICE:
            return
        if unit.unit_class == "A":
            ocha = self._find_capability("priority_allocation")
            if ocha:
                self._send(unit, ocha, "situation_report", {"reading": self.rng.random()})
        elif unit.unit_class == "B":
            ocha = self._find_capability("priority_allocation")
            if ocha:
                self._send(unit, ocha, "status", {"pol": unit.pol})
        elif unit.unit_class == "C":
            if unit.capability == "priority_allocation":
                # Coordination signal to ALL agents (A, B, and other C),
                # so every unit's phase gets pulled into the OCHA hub.
                # Previously only class B received, leaving class A and
                # b2g_agent un-pulled (4/9 agents at random phase).
                for uid, u in self.units.items():
                    if uid != unit.unit_id:
                        self._send(unit, uid, "coordination_signal", {"cmd": "sync"})
