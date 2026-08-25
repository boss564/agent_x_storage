#!/usr/bin/env python3
"""Zustandsraum-Screening: I1-S / I1-G (und σ) über alle Trace-Dimensionen.

Kein Studien-Verdict, keine Pre-Reg. Charakterisiert den Zustandsraum.
Kandidaten aus diesem Lauf dürfen NICHT im selben Datensatz als Hypothese
getestet werden — nächste Studie = neuer DRAFT + neue Läufe.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


def _sample_sigma(values: Sequence[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    m = sum(values) / n
    return math.sqrt(sum((x - m) ** 2 for x in values) / (n - 1))


def _median(xs: List[float]) -> Optional[float]:
    if not xs:
        return None
    s = sorted(xs)
    mid = len(s) // 2
    if len(s) % 2:
        return s[mid]
    return 0.5 * (s[mid - 1] + s[mid])


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


def minmax_scale_panel(hist: List[List[float]]) -> List[List[float]]:
    """Scale one dimension's T×N panel to [0,1] over the full window."""
    flat = [v for row in hist for v in row]
    if not flat:
        return hist
    lo, hi = min(flat), max(flat)
    span = hi - lo
    if span < 1e-15:
        return [[0.0 for _ in row] for row in hist]
    return [[(v - lo) / span for v in row] for row in hist]


def mae_under_permutation(
    hist: List[List[float]],
    agent_ids: Sequence[str],
    map_b: Mapping[Tuple[str, str], str],
    map_c: Mapping[Tuple[str, str], str],
) -> Tuple[float, int]:
    """Mean over sticky edges of MAE_t(|x_pB − x_pC|). Same construction as I1-S."""
    id_to_idx = {aid: i for i, aid in enumerate(agent_ids)}
    maes: List[float] = []
    for key, pid_b in (map_b or {}).items():
        pid_c = (map_c or {}).get(key)
        if pid_c is None:
            continue
        ib = id_to_idx.get(pid_b)
        ic = id_to_idx.get(pid_c)
        if ib is None or ic is None:
            continue
        errs = [abs(row[ib] - row[ic]) for row in hist]
        if errs:
            maes.append(sum(errs) / len(errs))
    if not maes:
        return 0.0, 0
    return sum(maes) / len(maes), len(maes)


def median_abs_corr_to_mean(
    hist: List[List[float]],
    *,
    min_corr_agents: int = 14,
) -> Tuple[Optional[float], int, bool]:
    """Median |corr_t(x_i, x̄)| — same construction as I1-G.

    Returns (median_rho, n_corr, enough_agents).
    """
    if not hist:
        return None, 0, False
    T = len(hist)
    n = len(hist[0])
    hbar = [sum(hist[t][i] for i in range(n)) / n for t in range(T)]
    corrs: List[float] = []
    for i in range(n):
        xs = [hist[t][i] for t in range(T)]
        c = _corr_abs(xs, hbar)
        if c is not None:
            corrs.append(c)
    med = _median(corrs)
    enough = len(corrs) >= min_corr_agents
    return med, len(corrs), enough


def screen_dimension(
    hist: List[List[float]],
    *,
    agent_ids: Sequence[str],
    map_b: Mapping[Tuple[str, str], str],
    map_c: Mapping[Tuple[str, str], str],
    name: str,
    mae_min: float = 0.05,
    rho_max: float = 0.90,
    sigma_min: float = 0.0,
) -> Dict[str, Any]:
    """Characterize one state dimension. Flags are screening labels, not study verdicts."""
    n = len(agent_ids)
    last = [float(x) for x in hist[-1]] if hist else [0.0] * n
    sigma = _sample_sigma(last)

    # Time variation: max over agents of (max_t - min_t)
    ranges = []
    for i in range(n):
        series = [row[i] for row in hist]
        ranges.append(max(series) - min(series) if series else 0.0)
    max_agent_range = max(ranges) if ranges else 0.0
    static = max_agent_range < 1e-12

    mae_raw, n_edges = mae_under_permutation(hist, agent_ids, map_b, map_c)
    scaled = minmax_scale_panel(hist)
    mae_scaled, _ = mae_under_permutation(scaled, agent_ids, map_b, map_c)

    rho, n_corr, enough = median_abs_corr_to_mean(hist)
    rho_scaled, _, _ = median_abs_corr_to_mean(scaled)

    # Screening flags (same numeric cutoffs as I1-S/G on scaled signal)
    # Static config dims can show high MAE (heterogeneity) but are not dynamical signals.
    flag_s = (not static) and mae_scaled >= mae_min
    flag_g = bool((not static) and enough and rho is not None and rho <= rho_max)
    flag_v = sigma > sigma_min
    candidate = bool(flag_s and flag_g and flag_v)

    return {
        "dimension": name,
        "static_over_window": static,
        "sigma_last": round(sigma, 6),
        "mae_raw": round(mae_raw, 6),
        "mae_scaled": round(mae_scaled, 6),
        "median_abs_rho": None if rho is None else round(rho, 6),
        "median_abs_rho_scaled": None if rho_scaled is None else round(rho_scaled, 6),
        "n_edges": n_edges,
        "n_corr": n_corr,
        "flags": {
            "variance": flag_v,
            "partner_selective_scaled": flag_s,
            "not_global": flag_g,
            "candidate": candidate,
        },
    }


def screen_state_matrix(
    states,  # np.ndarray T×N×D
    state_keys: Sequence[str],
    agent_ids: Sequence[str],
    map_b: Mapping[Tuple[str, str], str],
    map_c: Mapping[Tuple[str, str], str],
    *,
    mae_min: float = 0.05,
    rho_max: float = 0.90,
    skip_prefixes: Sequence[str] = (),
) -> Dict[str, Any]:
    """Run screening over all dimensions of a SwarmTrace state tensor."""
    import numpy as np

    arr = np.asarray(states, dtype=float)
    T, N, D = arr.shape
    if N != len(agent_ids):
        raise ValueError("agent_ids length mismatch")
    if D != len(state_keys):
        raise ValueError("state_keys length mismatch")

    rows: List[Dict[str, Any]] = []
    for d, name in enumerate(state_keys):
        if any(name.startswith(p) for p in skip_prefixes):
            continue
        hist = [[float(arr[t, i, d]) for i in range(N)] for t in range(T)]
        rows.append(
            screen_dimension(
                hist,
                agent_ids=agent_ids,
                map_b=map_b,
                map_c=map_c,
                name=name,
                mae_min=mae_min,
                rho_max=rho_max,
            )
        )

    candidates = [r["dimension"] for r in rows if r["flags"]["candidate"]]
    # Sort: candidate first, then by mae_scaled desc
    rows.sort(key=lambda r: (not r["flags"]["candidate"], -r["mae_scaled"]))

    if candidates:
        outcome = "SOME_CANDIDATES"
    else:
        near = [
            r
            for r in rows
            if (not r.get("static_over_window"))
            and r["mae_scaled"] >= mae_min * 0.5
        ]
        if near:
            outcome = "NONE_CLOSE"
        else:
            outcome = "NONE_CLEAR"

    return {
        "kind": "state_space_screening",
        "not_a_study": True,
        "harking_guard": (
            "Candidates must not be hypothesis-tested on this same run. "
            "Next study = new DRAFT Pre-Reg + new seeds/runs."
        ),
        "T": T,
        "N": N,
        "D_screened": len(rows),
        "mae_min": mae_min,
        "rho_max": rho_max,
        "outcome": outcome,
        "candidates": candidates,
        "dimensions": rows,
    }
