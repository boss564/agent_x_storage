#!/usr/bin/env python3
"""
M2b Backtest: Volume-Explosion Breakout (Smart-Money Hypothesis)

Hypothesis: Sudden volume > k_vol * median(volume, 96) combined with
|return_15m| > k_entry * sigma_15m signals institutional entry.

Execution (aligned with Stage A / H2 / H1_M2_EVENT_DRIVEN_SPEC):
  - sigma and volume median: shift(1) look-ahead protection
  - non-overlapping positions
  - pessimistic intrabar TP/SL (SL first if both hit)
  - time exit after 4 candles (60 min)
  - friction: 19 bps BTC, 25 bps ETH (override via --cost)
"""
from __future__ import annotations

import argparse
import os
import sys
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.backtest_metrics import metrics_from_trades, trade_sharpe_stats, years_from_timestamps

DATA_DIR = "data"
RESULTS_DIR = "results"
SYMBOLS = ["BTC/USDT", "ETH/USDT"]
FRICTION_BPS = 0.0019  # 19 bps default round-trip
LOOKBACK_DAYS = 365

LOOKBACK_PERIOD = 96
TIME_EXIT_BARS = 4
MIN_TRADES_FOR_VALIDATION = 20

DEFAULT_K_VOL = 5.0
DEFAULT_K_ENTRY = 1.5
DEFAULT_K_TP = 2.0
DEFAULT_K_SL = 1.0

TRADING_COST_BPS = {
    "BTC": 19.0,
    "ETH": 25.0,
}

K_VOL_GRID = [3.0, 5.0, 7.0]
K_ENTRY_GRID = [1.5, 2.0, 2.5]
K_TP_GRID = [1.0, 1.5, 2.0]
K_SL_GRID = [0.5, 1.0, 1.5]

MIN_IDX = LOOKBACK_PERIOD + 2

os.makedirs(RESULTS_DIR, exist_ok=True)


def _load_cached_symbol(symbol: str) -> pd.DataFrame:
    slug = symbol.replace("/", "_").lower()
    path = Path(DATA_DIR) / f"{slug}_15m.csv"
    if not path.is_file():
        raise FileNotFoundError(f"Missing {path} — run backtest_h1_price.py once or pass --data")
    return load_data(path)


