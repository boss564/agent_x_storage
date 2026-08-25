"""Stufe-A statistics: Hawkes histogram kernel, jitter/shuffle nulls, BH-FDR, verdict.

Captures live chain data elsewhere. This module is deterministic given timestamps
and an RNG seed.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import Counter
from math import log2, sqrt
from typing import Iterable, Sequence

from bridge_stufe_a_config import (
    DELTA_TAU_SEC,
    DRIVER_COVERAGE_MIN,
    JITTER_SECONDS,
    LAGS_MIN,
    N_MIN_EVENTS,
    WINDOW_END_UTC,
    WINDOW_START_UTC,
)

WINDOW_START_TS = WINDOW_START_UTC.timestamp()
WINDOW_END_TS = WINDOW_END_UTC.timestamp()


def plus_one_p(observed: float, surrogates: Sequence[float], *, greater: bool = True) -> float:
    """Conservative Monte-Carlo p: (1 + #{surr ⋈ obs}) / (1 + n)."""
    n = len(surrogates)
    if n == 0:
        raise ValueError("need surrogates")
    if greater:
        hits = sum(1 for s in surrogates if s >= observed)
    else:
        hits = sum(1 for s in surrogates if s <= observed)
    return (1 + hits) / (1 + n)


def jitter_timestamps(
    times: Sequence[float],
    rng,
    *,
    window_start: float = WINDOW_START_TS,
    window_end: float = WINDOW_END_TS,
    jitter: float = JITTER_SECONDS,
    max_draws: int = 10_000,
) -> list[float]:
    """Shift each event by U(-jitter, +jitter); redraw until inside the window."""
    out: list[float] = []
    append = out.append
    uniform = rng.uniform
    for t in times:
        for _ in range(max_draws):
            candidate = t + uniform(-jitter, jitter)
            if window_start <= candidate <= window_end:
                append(candidate)
                break
        else:
            raise RuntimeError("jitter rejection sampler failed to stay in window")
    out.sort()
    return out


def hawkes_gamma_histogram(
    src: Sequence[float],
    tgt: Sequence[float],
    *,
    lags_min: Sequence[int] = LAGS_MIN,
    delta_tau: float = DELTA_TAU_SEC,
    window_start: float = WINDOW_START_TS,
    window_end: float = WINDOW_END_TS,
) -> list[float]:
    """Nonparametric excitation kernel γ̂(τ) at 1-minute lags (pre-reg §4).

    Counts are identical to per-lag bisect_left on [s+τ, s+τ+Δτ). Numpy
    searchsorted is the same left-side count, used when available.
    """
    t_len = window_end - window_start
    if t_len <= 0:
        raise ValueError("empty window")
    n_src = len(src)
    n_tgt = len(tgt)
    lam_tgt = n_tgt / t_len
    lags = list(lags_min)
    n_lags = len(lags)
    if n_src == 0:
        return [0.0] * n_lags
    tgt_sorted = sorted(tgt)
    counts = [0] * n_lags
    n_complete = [0] * n_lags
    try:
        import numpy as np
    except ImportError:
        np = None
    if np is not None:
        src_a = np.asarray(src, dtype=np.float64)
        tgt_a = np.asarray(tgt_sorted, dtype=np.float64)
        for i, lag in enumerate(lags):
            lo = src_a + lag * delta_tau
            hi = lo + delta_tau
            ok = hi <= window_end
            n_c = int(np.count_nonzero(ok))
            n_complete[i] = n_c
            if n_c == 0:
                continue
            counts[i] = int(
                (
                    np.searchsorted(tgt_a, hi[ok], side="left")
                    - np.searchsorted(tgt_a, lo[ok], side="left")
                ).sum()
            )
    else:
        for s in src:
            for i, lag in enumerate(lags):
                tau = lag * delta_tau
                lo = s + tau
                hi = s + tau + delta_tau
                if hi > window_end:
                    continue
                n_complete[i] += 1
                counts[i] += bisect_left(tgt_sorted, hi) - bisect_left(tgt_sorted, lo)
    gammas: list[float] = []
    for i in range(n_lags):
        if n_complete[i] == 0:
            gammas.append(0.0)
        else:
            gammas.append((counts[i] / (n_complete[i] * delta_tau)) - lam_tgt)
    return gammas


def benjamini_hochberg(p_values: Sequence[float], q: float = 0.05) -> list[bool]:
    """BH-FDR: reject where p_(i) <= q * i / m. Returns mask in original order."""
    m = len(p_values)
    if m == 0:
        return []
    if not 0 < q <= 1:
        raise ValueError("q must be in (0, 1]")
    order = sorted(range(m), key=lambda i: p_values[i])
    reject = [False] * m
    max_k = -1
    for rank, idx in enumerate(order, start=1):
        if p_values[idx] <= q * rank / m:
            max_k = rank
    if max_k >= 0:
        for rank, idx in enumerate(order, start=1):
            if rank <= max_k:
                reject[idx] = True
    return reject


def occupancy_1min(
    times: Sequence[float],
    *,
    window_start: float,
    window_end: float,
    bin_sec: float = 60.0,
) -> list[int]:
    n_bins = int((window_end - window_start) // bin_sec)
    occ = [0] * n_bins
    for t in times:
        if t < window_start or t > window_end:
            continue
        idx = int((t - window_start) // bin_sec)
        if 0 <= idx < n_bins:
            occ[idx] = 1
    return occ


def interpolate_short_gaps(values: list[float | None], max_gap: int = 5) -> list[float | None]:
    """Linear fill of interior NaN-runs of length <= max_gap. Longer runs stay None."""
    out = list(values)
    n = len(out)
    i = 0
    while i < n:
        if out[i] is not None:
            i += 1
            continue
        j = i
        while j < n and out[j] is None:
            j += 1
        gap = j - i
        left = out[i - 1] if i > 0 else None
        right = out[j] if j < n else None
        if left is not None and right is not None and gap <= max_gap:
            for k in range(i, j):
                w = (k - i + 1) / (gap + 1)
                out[k] = left + w * (right - left)
        i = j
    return out


def driver_coverage(gas: Sequence[float | None], btc: Sequence[float | None], cex: Sequence[float | None]) -> float:
    n = len(gas)
    if n == 0 or n != len(btc) or n != len(cex):
        raise ValueError("driver series length mismatch")
    ok = sum(1 for a, b, c in zip(gas, btc, cex) if a is not None and b is not None and c is not None)
    return ok / n


def zscore_finite(values: Sequence[float | None]) -> list[float | None]:
    finite = [v for v in values if v is not None]
    if len(finite) < 2:
        return [None if v is None else 0.0 for v in values]
    mean = sum(finite) / len(finite)
    var = sum((v - mean) ** 2 for v in finite) / len(finite)
    sd = sqrt(var) if var > 0 else 1.0
    return [None if v is None else (v - mean) / sd for v in values]


def tertile_edges(values: Sequence[float]) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    ordered = sorted(values)
    n = len(ordered)
    return (ordered[n // 3], ordered[(2 * n) // 3])


def apply_tertiles(values: Sequence[float | None], edges: tuple[float, float]) -> list[int]:
    """Encode into {0,1,2}; NaN → -1 (dropped in CTE). Edges frozen from observation."""
    e1, e2 = edges
    out: list[int] = []
    for v in values:
        if v is None:
            out.append(-1)
        elif v <= e1:
            out.append(0)
        elif v <= e2:
            out.append(1)
        else:
            out.append(2)
    return out


def encode_drivers_tertiles(
    gas: Sequence[float | None],
    btc: Sequence[float | None],
    cex: Sequence[float | None],
) -> tuple[list[int], list[int], list[int], dict]:
    """Z-score then tertile. Edges from observation only — reuse for all surrogates."""
    zg = zscore_finite(gas)
    zb = zscore_finite(btc)
    zc = zscore_finite(cex)
    edges = {
        "gas": tertile_edges([v for v in zg if v is not None]),
        "btc": tertile_edges([v for v in zb if v is not None]),
        "cex": tertile_edges([v for v in zc if v is not None]),
    }
    return (
        apply_tertiles(zg, edges["gas"]),
        apply_tertiles(zb, edges["btc"]),
        apply_tertiles(zc, edges["cex"]),
        edges,
    )


def shuffle_occupancy(series: Sequence[int], rng) -> list[int]:
    out = list(series)
    rng.shuffle(out)
    return out


def _entropy(counts: Counter, n: int) -> float:
    if n == 0:
        return 0.0
    h = 0.0
    for c in counts.values():
        if c <= 0:
            continue
        p = c / n
        h -= p * log2(p)
    return h


def plugin_conditional_entropy(joint: Iterable[tuple], cond_idx: Sequence[int]) -> float:
    """H(Y | cond) via plugin MLE. Each row is a tuple; Y is index 0."""
    rows = list(joint)
    n = len(rows)
    if n == 0:
        return 0.0
    joint_counts: Counter = Counter(rows)
    cond_counts: Counter = Counter(tuple(row[i] for i in cond_idx) for row in rows)
    h_joint = _entropy(joint_counts, n)
    h_cond = _entropy(cond_counts, n)
    return max(0.0, h_joint - h_cond)


def _te_numpy(
    x: Sequence[int],
    y: Sequence[int],
    drivers: Sequence[Sequence[int]] | None,
    tau: int,
) -> float:
    import numpy as np

    xa = np.asarray(x, dtype=np.int16)
    ya = np.asarray(y, dtype=np.int16)
    n = len(ya)
    start = max(1, tau)
    y_t = ya[start:]
    y_lag = ya[start - 1 : n - 1]
    x_lag = xa[start:] if tau == 0 else xa[start - tau : n - tau]
    mask = np.ones(len(y_t), dtype=bool)
    drv_cols: list = []
    if drivers:
        for d in drivers:
            da = np.asarray(d, dtype=np.int16)[start:]
            if len(da) != len(y_t):
                raise ValueError("driver length mismatch")
            mask &= da >= 0
            drv_cols.append(da)
    y_t, y_lag, x_lag = y_t[mask], y_lag[mask], x_lag[mask]
    drv_f = [d[mask] for d in drv_cols]
    if y_t.size == 0:
        return 0.0

    def pack(cols: list, bases: list[int]):
        code = np.zeros(len(cols[0]), dtype=np.int32)
        mul = 1
        for col, base in zip(cols, bases):
            code += col.astype(np.int32) * mul
            mul *= base
        return code

    def entropy(codes) -> float:
        _, counts = np.unique(codes, return_counts=True)
        p = counts.astype(np.float64) / counts.sum()
        return float(-(p * np.log2(p)).sum())

    bases_red = [2, 2] + [3] * len(drv_f)
    bases_full = [2, 2, 2] + [3] * len(drv_f)
    cols_red = [y_t, y_lag, *drv_f]
    cols_full = [y_t, y_lag, x_lag, *drv_f]
    h_red = max(0.0, entropy(pack(cols_red, bases_red)) - entropy(pack(cols_red[1:], bases_red[1:])))
    h_full = max(0.0, entropy(pack(cols_full, bases_full)) - entropy(pack(cols_full[1:], bases_full[1:])))
    return max(0.0, h_red - h_full)


def transfer_entropy_binary(
    x: Sequence[int],
    y: Sequence[int],
    drivers: Sequence[Sequence[int]] | None,
    tau: int,
) -> float:
    """Discrete TE X→Y at lag tau minutes. Y_t | Y_{t-1} [, X_{t-tau}, drivers_t]."""
    n = len(y)
    if len(x) != n:
        raise ValueError("x/y length mismatch")
    if tau < 0:
        raise ValueError("tau must be >= 0")
    if n >= 4_000:
        try:
            return _te_numpy(x, y, drivers, tau)
        except ImportError:
            pass
    start = max(1, tau)
    rows_full: list[tuple] = []
    rows_red: list[tuple] = []
    for t in range(start, n):
        y_t = y[t]
        y_lag = y[t - 1]
        drv: list[int] = []
        if drivers:
            skip = False
            for d in drivers:
                if len(d) != n:
                    raise ValueError("driver length mismatch")
                val = d[t]
                if val < 0:
                    skip = True
                    break
                drv.append(val)
            if skip:
                continue
        x_lag = x[t - tau] if tau > 0 else x[t]
        rows_full.append((y_t, y_lag, x_lag, *drv))
        rows_red.append((y_t, y_lag, *drv))
    h_red = plugin_conditional_entropy(rows_red, cond_idx=tuple(range(1, 1 + 1 + len(drivers or ()))))
    n_drv = len(drivers) if drivers else 0
    h_full = plugin_conditional_entropy(rows_full, cond_idx=tuple(range(1, 1 + 1 + 1 + n_drv)))
    return max(0.0, h_red - h_full)


def verdict(
    *,
    n_events: dict[str, int],
    driver_coverage: float,
    n_sig_hawkes_treat: int,
    n_sig_cte_treat: int,
    n_sig_hawkes_ctrl: int,
    n_sig_cte_ctrl: int,
) -> str:
    """Pre-reg §6 labels. Pure function — do not retune after seeing data."""
    if any(n < N_MIN_EVENTS for n in n_events.values()) or driver_coverage < DRIVER_COVERAGE_MIN:
        return "INCONCLUSIVE"
    treat_h = n_sig_hawkes_treat > 0
    treat_c = n_sig_cte_treat > 0
    ctrl_any = n_sig_hawkes_ctrl > 0 or n_sig_cte_ctrl > 0
    if not treat_h and not treat_c:
        return "NEGATIVBEFUND"
    if ctrl_any:
        return "UNSPEZIFISCH"
    if treat_h and treat_c:
        return "POSITIVBEFUND"
    return "DISSOZIIERT"
