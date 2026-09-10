#!/usr/bin/env python3
"""M2a pre-data MDE for OOS episode test (Amendment A1, θ=0.05%)."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.backtest_h1_news_m2_shadow_lag import (
    MDE_POWER,
    MDE_REFERENCE_STD_BPS,
    min_detectable_effect_bps,
)
from scripts.m2a_config import MIN_EPISODES_OOS, PREREG_PRIMARY_THRESHOLD

# Single primary OOS hypothesis (θ=0.05%) — not Bonferroni across grid cells.
MDE_ALPHA_PRIMARY = 0.05

# From feasibility (funding-only, frozen split 2023-11-13) — Amendment A1 pre-PnL.
OOS_EPISODES_COMBINED = 33
OOS_EPISODES_BTC = 16
OOS_EPISODES_ETH = 17

MDE_INFORMATIVE_CEILING_BPS = 80.0  # above this, null ≈ underpowered (M2 convention)


def mde_report(n: int, label: str) -> dict:
    mde = min_detectable_effect_bps(
        n, MDE_REFERENCE_STD_BPS, alpha=MDE_ALPHA_PRIMARY, power=MDE_POWER
    )
    return {
        "label": label,
        "n_episodes": n,
        "sigma_ref_bps": MDE_REFERENCE_STD_BPS,
        "alpha": MDE_ALPHA_PRIMARY,
        "power": MDE_POWER,
        "mde_bps": round(mde, 2) if mde is not None else None,
        "informative": mde is not None and mde < MDE_INFORMATIVE_CEILING_BPS,
    }


def main() -> int:
    reports = [
        mde_report(OOS_EPISODES_COMBINED, "oos_combined"),
        mde_report(OOS_EPISODES_BTC, "oos_btc"),
        mde_report(OOS_EPISODES_ETH, "oos_eth"),
    ]
    primary = reports[0]

    print("=" * 72)
    print("M2a MDE — pre-data (Amendment A1, θ=0.05% OOS)")
    print("=" * 72)
    print(f"Formula: MDE = (z_(1-α) + z_power) · σ / √n_episodes  (M2 shadow lag)")
    print(f"σ_ref = {MDE_REFERENCE_STD_BPS} bps · α = {MDE_ALPHA_PRIMARY} · power = {MDE_POWER}")
    print(f"Informative ceiling: MDE < {MDE_INFORMATIVE_CEILING_BPS} bps")
    print()
    for r in reports:
        inf = "INFORMATIVE" if r["informative"] else "UNDERPOWERED (null non-informative)"
        print(f"  {r['label']:16s} n={r['n_episodes']:2d}  MDE={r['mde_bps']:.1f} bps  → {inf}")

    out = {
        "amendment": "A1",
        "primary_threshold": PREREG_PRIMARY_THRESHOLD,
        "min_episodes_oos": MIN_EPISODES_OOS,
        "mde_informative_ceiling_bps": MDE_INFORMATIVE_CEILING_BPS,
        "reports": reports,
        "primary_verdict_gate": primary["informative"],
    }
    path = Path("results") / "m2a_mde_prereg.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\n[OUTPUT] {path}")
    print(
        f"\n[GO] Primary OOS MDE={primary['mde_bps']:.1f} bps < {MDE_INFORMATIVE_CEILING_BPS} "
        f"— proceed with OHLCV download"
        if primary["informative"]
        else "\n[STOP] MDE too high — OOS null would be non-informative"
    )
    return 0 if primary["informative"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
