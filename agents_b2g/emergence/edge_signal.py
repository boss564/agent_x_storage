#!/usr/bin/env python3
"""Edge state E_ij for KOPPLUNG_EIJ_v1 (BINDEND Pre-Reg).

e_ij = trust * freshness * (1 - risk)
Decay γ=0.05/tick · Thompson prior Beta(1,1) · risk_limit=0.80
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

GAMMA = 0.05
ALPHA0 = 1.0
BETA0 = 1.0
RISK_LIMIT = 0.80
S_NEU = 0.10
EdgeKey = Tuple[str, str]  # (sender_id, receiver_id)


@dataclass
class EdgeState:
    alpha: float = ALPHA0
    beta: float = BETA0
    trust: float = 0.5  # α/(α+β) at prior
    risk: float = 0.0
    freshness: float = 1.0
    last_tick: int = 0
    updates: int = 0
    ever_updated: bool = False

    def posterior_mean(self) -> float:
        return float(self.alpha / (self.alpha + self.beta))

    def scalar(self) -> float:
        return float(
            max(0.0, min(1.0, self.trust))
            * max(0.0, min(1.0, self.freshness))
            * (1.0 - max(0.0, min(1.0, self.risk)))
        )


class EdgeBook:
    """Directed edge store for the 27-agent swarm."""

    def __init__(self, *, gamma: float = GAMMA, risk_limit: float = RISK_LIMIT):
        self.gamma = float(gamma)
        self.risk_limit = float(risk_limit)
        self._edges: Dict[EdgeKey, EdgeState] = {}
        self._updated_in_window: Dict[EdgeKey, bool] = {}

    def get(self, i: str, j: str) -> Optional[EdgeState]:
        return self._edges.get((i, j))

    def ensure(self, i: str, j: str, tick: int = 0) -> EdgeState:
        key = (i, j)
        if key not in self._edges:
            self._edges[key] = EdgeState(last_tick=tick)
        return self._edges[key]

    def scalar(self, i: Optional[str], j: Optional[str]) -> float:
        if i is None or j is None:
            return 0.0
        e = self._edges.get((i, j))
        if e is None or not e.ever_updated:
            return 0.0
        return e.scalar()

    def thompson_sample(self, i: str, j: str, rng: random.Random) -> float:
        e = self.ensure(i, j)
        return float(rng.betavariate(max(e.alpha, 1e-9), max(e.beta, 1e-9)))

    def decay_all(self, tick: int) -> None:
        decay = math.exp(-self.gamma * 1.0)
        for e in self._edges.values():
            dt = max(0, int(tick) - int(e.last_tick))
            if dt <= 0:
                continue
            factor = math.exp(-self.gamma * dt)
            e.trust = max(0.0, min(1.0, e.trust * factor))
            e.risk = max(0.0, min(1.0, e.risk * factor))
            e.freshness = factor if e.ever_updated else e.freshness
            e.last_tick = int(tick)

    def record_success(self, i: str, j: str, tick: int) -> None:
        e = self.ensure(i, j, tick)
        e.alpha += 1.0
        e.trust = max(0.0, min(1.0, e.posterior_mean() + S_NEU))
        e.freshness = 1.0
        e.last_tick = int(tick)
        e.updates += 1
        e.ever_updated = True
        self._updated_in_window[(i, j)] = True

    def record_failure(self, i: str, j: str, tick: int, *, risk_bump: bool = True) -> None:
        e = self.ensure(i, j, tick)
        e.beta += 1.0
        e.trust = max(0.0, min(1.0, e.posterior_mean()))
        if risk_bump:
            e.risk = max(0.0, min(1.0, e.risk + S_NEU))
        e.freshness = 1.0
        e.last_tick = int(tick)
        e.updates += 1
        e.ever_updated = True
        self._updated_in_window[(i, j)] = True

    def apply_tx_gate(self, i: str, j: str, tick: int, *, delta_ok: bool) -> bool:
        """Z3-edge stub: admissible ⇔ Δ=0 ∧ risk≤limit. Returns True if success path."""
        e = self.ensure(i, j, tick)
        if (not delta_ok) or e.risk > self.risk_limit:
            self.record_failure(i, j, tick, risk_bump=True)
            return False
        self.record_success(i, j, tick)
        return True

    def reset_window_flags(self) -> None:
        self._updated_in_window = {k: False for k in self._edges}

    def window_updated(self, key: EdgeKey) -> bool:
        return bool(self._updated_in_window.get(key, False))


def evaluate_i1_edge(
    *,
    sticky_map_b: Mapping[Tuple[str, str], str],
    sticky_map_c: Mapping[Tuple[str, str], str],
    edge_hist: List[Dict[EdgeKey, float]],
    updated_flags: Mapping[EdgeKey, bool],
    run_seed: int,
    warmup: int,
    cycles: int,
    sigma_min: float = 0.05,
    mae_min: float = 0.05,
    upd_min: float = 0.40,
    rho_max: float = 0.90,
) -> Dict[str, Any]:
    """I1E-V/S/U/G — Pre-Reg KOPPLUNG_EIJ_v1 §4."""
    keys = list(sticky_map_b.keys())
    if not edge_hist or not keys:
        return {
            "verdict": "SIGNAL_BLIND",
            "i1_pass": False,
            "error": "empty edge hist or sticky map",
            "run_seed": run_seed,
        }

    def edge_key_for(sender_key: str, partner_id: str) -> EdgeKey:
        # sender_key may be "id" or "id:contract"
        sid = sender_key.split(":")[0]
        return (sid, partner_id)

    # Build per-sticky-edge scalar series from hist snapshots
    series_b: Dict[Tuple[str, str], List[float]] = {k: [] for k in keys}
    series_c: Dict[Tuple[str, str], List[float]] = {k: [] for k in keys}
    for snap in edge_hist:
        for sk_role, pid_b in sticky_map_b.items():
            sender_key, role = sk_role
            ek_b = edge_key_for(sender_key, pid_b)
            series_b[sk_role].append(float(snap.get(ek_b, 0.0)))
            pid_c = sticky_map_c.get(sk_role, pid_b)
            ek_c = edge_key_for(sender_key, pid_c)
            series_c[sk_role].append(float(snap.get(ek_c, 0.0)))

    # I1E-V: σ of e at last tick over sticky edges (B map)
    last_vals = [series_b[k][-1] for k in keys]
    n = len(last_vals)
    mean = sum(last_vals) / n
    sigma = math.sqrt(sum((x - mean) ** 2 for x in last_vals) / (n - 1)) if n > 1 else 0.0
    i1_v = bool(sigma >= sigma_min)

    # I1E-S: mean MAE over senders (sticky keys)
    maes = []
    for k in keys:
        sb, sc = series_b[k], series_c[k]
        maes.append(sum(abs(a - b) for a, b in zip(sb, sc)) / len(sb))
    mean_mae = sum(maes) / len(maes) if maes else 0.0
    i1_s = bool(mean_mae >= mae_min)

    # I1E-U: fraction of sticky edges with ≥1 update in window
    n_upd = 0
    for sender_key, role in keys:
        pid = sticky_map_b[(sender_key, role)]
        ek = edge_key_for(sender_key, pid)
        if updated_flags.get(ek, False):
            n_upd += 1
    frac_u = n_upd / len(keys) if keys else 0.0
    i1_u = bool(frac_u >= upd_min)

    # I1E-G: median |corr_t(e_ij, ē)| over sticky edges
    T = len(edge_hist)
    ebar = []
    for t in range(T):
        vals = [series_b[k][t] for k in keys]
        ebar.append(sum(vals) / len(vals))
    corrs: List[float] = []
    for k in keys:
        xs = series_b[k]
        mx = sum(xs) / T
        my = sum(ebar) / T
        num = sum((xs[t] - mx) * (ebar[t] - my) for t in range(T))
        dx = math.sqrt(sum((xs[t] - mx) ** 2 for t in range(T)))
        dy = math.sqrt(sum((ebar[t] - my) ** 2 for t in range(T)))
        if dx < 1e-12 or dy < 1e-12:
            continue
        corrs.append(abs(num / (dx * dy)))
    if len(corrs) < 14:
        i1_g = False
        median_rho = None
    else:
        sc = sorted(corrs)
        mid = len(sc) // 2
        median_rho = sc[mid] if len(sc) % 2 else 0.5 * (sc[mid - 1] + sc[mid])
        i1_g = bool(median_rho <= rho_max)

    i1_pass = bool(i1_v and i1_s and i1_u and i1_g)
    return {
        "pre_reg": "docs/KOPPLUNG_EIJ_v1_PREREG.md",
        "status": "BINDEND",
        "check": "I1-Edge",
        "run_seed": run_seed,
        "warmup": warmup,
        "cycles": cycles,
        "kappa": 0.0,
        "n_sticky_edges": len(keys),
        "criteria": {
            "I1E-V": {"value": round(sigma, 6), "threshold": sigma_min, "pass": i1_v},
            "I1E-S": {"value": round(mean_mae, 6), "threshold": mae_min, "pass": i1_s},
            "I1E-U": {
                "value": round(frac_u, 6),
                "threshold": upd_min,
                "pass": i1_u,
                "n_updated": n_upd,
            },
            "I1E-G": {
                "value": None if median_rho is None else round(median_rho, 6),
                "threshold": rho_max,
                "pass": i1_g,
                "n_corr": len(corrs),
            },
        },
        "i1_pass": i1_pass,
        "verdict": "I1_PASS" if i1_pass else "SIGNAL_BLIND",
        "params": {"gamma": GAMMA, "prior": "Beta(1,1)", "risk_limit": RISK_LIMIT},
    }
