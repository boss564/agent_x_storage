#!/usr/bin/env python3
"""
Stage H2 Backtest: Volatility Breakout (BTC/ETH 15m)

Hypothesis: After volatility compression, a volatility spike predicts expansion
tradeable via directional bets (Long / Short variants tested separately).

Same execution discipline as Stage A / B2:
  - sigma with shift(1) look-ahead protection
  - non-overlapping positions
  - pessimistic intrabar TP/SL
  - 19 bps round-trip friction
"""
from __future__ import annotations

import os
import sys
from itertools import product
from pathlib import Path

from scripts.backtest_metrics import metrics_from_trades, years_from_timestamps

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.backtest_h1_price import (  # noqa: E402
    FRICTION_BPS,
    LOOKBACK_DAYS,
    RESULTS_DIR,
    SYMBOLS,
    classify_scenario,
    fetch_and_cache_ohlcv,
)

K_LOW_GRID = [0.5, 0.7, 0.9]
K_HIGH_GRID = [1.5, 2.0, 2.5]
K_TP_GRID = [1.0, 1.5, 2.0]
K_SL_GRID = [0.5, 1.0, 1.5]
VOL_WINDOW = 15  # short-horizon σ for compression/breakout detection
MEDIAN_WINDOW = 96  # baseline median(σ) lookback
MIN_IDX = MEDIAN_WINDOW + VOL_WINDOW + 2

os.makedirs(RESULTS_DIR, exist_ok=True)


def prepare_vol_features(
    df: pd.DataFrame,
    vol_window: int = VOL_WINDOW,
    median_window: int = MEDIAN_WINDOW,
) -> pd.DataFrame:
    """Volatility features: σ_15m = std(returns, vol_window); baseline = median(σ, 96)."""
    df = df.copy()
    df["return_15m"] = df["close"].pct_change()
    df["sigma_15m"] = df["return_15m"].shift(1).rolling(window=vol_window).std()
    df["sigma_median"] = df["sigma_15m"].rolling(window=median_window).median()
    return df


def _resolve_exit(
    df: pd.DataFrame,
    idx: int,
    entry_price: float,
    sigma: float,
    k_tp: float,
    k_sl: float,
    direction: str,
) -> tuple[float, str, int]:
    if direction == "long":
        tp_price = entry_price * (1.0 + k_tp * sigma)
        sl_price = entry_price * (1.0 - k_sl * sigma)
    else:
        tp_price = entry_price * (1.0 - k_tp * sigma)
        sl_price = entry_price * (1.0 + k_sl * sigma)

    exit_price = None
    exit_reason = None
    exit_idx = idx + 4

    for future_idx in range(idx + 1, idx + 5):
        high = df.at[future_idx, "high"]
        low = df.at[future_idx, "low"]
        if direction == "long":
            hit_tp = high >= tp_price
            hit_sl = low <= sl_price
        else:
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

    return exit_price, exit_reason, exit_idx


def simulate_vol_breakout(
    df: pd.DataFrame,
    k_low: float,
    k_high: float,
    k_tp: float,
    k_sl: float,
    direction: str,
) -> list:
    """Non-overlapping vol-compression → vol-breakout trades."""
    trades = []
    n_candles = len(df)
    idx = MIN_IDX

    while idx < n_candles - 4:
        sigma_prev = df.at[idx - 1, "sigma_15m"]
        med_prev = df.at[idx - 1, "sigma_median"]
        sigma_curr = df.at[idx, "sigma_15m"]
        med_curr = df.at[idx, "sigma_median"]

        if any(np.isnan(x) or x <= 0 for x in (sigma_prev, med_prev, sigma_curr, med_curr)):
            idx += 1
            continue

        compression = sigma_prev < k_low * med_prev
        breakout = sigma_curr > k_high * med_curr

        if compression and breakout:
            entry_price = df.at[idx, "close"]
            exit_price, exit_reason, exit_idx = _resolve_exit(
                df, idx, entry_price, sigma_curr, k_tp, k_sl, direction
            )

            if direction == "long":
                gross_pnl = (exit_price - entry_price) / entry_price
            else:
                gross_pnl = (entry_price - exit_price) / entry_price

            net_pnl = gross_pnl - FRICTION_BPS
            trades.append(
                {
                    "entry_time": df.at[idx, "timestamp"],
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "exit_reason": exit_reason,
                    "direction": direction,
                    "gross_pnl": gross_pnl,
                    "net_pnl": net_pnl,
                }
            )
            idx = exit_idx + 1
        else:
            idx += 1

    return trades


