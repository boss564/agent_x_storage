"""
Rate-ratio test for regime documentation (Präreg §3.2 + §4).

Compares two event rates (e.g. pre/post a fixed boundary) with:
  - Headline: rate_ratio = rate2 / rate1 (distribution-free)
  - Auxiliary: exact conditional Poisson test (Binomial), one-sided p_lower / p_upper
  - Verdict thresholds: 1/4 (decrease) and 4× (increase)

See docs/REGIME_DOCUMENTATION_PREREG.md
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

try:
    from scipy.stats import binom as _binom
except ImportError:  # pragma: no cover — stdlib fallback for small n
    _binom = None

RateDecision = Literal["decrease", "increase", "no_change"]
ShiftDirection = Literal["decrease", "increase"]

RegimeVerdict = Literal[
    "REGIME_SHIFT_CONFIRMED",
    "FLUCTUATION",
    "INSUFFICIENT_DATA",
]

# Frozen before first regime-class verdict (2026-09-02)
ALPHA_REGIME = 0.01  # one-sided per direction (decrease / increase)
MIN_REFERENCE_EPISODES = 30
MIN_POST_EXPOSURE_MONTHS = 12.0
# Factor-of-4 rule — frozen 2026-09-02 with class introduction, *before* second finding.
MIN_RATE_RATIO_SHIFT = 0.25
MAX_RATE_RATIO_SHIFT = 4.0


@dataclass(frozen=True)
class RateRatioResult:
    decision: RateDecision
    ratio: float
    p_lower: float
    p_upper: float
    rate1: float
    rate2: float


@dataclass(frozen=True)
class RateWindow:
    label: str
    start: datetime
    end: datetime
    episodes: int

    @property
    def exposure_months(self) -> float:
        days = (self.end - self.start).total_seconds() / 86400.0
        return max(days / 30.4375, 1e-9)

    @property
    def rate_per_month(self) -> float:
        return self.episodes / self.exposure_months


@dataclass(frozen=True)
class RegimeRateResult:
    pre: RateWindow
    post: RateWindow
    expected_post_under_constant_rate: float
    rate_ratio_post_pre: float
    p_value_lower: float
    p_value_upper: float
    p_value_one_sided: float
    shift_direction: ShiftDirection | None
    verdict: RegimeVerdict
    detail: str


def _binom_cdf(k: int, n: int, p: float) -> float:
    if _binom is not None:
        return float(_binom.cdf(k, n, p))
    return sum(math.comb(n, i) * (p**i) * ((1 - p) ** (n - i)) for i in range(k + 1))


def _binom_sf(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p)."""
    if k <= 0:
        return 1.0
    if _binom is not None:
        return float(_binom.sf(k - 1, n, p))
    return 1.0 - _binom_cdf(k - 1, n, p)


def rate_ratio_test(
    count1: float,
    exposure1: float,
    count2: float,
    exposure2: float,
    alpha: float = ALPHA_REGIME,
) -> RateRatioResult:
    """
    Exact conditional Poisson rate comparison (Präreg §3.2).

    Period 1 = reference (pre), period 2 = comparison (post).
    Under H0 (equal rates), count2 | total ~ Binomial(total, p0)
    with p0 = exposure2 / (exposure1 + exposure2).

    Returns (decision, ratio, p_lower, p_upper) where:
      - ratio = rate2 / rate1
      - p_lower: one-sided test for rate2 < rate1
      - p_upper: one-sided test for rate2 > rate1
      - decision: decrease | increase | no_change (thresholds 0.25 / 4.0 + alpha)
    """
    rate1 = count1 / exposure1 if exposure1 > 0 else math.inf
    rate2 = count2 / exposure2 if exposure2 > 0 else math.inf
    ratio = rate2 / rate1 if rate1 > 0 and math.isfinite(rate1) else math.inf

    total = int(round(count1 + count2))
    if total == 0:
        return RateRatioResult("no_change", ratio, 1.0, 1.0, rate1, rate2)

    p0 = exposure2 / (exposure1 + exposure2)
    k2 = int(round(count2))
    p_lower = _binom_cdf(k2, total, p0)
    p_upper = _binom_sf(k2, total, p0)

    if ratio < MIN_RATE_RATIO_SHIFT and p_lower < alpha:
        decision: RateDecision = "decrease"
    elif ratio > MAX_RATE_RATIO_SHIFT and p_upper < alpha:
        decision = "increase"
    else:
        decision = "no_change"

    return RateRatioResult(decision, ratio, p_lower, p_upper, rate1, rate2)


