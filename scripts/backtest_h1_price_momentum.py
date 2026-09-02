#!/usr/bin/env python3
"""
Backtest Stage B2: Dip Momentum / Continuation (SHORT after negative sigma shock)

Orthogonal to Stage A (long mean-reversion on the same dip trigger).

Assets: BTC/USDT, ETH/USDT (15m OHLCV)

Rules:
  - Entry: return_15m < -k_entry * sigma_15m → open SHORT at close
  - TP: price falls k_tp * sigma below entry (low touches tp_price)
  - SL: price rallies k_sl * sigma above entry (high touches sl_price)
  - Time exit: 4 candles (60 min) at close
  - Pessimistic intrabar: if TP and SL same bar → assume SL (adverse for short)
  - Non-overlapping positions; 19 bps round-trip friction
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
    K_ENTRY_GRID,
    K_SL_GRID,
    K_TP_GRID,
    LOOKBACK_DAYS,
    RESULTS_DIR,
    SYMBOLS,
    fetch_and_cache_ohlcv,
    prepare_features,
)
from scripts.backtest_metrics import metrics_from_trades, years_from_timestamps  # noqa: E402

os.makedirs(RESULTS_DIR, exist_ok=True)


def simulate_short_momentum(df: pd.DataFrame, k_entry: float, k_tp: float, k_sl: float) -> list:
    """Non-overlapping SHORT trades after negative sigma dips."""
    trades = []
    n_candles = len(df)
    idx = 97

    while idx < n_candles - 4:
        sigma = df.at[idx, "sigma_15m"]
        ret = df.at[idx, "return_15m"]
        if np.isnan(sigma) or sigma <= 0 or np.isnan(ret):
            idx += 1
            continue

        if ret < -k_entry * sigma:
            entry_price = df.at[idx, "close"]
            tp_price = entry_price * (1.0 - k_tp * sigma)
            sl_price = entry_price * (1.0 + k_sl * sigma)

            exit_price = None
            exit_reason = None
            exit_idx = idx + 4

            for future_idx in range(idx + 1, idx + 5):
                high = df.at[future_idx, "high"]
                low = df.at[future_idx, "low"]
                hit_tp = low <= tp_price
                hit_sl = high >= sl_price

                if hit_tp and hit_sl:
                    exit_price = sl_price
                    exit_reason = "SL_Pessimistic"
                    exit_idx = future_idx
                    break
                if hit_sl:
                    exit_price = sl_price
                    exit_reason = "SL"
                    exit_idx = future_idx
                    break
                if hit_tp:
                    exit_price = tp_price
                    exit_reason = "TP"
                    exit_idx = future_idx
                    break

            if exit_price is None:
                exit_price = df.at[idx + 4, "close"]
                exit_reason = "Time_Exit"

            gross_pnl = (entry_price - exit_price) / entry_price
            net_pnl = gross_pnl - FRICTION_BPS

            trades.append(
                {
                    "entry_time": df.at[idx, "timestamp"],
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "exit_reason": exit_reason,
                    "gross_pnl": gross_pnl,
                    "net_pnl": net_pnl,
                    "side": "SHORT",
                }
            )
            idx = exit_idx + 1
        else:
            idx += 1

    return trades


def classify_scenario(df_results: pd.DataFrame) -> str:
    max_pnl = df_results["e_pnl_net"].max()
    has_robust = (df_results["plateau_robust"] & (df_results["e_pnl_net"] >= 0.001)).any()

    if max_pnl >= 0.001 and has_robust:
        return "SCENARIO 1: Standalone Momentum Alpha (dip continuation SHORT works)."
    if max_pnl >= -0.0005:
        return "SCENARIO 2: Neutral Momentum Baseline. Sentiment filter may help."
    return "SCENARIO 3: Momentum Falsified. Neither reversion nor continuation survives fees on 15m."


def evaluate_grid(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    results = []
    grid_dict: dict = {}
    years = years_from_timestamps(df["timestamp"])

    for ke in K_ENTRY_GRID:
        for ktp in K_TP_GRID:
            for ksl in K_SL_GRID:
                trades = simulate_short_momentum(df, ke, ktp, ksl)
                metrics = {
                    "symbol": symbol,
                    "k_entry": ke,
                    "k_tp": ktp,
                    "k_sl": ksl,
                    **metrics_from_trades(trades, years=years),
                }
                results.append(metrics)
                grid_dict[(ke, ktp, ksl)] = metrics

    res_df = pd.DataFrame(results)
    plateau_robust = []
    for _, row in res_df.iterrows():
        ke, ktp, ksl = row["k_entry"], row["k_tp"], row["k_sl"]
        neighbors = []
        for d_ke in [-0.5, 0.0, 0.5]:
            for d_ktp in [-0.5, 0.0, 0.5]:
                for d_ksl in [-0.5, 0.0, 0.5]:
                    if d_ke == 0.0 and d_ktp == 0.0 and d_ksl == 0.0:
                        continue
                    n_key = (ke + d_ke, ktp + d_ktp, ksl + d_ksl)
                    if n_key in grid_dict:
                        neighbors.append(grid_dict[n_key])
        if not neighbors:
            plateau_robust.append(False)
        else:
            positive_neighbors = sum(1 for n in neighbors if n["e_pnl_net"] > 0)
            plateau_robust.append(positive_neighbors / len(neighbors) >= 0.60)

    res_df["plateau_robust"] = plateau_robust
    return res_df


def main() -> None:
    all_results = []

    for symbol in SYMBOLS:
        print("\n==========================================")
        print(f"   RUNNING STAGE B2 MOMENTUM BACKTEST FOR {symbol}")
        print("==========================================")

        raw_df = fetch_and_cache_ohlcv(symbol, days=LOOKBACK_DAYS)
        df = prepare_features(raw_df)
        symbol_res = evaluate_grid(df, symbol)
        all_results.append(symbol_res)

        sorted_res = symbol_res.sort_values(by="e_pnl_net", ascending=False)
        best = sorted_res.iloc[0]
        print(f"\n[SCENARIO] {classify_scenario(symbol_res)}")
        print(
            f"[GROSS] Best combo E[PnL_gross]={best['e_pnl_gross']:.6f} "
            f"E[PnL_net]={best['e_pnl_net']:.6f} trades={int(best['trades'])}"
        )
        print(f"\n[RESULTS] Top 5 Parameter Configurations for {symbol}:")
        print(
            sorted_res[
                [
                    "k_entry",
                    "k_tp",
                    "k_sl",
                    "trades",
                    "win_rate",
                    "e_pnl_gross",
                    "e_pnl_net",
                    "sharpe_per_trade",
                    "sharpe_annualized",
                    "profit_factor",
                    "plateau_robust",
                ]
            ]
            .head()
            .to_string(index=False)
        )

    final_df = pd.concat(all_results, ignore_index=True)
    out_file = os.path.join(RESULTS_DIR, "results_stage_b2_momentum.csv")
    final_df.to_csv(out_file, index=False)
    print(f"\n[OUTPUT] Complete grid results saved to {out_file}")
    print(f"\n[OVERALL] {classify_scenario(final_df)}")


if __name__ == "__main__":
    main()