def _metrics(
    trades: list,
    symbol: str,
    direction: str,
    k_low: float,
    k_high: float,
    k_tp: float,
    k_sl: float,
    years: float | None,
) -> dict:
    base = metrics_from_trades(trades, years=years)
    return {
        "symbol": symbol,
        "direction": direction,
        "k_low": k_low,
        "k_high": k_high,
        "k_tp": k_tp,
        "k_sl": k_sl,
        **base,
    }


def evaluate_grid(df: pd.DataFrame, symbol: str, direction: str) -> pd.DataFrame:
    results = []
    grid_dict: dict = {}
    years = years_from_timestamps(df["timestamp"])

    for k_low, k_high, k_tp, k_sl in product(K_LOW_GRID, K_HIGH_GRID, K_TP_GRID, K_SL_GRID):
        trades = simulate_vol_breakout(df, k_low, k_high, k_tp, k_sl, direction)
        metrics = _metrics(trades, symbol, direction, k_low, k_high, k_tp, k_sl, years)
        results.append(metrics)
        grid_dict[(k_low, k_high, k_tp, k_sl)] = metrics

    res_df = pd.DataFrame(results)
    plateau_robust = []

    for _, row in res_df.iterrows():
        k_low, k_high, k_tp, k_sl = row["k_low"], row["k_high"], row["k_tp"], row["k_sl"]
        neighbors = []
        for d_lo in [-0.2, 0.0, 0.2]:
            for d_hi in [-0.5, 0.0, 0.5]:
                for d_tp in [-0.5, 0.0, 0.5]:
                    for d_sl in [-0.5, 0.0, 0.5]:
                        if d_lo == d_hi == d_tp == d_sl == 0.0:
                            continue
                        key = (k_low + d_lo, k_high + d_hi, k_tp + d_tp, k_sl + d_sl)
                        if key in grid_dict:
                            neighbors.append(grid_dict[key])

        if not neighbors:
            plateau_robust.append(False)
        else:
            positive = sum(1 for n in neighbors if n["e_pnl_net"] > 0)
            plateau_robust.append(positive / len(neighbors) >= 0.60)

    res_df["plateau_robust"] = plateau_robust
    return res_df


def classify_h2(df_results: pd.DataFrame, min_trades: int = 10) -> str:
    """H2 scenario: require min_trades — sparse cells must not trigger Scenario 1."""
    eligible = df_results[df_results["trades"] >= min_trades]
    if eligible.empty:
        eligible = df_results

    max_pnl = eligible["e_pnl_net"].max()
    has_robust = (
        (eligible["plateau_robust"] & (eligible["e_pnl_net"] >= 0.001) & (eligible["trades"] >= min_trades))
    ).any()

    if max_pnl >= 0.001 and has_robust:
        return "SCENARIO 1: Vol-Breakout standalone alpha (grid + plateau robust)."
    if max_pnl >= -0.0005:
        return "SCENARIO 2: Neutral baseline — exogenous catalyst required."
    return "SCENARIO 3: Hypothesis falsified — Vol-Breakout dies to fees on 15m."


def main() -> None:
    all_results = []

    for symbol in SYMBOLS:
        raw_df = fetch_and_cache_ohlcv(symbol, days=LOOKBACK_DAYS)
        df = prepare_vol_features(raw_df)

        for direction in ("long", "short"):
            print("\n==========================================")
            print(f"   STAGE H2 VOL-BREAKOUT — {symbol} — {direction.upper()}")
            print("==========================================")

            symbol_res = evaluate_grid(df, symbol, direction)
            all_results.append(symbol_res)

            sorted_res = symbol_res.sort_values(by="e_pnl_net", ascending=False)
            best = sorted_res.iloc[0]
            print(f"\n[SCENARIO] {classify_h2(symbol_res)}")
            print(
                f"[GROSS] Best E[PnL_gross]={best['e_pnl_gross']:.6f} "
                f"E[PnL_net]={best['e_pnl_net']:.6f} trades={int(best['trades'])}"
            )
            print("\n[RESULTS] Top 5:")
            print(
                sorted_res[
                    [
                        "k_low",
                        "k_high",
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
    out_file = os.path.join(RESULTS_DIR, "results_stage_h2_vol_breakout.csv")
    final_df.to_csv(out_file, index=False)
    print(f"\n[OUTPUT] Saved to {out_file}")
    print(f"\n[OVERALL] {classify_h2(final_df)}")


if __name__ == "__main__":
    main()
