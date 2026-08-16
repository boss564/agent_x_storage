"""Humanitarian logistics simulation: H0 normal-op + stress injectors.

Normal op (HumanitarianNormalSimulation): jitter + heartbeat for H0 gate.
Stress (HumanitarianStressSimulation): hub_verlust / nachbeben / komm_kollaps
plus Request-Fulfillment efficiency tracking (H3).
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional

from agents_b2g.humanitarian.unit_base import HumanitarianUnit, UnitState
from agents_b2g.humanitarian.agents import build_humanitarian_swarm

TWO_PI = 2 * math.pi


def phase_pull(phase: float, target: float, strength: float) -> float:
    delta = target - phase
    delta = ((delta + math.pi) % TWO_PI) - math.pi
    return (phase + strength * delta) % TWO_PI


class HumanitarianNormalSimulation:
    """H0 gate: normal operation with pre-registered jitter + OCHA heartbeat."""

    def __init__(self, seed: int = 42, duration_s: float = 1440.0, dt: float = 1.0,
                 coupling: float = 0.30, t_warmup: float = 60.0,
                 sample_interval: float = 1.0):
        self.rng = random.Random(seed)
        self.jitter_rng = random.Random(seed + 7777)
        self.duration_s = duration_s
        self.dt = dt
        self.coupling = coupling
        self.t_warmup = t_warmup
        self.sample_interval = sample_interval
        self.units: Dict[str, HumanitarianUnit] = build_humanitarian_swarm()
        for u in self.units.values():
            u.ooda_phase = self.jitter_rng.uniform(0, TWO_PI)
            u.cycle_period_s = u.cycle_period_s * (1.0 + self.jitter_rng.uniform(-0.1, 0.1))
            u._last_act_cycle = -1
        self.t = 0.0
        self.transit: List[tuple] = []
        self.delivered_count = 0
        self.phase_records: Dict[str, List[float]] = {uid: [] for uid in self.units}
        self._last_sample_t = -1.0
        self.heartbeat_interval = 2.0
        self._last_heartbeat_t = 0.0

    def run(self) -> Dict[str, List[float]]:
        while self.t < self.duration_s:
            self.step()
        return self.phase_records

    def step(self) -> None:
        self.t += self.dt
        for u in self.units.values():
            u.advance_ooda(self.dt, self.t)
        self._deliver()
        if self.t - self._last_heartbeat_t >= self.heartbeat_interval:
            self._last_heartbeat_t = self.t
            ocha_id = self._find_capability("priority_allocation")
            if ocha_id:
                for uid, u in self.units.items():
                    if uid != ocha_id:
                        self._send(self.units[ocha_id], uid, "coord_heartbeat", {})
                        self._send(u, ocha_id, "heartbeat", {})
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
                for uid, u in self.units.items():
                    if uid != unit.unit_id:
                        self._send(unit, uid, "coordination_signal", {"cmd": "sync"})


class HumanitarianStressSimulation:
    """Stress study: within-run normal + stress windows, efficiency tracking."""

    def __init__(self, seed: int = 42, duration_s: float = 4320.0, dt: float = 1.0,
                 coupling: float = 0.50, t_warmup: float = 60.0,
                 t_stress: float = 1440.0, burn_in: float = 60.0,
                 heartbeat_interval: float = 2.0,
                 stress_type: Optional[str] = None,
                 sample_interval: float = 1.0):
        self.rng = random.Random(seed)
        self.jitter_rng = random.Random(seed + 7777)
        self.stress_rng = random.Random(seed + 999999)
        self.duration_s = duration_s
        self.dt = dt
        self.coupling = coupling
        self.t_warmup = t_warmup
        self.t_stress = t_stress
        self.burn_in = burn_in
        self.heartbeat_interval = heartbeat_interval
        self.stress_type = stress_type
        self.sample_interval = sample_interval
        self.units: Dict[str, HumanitarianUnit] = build_humanitarian_swarm()
        for u in self.units.values():
            u.ooda_phase = self.jitter_rng.uniform(0, TWO_PI)
            u.cycle_period_s = u.cycle_period_s * (1.0 + self.jitter_rng.uniform(-0.1, 0.1))
            u._last_act_cycle = -1
        self.t = 0.0
        self.transit: List[tuple] = []
        self.delivered_count = 0
        self._last_heartbeat_t = 0.0
        self._stress_injected = False
        self.phase_normal: Dict[str, List[float]] = {uid: [] for uid in self.units}
        self.phase_stress: Dict[str, List[float]] = {uid: [] for uid in self.units}
        self._last_sample_normal = -1.0
        self._last_sample_stress = -1.0
        self.requests: List[Dict] = []
        self.fulfillments: List[Dict] = []
        self._request_seq = 0

    def run(self) -> Dict:
        while self.t < self.duration_s:
            self.step()
        return {
            "normal": self.phase_normal,
            "stress": self.phase_stress,
            "requests": self.requests,
            "fulfillments": self.fulfillments,
        }

    def step(self) -> None:
        self.t += self.dt
        if not self._stress_injected and self.t >= self.t_stress:
            self._inject_stress()
            self._stress_injected = True
        for u in self.units.values():
            u.advance_ooda(self.dt, self.t)
        self._deliver()
        if self.t - self._last_heartbeat_t >= self.heartbeat_interval:
            self._last_heartbeat_t = self.t
            ocha_id = self._find_capability("priority_allocation")
            if ocha_id:
                for uid, u in self.units.items():
                    if uid != ocha_id:
                        self._send(self.units[ocha_id], uid, "coord_heartbeat", {})
                        self._send(u, ocha_id, "heartbeat", {})
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
        if self.stress_type == "hub_verlust":
            self._stress_hub_verlust()
        elif self.stress_type == "nachbeben":
            self._stress_nachbeben()
        elif self.stress_type == "komm_kollaps":
            self._stress_komm_kollaps()

    def _stress_hub_verlust(self) -> None:
        target = self.units.get("forward_hub_agent")
        if target:
            target.state = UnitState.OUT_OF_SERVICE

    def _stress_nachbeben(self) -> None:
        for uid in ("thw_agent", "uav_agent"):
            u = self.units.get(uid)
            if u:
                u.cycle_period_s *= 1.5
                u.state = UnitState.DEGRADED

    def _stress_komm_kollaps(self) -> None:
        for uid, u in self.units.items():
            if u.unit_class == "A":
                u.pol_cost_per_msg *= 3.0
                u.pol_drain_per_cycle *= 2.0

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
            if self.rng.random() < 0.3:
                self._request_seq += 1
                self.requests.append({
                    "request_id": self._request_seq,
                    "requester": unit.unit_id,
                    "t_request": self.t,
                    "t_fulfill": None,
                    "fulfilled": False,
                })
        elif unit.unit_class == "B":
            ocha = self._find_capability("priority_allocation")
            if ocha:
                self._send(unit, ocha, "status", {"pol": unit.pol})
            for req in self.requests:
                if not req["fulfilled"] and self.rng.random() < 0.1:
                    req["t_fulfill"] = self.t
                    req["fulfilled"] = True
                    self.fulfillments.append(req)
        elif unit.unit_class == "C":
            if unit.capability == "priority_allocation":
                for uid, u in self.units.items():
                    if uid != unit.unit_id:
                        self._send(unit, uid, "coordination_signal", {"cmd": "sync"})
            elif unit.capability == "customs_clearance":
                acts = [uid for uid, u in self.units.items() if u.unit_class == "B"]
                if acts:
                    self._send(unit, acts[unit.cycles_completed % len(acts)],
                               "customs", {"clearance": True})

    def compute_efficiency(self, window_start: float, window_end: float) -> Dict:
        window_requests = [r for r in self.requests
                           if window_start <= r["t_request"] < window_end]
        if not window_requests:
            return {"quote": 0.0, "mean_rt": 0.0, "n_requests": 0}
        fulfilled = [r for r in window_requests if r["fulfilled"]]
        quote = len(fulfilled) / len(window_requests)
        rts = [r["t_fulfill"] - r["t_request"] for r in fulfilled if r["t_fulfill"]]
        mean_rt = sum(rts) / len(rts) if rts else 0.0
        return {"quote": quote, "mean_rt": mean_rt, "n_requests": len(window_requests)}
