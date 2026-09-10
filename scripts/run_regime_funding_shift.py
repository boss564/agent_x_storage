#!/usr/bin/env python3
"""
Regime documentation: Poisson rate test for funding-extreme episodes.

Example (frozen windows, θ=0.10%/8h, BTC+ETH combined):
  Pre-split  102 episodes / ~50 mo → 2.02/mo
  Post-split   1 episode  / ~34 mo → 0.03/mo
  Headline: rate ratio 0.015 (68 expected vs 1 observed under constant rate)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.m2a_config import OOS_SPLIT_TS, PERP_START, PREREG_FREEZE
from scripts.m2a_funding_feasibility import SYMBOLS, count_episodes, download_funding
from scripts.regime_rate_test import RateWindow, poisson_rate_test

RESULTS_DIR = Path("results")
# Regime class uses structural threshold (extreme funding), not M2a trade θ_primary
REGIME_THRESHOLD = 0.001  # 0.10% / 8h — frozen 2026-09-02


def episode_counts_combined(threshold: float) -> tuple[int, int]:
    """Return (pre_split, post_split) episode counts summed over BTC+ETH."""
    pre = post = 0
    for sym in SYMBOLS:
        df = download_funding(sym)
        _, _, episodes = count_episodes(df, threshold)
        for ep in episodes:
            start = datetime.fromisoformat(ep["start"].replace("Z", "+00:00"))
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if start < OOS_SPLIT_TS:
                pre += 1
            else:
                post += 1
    return pre, post


def main() -> int:
    pre_n, post_n = episode_counts_combined(REGIME_THRESHOLD)
    pre = RateWindow("pre_split", PERP_START, OOS_SPLIT_TS, pre_n)
    post = RateWindow("post_split", OOS_SPLIT_TS, PREREG_FREEZE, post_n)
    result = poisson_rate_test(pre, post)

    print("=" * 72)
    print("REGIME DOCUMENTATION — Funding extreme rate shift (θ=0.10%/8h)")
    print("=" * 72)
    print(f"Pre:  {pre.start.date()} .. {pre.end.date()}  n={pre.episodes}  "
          f"({pre.exposure_months:.1f} mo)  λ={pre.rate_per_month:.2f}/mo")
    print(f"Post: {post.start.date()} .. {post.end.date()}  n={post.episodes}  "
          f"({post.exposure_months:.1f} mo)  λ={post.rate_per_month:.2f}/mo")
    print(f"Expected post under constant pre-rate: {result.expected_post_under_constant_rate:.1f}")
    print(f"HEADLINE rate ratio post/pre: {result.rate_ratio_post_pre:.4f}")
    print(f"Auxiliary exact p_lower={result.p_value_lower:.2e}, p_upper={result.p_value_upper:.2e}")
    print(f"VERDICT: {result.verdict} — {result.detail}")

    out = {
        "class": "regime_rate_shift",
        "threshold": REGIME_THRESHOLD,
        "threshold_label": "0.10% per 8h",
        "assets": SYMBOLS,
        "boundary": {
            "type": "fixed_exogenous",
            "split_ts": OOS_SPLIT_TS.isoformat(),
            "source": "M2a/M2 strategy prereg 60/40 calendar split (not breakpoint search)",
            "reference": "docs/M2A_FUNDING_SQUEEZE_PREREG.md §4",
        },
        "thresholds": {
            "min_rate_ratio_decrease": 0.25,
            "max_rate_ratio_increase": 4.0,
            "rationale": "factor-of-4 structural break (reciprocal pair); frozen before second finding",
        },
        "citation": {
            "headline_stat": "rate_ratio_post_pre",
            "headline_value": round(result.rate_ratio_post_pre, 6),
            "headline_note": "distribution-free; cite this, not p-value precision",
            "supporting": f"{result.expected_post_under_constant_rate:.0f} expected vs {post.episodes} observed post",
            "auxiliary_stat": "p_value_one_sided_poisson",
            "auxiliary_note": "assumes independent events; clustering would inflate p",
        },
        "pre_window": {
            "start": pre.start.isoformat(),
            "end": pre.end.isoformat(),
            "episodes": pre.episodes,
            "exposure_months": round(pre.exposure_months, 2),
            "rate_per_month": round(pre.rate_per_month, 4),
        },
        "post_window": {
            "start": post.start.isoformat(),
            "end": post.end.isoformat(),
            "episodes": post.episodes,
            "exposure_months": round(post.exposure_months, 2),
            "rate_per_month": round(post.rate_per_month, 4),
        },
        "expected_post_constant_rate": round(result.expected_post_under_constant_rate, 2),
        "rate_ratio_post_pre": round(result.rate_ratio_post_pre, 6),
        "shift_direction": result.shift_direction,
        "p_value_lower": result.p_value_lower,
        "p_value_upper": result.p_value_upper,
        "p_value_one_sided": result.p_value_one_sided,
        "verdict": result.verdict,
        "detail": result.detail,
    }
    path = RESULTS_DIR / "regime_funding_extreme_shift.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\n[OUTPUT] {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