def load_data(file_path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(file_path, parse_dates=["timestamp"])
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def prepare_features(df: pd.DataFrame, lookback: int = LOOKBACK_PERIOD) -> pd.DataFrame:
    df = df.copy()
    df["return_15m"] = df["close"].pct_change()
    df["sigma_15m"] = df["return_15m"].shift(1).rolling(window=lookback).std()
    df["vol_median_96"] = df["volume"].shift(1).rolling(window=lookback).median()
    return df


def _resolve_exit(
    df: pd.DataFrame,
    idx: int,
    entry_price: float,
    sigma: float,
    k_tp: float,
    k_sl: float,
    direction: int,
) -> tuple[float, str, int]:
    if direction == 1:
        tp_price = entry_price * (1.0 + k_tp * sigma)
        sl_price = entry_price * (1.0 - k_sl * sigma)
    else:
        tp_price = entry_price * (1.0 - k_tp * sigma)
        sl_price = entry_price * (1.0 + k_sl * sigma)

    exit_price = None
    exit_reason = None
    exit_idx = idx + TIME_EXIT_BARS

    for future_idx in range(idx + 1, idx + TIME_EXIT_BARS + 1):
        high = df.at[future_idx, "high"]
        low = df.at[future_idx, "low"]
        if direction == 1:
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
        exit_price = df.at[idx + TIME_EXIT_BARS, "close"]
        exit_reason = "Time_Exit"

    return exit_price, exit_reason, exit_idx


def simulate_volume_breakout(
    df: pd.DataFrame,
    k_vol: float = DEFAULT_K_VOL,
    k_entry: float = DEFAULT_K_ENTRY,
    k_tp: float = DEFAULT_K_TP,
    k_sl: float = DEFAULT_K_SL,
    friction: float = FRICTION_BPS,
) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    n_candles = len(df)
    idx = MIN_IDX

    while idx < n_candles - TIME_EXIT_BARS:
        sigma = df.at[idx, "sigma_15m"]
        vol_med = df.at[idx, "vol_median_96"]
        ret = df.at[idx, "return_15m"]
        curr_vol = df.at[idx, "volume"]

        if (
            np.isnan(sigma)
            or sigma <= 0
            or np.isnan(vol_med)
            or vol_med <= 0
            or np.isnan(ret)
        ):
            idx += 1
            continue

        vol_spike = curr_vol > k_vol * vol_med
        ret_spike = abs(ret) > k_entry * sigma

        if vol_spike and ret_spike:
            direction = 1 if ret > 0 else -1
            entry_price = df.at[idx, "close"]
            exit_price, exit_reason, exit_idx = _resolve_exit(
                df, idx, entry_price, sigma, k_tp, k_sl, direction
            )
            gross_pnl = direction * (exit_price - entry_price) / entry_price
            net_pnl = gross_pnl - friction
            trades.append(
                {
                    "entry_time": df.at[idx, "timestamp"],
                    "exit_time": df.at[exit_idx, "timestamp"],
                    "direction": "LONG" if direction == 1 else "SHORT",
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "gross_pnl": gross_pnl,
                    "net_pnl": net_pnl,
                    "exit_reason": exit_reason,
                }
            )
            idx = exit_idx + 1
        else:
            idx += 1

    return trades


def aggregate_trades(
    trades: list[dict[str, Any]],
    *,
    years: float | None = None,
) -> dict[str, Any]:
    if not trades:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "avg_return": 0.0,
            "std_return": 0.0,
            "sharpe_per_trade": 0.0,
            "sharpe_annualized": 0.0,
            "cumulative_return": 0.0,
            "profit_factor": 0.0,
            "trades_df": pd.DataFrame(),
        }

    df_trades = pd.DataFrame(trades)
    net = df_trades["net_pnl"].to_numpy()
    m = metrics_from_trades(trades, years=years)
    sharpe = trade_sharpe_stats(net, years=years)

    return {
        "total_trades": m["trades"],
        "win_rate": m["win_rate"],
        "avg_return": m["e_pnl_net"],
        "std_return": sharpe["std"],
        "sharpe_per_trade": m["sharpe_per_trade"],
        "sharpe_annualized": m["sharpe_annualized"],
        "cumulative_return": float(np.sum(net)),
        "profit_factor": m["profit_factor"],
        "trades_df": df_trades,
    }


def evaluate_verdict(
    result: dict[str, Any],
    min_trades: int = MIN_TRADES_FOR_VALIDATION,
) -> tuple[str, str]:
    total = result["total_trades"]
    if total < min_trades:
        return "NEUTRAL", f"Zu wenige Trades ({total} < {min_trades}) — keine statistische Aussage"

    sharpe = result["sharpe_per_trade"]
    avg_ret = result["avg_return"]
    win_rate = result["win_rate"]

    if sharpe > 0.5 and avg_ret > 0 and win_rate > 0.5:
        return (
            "PASS",
            f"Sharpe={sharpe:.2f}, avg_ret={avg_ret * 100:.3f}%, win_rate={win_rate:.2%}",
        )
    if sharpe <= 0 or avg_ret <= 0 or win_rate <= 0.4:
        return (
            "FAIL",
            f"Sharpe={sharpe:.2f}, avg_ret={avg_ret * 100:.3f}%, win_rate={win_rate:.2%}",
        )
    return (
        "NEUTRAL",
        f"Sharpe={sharpe:.2f}, avg_ret={avg_ret * 100:.3f}%, win_rate={win_rate:.2%}",
    )


def _grid_metrics(
    trades: list[dict[str, Any]],
    symbol: str,
    k_vol: float,
    k_entry: float,
    k_tp: float,
    k_sl: float,
    years: float | None,
) -> dict[str, Any]:
    m = metrics_from_trades(trades, years=years)
    return {
        "symbol": symbol,
        "k_vol": k_vol,
        "k_entry": k_entry,
        "k_tp": k_tp,
        "k_sl": k_sl,
        **m,
    }


