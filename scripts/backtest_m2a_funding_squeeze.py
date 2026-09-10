#!/usr/bin/env python3
"""
Stage M2a Backtest: Funding Rate Squeeze (leverage overhang mean-reversion)

Hypothesis: Extreme funding rates indicate crowded leverage; market tends to
squeeze those positions → counter-move tradeable after costs.

Trigger:
  funding_rate > +threshold  → SHORT
  funding_rate < -threshold  → LONG

Exit: k_tp/k_sl × σ_15m (96-bar, shift(1)), time exit 4×15m, pessimistic intrabar.

Data:
  OHLCV: data/btc_usdt_15m.csv, data/eth_usdt_15m.csv
  Funding: Binance fapi/v1/fundingRate (8h cadence) → cache data/*_funding_rates.csv
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.backtest_metrics import (
    assign_funding_episode_ids,
    metrics_from_episodes,
    metrics_from_trades,
    years_from_timestamps,
)
from scripts.m2a_config import (
    FRICTION_EARLY,
    FRICTION_MODERN,
    FUNDING_THRESHOLDS_PREREG,
    K_SL_GRID,
    K_TP_GRID,
    MAX_TRADES_PER_EPISODE,
    MIN_EPISODES_OOS,
    OOS_SPLIT_TS,
    PERP_START,
    PREREG_FREEZE,
    PREREG_PRIMARY_THRESHOLD,
    friction_for_timestamp,
    split_label,
)

DATA_DIR = "data"
RESULTS_DIR = "results"
SYMBOLS = ["BTC/USDT", "ETH/USDT"]
LOOKBACK_PERIOD = 96
TIME_EXIT_BARS = 4
MIN_TRADES_GRID = 10
MIN_IDX = LOOKBACK_PERIOD + 2

FUNDING_THRESHOLDS_EXPLORATORY = [0.00003, 0.00005, 0.0001]  # nur mit --exploratory

REFERENCE_HIGH_FUNDING = {
    "BTC/USDT": ("2021-02-21T16:00:00+00:00", 0.00125820),
    "ETH/USDT": ("2024-11-12T08:00:00+00:00", 0.00057620),
}

BINANCE_FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)


def _api_funding_at(symbol: str, ts: pd.Timestamp) -> float:
    sym = symbol.replace("/", "")
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    else:
        t = t.tz_convert("UTC")
    ms = int(t.timestamp() * 1000)
    qs = urllib.parse.urlencode({"symbol": sym, "startTime": ms, "limit": 1})
    url = f"{BINANCE_FUNDING_URL}?{qs}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        rows = json.loads(resp.read().decode())
    if not rows:
        raise ValueError(f"no API funding row for {symbol} at {ts}")
    return float(rows[0]["fundingRate"])


def download_funding_rates(
    symbol: str, days: int = 365, refresh: bool = False, full_history: bool = False
) -> pd.DataFrame:
    slug = symbol.replace("/", "_").lower()
    suffix = "_full" if full_history else ""
    cache_file = Path(DATA_DIR) / f"{slug}_funding_rates{suffix}.csv"
    if cache_file.is_file() and not refresh:
        print(f"[DATA] cache {cache_file}")
        df = pd.read_csv(cache_file, parse_dates=["timestamp"])
        return df.sort_values("timestamp").reset_index(drop=True)

    if full_history:
        since = int(PERP_START.timestamp() * 1000)
        end = int(PREREG_FREEZE.timestamp() * 1000)
        print(f"[DATA] download funding {symbol} full history")
    else:
        since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
        end = int(datetime.now(timezone.utc).timestamp() * 1000)
        print(f"[DATA] download funding {symbol} ({days}d, refresh={refresh})")
    sym = symbol.replace("/", "")
    all_rows: list[dict[str, Any]] = []

    while since < end:
        qs = urllib.parse.urlencode({"symbol": sym, "startTime": since, "limit": 1000})
        url = f"{BINANCE_FUNDING_URL}?{qs}"
        with urllib.request.urlopen(url, timeout=30) as resp:
            rows = json.loads(resp.read().decode())
        if not rows:
            break
        all_rows.extend(rows)
        since = int(rows[-1]["fundingTime"]) + 1
        time.sleep(0.08)
        if len(rows) < 1000:
            break

    df = pd.DataFrame(all_rows)
    df = df.rename(columns={"fundingTime": "timestamp", "fundingRate": "funding_rate"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df["funding_rate"] = df["funding_rate"].astype(float)
    df = df[["timestamp", "funding_rate"]].drop_duplicates(subset=["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    df.to_csv(cache_file, index=False)
    print(f"[DATA] saved {cache_file} ({len(df)} rows)")
    return df


def validate_funding_data(
    symbol: str, funding: pd.DataFrame, ohlcv: pd.DataFrame
) -> dict[str, Any]:
    """Cache vs Binance-API + Erreichbarkeit der Prereg-Schwellen im OHLCV-Fenster."""
    fr = funding["funding_rate"].astype(float)
    ohlcv_ts = _to_utc_ns(ohlcv["timestamp"])
    fund_ts = _to_utc_ns(funding["timestamp"])
    ohlcv_start, ohlcv_end = ohlcv_ts.min(), ohlcv_ts.max()

    in_window = funding.loc[(fund_ts >= ohlcv_start) & (fund_ts <= ohlcv_end), "funding_rate"].astype(float)
    max_abs_window = float(in_window.abs().max()) if len(in_window) else float("nan")

    idx = fr.abs().idxmax()
    cache_max_ts = funding.at[idx, "timestamp"]
    cache_max_fr = float(funding.at[idx, "funding_rate"])
    api_max_fr = _api_funding_at(symbol, pd.Timestamp(cache_max_ts))

    ref_ts, ref_expected = REFERENCE_HIGH_FUNDING[symbol]
    api_ref_fr = _api_funding_at(symbol, pd.Timestamp(ref_ts))

    prereg_counts = {
        str(thr): int((in_window.abs() >= thr).sum()) for thr in FUNDING_THRESHOLDS_PREREG
    }

    scale_ok = abs(cache_max_fr - api_max_fr) < 1e-10
    ref_ok = abs(api_ref_fr - ref_expected) < 1e-6

    report: dict[str, Any] = {
        "symbol": symbol,
        "funding_rows": len(funding),
        "funding_span": [str(fund_ts.min()), str(fund_ts.max())],
        "ohlcv_span": [str(ohlcv_start), str(ohlcv_end)],
        "max_abs_fr_in_ohlcv_window": max_abs_window,
        "max_abs_fr_cache": float(fr.abs().max()),
        "cache_vs_api_max_ratio": cache_max_fr / api_max_fr if api_max_fr else None,
        "scale_check_pass": scale_ok,
        "reference_date": ref_ts,
        "reference_api_fr": api_ref_fr,
        "reference_expected_fr": ref_expected,
        "reference_check_pass": ref_ok,
        "prereg_event_counts_in_ohlcv_window": prereg_counts,
        "prereg_testable": any(v > 0 for v in prereg_counts.values()),
    }
    return report


def print_validation(report: dict[str, Any]) -> None:
    sym = report["symbol"]
    print(f"\n[VALIDATE] {sym}")
    print(f"  OHLCV window: {report['ohlcv_span'][0]} .. {report['ohlcv_span'][1]}")
    print(f"  Funding cache: {report['funding_span'][0]} .. {report['funding_span'][1]}")
    print(
        f"  max|fr| in OHLCV window: {report['max_abs_fr_in_ohlcv_window']:.8f} "
        f"({report['max_abs_fr_in_ohlcv_window']*100:.4f}%)"
    )
    ratio = report["cache_vs_api_max_ratio"]
    print(
        f"  cache vs API (max-abs slot): ratio={ratio:.6f} "
        f"→ {'SCALE OK' if report['scale_check_pass'] else 'SCALE MISMATCH'}"
    )
    print(
        f"  reference {report['reference_date']}: API={report['reference_api_fr']:.8f} "
        f"(expected {report['reference_expected_fr']:.8f}) "
        f"→ {'OK' if report['reference_check_pass'] else 'MISMATCH'}"
    )
    print(f"  prereg events in window: {report['prereg_event_counts_in_ohlcv_window']}")
    if report["prereg_testable"]:
        print("  → Prereg-Schwellen im Fenster ERREICHBAR")
    else:
        print("  → Prereg-Schwellen im Fenster NICHT ERREICHBAR (kein Negativbefund)")


def load_ohlcv(symbol: str, *, full_history: bool = False) -> pd.DataFrame:
    slug = symbol.replace("/", "_").lower()
    name = f"{slug}_15m_perp_full.csv" if full_history else f"{slug}_15m.csv"
    path = Path(DATA_DIR) / name
    if not path.is_file():
        raise FileNotFoundError(path)
    df = pd.read_csv(path, parse_dates=["timestamp"])
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)


def _to_utc_ns(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        ts = pd.to_datetime(series, utc=True)
    else:
        ts = pd.to_datetime(series, utc=True, format="mixed")
    return ts.astype("datetime64[ns, UTC]")


def merge_and_features(ohlcv: pd.DataFrame, funding: pd.DataFrame) -> pd.DataFrame:
    ohlcv = ohlcv.copy()
    funding = funding.copy()
    ohlcv["timestamp"] = _to_utc_ns(ohlcv["timestamp"])
    funding["timestamp"] = _to_utc_ns(funding["timestamp"])
    ohlcv = ohlcv.sort_values("timestamp").reset_index(drop=True)
    funding = funding.sort_values("timestamp").reset_index(drop=True)

    df = pd.merge_asof(ohlcv, funding, on="timestamp", direction="backward")
    df["funding_rate"] = df["funding_rate"].shift(1)
    df["return_15m"] = df["close"].pct_change()
    df["sigma_15m"] = df["return_15m"].shift(1).rolling(LOOKBACK_PERIOD).std()
    return df.dropna(subset=["funding_rate", "sigma_15m"]).reset_index(drop=True)


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
            return sl_price, "SL_Pessimistic", future_idx
        if hit_sl:
            return sl_price, "SL", future_idx
        if hit_tp:
            return tp_price, "TP", future_idx

    exit_idx = idx + TIME_EXIT_BARS
    return df.at[exit_idx, "close"], "Time_Exit", exit_idx


def simulate_funding_squeeze(
    df: pd.DataFrame,
    threshold: float,
    k_tp: float,
    k_sl: float,
    *,
    friction_mode: str = "period",
    uniform_friction: float | None = None,
) -> list[dict[str, Any]]:
    """
    One trade per funding episode (MAX_TRADES_PER_EPISODE=1).
    friction_mode: 'period' | 'uniform' (uses uniform_friction).
    """
    episode_ids = assign_funding_episode_ids(df["funding_rate"].to_numpy(), threshold)
    traded_episodes: set[int] = set()
    trades: list[dict[str, Any]] = []
    n = len(df)
    idx = MIN_IDX

    while idx < n - TIME_EXIT_BARS:
        fr = df.at[idx, "funding_rate"]
        sigma = df.at[idx, "sigma_15m"]
        ep_id = int(episode_ids[idx])
        if np.isnan(fr) or np.isnan(sigma) or sigma <= 0 or ep_id < 0:
            idx += 1
            continue
        if ep_id in traded_episodes:
            idx += 1
            continue

        if fr > threshold:
            direction = -1
            side = "SHORT"
        elif fr < -threshold:
            direction = 1
            side = "LONG"
        else:
            idx += 1
            continue

        entry_time = df.at[idx, "timestamp"]
        entry_price = df.at[idx, "close"]
        exit_price, exit_reason, exit_idx = _resolve_exit(
            df, idx, entry_price, sigma, k_tp, k_sl, direction
        )
        gross = direction * (exit_price - entry_price) / entry_price
        if friction_mode == "uniform" and uniform_friction is not None:
            friction = uniform_friction
        else:
            friction = friction_for_timestamp(entry_time)
        net = gross - friction
        traded_episodes.add(ep_id)
        trades.append(
            {
                "entry_time": entry_time,
                "exit_time": df.at[exit_idx, "timestamp"],
                "direction": side,
                "funding_rate": fr,
                "funding_threshold": threshold,
                "k_tp": k_tp,
                "k_sl": k_sl,
                "episode_id": ep_id,
                "split": split_label(entry_time),
                "friction_bps": friction * 10000,
                "gross_pnl": gross,
                "net_pnl": net,
                "exit_reason": exit_reason,
            }
        )
        idx = exit_idx + 1

    return trades


def evaluate_grid(
    df: pd.DataFrame,
    symbol: str,
    thresholds: list[float],
    grid_label: str,
    *,
    friction_mode: str = "period",
    uniform_friction: float | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    years = years_from_timestamps(df["timestamp"])
    rows = []
    trade_frames: list[pd.DataFrame] = []
    for thr, k_tp, k_sl in product(thresholds, K_TP_GRID, K_SL_GRID):
        trades = simulate_funding_squeeze(
            df, thr, k_tp, k_sl, friction_mode=friction_mode, uniform_friction=uniform_friction
        )
        trade_metrics = metrics_from_trades(trades, years=years)
        ep_metrics = metrics_from_episodes(trades, years=years)
        oos_trades = [t for t in trades if t["split"] == "oos"]
        oos_ep = metrics_from_episodes(oos_trades, years=years)
        rows.append(
            {
                "symbol": symbol,
                "grid": grid_label,
                "friction_mode": friction_mode,
                "funding_threshold": thr,
                "k_tp": k_tp,
                "k_sl": k_sl,
                **trade_metrics,
                **{f"oos_{k}": v for k, v in oos_ep.items()},
                **{f"ep_{k}": v for k, v in ep_metrics.items()},
            }
        )
        if trades:
            tdf = pd.DataFrame(trades)
            tdf["symbol"] = symbol
            tdf["grid"] = grid_label
            tdf["friction_mode"] = friction_mode
            trade_frames.append(tdf)
    res = pd.DataFrame(rows)
    trades_out = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    return res, trades_out


def classify_m2a_oos(res: pd.DataFrame, prereg_testable: bool, grid_label: str) -> str:
    """Primary verdict on OOS episode metrics (M2A prereg §5)."""
    if grid_label == "prereg" and not prereg_testable:
        return "NOT TESTABLE: Prereg-Schwellen im OHLCV-Fenster ohne Ereignisse (Messung, kein Negativbefund)"

    scope = res[res["funding_threshold"] == PREREG_PRIMARY_THRESHOLD] if grid_label == "prereg" else res
    if scope.empty:
        scope = res

    elig = scope[scope["oos_episodes"] >= MIN_EPISODES_OOS]
    if elig.empty:
        low = scope[scope["oos_episodes"] > 0]
        if low.empty and grid_label == "prereg":
            return "NOT TESTABLE: keine OOS-Episoden bei Prereg-Schwellen"
        return f"NOT TESTABLE: OOS episodes < {MIN_EPISODES_OOS} (n={int(scope['oos_episodes'].max())})"

    best = elig["oos_e_pnl_net_episode"].max()
    pass_cells = elig[
        (elig["oos_e_pnl_net_episode"] >= 0.0010)
        & (elig["oos_sharpe_episode"] >= 0.5)
        & (elig["oos_episodes"] >= MIN_EPISODES_OOS)
    ]
    prefix = "EXPLORATORY — " if grid_label == "exploratory" else ""
    thr_note = f" @ θ={PREREG_PRIMARY_THRESHOLD*100:.2f}%"
    if len(pass_cells) > 0:
        return f"{prefix}SCENARIO 1: PASS{thr_note} — {len(pass_cells)} cells (best OOS E[PnL_ep]={best*100:.3f}%)"
    if best >= -0.0005:
        return f"{prefix}SCENARIO 2: Neutral{thr_note} — best OOS E[PnL_ep]={best*100:.3f}%"
    return f"{prefix}SCENARIO 3: Falsified{thr_note} — best OOS E[PnL_ep]={best*100:.3f}%"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stage M2a funding squeeze backtest")
    p.add_argument("--full-history", action="store_true", help="Perp full OHLCV + funding ab 2019-09")
    p.add_argument("--exploratory", action="store_true", help="zusätzlich niedrige Schwellen (andere Hypothese)")
    p.add_argument("--validate-only", action="store_true", help="nur Datenvalidierung, kein Backtest")
    p.add_argument("--refresh-cache", action="store_true", help="Funding-Cache neu laden")
    p.add_argument("--days", type=int, default=365, help="Funding-Historie in Tagen (default 365)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    print("=" * 72)
    print("STAGE M2a — Funding Rate Squeeze (BTC/ETH)")
    print("=" * 72)
    print(f"OOS split (frozen): {OOS_SPLIT_TS.isoformat()}")
    print(f"Friction: period ({FRICTION_EARLY*10000:.0f}bps early / {FRICTION_MODERN*10000:.0f}bps modern)")
    print(f"Inference: 1 trade/episode · verdict OOS @ θ_primary={PREREG_PRIMARY_THRESHOLD*100:.2f}%")

    grids: list[tuple[str, list[float]]] = [("prereg", FUNDING_THRESHOLDS_PREREG)]
    if args.exploratory:
        grids.append(("exploratory", FUNDING_THRESHOLDS_EXPLORATORY))

    all_results: list[pd.DataFrame] = []
    all_trades: list[pd.DataFrame] = []
    validations: list[dict[str, Any]] = []
    prereg_testable_any = False

    for symbol in SYMBOLS:
        print(f"\n--- {symbol} ---")
        ohlcv = load_ohlcv(symbol, full_history=args.full_history)
        funding = download_funding_rates(
            symbol, days=args.days, refresh=args.refresh_cache, full_history=args.full_history
        )

        report = validate_funding_data(symbol, funding, ohlcv)
        validations.append(report)
        print_validation(report)
        prereg_testable_any = prereg_testable_any or report["prereg_testable"]

        if args.validate_only:
            continue

        df = merge_and_features(ohlcv, funding)
        print(f"  ohlcv={len(ohlcv)} funding={len(funding)} merged={len(df)}")

        for grid_label, thresholds in grids:
            n_params = len(thresholds) * len(K_TP_GRID) * len(K_SL_GRID)
            print(f"\n  Grid [{grid_label}]: {n_params} combos, thresholds={[round(t*10000,1) for t in thresholds]} bps/8h")
            res, trades_part = evaluate_grid(df, symbol, thresholds, grid_label)
            all_results.append(res)
            if not trades_part.empty:
                all_trades.append(trades_part)

            verdict = classify_m2a_oos(res, report["prereg_testable"], grid_label)
            print(f"  {verdict}")
            if not res.empty and res["ep_episodes"].max() > 0:
                primary_res = res[res["funding_threshold"] == PREREG_PRIMARY_THRESHOLD]
                top_src = primary_res if not primary_res.empty else res
                top = top_src.sort_values("oos_e_pnl_net_episode", ascending=False).head(3)
                print(
                    top[
                        [
                            "funding_threshold",
                            "k_tp",
                            "k_sl",
                            "ep_episodes",
                            "oos_episodes",
                            "oos_e_pnl_net_episode",
                            "oos_sharpe_episode",
                        ]
                    ].to_string(index=False)
                )

    val_path = Path(RESULTS_DIR) / "m2a_data_validation.json"
    val_path.write_text(json.dumps(validations, indent=2), encoding="utf-8")
    print(f"\n[OUTPUT] {val_path}")

    if args.validate_only:
        return 0

    if not all_results:
        return 0

    final = pd.concat(all_results, ignore_index=True)
    out_grid = Path(RESULTS_DIR) / "stage_m2a_results.csv"
    final.to_csv(out_grid, index=False)

    prereg_final = final[final["grid"] == "prereg"]
    print(f"\n[OUTPUT] {out_grid}")
    if not prereg_final.empty:
        print(f"[PREREG OOS] {classify_m2a_oos(prereg_final, prereg_testable_any, 'prereg')}")
    if args.exploratory:
        expl = final[final["grid"] == "exploratory"]
        if not expl.empty:
            print(f"[EXPLORATORY] {classify_m2a_oos(expl, True, 'exploratory')} (andere Hypothese)")

    if all_trades:
        trades_df = pd.concat(all_trades, ignore_index=True)
        trades_path = Path(RESULTS_DIR) / "m2a_trades.csv"
        trades_df.to_csv(trades_path, index=False)
        print(f"[TRADES] {trades_path} ({len(trades_df)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
