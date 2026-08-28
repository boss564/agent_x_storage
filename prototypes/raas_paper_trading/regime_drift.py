"""Regime drift & feature-shift detection — monitoring only (Baustein 2).

Hypothesis: two-sample KS + 1D Wasserstein on tick-derived features flag distributional
shifts between a frozen reference window and a trailing test window before breaks dominate.

No live execution. Diagnostic / audit only.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"

# Frozen v0 — amend only with pre-reg note (docs/RaaS_REGIME_DRIFT_PREREG.md).
REF_FRAC = 0.25
TEST_FRAC = 0.25
MIN_SAMPLES_PER_WINDOW = 30
ALPHA = 0.01
PERMUTATION_N = 500
WASSERSTEIN_ALERT_Q = 0.99  # test vs reference empirical quantile of |Δ|
FEATURES = ("log_return_pct", "abs_return_pct", "down_move_pct")


def definition_hash() -> str:
    payload = {
        "schema": "raas_regime_drift_v0",
        "ref_frac": REF_FRAC,
        "test_frac": TEST_FRAC,
        "min_samples_per_window": MIN_SAMPLES_PER_WINDOW,
        "alpha": ALPHA,
        "permutation_n": PERMUTATION_N,
        "wasserstein_alert_q": WASSERSTEIN_ALERT_Q,
        "features": list(FEATURES),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _pct_move(prev: float, cur: float) -> float:
    if prev <= 0:
        return 0.0
    return 100.0 * (cur - prev) / prev


def prices_to_feature_rows(prices: Sequence[float]) -> Dict[str, List[float]]:
    """Tick-level features from mark_price series (SIGNAL order)."""
    log_ret: List[float] = []
    abs_ret: List[float] = []
    down: List[float] = []
    for i in range(1, len(prices)):
        mv = _pct_move(float(prices[i - 1]), float(prices[i]))
        log_ret.append(mv)
        abs_ret.append(abs(mv))
        down.append(max(0.0, -mv))
    return {
        "log_return_pct": log_ret,
        "abs_return_pct": abs_ret,
        "down_move_pct": down,
    }


def load_signal_prices(path: Path) -> List[float]:
    """Extract mark_price from WORM SIGNAL rows (chronological)."""
    if not path.is_file():
        return []
    out: List[float] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("action") != "SIGNAL":
            continue
        raw = row.get("mark_price")
        if raw is None:
            continue
        out.append(float(raw))
    return out


def kolmogorov_smirnov_stat(a: Sequence[float], b: Sequence[float]) -> float:
    """Two-sample KS D statistic (pure Python, tie-safe)."""
    xs = sorted(float(x) for x in a)
    ys = sorted(float(y) for y in b)
    if not xs or not ys:
        return 0.0
    n, m = len(xs), len(ys)
    d = 0.0
    for v in sorted(set(xs + ys)):
        cdf_x = sum(1 for x in xs if x <= v) / n
        cdf_y = sum(1 for y in ys if y <= v) / m
        d = max(d, abs(cdf_x - cdf_y))
    return d


def permutation_ks_pvalue(
    a: Sequence[float],
    b: Sequence[float],
    *,
    n_perm: int = PERMUTATION_N,
    seed: int = 42,
) -> Tuple[float, float]:
    """Monte Carlo permutation p-value for KS (one-sided: observed >= permuted)."""
    a_list = [float(x) for x in a]
    b_list = [float(y) for y in b]
    if len(a_list) < 2 or len(b_list) < 2:
        return 0.0, 1.0
    rng = random.Random(seed)
    sample_a = list(a_list)
    sample_b = list(b_list)
    obs = kolmogorov_smirnov_stat(sample_a, sample_b)
    pooled = sample_a + sample_b
    n_a = len(sample_a)
    exceed = 0
    for _ in range(max(1, n_perm)):
        rng.shuffle(pooled)
        perm_a = pooled[:n_a]
        perm_b = pooled[n_a:]
        if kolmogorov_smirnov_stat(perm_a, perm_b) >= obs - 1e-15:
            exceed += 1
    p = (exceed + 1) / (n_perm + 1)
    return obs, p


def wasserstein_1d(a: Sequence[float], b: Sequence[float]) -> float:
    """Earth-mover distance between two 1D empirical distributions."""
    xs = sorted(float(x) for x in a)
    ys = sorted(float(y) for y in b)
    if not xs or not ys:
        return 0.0
    support = sorted(set(xs + ys))
    if len(support) == 1:
        return abs(xs[0] - ys[0])
    total = 0.0
    n_x, n_y = len(xs), len(ys)
    for k in range(len(support) - 1):
        left, right = support[k], support[k + 1]
        mid = (left + right) / 2.0
        cdf_x = sum(1 for v in xs if v <= mid) / n_x
        cdf_y = sum(1 for v in ys if v <= mid) / n_y
        total += abs(cdf_x - cdf_y) * (right - left)
    return total


def _split_windows(
    values: Sequence[float],
    *,
    ref_frac: float = REF_FRAC,
    test_frac: float = TEST_FRAC,
    min_samples: int = MIN_SAMPLES_PER_WINDOW,
) -> Optional[Tuple[List[float], List[float]]]:
    n = len(values)
    if n < 2 * min_samples:
        return None
    ref_n = max(min_samples, int(n * ref_frac))
    test_n = max(min_samples, int(n * test_frac))
    if ref_n + test_n > n:
        return None
    ref = list(values[:ref_n])
    test = list(values[-test_n:])
    return ref, test


@dataclass(frozen=True)
class FeatureDriftResult:
    feature: str
    n_reference: int
    n_test: int
    ks_d: float
    ks_p: float
    wasserstein: float
    drift_ks: bool
    drift_wasserstein: bool
    drift: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature": self.feature,
            "n_reference": self.n_reference,
            "n_test": self.n_test,
            "ks_d": round(self.ks_d, 6),
            "ks_p": round(self.ks_p, 6),
            "wasserstein": round(self.wasserstein, 8),
            "drift_ks": self.drift_ks,
            "drift_wasserstein": self.drift_wasserstein,
            "drift": self.drift,
        }


def assess_feature_drift(
    reference: Sequence[float],
    test: Sequence[float],
    *,
    feature: str,
    alpha: float = ALPHA,
    wasserstein_alert_q: float = WASSERSTEIN_ALERT_Q,
    seed: int = 42,
) -> FeatureDriftResult:
    ref = [float(x) for x in reference]
    tst = [float(x) for x in test]
    ks_d, ks_p = permutation_ks_pvalue(ref, tst, seed=seed)
    w_dist = wasserstein_1d(ref, tst)
    # Reference-only bootstrap for Wasserstein alert threshold (self-shift null).
    rng = random.Random(seed + 1)
    null_w: List[float] = []
    pooled = ref + tst
    half = len(pooled) // 2
    if len(pooled) >= 4:
        for _ in range(200):
            rng.shuffle(pooled)
            null_w.append(wasserstein_1d(pooled[:half], pooled[half:]))
    w_thresh = (
        sorted(null_w)[int(wasserstein_alert_q * (len(null_w) - 1))]
        if null_w
        else w_dist
    )
    drift_ks = ks_p < alpha
    drift_w = w_dist > w_thresh and w_dist > 0
    return FeatureDriftResult(
        feature=feature,
        n_reference=len(ref),
        n_test=len(tst),
        ks_d=ks_d,
        ks_p=ks_p,
        wasserstein=w_dist,
        drift_ks=drift_ks,
        drift_wasserstein=drift_w,
        drift=drift_ks or drift_w,
    )


def assess_price_series(
    prices: Sequence[float],
    *,
    symbol: str = "UNKNOWN",
    alpha: float = ALPHA,
    seed: int = 42,
) -> Dict[str, Any]:
    """Full report for one symbol price series."""
    feats = prices_to_feature_rows(prices)
    feature_results: List[FeatureDriftResult] = []
    insufficient: List[str] = []
    for name in FEATURES:
        series = feats.get(name, [])
        windows = _split_windows(series)
        if windows is None:
            insufficient.append(name)
            continue
        ref, tst = windows
        feature_results.append(
            assess_feature_drift(ref, tst, feature=name, alpha=alpha, seed=seed)
        )
    any_drift = any(r.drift for r in feature_results)
    return {
        "symbol": symbol,
        "n_prices": len(prices),
        "definition_hash": definition_hash(),
        "insufficient_features": insufficient,
        "features": [r.to_dict() for r in feature_results],
        "regime_drift": any_drift,
        "diagnostic_only": True,
        "not_investment_advice": True,
        "scope": SCOPE,
    }


def discover_worm_files(root: Path) -> List[Path]:
    if root.is_file():
        return [root]
    if not root.is_dir():
        return []
    return sorted(root.rglob("paper_trades.worm.jsonl"))


def assess_worm_path(path: Path, *, seed: int = 42) -> Dict[str, Any]:
    symbol = "UNKNOWN"
    for part in path.parts:
        low = part.lower()
        for suffix in ("btcusdc", "ethusdc", "solusdc"):
            if low.endswith(suffix):
                symbol = suffix.upper()
                break
    prices = load_signal_prices(path)
    report = assess_price_series(prices, symbol=symbol, seed=seed)
    report["worm_path"] = str(path)
    run_id = path.parent.name if path.name == "paper_trades.worm.jsonl" else path.stem
    report["run_id"] = run_id
    return report