def evaluate_grid(df: pd.DataFrame, symbol: str, friction: float) -> pd.DataFrame:
    years = years_from_timestamps(df["timestamp"])
    results = []
    for k_vol, k_entry, k_tp, k_sl in product(K_VOL_GRID, K_ENTRY_GRID, K_TP_GRID, K_SL_GRID):
        trades = simulate_volume_breakout(
            df, k_vol=k_vol, k_entry=k_entry, k_tp=k_tp, k_sl=k_sl, friction=friction
        )
        results.append(_grid_metrics(trades, symbol, k_vol, k_entry, k_tp, k_sl, years))
    return pd.DataFrame(results)


def classify_m2b(df_results: pd.DataFrame, min_trades: int = 10) -> str:
    eligible = df_results[df_results["trades"] >= min_trades]
    if eligible.empty:
        eligible = df_results
    max_pnl = eligible["e_pnl_net"].max()
    if max_pnl >= 0.0010:
        return "SCENARIO 1: Standalone Alpha Validated (Volume Breakouts survive friction)."
    if max_pnl >= -0.0005:
        return "SCENARIO 2: Neutral Baseline. Requires Sentiment or Orderbook Filter."
    return "SCENARIO 3: Hypothesis Falsified. Volume Breakouts die to fees."


def _friction_bps(symbol: str, cost_override: float | None) -> float:
    if cost_override is not None:
        return cost_override / 10000.0
    return TRADING_COST_BPS.get(symbol.upper(), 25.0) / 10000.0


def run_single(
    df: pd.DataFrame,
    symbol: str,
    friction: float,
    k_vol: float,
    k_entry: float,
    k_tp: float,
    k_sl: float,
) -> dict[str, Any]:
    featured = prepare_features(df)
    n_signals = 0
    for idx in range(MIN_IDX, len(featured) - TIME_EXIT_BARS):
        row = featured.iloc[idx]
        if (
            not np.isnan(row["sigma_15m"])
            and row["sigma_15m"] > 0
            and not np.isnan(row["vol_median_96"])
            and row["vol_median_96"] > 0
            and not np.isnan(row["return_15m"])
            and row["volume"] > k_vol * row["vol_median_96"]
            and abs(row["return_15m"]) > k_entry * row["sigma_15m"]
        ):
            n_signals += 1

    trades = simulate_volume_breakout(
        featured, k_vol=k_vol, k_entry=k_entry, k_tp=k_tp, k_sl=k_sl, friction=friction
    )
    years = years_from_timestamps(df["timestamp"])
    result = aggregate_trades(trades, years=years)
    result["raw_signals"] = n_signals
    return result


def _print_single_report(
    symbol: str,
    df: pd.DataFrame,
    result: dict[str, Any],
    friction_bps: float,
    k_vol: float,
    k_entry: float,
    k_tp: float,
    k_sl: float,
    export_prefix: str | None = None,
) -> str:
    print(f"Daten: {len(df)} Kerzen, {df['timestamp'].iloc[0]} .. {df['timestamp'].iloc[-1]}")
    print(f"Parameter: k_vol={k_vol} k_entry={k_entry} k_tp={k_tp} k_sl={k_sl}")
    print(f"Reibung (Round-Trip): {friction_bps:.1f} bps")
    print(f"Roh-Signale (überlappend): {result.get('raw_signals', '—')}")
    print(f"Trades (non-overlap): {result['total_trades']}")
    if result["total_trades"] > 0:
        print(f"  Win-Rate: {result['win_rate']:.2%}")
        print(f"  E[PnL_net]: {result['avg_return'] * 100:.3f}%")
        print(f"  Sharpe/trade: {result['sharpe_per_trade']:.3f}")
        print(f"  Sharpe (annualisiert, sqrt(trades/J)): {result['sharpe_annualized']:.2f}")
        print(f"  Profit Factor: {result['profit_factor']:.2f}")
        print(f"  Kumuliert (net): {result['cumulative_return'] * 100:.2f}%")

    verdict, reason = evaluate_verdict(result)
    print("\n--- URTEIL ---")
    print(f"Verdict: {verdict}")
    print(f"Begründung: {reason}")

    if result["total_trades"] > 0 and export_prefix:
        out = os.path.join(RESULTS_DIR, f"m2b_trades_{export_prefix}.csv")
        result["trades_df"].to_csv(out, index=False)
        print(f"Trades exportiert: {out}")
    return verdict


