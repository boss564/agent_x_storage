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
# M7 spike (docs/THREAT_MODEL_POST_QUANTUM_v0.md §3.5): engineering, not Pre-Reg
LATENCY_MODE_EWMA = "ewma"
LATENCY_MODE_M7 = "median_m7"          # aggressive — loses sticky-ℓ selectivity
LATENCY_MODE_M7_TRIM = "trimmed_m7"    # MAD + upper-tail trim (canonical candidate)
LATENCY_MODE_EWMA_GATE = "ewma_gate"    # EWMA intake, reject extreme spikes via MAD
LATENCY_N_MIN = 14
LATENCY_WINDOW_CAP = 64
LATENCY_TRIM_FRAC = 0.1  # symmetric trimmed-mean tails (legacy flag)
LATENCY_TRIM_HIGH_FRAC = 0.10  # delay spikes live in the upper tail
LATENCY_MAD_K = 3.0

_LATENCY_MODES = {
    LATENCY_MODE_EWMA,
    LATENCY_MODE_M7,
    LATENCY_MODE_M7_TRIM,
    LATENCY_MODE_EWMA_GATE,
}

EdgeKey = Tuple[str, str]


def _median(xs: Sequence[float]) -> float:
    ys = sorted(float(x) for x in xs)
    n = len(ys)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2:
        return ys[mid]
    return 0.5 * (ys[mid - 1] + ys[mid])


def _mad(xs: Sequence[float], med: float) -> float:
    if not xs:
        return 0.0
    return _median([abs(float(x) - med) for x in xs])


def _trimmed_mean(xs: Sequence[float], frac: float = LATENCY_TRIM_FRAC) -> float:
    ys = sorted(float(x) for x in xs)
    n = len(ys)
    if n == 0:
        return 0.0
    k = int(n * frac)
    if 2 * k >= n:
        return _median(ys)
    core = ys[k : n - k] if k > 0 else ys
    return sum(core) / len(core)


def _upper_trimmed_mean(
    xs: Sequence[float], frac: float = LATENCY_TRIM_HIGH_FRAC
) -> float:
    """Drop only the highest frac — delay attacks inflate the upper tail."""
    ys = sorted(float(x) for x in xs)
    n = len(ys)
    if n == 0:
        return 0.0
    k = int(n * frac)
    if k >= n:
        return _median(ys)
    core = ys[: n - k] if k > 0 else ys
    return sum(core) / len(core)


