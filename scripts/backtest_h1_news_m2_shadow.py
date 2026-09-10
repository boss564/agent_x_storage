#!/usr/bin/env python3
"""
M2 Shadow Backtest — detection-lag stratification + slippage-aware PnL.

Uses spec lag buckets (§2.2.1): <15 min | 15–60 min | >60 min.
OHLCV-aligned PnL via backtest_h1_news_m2_skeleton (no sentiment proxy).

Blocked until ≥90d JSONL + ≥200 gated events (spec §4.2) — still runs
diagnostically but decision_engine returns BLOCKED.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.backtest_h1_news_m2_shadow_lag import (  # noqa: E402
    ALPHA_EFF,
    LAG_BUCKETS_SEC,
    MDE_REFERENCE_STD_BPS,
    MIN_TRADES_PER_BUCKET,
    N_BUCKET_HYPOTHESES,
    BucketResult,
    assign_lag_bucket,
    bucket_statistics,
    data_threshold_status,
    decision_engine,
    estimate_slippage_bps,
)
from services.m2_shadow.risk_alpha import AlphaDecayDiagnostic, LagTradeObservation  # noqa: E402
from scripts.backtest_h1_news_m2_skeleton import (  # noqa: E402
    AlignedEntry,
    TIME_EXIT_CANDLES,
    align_event_to_ohlcv,
    build_execution_window,
    load_news_events,
)
from scripts.backtest_h1_price import (  # noqa: E402
    DATA_DIR,
    FRICTION_BPS,
    RESULTS_DIR,
    SYMBOLS,
    fetch_and_cache_ohlcv,
)

os.makedirs(RESULTS_DIR, exist_ok=True)
logger = logging.getLogger(__name__)

__all__ = [
    "LAG_BUCKETS_SEC",
    "BucketResult",
    "assign_lag_bucket",
    "bucket_statistics",
    "data_threshold_status",
    "decision_engine",
    "estimate_slippage_bps",
    "run_shadow_backtest",
    "print_shadow_report",
]


def gross_pnl_frac(aligned: AlignedEntry, ohlcv: pd.DataFrame) -> Optional[float]:
    exit_idx = aligned.entry_idx + TIME_EXIT_CANDLES
    if exit_idx >= len(ohlcv):
        return None
    entry = aligned.entry_price
    exit_price = float(ohlcv.iloc[exit_idx]["close"])
    if aligned.direction == "long":
        return (exit_price - entry) / entry
    return (entry - exit_price) / entry


def gross_pnl_bps(aligned: AlignedEntry, ohlcv: pd.DataFrame) -> Optional[float]:
    gross = gross_pnl_frac(aligned, ohlcv)
    if gross is None:
        return None
    return gross * 10_000.0


def net_pnl_bps(aligned: AlignedEntry, ohlcv: pd.DataFrame) -> Optional[float]:
    gross = gross_pnl_frac(aligned, ohlcv)
    if gross is None:
        return None
    slippage_bps = estimate_slippage_bps(sigma_15m=aligned.sigma_15m)
    net_frac = gross - FRICTION_BPS - (slippage_bps / 10_000.0)
    return net_frac * 10_000.0


def run_shadow_backtest(
    jsonl_path: Path | str,
    *,
    anchor: str = "ingest",
    max_files: Optional[int] = None,
) -> Dict[str, object]:
    path = Path(jsonl_path)
    events = load_news_events(path, max_files=max_files)
    threshold_status, threshold_reason = data_threshold_status(events)

    bucket_pnls: Dict[str, List[float]] = {name: [] for name in LAG_BUCKETS_SEC}
    alpha_diag = AlphaDecayDiagnostic()
    aligned_count = 0
    skipped_no_lag = 0

    ohlcv_cache = {sym: fetch_and_cache_ohlcv(sym) for sym in SYMBOLS}

    for event in events:
        lag = event.detection_lag_seconds
        if lag is None:
            skipped_no_lag += 1
            continue

        bucket = assign_lag_bucket(lag)
        if bucket is None:
            continue

        window = build_execution_window(event, anchor=anchor)  # type: ignore[arg-type]
        if window is None:
            continue
        ohlcv = ohlcv_cache.get(window.symbol)
        if ohlcv is None:
            continue

        aligned = align_event_to_ohlcv(window, ohlcv)
        if aligned is None:
            continue

        pnl = net_pnl_bps(aligned, ohlcv)
        if pnl is None:
            continue

        gross_bps = gross_pnl_bps(aligned, ohlcv)
        if gross_bps is not None:
            asset = window.symbol.split("/")[0]
            alpha_diag.add(
                LagTradeObservation(
                    asset=asset,
                    lag_sec=lag,
                    gross_pnl_bps=gross_bps,
                    net_pnl_bps=pnl,
                    lag_bucket=bucket,
                )
            )

        aligned_count += 1
        bucket_pnls[bucket].append(pnl)

    alpha_diag.fit()

    results = {name: bucket_statistics(name, bucket_pnls[name]) for name in LAG_BUCKETS_SEC}
    decision, reason = decision_engine(results, threshold_status, threshold_reason)

    span_days = 0.0
    if len(events) >= 2:
        span_days = (events[-1].t_ingest - events[0].t_ingest).total_seconds() / 86_400.0

    return {
        "jsonl": str(path),
        "anchor": anchor,
        "n_gated_events": len(events),
        "span_days": round(span_days, 2),
        "aligned_trades": aligned_count,
        "skipped_no_lag": skipped_no_lag,
        "threshold_status": threshold_status,
        "threshold_reason": threshold_reason,
        "bonferroni_alpha": ALPHA_EFF,
        "bonferroni_n_hypotheses": N_BUCKET_HYPOTHESES,
        "min_trades_per_bucket": MIN_TRADES_PER_BUCKET,
        "mde_reference_std_bps": MDE_REFERENCE_STD_BPS,
        "buckets": {
            name: {
                "lag_range_sec": list(res.lag_range_sec),
                "n_trades": res.n_trades,
                "adjudication": res.adjudication,
                "mean_pnl_bps": round(res.mean_pnl_bps, 1),
                "std_pnl_bps": round(res.std_pnl_bps, 1),
                "sigma_bps_realized": (
                    round(res.sigma_bps_realized, 1)
                    if res.sigma_bps_realized is not None
                    else None
                ),
                "t_stat": round(res.t_stat, 4),
                "p_value": round(res.p_value, 6),
                "bonferroni_significant": res.bonferroni_significant,
                "mde_bps_prereg": (
                    round(res.mde_bps_prereg, 1) if res.mde_bps_prereg is not None else None
                ),
                "mde_bps_realized": (
                    round(res.mde_bps_realized, 1)
                    if res.mde_bps_realized is not None
                    else None
                ),
                "effective_alpha": res.effective_alpha,
            }
            for name, res in results.items()
        },
        "decision": decision,
        "decision_reason": reason,
        "alpha_decay_diagnostic": alpha_diag.to_dict(),
    }


def print_shadow_report(report: Dict[str, object]) -> None:
    print("\n" + "=" * 60)
    print("M2 SHADOW BACKTEST — DETECTION-LAG STRATIFIZIERUNG")
    print("Spec: docs/H1_M2_EVENT_DRIVEN_SPEC.md §2.2.1")
    print("=" * 60)
    print(f"  JSONL:           {report.get('jsonl')}")
    print(f"  Gated events:    {report.get('n_gated_events')}")
    print(f"  Span (days):     {report.get('span_days')}")
    print(f"  Aligned trades:  {report.get('aligned_trades')}")
    print(f"  Skipped no lag:  {report.get('skipped_no_lag')}")
    print(f"  Threshold:       {report.get('threshold_status')}")
    print(
        f"  Bonferroni:      α_eff={report.get('bonferroni_alpha'):.4f} "
        f"({report.get('bonferroni_n_hypotheses')} Hypothesen), "
        f"min n/bucket={report.get('min_trades_per_bucket')}"
    )

    buckets = report.get("buckets") or {}
    for name, res in buckets.items():
        lo, hi = res["lag_range_sec"]
        hi_s = "inf" if hi == float("inf") else f"{int(hi)}"
        adj = res.get("adjudication", "adjudicated")
        print(f"\nBucket {name} ({int(lo)} - {hi_s}s) [{adj}]:")
        print(f"  Trades:          {res['n_trades']}")
        print(f"  Mean PnL (bps):  {res['mean_pnl_bps']:.2f}")
        print(f"  StdDev (bps):    {res['std_pnl_bps']:.2f}")
        print(f"  t-Statistik:     {res['t_stat']:.3f}")
        print(f"  p-Wert:          {res['p_value']:.4f}")
        if adj == "insufficient":
            mde_p = res.get("mde_bps_prereg")
            mde_r = res.get("mde_bps_realized")
            if mde_p is not None or mde_r is not None:
                mde_p_s = f"{mde_p:.1f}" if mde_p is not None else "—"
                mde_r_s = f"{mde_r:.1f}" if mde_r is not None else "—"
                print(
                    f"  MDE prereg/real: {mde_p_s} / {mde_r_s} bps "
                    f"(diagnostisch, n < {MIN_TRADES_PER_BUCKET})"
                )
            print(f"  Urteil:          — (n < {MIN_TRADES_PER_BUCKET})")
        else:
            sig = res.get("bonferroni_significant", False)
            mde_p = res.get("mde_bps_prereg")
            mde_r = res.get("mde_bps_realized")
            sigma = res.get("sigma_bps_realized")
            print(
                f"  Bonferroni:      {'JA' if sig else 'NEIN'} "
                f"(α_eff={ALPHA_EFF:.4f})"
            )
            if mde_p is not None:
                print(f"  MDE prereg:      {mde_p:.1f} bps (σ={MDE_REFERENCE_STD_BPS:.0f})")
            if mde_r is not None:
                sig_s = f"{sigma:.1f}" if sigma is not None else "—"
                print(f"  MDE realized:    {mde_r:.1f} bps (σ={sig_s})")

    print("\n" + "=" * 60)
    print(f"ENTSCHEIDUNG: {report.get('decision')}")
    print(f"Begründung:   {report.get('decision_reason')}")
    print("=" * 60 + "\n")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="M2 Shadow Backtest (lag stratification)")
    parser.add_argument(
        "--jsonl",
        default=os.path.join(DATA_DIR, "news_scores.jsonl"),
        help="news_scores.jsonl path (active + rotated archives)",
    )
    parser.add_argument("--max-files", type=int, default=None, help="Max archive files to read")
    parser.add_argument("--anchor", choices=("ingest", "published"), default="ingest")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--output",
        default=os.path.join(RESULTS_DIR, "h1_m2_shadow_backtest.json"),
        help="JSON report path",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)

    report = run_shadow_backtest(
        args.jsonl,
        anchor=args.anchor,
        max_files=args.max_files,
    )
    print_shadow_report(report)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"[OUTPUT] {out}")


if __name__ == "__main__":
    main()
