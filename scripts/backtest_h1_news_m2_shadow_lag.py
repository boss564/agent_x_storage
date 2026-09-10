"""M2 shadow lag stratification — pure stats (no OHLCV/ccxt)."""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Tuple

# Spec §2.2.1 lag buckets (seconds)
LAG_BUCKETS_SEC: Dict[str, Tuple[float, float]] = {
    "LT_15M": (0.0, 900.0),
    "M15_60": (900.0, 3600.0),
    "GT_60": (3600.0, float("inf")),
}

SLIPPAGE_BASE_BPS = 2.0
SLIPPAGE_K = 0.1
DEFAULT_SLIPPAGE_BPS = 5.0

# Family-wise α across three lag-bucket hypotheses (regime-swarm A7 pattern).
ALPHA = 0.05
N_BUCKET_HYPOTHESES = 3
ALPHA_EFF = ALPHA / N_BUCKET_HYPOTHESES

MIN_CALENDAR_DAYS = 90
MIN_GATED_EVENTS = 200
# Power-informed floor: at n=40, σ≈75 bps, α_eff≈0.0167 (80 % power) → MDE≈35 bps.
# Below this, non-significance is indistinguishable from underpowered (not a negative finding).
MIN_TRADES_PER_BUCKET = 40
MDE_POWER = 0.80
# Reference σ for pre-data power planning (~typical per-trade net PnL dispersion).
MDE_REFERENCE_STD_BPS = 75.0

PRIMARY_VERDICT_BUCKET = "M15_60"
ARMS_RACE_BUCKET = "LT_15M"

Adjudication = Literal["insufficient", "adjudicated"]


@dataclass
class BucketResult:
    bucket_name: str
    lag_range_sec: Tuple[float, float]
    n_trades: int
    mean_pnl_bps: float
    std_pnl_bps: float
    t_stat: float
    p_value: float
    adjudication: Adjudication
    bonferroni_significant: bool
    mde_bps_prereg: Optional[float] = None
    mde_bps_realized: Optional[float] = None
    sigma_bps_realized: Optional[float] = None
    effective_alpha: float = ALPHA_EFF
    trades: List[float] = field(default_factory=list)

    @property
    def significant(self) -> bool:
        """Alias for reports — only meaningful when adjudicated."""
        return self.bonferroni_significant


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def one_sided_p_value(t_stat: float) -> float:
    return 1.0 - norm_cdf(t_stat)


def _norm_ppf(p: float) -> float:
    if not 0.0 < p < 1.0:
        raise ValueError(f"ppf requires 0 < p < 1, got {p}")
    lo, hi = -8.0, 8.0
    for _ in range(64):
        mid = (lo + hi) / 2.0
        if norm_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def min_detectable_effect_bps(
    n: int,
    std_bps: float,
    *,
    alpha: float = ALPHA_EFF,
    power: float = MDE_POWER,
) -> Optional[float]:
    """
    One-sided MDE at (1−α) significance and ``power`` (default 80 %).

    MDE_bps = (z_{1−α} + z_{power}) · σ_bps / √n
    """
    if n < 2 or std_bps <= 0:
        return None
    z_alpha = _norm_ppf(1.0 - alpha)
    z_beta = _norm_ppf(power)
    return (z_alpha + z_beta) * std_bps / math.sqrt(n)


def assign_lag_bucket(lag_seconds: float) -> Optional[str]:
    for name, (lower, upper) in LAG_BUCKETS_SEC.items():
        if lower <= lag_seconds < upper:
            return name
    return None


def estimate_slippage_bps(*, sigma_15m: Optional[float] = None) -> float:
    if sigma_15m is not None and sigma_15m > 0:
        return SLIPPAGE_BASE_BPS + SLIPPAGE_K * (sigma_15m * 100.0)
    return DEFAULT_SLIPPAGE_BPS


def data_threshold_status(events: list) -> Tuple[str, str]:
    if len(events) < MIN_GATED_EVENTS:
        return (
            "BLOCKED",
            f"gated events {len(events)} < {MIN_GATED_EVENTS} (spec §4.2)",
        )
    span_days = (events[-1].t_ingest - events[0].t_ingest).total_seconds() / 86_400.0
    if span_days < MIN_CALENDAR_DAYS:
        return (
            "BLOCKED",
            f"calendar span {span_days:.1f}d < {MIN_CALENDAR_DAYS}d (spec §4.2)",
        )
    return "OK", ""


def _bonferroni_significant(*, mean: float, p_value: float, adjudicated: bool) -> bool:
    return adjudicated and mean > 0 and p_value < ALPHA_EFF


