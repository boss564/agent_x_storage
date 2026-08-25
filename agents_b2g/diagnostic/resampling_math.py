"""Lag-Spearman resampling math — Wave 38 Amendment A1.

Verdict-bearing alternative to non-discriminative P_sign (Bridge Diagnostic §5).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from agents_b2g.diagnostic.cte_math import (
    DIRECTION_IDS,
    OccupancyBundle,
    drivers_full,
)
from agents_b2g.diagnostic.live_prereg import Wave38Thresholds

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from bridge_stufe_a_v3_pipeline import cte_observed_grid  # noqa: E402


@dataclass
class ResamplingResult:
    resampling_fragment: str
    n_unstable_folds: int
    folds: list[dict[str, Any]]
    rho_min: float
    p_sign_descriptive: dict[str, Any] = field(default_factory=dict)
    peak_lag_retention: dict[str, float] = field(default_factory=dict)


def fold_ranges_for_n(n_bins: int, k_folds: int) -> list[tuple[int, int]]:
    """Equal-ish contiguous blocks; remainder absorbed by last fold."""
    if k_folds < 1 or n_bins < k_folds:
        raise ValueError(f"need n_bins >= k_folds (>=1), got {n_bins}/{k_folds}")
    base = n_bins // k_folds
    ranges: list[tuple[int, int]] = []
    for k in range(k_folds):
        start = k * base
        end = (k + 1) * base if k < k_folds - 1 else n_bins
        ranges.append((start, end))
    return ranges


def _rankdata(values: Sequence[float]) -> list[float]:
    """Average ranks for ties (1-based ranks)."""
    indexed = sorted(enumerate(values), key=lambda iv: iv[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for t in range(i, j + 1):
            ranks[indexed[t][0]] = avg
        i = j + 1
    return ranks


def spearman_rho(x: Sequence[float], y: Sequence[float]) -> float:
    """Spearman ρ; returns 0.0 if either series has zero rank variance."""
    if len(x) != len(y) or len(x) < 2:
        return 0.0
    rx = _rankdata(x)
    ry = _rankdata(y)
    mx = sum(rx) / len(rx)
    my = sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den_x = sum((a - mx) ** 2 for a in rx) ** 0.5
    den_y = sum((b - my) ** 2 for b in ry) ** 0.5
    if den_x < 1e-15 or den_y < 1e-15:
        return 0.0
    return num / (den_x * den_y)


def peak_lag(profile: Sequence[float]) -> int:
    if not profile:
        return -1
    return int(max(range(len(profile)), key=lambda i: profile[i]))


def _slice_occ(occ: Sequence[int], start: int, end: int) -> list[int]:
    return list(occ[start:end])


def _slice_drivers(drivers: list[list[int]], start: int, end: int) -> list[list[int]]:
    return [list(d[start:end]) for d in drivers]


def _p_sign(
    full: dict[str, list[float]], fold: dict[str, list[float]]
) -> dict[str, float]:
    out: dict[str, float] = {}
    for d in DIRECTION_IDS:
        matches = sum(
            1 for a, b in zip(full[d], fold[d]) if (a >= 0) == (b >= 0)
        )
        out[d] = matches / len(full[d]) if full[d] else 0.0
    return out


def run_lag_spearman_resampling(
    bundle: OccupancyBundle,
    thresholds: Wave38Thresholds,
) -> ResamplingResult:
    """Compute KFOLD_STABLE / KFOLD_UNSTABLE via Lag-Spearman (Pre-Reg §5A)."""
    k_folds = thresholds.k_folds
    n_bins = len(bundle.bridge_eth)
    ranges = fold_ranges_for_n(n_bins, k_folds)

    drivers = drivers_full(bundle.z_alt, bundle.z_neu_ter, bundle.candidate_ids)
    full_grid = cte_observed_grid(bundle.bridge_eth, bundle.bridge_gnosis, drivers)
    peak_full = {d: peak_lag(full_grid[d]) for d in DIRECTION_IDS}

    folds: list[dict[str, Any]] = []
    peak_hits = {d: 0 for d in DIRECTION_IDS}
    rho_values: list[float] = []

    for k, (start, end) in enumerate(ranges):
        eth_f = _slice_occ(bundle.bridge_eth, start, end)
        gno_f = _slice_occ(bundle.bridge_gnosis, start, end)
        drivers_f = _slice_drivers(drivers, start, end)
        fold_grid = cte_observed_grid(eth_f, gno_f, drivers_f)

        rho: dict[str, float] = {}
        peaks: dict[str, int] = {}
        for d in DIRECTION_IDS:
            rho[d] = round(spearman_rho(fold_grid[d], full_grid[d]), 6)
            peaks[d] = peak_lag(fold_grid[d])
            rho_values.append(rho[d])
            if peaks[d] == peak_full[d]:
                peak_hits[d] += 1

        rho_fold_min = min(rho.values())
        stable = rho_fold_min >= thresholds.rho_spearman_min
        p_sign = _p_sign(full_grid, fold_grid)
        folds.append(
            {
                "fold_index": k,
                "minute_range": [start, end],
                "rho_ab": rho["ab"],
                "rho_ba": rho["ba"],
                "rho_min": round(rho_fold_min, 6),
                "stable": stable,
                "peak_lag": peaks,
                "p_sign_ab": round(p_sign["ab"], 6),
                "p_sign_ba": round(p_sign["ba"], 6),
            }
        )

    n_unstable = sum(1 for f in folds if not f["stable"])
    fragment = (
        "KFOLD_STABLE"
        if n_unstable <= thresholds.n_unstable_folds_max
        else "KFOLD_UNSTABLE"
    )
    retention = {
        d: round(peak_hits[d] / k_folds, 6) if k_folds else 0.0 for d in DIRECTION_IDS
    }

    return ResamplingResult(
        resampling_fragment=fragment,
        n_unstable_folds=n_unstable,
        folds=folds,
        rho_min=round(min(rho_values) if rho_values else 0.0, 6),
        p_sign_descriptive={
            "note": "Descriptive only — TE non-negative; not verdict-bearing",
            "all_folds_p_sign": [
                {"fold": f["fold_index"], "ab": f["p_sign_ab"], "ba": f["p_sign_ba"]}
                for f in folds
            ],
        },
        peak_lag_retention=retention,
    )