def rate_ratio_from_rates(
    rate1: float,
    rate2: float,
    exposure1: float = 1.0,
    exposure2: float = 1.0,
    alpha: float = ALPHA_REGIME,
) -> RateRatioResult:
    """Wrapper when only rates (and exposures) are known."""
    return rate_ratio_test(
        rate1 * exposure1,
        exposure1,
        rate2 * exposure2,
        exposure2,
        alpha=alpha,
    )


def poisson_rate_test(pre: RateWindow, post: RateWindow) -> RegimeRateResult:
    """
    Regime verdict wrapper around rate_ratio_test (fixed-boundary windows).

    Maps decrease/increase/no_change → REGIME_SHIFT_CONFIRMED / FLUCTUATION.
    """
    if pre.episodes < MIN_REFERENCE_EPISODES:
        return RegimeRateResult(
            pre=pre,
            post=post,
            expected_post_under_constant_rate=0.0,
            rate_ratio_post_pre=0.0,
            p_value_lower=1.0,
            p_value_upper=1.0,
            p_value_one_sided=1.0,
            shift_direction=None,
            verdict="INSUFFICIENT_DATA",
            detail=f"reference episodes {pre.episodes} < {MIN_REFERENCE_EPISODES}",
        )
    if post.exposure_months < MIN_POST_EXPOSURE_MONTHS:
        return RegimeRateResult(
            pre=pre,
            post=post,
            expected_post_under_constant_rate=0.0,
            rate_ratio_post_pre=0.0,
            p_value_lower=1.0,
            p_value_upper=1.0,
            p_value_one_sided=1.0,
            shift_direction=None,
            verdict="INSUFFICIENT_DATA",
            detail=f"post exposure {post.exposure_months:.1f}mo < {MIN_POST_EXPOSURE_MONTHS}",
        )

    rr = rate_ratio_test(
        pre.episodes,
        pre.exposure_months,
        post.episodes,
        post.exposure_months,
    )
    expected_post = pre.rate_per_month * post.exposure_months

    if rr.decision == "decrease":
        verdict: RegimeVerdict = "REGIME_SHIFT_CONFIRMED"
        direction: ShiftDirection | None = "decrease"
        p_one = rr.p_lower
        detail = (
            f"decrease: rate ratio {rr.ratio:.3f} < {MIN_RATE_RATIO_SHIFT}; "
            f"expected {expected_post:.0f} vs observed {post.episodes}; "
            f"exact p_lower={rr.p_lower:.2e} (auxiliary)"
        )
    elif rr.decision == "increase":
        verdict = "REGIME_SHIFT_CONFIRMED"
        direction = "increase"
        p_one = rr.p_upper
        detail = (
            f"increase: rate ratio {rr.ratio:.3f} > {MAX_RATE_RATIO_SHIFT}; "
            f"expected {expected_post:.0f} vs observed {post.episodes}; "
            f"exact p_upper={rr.p_upper:.2e} (auxiliary)"
        )
    else:
        verdict = "FLUCTUATION"
        direction = None
        p_one = rr.p_lower if rr.ratio <= 1.0 else rr.p_upper
        detail = (
            f"rate ratio {rr.ratio:.3f}; "
            f"exact p_lower={rr.p_lower:.3f}, p_upper={rr.p_upper:.3f}"
        )

    return RegimeRateResult(
        pre=pre,
        post=post,
        expected_post_under_constant_rate=expected_post,
        rate_ratio_post_pre=rr.ratio,
        p_value_lower=rr.p_lower,
        p_value_upper=rr.p_upper,
        p_value_one_sided=p_one,
        shift_direction=direction,
        verdict=verdict,
        detail=detail,
    )


if __name__ == "__main__":
    r = rate_ratio_test(50, 100, 10, 100)
    print(
        f"Abnahme: decision={r.decision}, ratio={r.ratio:.3f}, "
        f"p_lower={r.p_lower:.4f}, p_upper={r.p_upper:.4f}"
    )
    r = rate_ratio_test(10, 100, 50, 100)
    print(
        f"Zunahme: decision={r.decision}, ratio={r.ratio:.3f}, "
        f"p_lower={r.p_lower:.4f}, p_upper={r.p_upper:.4f}"
    )
    r = rate_ratio_test(30, 100, 35, 100)
    print(
        f"Kein Effekt: decision={r.decision}, ratio={r.ratio:.3f}, "
        f"p_lower={r.p_lower:.4f}, p_upper={r.p_upper:.4f}"
    )
