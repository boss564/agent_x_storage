#!/usr/bin/env python3
"""
Backtest Stage A: Pure Price Baseline (Dip-Reversion Model)

Assets: BTC/USDT, ETH/USDT (15m OHLCV)

Rules:
  - Entry: return_15m < -k_entry * sigma_15m (rolling 96, shift 1)
  - Exit: Target TP, Stop Loss SL, or Time Exit (4 candles / 60 min)
  - Execution: Pessimistic Intrabar Resolution; non-overlapping positions
  - Friction: 19 bps round-trip deduction per trade
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import ccxt
import numpy as np
import pandas as pd

DATA_DIR = "data"
RESULTS_DIR = "results"
SYMBOLS = ["BTC/USDT", "ETH/USDT"]
TIMEFRAME = "15m"
LOOKBACK_DAYS = 365
FRICTION_BPS = 0.0019  # 19 bps round-trip

K_ENTRY_GRID = [1.5, 2.0, 2.5, 3.0]
K_TP_GRID = [1.0, 1.5, 2.0]
K_SL_GRID = [0.5, 1.0, 1.5]

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)


def fetch_and_cache_ohlcv(symbol: str, days: int = 365) -> pd.DataFrame:
    """Fetch historical 15m OHLCV via ccxt with pagination and local CSV cache."""
    clean_symbol = symbol.replace("/", "_").lower()
    file_path = os.path.join(DATA_DIR, f"{clean_symbol}_15m.csv")

    if os.path.exists(file_path):
        print(f"[DATA] Loading cached data from {file_path}")
        return pd.read_csv(file_path, parse_dates=["timestamp"])

    print(f"[DATA] Fetching {days} days of {TIMEFRAME} data for {symbol} from Binance...")
    exchange = ccxt.binance({"enableRateLimit": True})

    now_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
    since_ts = now_ts - (days * 24 * 60 * 60 * 1000)

    all_candles: list = []
    limit = 1000
    while since_ts < now_ts:
        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, since=since_ts, limit=limit)
            if not candles:
                break
            all_candles.extend(candles)
            since_ts = candles[-1][0] + 1
            print(
                f"  Fetched up to "
                f"{datetime.fromtimestamp(since_ts / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')}"
            )
            time.sleep(exchange.rateLimit / 1000)
        except Exception as exc:
            print(f"[ERROR] Rate limit or network issue: {exc}. Retrying in 5 seconds...")
            time.sleep(5)

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df.drop_duplicates(subset=["timestamp"], inplace=True)
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    df.to_csv(file_path, index=False)
    print(f"[DATA] Successfully cached {len(df)} candles to {file_path}")
    return df


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """Returns and rolling sigma with strict look-ahead protection (shift 1)."""
    df = df.copy()
    df["return_15m"] = df["close"].pct_change()
    df["sigma_15m"] = df["return_15m"].shift(1).rolling(window=96).std()
    return df


def simulate_trade_strategy(df: pd.DataFrame, k_entry: float, k_tp: float, k_sl: float) -> list:
    """Simulate non-overlapping trades (position must close before a new one opens)."""
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
            tp_price = entry_price * (1.0 + k_tp * sigma)
            sl_price = entry_price * (1.0 - k_sl * sigma)

            exit_price = None
            exit_reason = None
            exit_idx = idx + 4

            for future_idx in range(idx + 1, idx + 5):
                high = df.at[future_idx, "high"]
                low = df.at[future_idx, "low"]
                hit_tp = high >= tp_price
                hit_sl = low <= sl_price

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

            gross_pnl = (exit_price - entry_price) / entry_price
            net_pnl = gross_pnl - FRICTION_BPS

            trades.append(
                {
                    "entry_time": df.at[idx, "timestamp"],
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "exit_reason": exit_reason,
                    "gross_pnl": gross_pnl,
                    "net_pnl": net_pnl,
                }
            )
            idx = exit_idx + 1
        else:
            idx += 1

    return trades


def classify_scenario(df_results: pd.DataFrame) -> str:
    """Classify Stage A outcome as Scenario 1, 2, or 3."""
    max_pnl = df_results["e_pnl_net"].max()
    has_robust = (df_results["plateau_robust"] & (df_results["e_pnl_net"] >= 0.001)).any()

    if max_pnl >= 0.001 and has_robust:
        return "SCENARIO 1: Standalone Alpha Validated (Pure Price Reversion works)."
    if max_pnl >= -0.0005:
        return "SCENARIO 2: Neutral Baseline. Requires Stage B (News Sentiment Filter) as catalyst."
    return "SCENARIO 3: Hypothesis Falsified. Pure Mean-Reversion dies to fees."


def evaluate_grid(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """3D grid search with 60% neighbor plateau robustness."""
    results = []
    grid_dict: dict = {}

    for ke in K_ENTRY_GRID:
        for ktp in K_TP_GRID:
            for ksl in K_SL_GRID:
                trades = simulate_trade_strategy(df, ke, ktp, ksl)
                n_trades = len(trades)

                if n_trades == 0:
                    metrics = {
                        "symbol": symbol,
                        "k_entry": ke,
                        "k_tp": ktp,
                        "k_sl": ksl,
                        "trades": 0,
                        "win_rate": 0.0,
                        "e_pnl_net": 0.0,
                        "e_pnl_gross": 0.0,
                        "sharpe": 0.0,
                        "profit_factor": 0.0,
                    }
                else:
                    net_pnls = np.array([t["net_pnl"] for t in trades])
                    wins = net_pnls[net_pnls > 0]
                    losses = net_pnls[net_pnls < 0]
                    win_rate = len(wins) / n_trades
                    e_pnl_net = float(np.mean(net_pnls))
                    e_pnl_gross = float(np.mean([t["gross_pnl"] for t in trades]))

                    std_pnl = np.std(net_pnls)
                    sharpe = (e_pnl_net / std_pnl * np.sqrt(365 * 24 * 4)) if std_pnl > 0 else 0.0

                    gross_wins = float(np.sum(wins)) if len(wins) > 0 else 0.0
                    gross_losses = float(np.abs(np.sum(losses))) if len(losses) > 0 else 0.0
                    profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else 999.0

                    metrics = {
                        "symbol": symbol,
                        "k_entry": ke,
                        "k_tp": ktp,
                        "k_sl": ksl,
                        "trades": n_trades,
                        "win_rate": win_rate,
                        "e_pnl_net": e_pnl_net,
                        "e_pnl_gross": e_pnl_gross,
                        "sharpe": sharpe,
                        "profit_factor": profit_factor,
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
        print(f"   RUNNING STAGE A BACKTEST FOR {symbol}")
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
                    "sharpe",
                    "profit_factor",
                    "plateau_robust",
                ]
            ]
            .head()
            .to_string(index=False)
        )

    final_df = pd.concat(all_results, ignore_index=True)
    out_file = os.path.join(RESULTS_DIR, "results_stage_a.csv")
    final_df.to_csv(out_file, index=False)
    print(f"\n[OUTPUT] Complete grid results saved to {out_file}")
    print(f"\n[OVERALL] {classify_scenario(final_df)}")


if __name__ == "__main__":
    main()
