"""Normal-operation simulation for the smart grid (H0 gate). NO stress injectors.

Models OODA cycles (jitter +/-5%), power generation (Class A, stochastic),
load profile (daily cycle), power balance -> W_dyn (autarky, lambda=0), and
grid-bus coupling -> generator phase coherence -> R_grid.
"""

from __future__ import annotations

import math
import random
from typing import Dict, List

from agents_b2g.smartgrid.unit_base import SmartGridUnit, UnitState
from agents_b2g.smartgrid.agents import build_smartgrid_swarm

TWO_PI = 2 * math.pi


def phase_pull(phase: float, target: float, strength: float) -> float:
    delta = target - phase
    delta = ((delta + math.pi) % TWO_PI) - math.pi
    return (phase + strength * delta) % TWO_PI


class SmartGridNormalSimulation:
    def __init__(self, seed: int = 42, duration_s: float = 1440.0, dt: float = 1.0,
                 grid_coupling: float = 0.60, t_warmup: float = 60.0,
                 jitter_pct: float = 0.05, sample_interval: float = 1.0,
                 base_load: float = 180.0):
        self.rng = random.Random(seed)
        self.jitter_rng = random.Random(seed + 7777)
        self.load_rng = random.Random(seed + 5555)
        self.duration_s = duration_s
        self.dt = dt
        self.grid_coupling = grid_coupling
        self.t_warmup = t_warmup
        self.sample_interval = sample_interval
        self.base_load = base_load

        self.units: Dict[str, SmartGridUnit] = build_smartgrid_swarm()
        for u in self.units.values():
            u.ooda_phase = self.jitter_rng.uniform(0, TWO_PI)
            u.cycle_period_s = u.cycle_period_s * (1.0 + self.jitter_rng.uniform(-jitter_pct, jitter_pct))
            u._last_act_cycle = -1

        self.t = 0.0
        self.grid_bus_phase = 0.0
        self.grid_bus_period = 4.0

        self.phase_records: Dict[str, List[float]] = {
            uid: [] for uid, u in self.units.items() if u.unit_class == "A"
        }
        self._last_sample_t = -1.0
        self.w_dyn_records: List[float] = []

    def run(self) -> Dict[str, List[float]]:
        while self.t < self.duration_s:
            self.step()
        return self.phase_records

    def step(self) -> None:
        self.t += self.dt
        self.grid_bus_phase = (self.grid_bus_phase + TWO_PI * self.dt / self.grid_bus_period) % TWO_PI
        for u in self.units.values():
            u.advance_ooda(self.dt, self.t)
        for uid, u in self.units.items():
            if u.unit_class == "A" and u.state != UnitState.OUT_OF_SERVICE:
                u.ooda_phase = phase_pull(u.ooda_phase, self.grid_bus_phase, self.grid_coupling)
        for u in self.units.values():
            if u.cycles_completed > u._last_act_cycle:
                u._last_act_cycle = u.cycles_completed
                self._unit_act(u)
        self._compute_power_balance()
        if self.t >= self.t_warmup and (self.t - self._last_sample_t) >= self.sample_interval:
            self._last_sample_t = self.t
            for uid, u in self.units.items():
                if u.unit_class == "A":
                    self.phase_records[uid].append(u.ooda_phase)

    def _unit_act(self, unit: SmartGridUnit) -> None:
        pass

    def _compute_power_balance(self) -> None:
        gen_total = 0.0
        for uid, u in self.units.items():
            if u.unit_class == "A" and u.state != UnitState.OUT_OF_SERVICE:
                if u.capability == "chp_generation":
                    cf = 0.85 + 0.10 * self.rng.random()
                else:
                    cf = 0.2 + 0.7 * self.rng.random()
                gen_total += u.power_capacity * cf
        load = self.base_load * (1.0 + 0.25 * math.sin(TWO_PI * self.t / 1440.0))
        load += self.load_rng.uniform(-10.0, 10.0)
        load = max(load, 1.0)
        flex_available = sum(
            u.power_capacity * 0.4 for uid, u in self.units.items()
            if u.unit_class == "B" and u.state != UnitState.OUT_OF_SERVICE
        )
        served = min(gen_total + flex_available, load)
        w_dyn = max(0.0, min(1.0, served / load))
        if self.t >= self.t_warmup:
            self.w_dyn_records.append(w_dyn)
