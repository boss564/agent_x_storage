#!/usr/bin/env python3
"""KANTEN_LEDGER_v1 — directed relationship memory E[i][j] ∈ ℝ^5.

ARCH_BINDEND: docs/KANTEN_LEDGER_v1_DRAFT.md
Update only on interaction (i,j). Decay γ=0.05/tick.
Not the sealed KOPPLUNG_EIJ_v1 EdgeBook.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

GAMMA = 0.05
K = 5
COMPONENT_NAMES: Tuple[str, ...] = (
    "interaction_count",
    "bilateral_balance",
    "trust_score",
    "avg_latency",
    "edge_risk",
)
LATENCY_EWMA = 0.3
RISK_UP = 0.10
RISK_DOWN = 0.05

EdgeKey = Tuple[str, str]


@dataclass
class LedgerEdge:
    interaction_count: float = 0.0
    bilateral_balance: float = 0.0
    alpha: float = 1.0
    beta: float = 1.0
    avg_latency: float = 0.0
    edge_risk: float = 0.0
    last_tick: int = 0
    updates: int = 0
    ever_updated: bool = False

    def trust_score(self) -> float:
        return float(self.alpha / (self.alpha + self.beta))

    def vec(self) -> List[float]:
        return [
            float(self.interaction_count),
            float(self.bilateral_balance),
            float(self.trust_score()),
            float(self.avg_latency),
            float(self.edge_risk),
        ]

    def component(self, idx: int) -> float:
        return self.vec()[idx]


class LedgerBook:
    """Directed ledger: write only on (i,j) interaction."""

    def __init__(self, *, gamma: float = GAMMA):
        self.gamma = float(gamma)
        self._edges: Dict[EdgeKey, LedgerEdge] = {}
        self._updated_in_window: Dict[EdgeKey, bool] = {}

    def ensure(self, i: str, j: str, tick: int = 0) -> LedgerEdge:
        key = (i, j)
        if key not in self._edges:
            self._edges[key] = LedgerEdge(last_tick=tick)
        return self._edges[key]

    def get(self, i: str, j: str) -> Optional[LedgerEdge]:
        return self._edges.get((i, j))

    def component(self, i: str, j: str, idx: int) -> float:
        e = self._edges.get((i, j))
        if e is None or not e.ever_updated:
            return 0.0
        return e.component(idx)

    def decay_edge(self, e: LedgerEdge, tick: int) -> None:
        dt = max(0, int(tick) - int(e.last_tick))
        if dt <= 0 or not e.ever_updated:
            e.last_tick = int(tick)
            return
        factor = math.exp(-self.gamma * dt)
        # counts/balances: exponential fade of history
        e.interaction_count *= factor
        e.bilateral_balance *= factor
        e.avg_latency *= factor
        e.edge_risk = max(0.0, min(1.0, e.edge_risk * factor))
        e.last_tick = int(tick)

    def decay_all(self, tick: int) -> None:
        for e in self._edges.values():
            self.decay_edge(e, tick)

    def update(
        self,
        i: str,
        j: str,
        tick: int,
        *,
        success: bool,
        signed_net: float = 0.0,
        latency: float = 1.0,
    ) -> LedgerEdge:
        """Apply decay since last touch, then S_neu for this interaction."""
        if i == j:
            raise ValueError("no self-edges")
        e = self.ensure(i, j, tick)
        self.decay_edge(e, tick)

        # S_neu (§ ARCH_BINDEND mapping)
        e.interaction_count += 1.0
        e.bilateral_balance += float(signed_net)
        if success:
            e.alpha += 1.0
            e.edge_risk = max(0.0, min(1.0, e.edge_risk - RISK_DOWN))
        else:
            e.beta += 1.0
            e.edge_risk = max(0.0, min(1.0, e.edge_risk + RISK_UP))
        lat = max(0.0, float(latency))
        if e.updates == 0 and not e.ever_updated:
            e.avg_latency = lat
        else:
            e.avg_latency = (
                (1.0 - LATENCY_EWMA) * e.avg_latency + LATENCY_EWMA * lat
            )

        e.updates += 1
        e.ever_updated = True
        e.last_tick = int(tick)
        self._updated_in_window[(i, j)] = True
        return e

    def snapshot_component(self, idx: int) -> Dict[EdgeKey, float]:
        return {
            k: e.component(idx)
            for k, e in self._edges.items()
            if e.ever_updated
        }

    def reset_window_flags(self) -> None:
        self._updated_in_window = {k: False for k in self._edges}

    def window_updated(self, key: EdgeKey) -> bool:
        return bool(self._updated_in_window.get(key, False))


def _corr_abs(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    T = len(xs)
    if T < 2 or len(ys) != T:
        return None
    mx = sum(xs) / T
    my = sum(ys) / T
    num = sum((xs[t] - mx) * (ys[t] - my) for t in range(T))
    dx = math.sqrt(sum((xs[t] - mx) ** 2 for t in range(T)))
    dy = math.sqrt(sum((ys[t] - my) ** 2 for t in range(T)))
    if dx < 1e-12 or dy < 1e-12:
        return None
    return abs(num / (dx * dy))


def screen_ledger_component(
    *,
    sticky_map_b: Mapping[Tuple[str, str], str],
    sticky_map_c: Mapping[Tuple[str, str], str],
    edge_hist: List[Dict[EdgeKey, float]],
    component: str,
    mae_min: float = 0.05,
    rho_max: float = 0.90,
) -> Dict[str, Any]:
    """S-S / S-G on one ledger component (sticky edges). Near-miss reported."""
    keys = list(sticky_map_b.keys())
    if not edge_hist or not keys:
        return {
            "component": component,
            "pass": False,
            "flags": {"S_S": False, "S_G": False},
            "error": "empty hist or map",
        }

    def edge_key_for(sender_key: str, partner_id: str) -> EdgeKey:
        return (sender_key.split(":")[0], partner_id)

    series_b: Dict[Tuple[str, str], List[float]] = {k: [] for k in keys}
    series_c: Dict[Tuple[str, str], List[float]] = {k: [] for k in keys}
    for snap in edge_hist:
        for sk_role, pid_b in sticky_map_b.items():
            sender_key, _role = sk_role
            ek_b = edge_key_for(sender_key, pid_b)
            series_b[sk_role].append(float(snap.get(ek_b, 0.0)))
            pid_c = sticky_map_c.get(sk_role, pid_b)
            ek_c = edge_key_for(sender_key, pid_c)
            series_c[sk_role].append(float(snap.get(ek_c, 0.0)))

    maes = []
    for k in keys:
        sb, sc = series_b[k], series_c[k]
        maes.append(sum(abs(a - b) for a, b in zip(sb, sc)) / len(sb))
    mean_mae = sum(maes) / len(maes) if maes else 0.0
    flag_s = bool(mean_mae >= mae_min)

    T = len(edge_hist)
    ebar = [
        sum(series_b[k][t] for k in keys) / len(keys) for t in range(T)
    ]
    corrs: List[float] = []
    for k in keys:
        c = _corr_abs(series_b[k], ebar)
        if c is not None:
            corrs.append(c)
    if len(corrs) < 14:
        median_rho = None
        flag_g = False
    else:
        sc = sorted(corrs)
        mid = len(sc) // 2
        median_rho = sc[mid] if len(sc) % 2 else 0.5 * (sc[mid - 1] + sc[mid])
        flag_g = bool(median_rho <= rho_max)

    near_s = (0.03 <= mean_mae < mae_min)
    near_g = (
        median_rho is not None
        and rho_max < float(median_rho) <= 0.95
    )

    return {
        "component": component,
        "mae": round(mean_mae, 6),
        "median_abs_rho": None if median_rho is None else round(median_rho, 6),
        "n_sticky": len(keys),
        "n_corr": len(corrs),
        "flags": {
            "S_S": flag_s,
            "S_G": flag_g,
            "candidate": bool(flag_s and flag_g),
            "near_miss": bool((not (flag_s and flag_g)) and (near_s or near_g)),
        },
        "pass": bool(flag_s and flag_g),
    }