def bucket_statistics(name: str, pnls: List[float]) -> BucketResult:
    lower, upper = LAG_BUCKETS_SEC[name]
    n = len(pnls)
    adjudication: Adjudication = "insufficient" if n < MIN_TRADES_PER_BUCKET else "adjudicated"

    if n < 2:
        return BucketResult(
            bucket_name=name,
            lag_range_sec=(lower, upper),
            n_trades=n,
            mean_pnl_bps=0.0,
            std_pnl_bps=0.0,
            t_stat=0.0,
            p_value=1.0,
            adjudication=adjudication,
            bonferroni_significant=False,
            mde_bps_prereg=None,
            mde_bps_realized=None,
            sigma_bps_realized=None,
            trades=pnls,
        )

    mean = statistics.mean(pnls)
    stdev = statistics.stdev(pnls) if n > 1 else 0.0
    mde_bps_prereg = min_detectable_effect_bps(n, MDE_REFERENCE_STD_BPS)
    mde_bps_realized = min_detectable_effect_bps(n, stdev)
    sigma_bps_realized = stdev if stdev > 0 else None
    se = stdev / (n**0.5) if n else 0.0
    if se == 0:
        t_stat = 0.0
        p_value = 1.0
    else:
        t_stat = mean / se
        p_value = one_sided_p_value(t_stat)

    bonferroni_significant = _bonferroni_significant(
        mean=mean,
        p_value=p_value,
        adjudicated=adjudication == "adjudicated",
    )
    return BucketResult(
        bucket_name=name,
        lag_range_sec=(lower, upper),
        n_trades=n,
        mean_pnl_bps=mean,
        std_pnl_bps=stdev,
        t_stat=t_stat,
        p_value=p_value,
        adjudication=adjudication,
        bonferroni_significant=bonferroni_significant,
        mde_bps_prereg=mde_bps_prereg,
        mde_bps_realized=mde_bps_realized,
        sigma_bps_realized=sigma_bps_realized,
        trades=pnls,
    )


def _mde_interpretation_note(eligible: Dict[str, BucketResult]) -> str:
    parts: List[str] = []
    for name in sorted(eligible):
        r = eligible[name]
        if r.mde_bps_realized is not None:
            parts.append(f"{name} MDE≈{r.mde_bps_realized:.0f}bps")
    if not parts:
        return ""
    return (
        " Nicht-Signifikanz: mit 80 % Wahrscheinlichkeit nicht nachweisbar "
        f"({'; '.join(parts)})."
    )


def _adjudicated(results: Dict[str, BucketResult]) -> Dict[str, BucketResult]:
    return {name: r for name, r in results.items() if r.adjudication == "adjudicated"}


def _insufficient_names(results: Dict[str, BucketResult]) -> List[str]:
    return sorted(name for name, r in results.items() if r.adjudication == "insufficient")


def decision_engine(
    results: Dict[str, BucketResult],
    threshold_status: str = "OK",
    threshold_reason: str = "",
) -> Tuple[str, str]:
    if threshold_status == "BLOCKED":
        return "BLOCKED", threshold_reason or "Data threshold not met (spec §4.2)."

    lt = results.get("LT_15M")
    mid = results.get("M15_60")
    late = results.get("GT_60")
    if not lt or not mid or not late:
        return "INCONCLUSIVE", "Missing bucket results."

    if mid.adjudication != "adjudicated":
        return (
            "INCONCLUSIVE",
            f"M15_60 n={mid.n_trades} < {MIN_TRADES_PER_BUCKET} — "
            "Hauptbucket nicht urteilsfähig.",
        )

    eligible = _adjudicated(results)
    sig_buckets = [name for name, r in eligible.items() if r.bonferroni_significant]
    excluded = _insufficient_names(results)
    excluded_note = f" Ausgeschlossen (INSUFFICIENT): {', '.join(excluded)}." if excluded else ""

    if mid.bonferroni_significant:
        return (
            "PASS",
            f"Bucket M15_60 (15–60 min) Bonferroni-signifikant "
            f"(mean={mid.mean_pnl_bps:.2f} bps, p={mid.p_value:.4f}, "
            f"α_eff={ALPHA_EFF:.4f}).{excluded_note}",
        )

    if (
        lt.adjudication == "adjudicated"
        and lt.bonferroni_significant
        and not mid.bonferroni_significant
        and not any(name != ARMS_RACE_BUCKET for name in sig_buckets)
    ):
        return (
            "FAIL (Latency Arms Race)",
            "Nur LT_15M Bonferroni-signifikant — ohne Infrastruktur <15 min nicht umsetzbar."
            + excluded_note,
        )

    if eligible and not sig_buckets:
        return (
            "FAIL (No News Alpha)",
            "Kein urteilsfähiger Bucket Bonferroni-signifikant (positiv)."
            + _mde_interpretation_note(eligible)
            + excluded_note,
        )

    if not eligible:
        return "INCONCLUSIVE", "Kein Bucket mit Mindestbesatz — kein Urteil möglich."

    return "INCONCLUSIVE", "Gemischte Signale — manuelle Prüfung erforderlich." + excluded_note