def robust_latency_from_window(
    samples: Sequence[float],
    *,
    n_min: int = LATENCY_N_MIN,
    estimator: str = "median",
) -> Tuple[Optional[float], str]:
    """Return (ℓ, status). status: ok | thin | empty.

    estimator: median | trimmed | upper_trim
    MAD gate first (extreme outliers), then estimator on kept samples.
    """
    vals = [float(x) for x in samples if x is not None]
    n = len(vals)
    if n == 0:
        return None, "empty"
    if n < n_min:
        return None, "thin"
    med = _median(vals)
    mad = _mad(vals, med)
    if mad > 1e-12:
        kept = [
            v for v in vals
            if abs(v - med) <= LATENCY_MAD_K * mad
        ]
        if len(kept) < max(n_min, (n + 1) // 2):
            kept = list(vals)  # MAD wiped too much — fall back to full window
    else:
        kept = list(vals)
    est = str(estimator).lower()
    if est == "upper_trim":
        return _upper_trimmed_mean(kept), "ok"
    if est in {"trimmed", "trimmed_mean"}:
        return _trimmed_mean(kept), "ok"
    return _median(kept), "ok"


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
    # M7: raw latency window (settlement-weighted samples only when mode=m7)
    latency_samples: List[float] = field(default_factory=list)
    latency_evaluable: bool = False
    latency_status: str = "empty"  # ok | thin | empty | ewma

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

    def __init__(
        self,
        *,
        gamma: float = GAMMA,
        latency_mode: str = LATENCY_MODE_EWMA,
        latency_n_min: int = LATENCY_N_MIN,
        use_trimmed_mean: bool = False,
        m7_settlement_only: bool = False,
    ):
        self.gamma = float(gamma)
        mode = str(latency_mode).lower()
        if mode not in _LATENCY_MODES:
            raise ValueError(f"latency_mode={latency_mode}")
        self.latency_mode = mode
        self.latency_n_min = int(latency_n_min)
        # Legacy bool: if True with median_m7, treat as trimmed estimator
        self.use_trimmed_mean = bool(use_trimmed_mean)
        # False = engineering spike (all samples); True = §3.7 strict
        self.m7_settlement_only = bool(m7_settlement_only)
        self._edges: Dict[EdgeKey, LedgerEdge] = {}
        self._updated_in_window: Dict[EdgeKey, bool] = {}

    def _m7_estimator(self) -> str:
        if self.latency_mode == LATENCY_MODE_M7_TRIM:
            return "upper_trim"
        if self.latency_mode == LATENCY_MODE_M7 and self.use_trimmed_mean:
            return "trimmed"
        return "median"

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
        settlement_touch = abs(float(signed_net)) > 1e-12

        if self.latency_mode == LATENCY_MODE_EWMA:
            if e.updates == 0 and not e.ever_updated:
                e.avg_latency = lat
            else:
                e.avg_latency = (
                    (1.0 - LATENCY_EWMA) * e.avg_latency + LATENCY_EWMA * lat
                )
            e.latency_evaluable = True
            e.latency_status = "ewma"
        elif self.latency_mode == LATENCY_MODE_EWMA_GATE:
            # Keep window for MAD gate; EWMA only accepts non-extreme samples
            # once n ≥ n_min (thin windows stay provisional, not "robust").
            accept = settlement_touch or (not self.m7_settlement_only)
            if accept:
                e.latency_samples.append(lat)
                if len(e.latency_samples) > LATENCY_WINDOW_CAP:
                    e.latency_samples = e.latency_samples[-LATENCY_WINDOW_CAP:]
            n = len(e.latency_samples)
            take = True
            if n >= self.latency_n_min:
                med = _median(e.latency_samples)
                mad = _mad(e.latency_samples, med)
                if mad > 1e-12 and abs(lat - med) > LATENCY_MAD_K * mad:
                    take = False
                    e.edge_risk = max(0.0, min(1.0, e.edge_risk + RISK_UP))
            if take:
                if e.updates == 0 and not e.ever_updated:
                    e.avg_latency = lat
                else:
                    e.avg_latency = (
                        (1.0 - LATENCY_EWMA) * e.avg_latency + LATENCY_EWMA * lat
                    )
            e.latency_evaluable = n >= self.latency_n_min
            e.latency_status = "ok" if e.latency_evaluable else (
                "thin" if n > 0 else "empty"
            )
            if not settlement_touch:
                e.edge_risk = max(0.0, min(1.0, e.edge_risk + 0.5 * RISK_UP))
        else:
            # M7 window: settlement-only when m7_settlement_only (§3.7);
            # spike default accepts all samples so ℓ remains measurable.
            accept = settlement_touch or (not self.m7_settlement_only)
            if accept:
                e.latency_samples.append(lat)
                if len(e.latency_samples) > LATENCY_WINDOW_CAP:
                    e.latency_samples = e.latency_samples[-LATENCY_WINDOW_CAP:]
            if not settlement_touch:
                e.edge_risk = max(0.0, min(1.0, e.edge_risk + 0.5 * RISK_UP))

            ell, status = robust_latency_from_window(
                e.latency_samples,
                n_min=self.latency_n_min,
                estimator=self._m7_estimator(),
            )
            e.latency_status = status
            if status == "ok" and ell is not None:
                e.avg_latency = float(ell)
                e.latency_evaluable = True
            else:
                # thin/empty: not evaluable — do not claim robust ℓ
                e.latency_evaluable = False
                if status == "thin":
                    e.edge_risk = max(0.0, min(1.0, e.edge_risk + RISK_UP))
                # keep last avg_latency if any; else provisional last sample
                if e.updates == 0 and not e.ever_updated and settlement_touch:
                    e.avg_latency = lat

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
