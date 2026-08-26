#!/usr/bin/env python3
"""Event-driven prototype — discrete impulses only (no continuous ℓ(t)).

Engineering screen only — no Pre-Reg / no sweep.
Gate: ΔR_i > 0  ∧  median |ρ| < 0.90
Fail A or B → discard (no docs overhead).
"""
from __future__ import annotations

import math
import zlib
from typing import Any, Dict, List, Sequence, Tuple

from response_rij import AgentP, assign_p, r_ij, FORMULA_V02

EPS = 1e-9
RHO_MAX = 0.90
N_AGENTS = 9
N_EVENTS_PER_AGENT = 64
S_LOW = 0.5
S_HIGH = 2.0


def _crc_u01(material: str) -> float:
    return (zlib.crc32(material.encode()) & 0xFFFFFFFF) / 0xFFFFFFFF


def _corr_abs(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    n = len(xs)
    if n < 2 or len(ys) != n:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((xs[t] - mx) * (ys[t] - my) for t in range(n))
    dx = math.sqrt(sum((xs[t] - mx) ** 2 for t in range(n)))
    dy = math.sqrt(sum((ys[t] - my) ** 2 for t in range(n)))
    if dx < 1e-12 or dy < 1e-12:
        return None
    return abs(num / (dx * dy))


def _event_schedule(agent_id: str, run_seed: int, n: int) -> List[Tuple[float, float]]:
    """Irregular (time, payload S) impulses — agent-private clock, no shared tick."""
    out: List[Tuple[float, float]] = []
    t = 0.0
    for k in range(n):
        # Inter-arrival jitter unique per agent+seed+k (no global metronome)
        gap = 0.4 + 1.6 * _crc_u01(f"{run_seed}|{agent_id}|gap|{k}")
        t += gap
        # Bimodal payload: settlement-like high vs probe low (discrete levels)
        u = _crc_u01(f"{run_seed}|{agent_id}|S|{k}")
        s = S_HIGH if u > 0.45 else S_LOW
        # Small continuous jitter on payload — still event-local, not EWMA stream
        s *= 0.85 + 0.30 * _crc_u01(f"{run_seed}|{agent_id}|Sj|{k}")
        out.append((t, float(s)))
    return out


def run_event_driven_cell(*, run_seed: int) -> Dict[str, Any]:
    """One seed: discrete-event R series → ρ-screen + ΔR screen."""
    agent_ids = [f"E{i:02d}" for i in range(1, N_AGENTS + 1)]
    p_of = assign_p(agent_ids)
    # σ from pooled payloads (frozen after schedule build)
    all_s: List[float] = []
    schedules: Dict[str, List[Tuple[float, float]]] = {}
    for aid in agent_ids:
        schedules[aid] = _event_schedule(aid, run_seed, N_EVENTS_PER_AGENT)
        all_s.extend(s for _t, s in schedules[aid])
    mean_s = sum(all_s) / len(all_s)
    sigma = math.sqrt(
        sum((x - mean_s) ** 2 for x in all_s) / (len(all_s) - 1)
    )
    if sigma < EPS:
        sigma = 1.0

    # Per-agent: γ only updates on own events (stateful memory, event-triggered)
    series: Dict[str, List[float]] = {}
    delta_rs: List[float] = []
    for aid in agent_ids:
        p = p_of[aid]
        gamma = 0.05
        rs: List[float] = []
        r_low: List[float] = []
        r_high: List[float] = []
        for _t, s in schedules[aid]:
            # Event-local γ bump from payload (no continuous decay tick loop)
            gamma = math.tanh(gamma + 0.08 * (s - mean_s) / sigma)
            r = r_ij(s, gamma, p, sigma, formula=FORMULA_V02)
            rs.append(r)
            if s < (S_LOW + S_HIGH) / 2:
                r_low.append(r)
            else:
                r_high.append(r)
        series[aid] = rs
        if r_low and r_high:
            # ΔR_i: mean response gap between discrete payload classes
            delta_rs.append(abs(sum(r_high) / len(r_high) - sum(r_low) / len(r_low)))
        else:
            delta_rs.append(0.0)

    # Align by ordinal event index (not wall-clock) — tests shape commonality
    # without a shared continuous carrier.
    T = N_EVENTS_PER_AGENT
    ebar = [
        sum(series[aid][t] for aid in agent_ids) / N_AGENTS for t in range(T)
    ]
    corrs: List[float] = []
    for aid in agent_ids:
        c = _corr_abs(series[aid], ebar)
        if c is not None:
            corrs.append(c)
    med_rho = sorted(corrs)[len(corrs) // 2] if corrs else 1.0
    mean_delta_r = sum(delta_rs) / len(delta_rs) if delta_rs else 0.0

    flag_a = bool(med_rho < RHO_MAX and len(corrs) >= N_AGENTS)
    flag_b = bool(mean_delta_r > 0.0 and all(d > 0.0 for d in delta_rs))
    passed = bool(flag_a and flag_b)

    return {
        "run_seed": run_seed,
        "strand": "event_driven",
        "n_agents": N_AGENTS,
        "n_events_per_agent": N_EVENTS_PER_AGENT,
        "median_abs_rho": round(med_rho, 6),
        "n_corr": len(corrs),
        "mean_delta_r": round(mean_delta_r, 6),
        "min_delta_r": round(min(delta_rs), 6) if delta_rs else 0.0,
        "layer_a_pass": flag_a,  # median |ρ| < 0.90
        "layer_b_pass": flag_b,  # ΔR_i > 0 (all agents)
        "pass": passed,
        "sigma_s": round(sigma, 6),
        "formula": FORMULA_V02,
        "note": "discrete impulses only; no continuous ℓ(t) / shared tick EWMA",
    }
