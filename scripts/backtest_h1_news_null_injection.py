#!/usr/bin/env python3
"""
H1 Methodology Test (M0 + M1) — NOT a performance backtest.

M0: Random sentiment labels on Stage-A dip trades → verify filter does not
    hallucinate alpha (Monte-Carlo null injection).

M1: Oracle labels (gross_pnl >= threshold) → upper bound on any filter's
    achievable edge on the falsified dip pool.

See docs/H1_NEWS_METHODOLOGY_PREREG.md
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.backtest_h1_price import (  # noqa: E402
    FRICTION_BPS,
    LOOKBACK_DAYS,
    RESULTS_DIR,
    SYMBOLS,
    fetch_and_cache_ohlcv,
    prepare_features,
    simulate_trade_strategy,
)

# Canonical params (documented in prereg; stable trade count)
K_ENTRY = 2.0
K_TP = 1.5
K_SL = 1.0

M0_N_SEEDS = 500
M0_DELTA_BPS = 0.0005  # 5 bps tolerance for PASS
ORACLE_GROSS_THRESH = 0.003  # +30 bps
ORACLE_TOP_PCTS = [10, 20, 30]

os.makedirs(RESULTS_DIR, exist_ok=True)


def build_trade_pool() -> pd.DataFrame:
    """Export per-trade PnL from Stage A canonical params."""
    rows = []
    for symbol in SYMBOLS:
        df = prepare_features(fetch_and_cache_ohlcv(symbol, days=LOOKBACK_DAYS))
        trades = simulate_trade_strategy(df, K_ENTRY, K_TP, K_SL)
        for t in trades:
            rows.append({"symbol": symbol, **t})
    return pd.DataFrame(rows)


def _metrics(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"n": 0, "e_gross": 0.0, "e_net": 0.0}
    return {
        "n": len(trades),
        "e_gross": float(trades["gross_pnl"].mean()),
        "e_net": float(trades["net_pnl"].mean()),
    }


def run_m0(trade_pool: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Monte-Carlo null injection: random ±1 labels, keep sentiment==+1."""
    baseline = _metrics(trade_pool)
    rng = np.random.default_rng(42)
    records = []

    for seed in range(M0_N_SEEDS):
        labels = rng.choice([-1, 1], size=len(trade_pool))
        labeled = trade_pool.copy()
        labeled["sentiment"] = labels
        filtered = labeled[labeled["sentiment"] == 1]
        m = _metrics(filtered)
        records.append(
            {
                "seed": seed,
                "n_filtered": m["n"],
                "e_gross": m["e_gross"],
                "e_net": m["e_net"],
                "delta_net_vs_baseline": m["e_net"] - baseline["e_net"],
            }
        )

    mc_df = pd.DataFrame(records)
    within_tol = (mc_df["delta_net_vs_baseline"].abs() < M0_DELTA_BPS).mean()
    summary = {
        "baseline_n": baseline["n"],
        "baseline_e_gross": baseline["e_gross"],
        "baseline_e_net": baseline["e_net"],
        "mc_seeds": M0_N_SEEDS,
        "pct_within_5bps": float(within_tol),
        "m0_pass": bool(within_tol >= 0.95),
    }
    return mc_df, summary


def run_m1(trade_pool: pd.DataFrame) -> pd.DataFrame:
    """Oracle ceiling: perfect foreknowledge filters."""
    baseline = _metrics(trade_pool)
    rows = [
        {
            "filter": "unfiltered",
            "n": baseline["n"],
            "e_gross": baseline["e_gross"],
            "e_net": baseline["e_net"],
            "pct_of_pool": 100.0,
        }
    ]

    oracle = trade_pool[trade_pool["gross_pnl"] >= ORACLE_GROSS_THRESH]
    om = _metrics(oracle)
    rows.append(
        {
            "filter": f"oracle_gross>={ORACLE_GROSS_THRESH:.4f}",
            "n": om["n"],
            "e_gross": om["e_gross"],
            "e_net": om["e_net"],
            "pct_of_pool": 100.0 * om["n"] / baseline["n"] if baseline["n"] else 0.0,
        }
    )

    for pct in ORACLE_TOP_PCTS:
        k = max(1, int(np.ceil(len(trade_pool) * pct / 100)))
        top = trade_pool.nlargest(k, "gross_pnl")
        tm = _metrics(top)
        rows.append(
            {
                "filter": f"oracle_top_{pct}pct",
                "n": tm["n"],
                "e_gross": tm["e_gross"],
                "e_net": tm["e_net"],
                "pct_of_pool": 100.0 * tm["n"] / baseline["n"] if baseline["n"] else 0.0,
            }
        )

    return pd.DataFrame(rows)


def main() -> None:
    print("=" * 72)
    print("H1 METHODOLOGY — M0 Null-Injection + M1 Oracle Ceiling")
    print("=" * 72)

    pool = build_trade_pool()
    pool_path = os.path.join(RESULTS_DIR, "h1_trade_pool_stage_a.csv")
    pool.to_csv(pool_path, index=False)
    print(f"\n[POOL] {len(pool)} trades → {pool_path}")
    print(f"       E[gross]={pool['gross_pnl'].mean():.6f}  E[net]={pool['net_pnl'].mean():.6f}")

    mc_df, m0 = run_m0(pool)
    mc_path = os.path.join(RESULTS_DIR, "h1_m0_null_injection_summary.csv")
    mc_df.to_csv(mc_path, index=False)

    print("\n--- M0 Null-Injection ---")
    print(f"Baseline: n={m0['baseline_n']} E[net]={m0['baseline_e_net']:.6f}")
    print(f"MC seeds={m0['mc_seeds']}  within ±5bps: {m0['pct_within_5bps']:.1%}")
    print(f"M0 PASS: {m0['m0_pass']}")

    m1_df = run_m1(pool)
    m1_path = os.path.join(RESULTS_DIR, "h1_m1_oracle_ceiling.csv")
    m1_df.to_csv(m1_path, index=False)

    print("\n--- M1 Oracle Ceiling ---")
    print(m1_df.to_string(index=False))
    print(f"\n[OUTPUT] {mc_path}")
    print(f"[OUTPUT] {m1_path}")

    oracle_row = m1_df[m1_df["filter"].str.startswith("oracle_gross")].iloc[0]
    print(
        f"\n[VERDICT] M0: {'PASS' if m0['m0_pass'] else 'FAIL'} — filter methodology clean."
    )
    print(
        f"[VERDICT] M1: Oracle n={int(oracle_row['n'])} "
        f"E[net]={oracle_row['e_net']:.4%} (CHEATING — variance exists, not news proof)."
    )
    print(
        "         H1 path: News-FIRST exogenous trigger; dip-filter remains negative control."
    )


if __name__ == "__main__":
    main()
