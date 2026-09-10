"""
M2 shadow overlays — asset gate, spread proxy, alpha-decay diagnostic.

Aligned with docs/H1_M2_EVENT_DRIVEN_SPEC.md v1 (frozen):
  - Assets: BTC/ETH only (§2.1)
  - θ_abs = 0.30 (§2.3) — gate lives in skeleton, not re-fit here
  - Friction 19 bps round-trip (§3) — from backtest_h1_price.FRICTION_BPS
  - Shadow verdict: lag buckets + OHLCV PnL — not sentiment-scaled sizing

NOT in scope (by design):
  - Position sizing / Kelly → prototypes/raas_paper_trading/position_sizing (Strang B)
  - λ fitting in watchdog (read-only transport)
  - Tier-2 alts (SOL/XRP/ADA) until M2 v1.1 prereg
  - r0 from |sentiment|×100 bps — tautological; r0 = max observed OHLCV gross only
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

# Spec §2.1 — v1 core universe only
V1_CORE_ASSETS = frozenset({"BTC", "ETH"})

ASSET_TIERS_V1: Dict[str, Dict[str, float]] = {
    "BTC": {"tier": 1, "base_spread_bps": 2.0, "max_spread_bps": 5.0},
    "ETH": {"tier": 1, "base_spread_bps": 2.0, "max_spread_bps": 5.0},
}

THETA_ABS = 0.30
FRICTION_BPS_RT = 19.0
LAMBDA_DEFAULT_PER_S = 0.001
MIN_OBS_FOR_LAMBDA_FIT = 10
MIN_LAG_SPREAD_S = 30.0


@dataclass(frozen=True)
class LagTradeObservation:
    """One aligned shadow trade with lag stratification."""

    asset: str
    lag_sec: float
    gross_pnl_bps: float
    net_pnl_bps: float
    lag_bucket: Optional[str] = None


@dataclass
class AssetLiquidityGate:
    """v1 eligibility — tier-1 core only; tier-2 depth check reserved for v1.1."""

    tiers: Mapping[str, Mapping[str, float]] = field(default_factory=lambda: ASSET_TIERS_V1)
    min_depth_factor: float = 10.0

    def tier(self, symbol: str) -> Optional[int]:
        row = self.tiers.get(symbol.upper())
        if not row:
            return None
        return int(row["tier"])

    def is_eligible(
        self,
        symbol: str,
        *,
        order_size_usd: float = 10_000.0,
        orderbook_depth_usd: Optional[float] = None,
    ) -> Tuple[bool, str]:
        sym = symbol.upper()
        if sym not in V1_CORE_ASSETS:
            return False, f"{sym} outside M2 v1 core ({', '.join(sorted(V1_CORE_ASSETS))})"
        row = self.tiers.get(sym)
        if not row:
            return False, f"{sym} not in tier table"
        tier = int(row["tier"])
        if tier == 1:
            return True, "tier_1_core"
        if tier == 2:
            if orderbook_depth_usd is None:
                return False, "tier_2_requires_orderbook_depth"
            required = order_size_usd * self.min_depth_factor
            if orderbook_depth_usd >= required:
                return True, f"depth_ok_{orderbook_depth_usd:.0f}"
            return False, f"depth_{orderbook_depth_usd:.0f}_lt_{required:.0f}"
        return False, "unknown_tier"

    def estimate_spread_bps(
        self,
        symbol: str,
        *,
        sigma_15m: Optional[float] = None,
        news_spike: bool = False,
    ) -> float:
        """Spread proxy — delegates to shadow slippage base when σ known."""
        from scripts.backtest_h1_news_m2_shadow_lag import estimate_slippage_bps

        row = self.tiers.get(symbol.upper())
        if not row:
            return estimate_slippage_bps(sigma_15m=sigma_15m)
        base = float(row["base_spread_bps"])
        cap = float(row["max_spread_bps"])
        if news_spike and sigma_15m and sigma_15m > 0:
            vol_boost = min(sigma_15m * 500.0, 2.0) / 2.0
            spread = base + (cap - base) * vol_boost
            return min(max(spread, base), cap)
        return min(max(estimate_slippage_bps(sigma_15m=sigma_15m), base), cap)


def expected_gross_decay_bps(
    lag_sec: float,
    r0_bps: float,
    *,
    lambda_per_s: float = LAMBDA_DEFAULT_PER_S,
) -> float:
    if lag_sec < 0:
        return r0_bps
    return r0_bps * math.exp(-lambda_per_s * lag_sec)


def observed_lag_stats(
    observations: Sequence[LagTradeObservation],
) -> Dict[str, Optional[float]]:
    if not observations:
        return {"min": None, "max": None, "median": None, "n": 0}
    lags = sorted(o.lag_sec for o in observations)
    n = len(lags)
    mid = n // 2
    if n % 2:
        median = lags[mid]
    else:
        median = (lags[mid - 1] + lags[mid]) / 2.0
    return {"min": lags[0], "max": lags[-1], "median": median, "n": float(n)}


def build_decay_curve_bps(
    observations: Sequence[LagTradeObservation],
    *,
    r0_bps: float,
    lambda_per_s: float,
) -> List[Dict[str, object]]:
    """
    Decay curve evaluated only on the empirical lag support.

    Points with lag outside [observed_min, observed_max] carry extrapolated=true.
    No t=0 anchor — with hourly polling that lag is off-support and would read
    like a §11 polling justification if quoted without a flag.
    """
    stats = observed_lag_stats(observations)
    lag_min = stats["min"]
    lag_max = stats["max"]
    if lag_min is None or lag_max is None:
        return []

    lags = sorted(o.lag_sec for o in observations)
    points: List[Dict[str, object]] = []

    def add(lag_sec: float, label: str, *, extrapolated: bool) -> None:
        points.append(
            {
                "lag_sec": round(lag_sec, 1),
                "lag_label": label,
                "gross_bps": round(
                    expected_gross_decay_bps(lag_sec, r0_bps, lambda_per_s=lambda_per_s),
                    2,
                ),
                "extrapolated": extrapolated,
            }
        )

    quantile_labels = (
        ("observed_min", 0.0),
        ("p25", 0.25),
        ("p50", 0.5),
        ("p75", 0.75),
        ("observed_max", 1.0),
    )
    for label, q in quantile_labels:
        idx = int(min(len(lags) - 1, max(0, round(q * (len(lags) - 1)))))
        lag = lags[idx]
        add(lag, label, extrapolated=False)

    for ref_lag, ref_label in ((300.0, "ref_5m"), (900.0, "ref_15m"), (3600.0, "ref_60m")):
        out_of_support = ref_lag < lag_min or ref_lag > lag_max
        add(ref_lag, ref_label, extrapolated=out_of_support)

    return points


def fit_lambda_per_second(
    observations: Sequence[LagTradeObservation],
    *,
    r0_bps: Optional[float] = None,
    min_obs: int = MIN_OBS_FOR_LAMBDA_FIT,
) -> Tuple[Optional[float], str]:
    """
    OLS on log(gross) = log(r0) − λ·lag (diagnostic only — not a trading gate).

    Uses realized OHLCV gross PnL, not sentiment × 100 bps.
    """
    if len(observations) < min_obs:
        return None, f"insufficient_observations n={len(observations)}<{min_obs}"

    lags = [o.lag_sec for o in observations]
    if max(lags) - min(lags) < MIN_LAG_SPREAD_S:
        return None, f"lag_spread_too_narrow span={max(lags) - min(lags):.1f}s"

    gross = [max(o.gross_pnl_bps, 1e-3) for o in observations]
    if r0_bps is None:
        r0_bps = max(gross)

    y = [math.log(g) - math.log(r0_bps) for g in gross]
    x = lags
    n = float(len(x))
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    var_x = sum((xi - mean_x) ** 2 for xi in x)
    if var_x <= 0:
        return None, "degenerate_lag_variance"
    cov_xy = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    slope = cov_xy / var_x
    lambda_fit = -slope
    if lambda_fit <= 0:
        return None, f"non_positive_lambda_fit {lambda_fit:.6f}"
    return lambda_fit, "ok"


@dataclass
class AlphaDecayDiagnostic:
    """Post-hoc decay report from shadow backtest trade list."""

    observations: List[LagTradeObservation] = field(default_factory=list)
    lambda_per_s: Optional[float] = None
    lambda_fit_status: str = "not_run"
    r0_bps: Optional[float] = None
    friction_bps_rt: float = FRICTION_BPS_RT

    def add(self, obs: LagTradeObservation) -> None:
        self.observations.append(obs)

    def fit(self) -> None:
        if not self.observations:
            self.lambda_fit_status = "no_observations"
            return
        gross_pos = [o.gross_pnl_bps for o in self.observations if o.gross_pnl_bps > 0]
        self.r0_bps = max(gross_pos) if gross_pos else None
        if self.r0_bps is None:
            self.lambda_fit_status = "no_positive_gross"
            return
        lam, status = fit_lambda_per_second(self.observations, r0_bps=self.r0_bps)
        self.lambda_per_s = lam
        self.lambda_fit_status = status

    def bucket_mean_gross(self) -> Dict[str, float]:
        acc: Dict[str, List[float]] = {}
        for o in self.observations:
            if o.lag_bucket is None:
                continue
            acc.setdefault(o.lag_bucket, []).append(o.gross_pnl_bps)
        return {k: sum(v) / len(v) for k, v in acc.items() if v}

    def to_dict(self) -> Dict[str, object]:
        lam = self.lambda_per_s if self.lambda_per_s is not None else LAMBDA_DEFAULT_PER_S
        r0 = self.r0_bps or 0.0
        lag_stats = observed_lag_stats(self.observations)
        return {
            "n_observations": len(self.observations),
            "lambda_per_s": self.lambda_per_s,
            "lambda_default_per_s": LAMBDA_DEFAULT_PER_S,
            "lambda_fit_status": self.lambda_fit_status,
            "r0_bps": self.r0_bps,
            "r0_source": "max_observed_ohlcv_gross_bps",
            "friction_bps_rt": self.friction_bps_rt,
            "lag_observed_sec": lag_stats,
            "bucket_mean_gross_bps": self.bucket_mean_gross(),
            "decay_curve_bps": build_decay_curve_bps(
                self.observations,
                r0_bps=r0,
                lambda_per_s=lam,
            ),
            "curve_disclaimer": (
                "gross_bps from λ-fit on OHLCV trades; extrapolated=true outside "
                "lag_observed_sec [min,max]; not valid for §11 polling decisions "
                "(§11 follows Tag-7 median vs T_max only — H1_M2 §5.1.1)"
            ),
            "diagnostic_only": True,
            "not_investment_advice": True,
        }
