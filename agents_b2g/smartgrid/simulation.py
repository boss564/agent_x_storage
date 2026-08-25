"""Smart Grid simulation: H0 normal-op + stress injectors + Hebel-4 plasticity.

Normal (SmartGridNormalSimulation): inverter fleets, grid-bus coupling, W_dyn.
Stress (SmartGridStressSimulation): bewoelkung / spitzenlast / leitungsausfall.
Hebel 4: plasticity=True enables Class-B waterfall dispatch (replaces 0.4 stub).

Metrics: R_grid (Class-A inverter phases), W_dyn (autarky, lambda=0).
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Optional

from agents_b2g.smartgrid.unit_base import SmartGridUnit, UnitState
from agents_b2g.smartgrid.agents import build_smartgrid_swarm
from agents_b2g.smartgrid.flex_dispatch import (
    PASSIVE_FLEX_FRACTION,
    WATERFALL_ORDER,
    flex_available_null,
    flex_available_treatment,
    run_waterfall,
)

TWO_PI = 2 * math.pi


def phase_pull(phase: float, target: float, strength: float) -> float:
    delta = target - phase
    delta = ((delta + math.pi) % TWO_PI) - math.pi
    return (phase + strength * delta) % TWO_PI


class SmartGridNormalSimulation:
    """H0 gate: normal operation with inverter fleets (N=9) + W_dyn."""

    def __init__(self, seed: int = 42, duration_s: float = 1440.0, dt: float = 1.0,
                 grid_coupling: float = 0.60, t_warmup: float = 60.0,
                 jitter_pct: float = 0.05, sample_interval: float = 1.0,
                 base_load: float = 180.0):
        self.rng = random.Random(seed + 1)
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

        self.inverters_per_gen = 3
        self.phase_records: Dict[str, List[float]] = {}
        self._inverter_state: Dict[str, Dict[str, float]] = {}
        for uid, u in self.units.items():
            if u.unit_class == "A":
                for k in range(self.inverters_per_gen):
                    inv_id = f"{uid}_inv{k}"
                    self.phase_records[inv_id] = []
                    self._inverter_state[inv_id] = {
                        "phase": self.jitter_rng.uniform(0, TWO_PI),
                        "period": u.cycle_period_s * (
                            1.0 + self.jitter_rng.uniform(-jitter_pct, jitter_pct)
                        ),
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
        for inv_id, inv in self._inverter_state.items():
            inv["phase"] = (inv["phase"] + TWO_PI * self.dt / inv["period"]) % TWO_PI
            inv["phase"] = phase_pull(inv["phase"], self.grid_bus_phase, self.grid_coupling)
        for u in self.units.values():
            if u.cycles_completed > u._last_act_cycle:
                u._last_act_cycle = u.cycles_completed
                self._unit_act(u)
        self._compute_power_balance()
        if self.t >= self.t_warmup and (self.t - self._last_sample_t) >= self.sample_interval:
            self._last_sample_t = self.t
            for inv_id, inv in self._inverter_state.items():
                self.phase_records[inv_id].append(inv["phase"])

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
            u.power_capacity * PASSIVE_FLEX_FRACTION for uid, u in self.units.items()
            if u.unit_class == "B" and u.state != UnitState.OUT_OF_SERVICE
        )
        served = min(gen_total + flex_available, load)
        w_dyn = max(0.0, min(1.0, served / load))
        if self.t >= self.t_warmup:
            self.w_dyn_records.append(w_dyn)


class SmartGridStressSimulation:
    """Stress study: within-run normal + stress windows; R_grid + W_dyn.

    plasticity=False (null): Class-B contributes PASSIVE_FLEX_FRACTION × capacity.
    plasticity=True (treatment): waterfall dispatch replaces 0.4 (no max).
    """

    def __init__(self, seed: int = 42, duration_s: float = 4320.0, dt: float = 1.0,
                 grid_coupling: float = 0.60, t_warmup: float = 60.0,
                 t_stress: float = 1440.0, burn_in: float = 60.0,
                 jitter_pct: float = 0.05, sample_interval: float = 1.0,
                 base_load: float = 180.0,
                 stress_type: Optional[str] = None,
                 plasticity: bool = False):
        # Independent RNG streams per seed (Hebel-3 determinism caveat avoided)
        self.rng = random.Random(seed + 1)
        self.jitter_rng = random.Random(seed + 7777)
        self.load_rng = random.Random(seed + 5555)
        self.stress_rng = random.Random(seed + 999999)
        self.duration_s = duration_s
        self.dt = dt
        self.grid_coupling = grid_coupling
        self.t_warmup = t_warmup
        self.t_stress_nominal = t_stress
        # Stress onset jitter ±30 sim-min — seed-dependent. Clamp only when the
        # nominal schedule leaves room for a stress window (≥120 samples).
        jitter = self.stress_rng.uniform(-30.0, 30.0)
        t_cand = t_stress + jitter
        t_lo = t_warmup + 120.0
        t_hi = duration_s - burn_in - 120.0
        if t_hi > t_lo:
            self.t_stress = min(max(t_cand, t_lo), t_hi)
        else:
            # Short unit-test runs: keep nominal±jitter inside [warmup, end-burn_in)
            self.t_stress = min(
                max(t_cand, t_warmup + self.dt),
                max(duration_s - burn_in - self.dt, t_warmup + self.dt),
            )
        self.burn_in = burn_in
        self.sample_interval = sample_interval
        self.base_load = base_load
        self.stress_type = stress_type
        self.plasticity = plasticity

        self.units: Dict[str, SmartGridUnit] = build_smartgrid_swarm()
        self.inverters_per_gen = 3
        self.phase_normal: Dict[str, List[float]] = {}
        self.phase_stress: Dict[str, List[float]] = {}
        self._inverter_state: Dict[str, Dict[str, float]] = {}
        for uid, u in self.units.items():
            u.ooda_phase = self.jitter_rng.uniform(0, TWO_PI)
            u.cycle_period_s = u.cycle_period_s * (1.0 + self.jitter_rng.uniform(-jitter_pct, jitter_pct))
            u._last_act_cycle = -1
            if u.unit_class == "A":
                for k in range(self.inverters_per_gen):
                    inv_id = f"{uid}_inv{k}"
                    self.phase_normal[inv_id] = []
                    self.phase_stress[inv_id] = []
                    self._inverter_state[inv_id] = {
                        "phase": self.jitter_rng.uniform(0, TWO_PI),
                        "period": u.cycle_period_s * (
                            1.0 + self.jitter_rng.uniform(-jitter_pct, jitter_pct)
                        ),
                        "capacity_factor": 1.0,
                    }

        self.soc: Dict[str, float] = {
            "battery_storage": 0.80,
            "ev_mobility": 0.60,
        }
        self.shed_headroom = 1.0
        self.flex_dispatch: Dict[str, float] = {uid: 0.0 for uid in WATERFALL_ORDER}
        self.dispatch_stress_samples: List[float] = []
        self.last_deficit = 0.0
        self.last_flex_available = 0.0

        self.t = 0.0
        self.grid_bus_phase = 0.0
        self.grid_bus_period = 4.0
        self._last_sample_normal = -1.0
        self._last_sample_stress = -1.0
        self._stress_injected = False
        self.w_dyn_normal: List[float] = []
        self.w_dyn_stress: List[float] = []

    def _class_b_capacities(self) -> Dict[str, float]:
        return {
            uid: u.power_capacity
            for uid, u in self.units.items()
            if u.unit_class == "B" and u.state != UnitState.OUT_OF_SERVICE
        }

    def run(self) -> Dict:
        while self.t < self.duration_s:
            self.step()
        return {
            "normal": self.phase_normal,
            "stress": self.phase_stress,
            "w_dyn_normal": self.w_dyn_normal,
            "w_dyn_stress": self.w_dyn_stress,
            "mean_dispatch_kw": (
                sum(self.dispatch_stress_samples) / len(self.dispatch_stress_samples)
                if self.dispatch_stress_samples else 0.0
            ),
            "t_stress_effective": self.t_stress,
            "plasticity": self.plasticity,
        }

    def step(self) -> None:
        self.t += self.dt
        if not self._stress_injected and self.t >= self.t_stress:
            self._inject_stress()
            self._stress_injected = True
        self.grid_bus_phase = (self.grid_bus_phase + TWO_PI * self.dt / self.grid_bus_period) % TWO_PI
        for u in self.units.values():
            u.advance_ooda(self.dt, self.t)
        for inv_id, inv in self._inverter_state.items():
            inv["phase"] = (inv["phase"] + TWO_PI * self.dt / inv["period"]) % TWO_PI
            if inv.get("capacity_factor", 1.0) > 0.0:
                inv["phase"] = phase_pull(inv["phase"], self.grid_bus_phase, self.grid_coupling)
        for u in self.units.values():
            if u.cycles_completed > u._last_act_cycle:
                u._last_act_cycle = u.cycles_completed
                self._unit_act(u)
        self._compute_power_balance()
        if self.t_warmup <= self.t < self.t_stress:
            if (self.t - self._last_sample_normal) >= self.sample_interval:
                self._last_sample_normal = self.t
                for inv_id in self.phase_normal:
                    self.phase_normal[inv_id].append(self._inverter_state[inv_id]["phase"])
        elif (self.stress_type is not None
              and self.t >= (self.t_stress + self.burn_in)):
            if (self.t - self._last_sample_stress) >= self.sample_interval:
                self._last_sample_stress = self.t
                for inv_id in self.phase_stress:
                    self.phase_stress[inv_id].append(self._inverter_state[inv_id]["phase"])

    def _inject_stress(self) -> None:
        if self.stress_type is None:
            return
        if self.stress_type == "bewoelkung":
            self._stress_bewoelkung()
        elif self.stress_type == "spitzenlast":
            self._stress_spitzenlast()
        elif self.stress_type == "leitungsausfall":
            self._stress_leitungsausfall()

    def _stress_bewoelkung(self) -> None:
        for inv_id in self._inverter_state:
            if "pv_prosumer" in inv_id:
                self._inverter_state[inv_id]["capacity_factor"] = 0.1

    def _stress_spitzenlast(self) -> None:
        self.base_load *= 1.5

    def _stress_leitungsausfall(self) -> None:
        for inv_id in list(self._inverter_state.keys()):
            if "wind_turbine" in inv_id:
                self._inverter_state[inv_id]["capacity_factor"] = 0.0
                self._inverter_state[inv_id]["period"] = 100.0

    def _unit_act(self, unit: SmartGridUnit) -> None:
        # Class-B dispatch is step-synchronous in _compute_power_balance (spec).
        pass

    def _gen_and_load(self) -> tuple:
        gen_total = 0.0
        for inv_id, inv in self._inverter_state.items():
            if "pv_prosumer" in inv_id:
                base_cap = 50.0 / self.inverters_per_gen
            elif "wind_turbine" in inv_id:
                base_cap = 80.0 / self.inverters_per_gen
            else:
                base_cap = 100.0 / self.inverters_per_gen
            cf = inv["capacity_factor"] * (0.2 + 0.7 * self.rng.random())
            gen_total += base_cap * cf
        load = self.base_load * (1.0 + 0.25 * math.sin(TWO_PI * self.t / 1440.0))
        load += self.load_rng.uniform(-10.0, 10.0)
        load = max(load, 1.0)
        return gen_total, load

    def _compute_power_balance(self) -> None:
        gen_total, load = self._gen_and_load()
        deficit = max(0.0, load - gen_total)
        self.last_deficit = deficit
        caps = self._class_b_capacities()

        if self.plasticity:
            dispatch, _residual, self.soc = run_waterfall(
                deficit, caps, self.soc, self.shed_headroom,
            )
            self.flex_dispatch = dispatch
            flex_available = flex_available_treatment(dispatch)
        else:
            self.flex_dispatch = {uid: 0.0 for uid in WATERFALL_ORDER}
            flex_available = flex_available_null(caps)

        self.last_flex_available = flex_available
        served = min(gen_total + flex_available, load)
        w_dyn = max(0.0, min(1.0, served / load))

        if self.t_warmup <= self.t < self.t_stress:
            self.w_dyn_normal.append(w_dyn)
        elif self.t >= (self.t_stress + self.burn_in):
            self.w_dyn_stress.append(w_dyn)
            if self.plasticity:
                self.dispatch_stress_samples.append(flex_available)

    def compute_efficiency(self, window: str) -> Dict:
        if window == "normal":
            w = self.w_dyn_normal
        elif window == "stress":
            w = self.w_dyn_stress
        else:
            return {"mean_w_dyn": 0.0, "n_samples": 0}
        if not w:
            return {"mean_w_dyn": 0.0, "n_samples": 0}
        return {"mean_w_dyn": sum(w) / len(w), "n_samples": len(w)}