def main() -> int:
    parser = argparse.ArgumentParser(description="M2b Volume-Explosion Backtest")
    parser.add_argument("--data", help="Pfad zur 15m-CSV (z.B. data/btc_usdt_15m.csv)")
    parser.add_argument("--symbol", default="BTC", help="Symbol für Kosten (BTC/ETH)")
    parser.add_argument("--cost", type=float, default=None, help="Round-Trip-Kosten in bps")
    parser.add_argument("--k-vol", type=float, default=DEFAULT_K_VOL)
    parser.add_argument("--k-entry", type=float, default=DEFAULT_K_ENTRY)
    parser.add_argument("--k-tp", type=float, default=DEFAULT_K_TP)
    parser.add_argument("--k-sl", type=float, default=DEFAULT_K_SL)
    parser.add_argument("--grid", action="store_true", help="81-Kombinationen Grid-Search")
    parser.add_argument(
        "--all",
        action="store_true",
        help="BTC+ETH mit Cache (fetch wenn fehlt)",
    )
    parser.add_argument("--min-trades", type=int, default=MIN_TRADES_FOR_VALIDATION)
    args = parser.parse_args()

    if args.grid or args.all:
        frames = []
        for symbol in SYMBOLS:
            slug = symbol.replace("/", "_").lower()
            print(f"\n==========================================")
            print(f"   STAGE M2b — {symbol}")
            print("==========================================")
            raw_df = _load_cached_symbol(symbol)
            featured = prepare_features(raw_df)
            sym = symbol.split("/")[0]
            friction = _friction_bps(sym, args.cost)

            if args.grid:
                res_df = evaluate_grid(featured, symbol, friction)
                frames.append(res_df)
                top = res_df.sort_values("e_pnl_net", ascending=False).head(5)
                print("\nTop 5 Konfigurationen:")
                print(
                    top[
                        [
                            "k_vol",
                            "k_entry",
                            "k_tp",
                            "k_sl",
                            "trades",
                            "win_rate",
                            "e_pnl_gross",
                            "e_pnl_net",
                            "sharpe_per_trade",
                            "sharpe_annualized",
                        ]
                    ].to_string(index=False)
                )
                print(f"\n{classify_m2b(res_df)}")
            else:
                result = run_single(
                    raw_df,
                    sym,
                    friction,
                    args.k_vol,
                    args.k_entry,
                    args.k_tp,
                    args.k_sl,
                )
                _print_single_report(
                    sym,
                    raw_df,
                    result,
                    friction * 10000,
                    args.k_vol,
                    args.k_entry,
                    args.k_tp,
                    args.k_sl,
                    export_prefix=slug,
                )

        if args.grid and frames:
            final = pd.concat(frames, ignore_index=True)
            out = os.path.join(RESULTS_DIR, "stage_m2b_results.csv")
            final.to_csv(out, index=False)
            print(f"\n[OUTPUT] {out}")
            print(f"[OVERALL] {classify_m2b(final)}")
        return 0

    if not args.data:
        parser.error("--data required unless --all or --grid is set")

    df = load_data(args.data)
    sym = args.symbol.upper()
    friction = _friction_bps(sym, args.cost)
    result = run_single(
        df, sym, friction, args.k_vol, args.k_entry, args.k_tp, args.k_sl
    )
    verdict = _print_single_report(
        sym,
        df,
        result,
        friction * 10000,
        args.k_vol,
        args.k_entry,
        args.k_tp,
        args.k_sl,
        export_prefix=sym.lower(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
