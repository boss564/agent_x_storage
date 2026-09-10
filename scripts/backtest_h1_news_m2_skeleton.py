#!/usr/bin/env python3
"""
H1 M2 Skeleton — Event-Driven Exogenous Engine (types + alignment only).

NO live M2 backtest. NO performance claims.
Implements data contract from docs/H1_M2_EVENT_DRIVEN_SPEC.md.

Allowed now:
  - Load/filter news_scores.jsonl
  - Align events to 15m OHLCV with look-ahead guards
  - Synthetic random-t0 injection dry run (bias audit)

Blocked until gate-close + data threshold:
  - Live replay evaluation / OOS report
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Literal, Optional

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.backtest_h1_price import (  # noqa: E402
    DATA_DIR,
    FRICTION_BPS,
    RESULTS_DIR,
    SYMBOLS,
    fetch_and_cache_ohlcv,
    prepare_features,
)

# --- Frozen v1 constants (docs/H1_M2_EVENT_DRIVEN_SPEC.md) ---
THETA_ABS = 0.30
T_MAX_MINUTES = 15
DELTA_PROCESSING_MINUTES = 1
K_TP = 1.5
K_SL = 1.0
TIME_EXIT_CANDLES = 4
GROSS_TAIL_THRESH = 0.003  # +30 bps — M1 oracle alignment
REQUIRED_SCHEMA = "news_agent_multi/v1.3"  # spec §2.1.3 — no v1.2 fallback
LAG_GO_THRESHOLD_MINUTES = T_MAX_MINUTES  # spec §5.1.1 — derived from entry window, not fitted
LAG_MIN_OBSERVATIONS = 100  # spec §5.1.1 — minimum n for GO/NO-GO verdict
PRIOR_EXPECTED_MEDIAN_LAG_MIN = 30.0  # hourly cron, uniform pub — prediction to confirm/refute
ALLOWED_SOURCE_TYPES = frozenset({"rss", "announcement", "regulatory"})

ASSET_TO_SYMBOL = {
    "BTC": "BTC/USDT",
    "ETH": "ETH/USDT",
}

os.makedirs(RESULTS_DIR, exist_ok=True)


@dataclass(frozen=True)
class NewsEvent:
    """Single exogenous trigger candidate (one JSONL row)."""

    event_id: str
    t_ingest: datetime  # server ingest anchor (JSONL timestamp)
    sentiment_score: float
    target_assets: tuple[str, ...]
    source_type: str
    source_name: str
    impact_level: str
    title: str
    t_published: Optional[datetime] = None  # feed published_at when present (v1.3)

    @property
    def detection_lag_seconds(self) -> Optional[float]:
        if self.t_published is None:
            return None
        return (self.t_ingest - self.t_published).total_seconds()


@dataclass
class ExecutionWindow:
    """Valid entry interval for one event."""

    event: NewsEvent
    symbol: str
    t_earliest: datetime
    t_expires: datetime
    direction: Literal["long", "short"]
    anchor: Literal["ingest", "published"]  # Arm A vs Arm B (spec §2.2.1)


@dataclass
class AlignedEntry:
    """Event aligned to OHLCV — ready for simulation (not executed here)."""

    event_id: str
    symbol: str
    direction: str
    entry_idx: int
    entry_time: pd.Timestamp
    entry_price: float
    sigma_15m: float
    t0: datetime
    anchor: str
    detection_lag_seconds: Optional[float] = None


def _parse_ts(value: str) -> datetime:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize(timezone.utc)
    return ts.to_pydatetime()


def _iter_gated_jsonl_rows(
    jsonl_path: Path | str,
    *,
    max_files: Optional[int] = None,
) -> Iterator[dict]:
    """Stream JSONL rows from active file + logrotate archives (read-only)."""
    from src.ingestion.news_jsonl_loader import iter_jsonl_store, iter_news_records

    path = Path(jsonl_path)
    if path.is_file():
        yield from iter_jsonl_store(path, max_files=max_files)
    elif path.is_dir():
        yield from iter_news_records(path, max_files=max_files)
    else:
        return


def load_news_events(
    jsonl_path: Path | str,
    *,
    theta_abs: float = THETA_ABS,
    max_files: Optional[int] = None,
) -> list[NewsEvent]:
    """Load and gate JSONL rows per M2 spec §2.1."""
    path = Path(jsonl_path)
    if not path.is_file() and not path.is_dir():
        return []

    events: list[NewsEvent] = []
    seen_ids: set[str] = set()

    for row in _iter_gated_jsonl_rows(path, max_files=max_files):
        if row.get("source_type") == "run_marker":
            continue
        if row.get("schema") != REQUIRED_SCHEMA:
            continue
        if row.get("source_type") not in ALLOWED_SOURCE_TYPES:
            continue

        assets = [a for a in (row.get("target_assets") or []) if a in ASSET_TO_SYMBOL]
        if not assets:
            continue

        score = float(row.get("sentiment_score") or 0.0)
        if abs(score) < theta_abs:
            continue

        event_id = str(row.get("item_id") or row.get("url") or "")
        if not event_id or event_id in seen_ids:
            continue
        seen_ids.add(event_id)

        pub_raw = row.get("published_at") or row.get("published")
        t_published = _parse_ts(str(pub_raw)) if pub_raw else None

        events.append(
            NewsEvent(
                event_id=event_id,
                t_ingest=_parse_ts(str(row["timestamp"])),
                sentiment_score=score,
                target_assets=tuple(assets),
                source_type=str(row.get("source_type") or ""),
                source_name=str(row.get("source_name") or ""),
                impact_level=str(row.get("impact_level") or "LOW"),
                title=str(row.get("title") or "")[:120],
                t_published=t_published,
            )
        )

    events.sort(key=lambda e: e.t_ingest)
    return events


def _pick_symbol(event: NewsEvent) -> Optional[str]:
    for asset in event.target_assets:
        if asset in ASSET_TO_SYMBOL:
            return ASSET_TO_SYMBOL[asset]
    return None


def build_execution_window(
    event: NewsEvent,
    *,
    anchor: Literal["ingest", "published"] = "ingest",
    t_max_minutes: int = T_MAX_MINUTES,
    delta_processing_minutes: int = DELTA_PROCESSING_MINUTES,
) -> Optional[ExecutionWindow]:
    symbol = _pick_symbol(event)
    if symbol is None:
        return None

    if anchor == "published":
        if event.t_published is None:
            return None
        t0 = event.t_published
    else:
        t0 = event.t_ingest

    direction: Literal["long", "short"] = (
        "long" if event.sentiment_score >= THETA_ABS else "short"
    )
    t_earliest = t0 + timedelta(minutes=delta_processing_minutes)
    t_expires = t0 + timedelta(minutes=t_max_minutes)
    return ExecutionWindow(
        event=event,
        symbol=symbol,
        t_earliest=t_earliest,
        t_expires=t_expires,
        direction=direction,
        anchor=anchor,
    )


def align_event_to_ohlcv(window: ExecutionWindow, ohlcv: pd.DataFrame) -> Optional[AlignedEntry]:
    """
    Map event to first valid 15m candle at or after t_earliest, before t_expires.
    Look-ahead guard: entry candle open must be >= t_earliest.
    """
    if ohlcv.empty:
        return None

    df = ohlcv.copy()
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    t_lo = pd.Timestamp(window.t_earliest)
    if t_lo.tzinfo is None:
        t_lo = t_lo.tz_localize(timezone.utc)
    t_hi = pd.Timestamp(window.t_expires)
    if t_hi.tzinfo is None:
        t_hi = t_hi.tz_localize(timezone.utc)

    eligible = df[(df["timestamp"] >= t_lo) & (df["timestamp"] <= t_hi)]
    if eligible.empty:
        return None

    entry_row = eligible.iloc[0]
    entry_idx = int(entry_row.name)
    entry_time = entry_row["timestamp"]

    # Look-ahead guard (spec §2.4)
    assert pd.Timestamp(entry_time) >= t_lo, "look-ahead: entry before t_earliest"

    feat = prepare_features(df)
    sigma = float(feat.at[entry_idx, "sigma_15m"])
    if np.isnan(sigma) or sigma <= 0:
        return None

    return AlignedEntry(
        event_id=window.event.event_id,
        symbol=window.symbol,
        direction=window.direction,
        entry_idx=entry_idx,
        entry_time=entry_time,
        entry_price=float(entry_row["close"]),
        sigma_15m=sigma,
        t0=window.t_earliest - timedelta(minutes=DELTA_PROCESSING_MINUTES),
        anchor=window.anchor,
        detection_lag_seconds=window.event.detection_lag_seconds,
    )


def _indices_matching_time(
    ohlcv: pd.DataFrame, hour: int, weekday: int, *, top_of_hour_only: bool = False
) -> np.ndarray:
    ts = pd.to_datetime(ohlcv["timestamp"], utc=True)
    mask = (ts.dt.hour == hour) & (ts.dt.weekday == weekday)
    if top_of_hour_only:
        mask &= ts.dt.minute == 0
    return np.flatnonzero(mask.to_numpy())


def _time_distribution(events: list[NewsEvent]) -> tuple[np.ndarray, np.ndarray, bool]:
    """Empirical (hour, weekday) from t_ingest; cron-proxy if sparse."""
    if len(events) >= 30:
        hours = np.array([e.t_ingest.hour for e in events], dtype=int)
        dows = np.array([e.t_ingest.weekday() for e in events], dtype=int)
        return hours, dows, False
  # Cron :00 proxy — all hours/dows, match top-of-hour candles only
    return np.arange(24, dtype=int), np.arange(7, dtype=int), True


def synthetic_structured_t0_injection(
    ohlcv: pd.DataFrame,
    events: list[NewsEvent],
    *,
    n_events: int = 1000,
    seed: int = 42,
) -> pd.DataFrame:
    """
    §6.2.2: sample entry times from empirical news (hour, weekday) distribution.
    IAAFT principle — null model shares temporal structure of treatment.
    """
    rng = np.random.default_rng(seed)
    feat = prepare_features(ohlcv)
    hours_pool, dows_pool, cron_proxy = _time_distribution(events)

    records = []
    attempts = 0
    while len(records) < n_events and attempts < n_events * 20:
        attempts += 1
        hour = int(rng.choice(hours_pool))
        dow = int(rng.choice(dows_pool))
        candidates = _indices_matching_time(
            feat, hour, dow, top_of_hour_only=cron_proxy
        )
        if len(candidates) == 0:
            continue
        idx = int(rng.choice(candidates))
        if idx < 110 or idx >= len(feat) - TIME_EXIT_CANDLES - 1:
            continue

        entry_price = float(feat.at[idx, "close"])
        sigma = float(feat.at[idx, "sigma_15m"])
        if np.isnan(sigma) or sigma <= 0:
            continue

        exit_idx = idx + TIME_EXIT_CANDLES
        exit_price = float(feat.at[exit_idx, "close"])
        direction = "long" if rng.random() < 0.5 else "short"
        gross = (
            (exit_price - entry_price) / entry_price
            if direction == "long"
            else (entry_price - exit_price) / entry_price
        )
        records.append(
            {
                "direction": direction,
                "gross_pnl": gross,
                "net_pnl": gross - FRICTION_BPS,
                "null_type": "structured",
                "hour": hour,
                "weekday": dow,
            }
        )

    return pd.DataFrame(records)


def synthetic_random_t0_injection(
    ohlcv: pd.DataFrame,
    *,
    n_events: int = 1000,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Dry run §6.2: random t0 on historical prices → expect E[net] ≈ -19 bps.
    Uses same TP/SL/time-exit as spec §3 (simplified close-to-close proxy).
    """
    rng = np.random.default_rng(seed)
    feat = prepare_features(ohlcv)
    min_idx = 110
    max_idx = len(feat) - TIME_EXIT_CANDLES - 1
    if max_idx <= min_idx:
        return pd.DataFrame()

    records = []
    for _ in range(n_events):
        idx = int(rng.integers(min_idx, max_idx))
        direction = "long" if rng.random() < 0.5 else "short"
        entry_price = float(feat.at[idx, "close"])
        sigma = float(feat.at[idx, "sigma_15m"])
        if np.isnan(sigma) or sigma <= 0:
            continue

        exit_idx = idx + TIME_EXIT_CANDLES
        exit_price = float(feat.at[exit_idx, "close"])

        if direction == "long":
            gross = (exit_price - entry_price) / entry_price
        else:
            gross = (entry_price - exit_price) / entry_price

        records.append(
            {
                "direction": direction,
                "gross_pnl": gross,
                "net_pnl": gross - FRICTION_BPS,
                "null_type": "uniform",
            }
        )

    return pd.DataFrame(records)


def _has_published_at(row: dict) -> bool:
    pub = row.get("published_at")
    return bool(pub and str(pub).strip())


def _lag_coverage_fields(
    n_items_total: int,
    n_with_published_at: int,
    n_with_lag: int,
    by_source: dict[str, dict[str, object]],
) -> dict:
    """Spec §5.1.3 — denominator visible before median; per-source median alongside coverage."""
    coverage_by_source: dict[str, float] = {}
    median_lag_by_source: dict[str, float | None] = {}
    for src in sorted(by_source):
        total = int(by_source[src]["total"])
        with_pub = int(by_source[src]["with_published_at"])
        coverage_by_source[src] = round(with_pub / total, 4) if total else 0.0
        src_lags = by_source[src].get("lags") or []
        if src_lags:
            median_lag_by_source[src] = round(float(np.median(np.array(src_lags, dtype=float))) / 60.0, 2)
        else:
            median_lag_by_source[src] = None

    lag_coverage = round(n_with_published_at / n_items_total, 4) if n_items_total else 0.0
    fields: dict = {
        "n_items_total": n_items_total,
        "n_with_published_at": n_with_published_at,
        "n_with_lag": n_with_lag,
        "lag_coverage": lag_coverage,
        "coverage_by_source": coverage_by_source,
        "median_lag_by_source": median_lag_by_source,
    }
    parse_gap = n_with_published_at - n_with_lag
    if parse_gap > 0:
        fields["published_at_parse_gap"] = parse_gap
    return fields


def report_detection_lag(jsonl_path: Path | str) -> dict:
    """
    Spec §5.1 — Tag-7 measurability check (lag distribution only, no price).
    Reads schema v1.3 rows; median only over non-null detection_lag (§5.1.3 coverage).
    """
    path = Path(jsonl_path)
    lags: list[int] = []
    n_items_total = 0
    n_with_published_at = 0
    n_with_lag = 0
    by_source: dict[str, dict[str, int]] = {}

    base_meta = {
        "verdict": None,
        "lag_go_threshold_min": LAG_GO_THRESHOLD_MINUTES,
        "lag_min_observations": LAG_MIN_OBSERVATIONS,
        "prior_expected_median_min": PRIOR_EXPECTED_MEDIAN_LAG_MIN,
        "prior_prediction": "NO_GO",
        "spec": "H1_M2_EVENT_DRIVEN_SPEC.md §5.1.1",
    }

    if not path.is_file() and not path.is_dir():
        return {
            **base_meta,
            "error": "file_not_found",
            **_lag_coverage_fields(0, 0, 0, {}),
            "measurability": "INSUFFICIENT_DATA",
        }

    for row in _iter_gated_jsonl_rows(path):
        if row.get("source_type") == "run_marker":
            continue
        if row.get("schema") != REQUIRED_SCHEMA:
            continue

        n_items_total += 1
        src = str(row.get("source_name") or "unknown")
        bucket = by_source.setdefault(src, {"total": 0, "with_published_at": 0, "lags": []})
        bucket["total"] = int(bucket["total"]) + 1

        has_pub = _has_published_at(row)
        if has_pub:
            n_with_published_at += 1
            bucket["with_published_at"] = int(bucket["with_published_at"]) + 1

        lag = row.get("detection_lag")
        if lag is not None:
            lag_s = int(lag)
            lags.append(lag_s)
            n_with_lag += 1
            bucket["lags"].append(lag_s)  # type: ignore[union-attr]

    coverage = _lag_coverage_fields(
        n_items_total, n_with_published_at, n_with_lag, by_source
    )

    if not lags:
        return {
            **base_meta,
            **coverage,
            "measurability": "INSUFFICIENT_DATA",
            "note": "no detection_lag observations — check published_at coverage_by_source",
        }

    arr = np.array(lags, dtype=float)
    median_min = float(np.median(arr)) / 60.0
    p90_min = float(np.percentile(arr, 90)) / 60.0
    report = {
        **base_meta,
        **coverage,
        "median_lag_min": median_min,
        "p25_lag_min": float(np.percentile(arr, 25)) / 60.0,
        "p75_lag_min": float(np.percentile(arr, 75)) / 60.0,
        "p90_lag_min": p90_min,
    }
    if n_with_lag < LAG_MIN_OBSERVATIONS:
        report["verdict"] = None
        report["measurability"] = "INSUFFICIENT_DATA"
        report["note"] = (
            f"n_with_lag={n_with_lag} < {LAG_MIN_OBSERVATIONS} — "
            "repeat report when threshold met"
        )
    elif median_min <= LAG_GO_THRESHOLD_MINUTES:
        report["verdict"] = "GO"
        report["measurability"] = "GO_90D_PATH"
        report["note"] = (
            f"Median lag {median_min:.1f}min ≤ {LAG_GO_THRESHOLD_MINUTES}min — "
            "90d M2 path may answer causal question"
        )
    else:
        report["verdict"] = "NO_GO"
        report["measurability"] = "NO_GO_POLLING_EPOCH_FIRST"
        report["note"] = (
            f"Median lag {median_min:.1f}min > {LAG_GO_THRESHOLD_MINUTES}min — "
            "polling epoch (§11) before 90d backtest; not news falsification"
        )
    report["p90_diagnostic"] = (
        "wide_tail" if p90_min > 3 * median_min else "tight_or_moderate"
    )
    return report


def run_synthetic_audit(
    symbol: str = "BTC/USDT",
    events: Optional[list[NewsEvent]] = None,
) -> list[dict]:
    """Bias audit — uniform + structured null (spec §6.2)."""
    ohlcv = fetch_and_cache_ohlcv(symbol, days=365)
    events = events or []
    rows = []

    for null_type, builder in (
        ("uniform", lambda: synthetic_random_t0_injection(ohlcv)),
        ("structured", lambda: synthetic_structured_t0_injection(ohlcv, events)),
    ):
        df = builder()
        if df.empty:
            rows.append({"symbol": symbol, "null_type": null_type, "n": 0, "e_net": 0.0, "pass": False})
            continue
        e_gross = float(df["gross_pnl"].mean())
        e_net = float(df["net_pnl"].mean())
        rows.append(
            {
                "symbol": symbol,
                "null_type": null_type,
                "n": len(df),
                "e_gross": e_gross,
                "e_net": e_net,
                "pass": abs(e_gross) < 0.0005 if null_type == "uniform" else True,
            }
        )
    return rows


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="H1 M2 skeleton — spec contract only")
    parser.add_argument(
        "--jsonl",
        default=os.path.join(DATA_DIR, "news_scores.jsonl"),
        help="news_scores.jsonl path (optional)",
    )
    parser.add_argument("--synthetic-audit", action="store_true", help="run §6.2 bias audit")
    parser.add_argument(
        "--lag-report",
        action="store_true",
        help="spec §5.1: detection_lag distribution only (no backtest)",
    )
    parser.add_argument(
        "--shadow-backtest",
        action="store_true",
        help="lag-stratified shadow PnL (§2.2.1; blocked until ≥90d + ≥200 events)",
    )
    parser.add_argument("--max-files", type=int, default=None, help="max JSONL archives to read")
    args = parser.parse_args()

    if args.shadow_backtest:
        from scripts.backtest_h1_news_m2_shadow import print_shadow_report, run_shadow_backtest

        report = run_shadow_backtest(args.jsonl, max_files=args.max_files)
        print_shadow_report(report)
        out = os.path.join(RESULTS_DIR, "h1_m2_shadow_backtest.json")
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        print(f"\n[OUTPUT] {out}")
        return

    print("=" * 72)
    print("H1 M2 SKELETON — spec contract (no live M2 backtest)")
    print("Spec: docs/H1_M2_EVENT_DRIVEN_SPEC.md")
    print("=" * 72)

    events = load_news_events(args.jsonl, max_files=args.max_files)
    print(f"\n[JSONL] {args.jsonl}")
    print(f"        gated events: {len(events)}")
    if events:
        print(f"        first: {events[0].t_ingest.isoformat()}  last: {events[-1].t_ingest.isoformat()}")
        with_pub = [e for e in events if e.t_published is not None]
        print(f"        with published_at: {len(with_pub)}")
        if with_pub:
            lags = [e.detection_lag_seconds for e in with_pub if e.detection_lag_seconds is not None]
            if lags:
                print(f"        detection_lag median: {np.median(lags)/60:.1f} min")

    if events:
        ohlcv_cache = {sym: fetch_and_cache_ohlcv(sym) for sym in SYMBOLS}
        aligned = 0
        for ev in events[:20]:
            win = build_execution_window(ev, anchor="ingest")
            if win is None:
                continue
            ohlcv = ohlcv_cache.get(win.symbol)
            if ohlcv is None:
                continue
            if align_event_to_ohlcv(win, ohlcv) is not None:
                aligned += 1
        print(f"        alignable Arm-A (first 20): {aligned}")

    if args.lag_report:
        report = report_detection_lag(args.jsonl)
        out = os.path.join(RESULTS_DIR, "h1_m2_detection_lag_report.json")
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        print("\n--- Detection Lag Report (§5.1.1 / §5.1.3) ---")
        cov = report.get("lag_coverage")
        if cov is not None:
            print(
                f"  COVERAGE: {report.get('n_with_published_at')}/"
                f"{report.get('n_items_total')} ({cov:.0%} with published_at)"
            )
        coverage = report.get("coverage_by_source") or {}
        medians = report.get("median_lag_by_source") or {}
        if coverage:
            print("  by_source (coverage | median_lag_min):")
            for src in sorted(coverage):
                med = medians.get(src)
                med_s = f"{med:.1f} min" if med is not None else "—"
                print(f"    {src}: {coverage[src]:.0%} | {med_s}")
        skip = {"verdict", "coverage_by_source", "median_lag_by_source"}
        for k, v in report.items():
            if k in skip:
                continue
            print(f"  {k}: {v}")
        verdict = report.get("verdict")
        if verdict:
            print(f"  VERDICT: {verdict}")
        print(f"\n[OUTPUT] {out}")
    elif args.synthetic_audit:
        print("\n--- Synthetic Injection Audit (§6.2 uniform + structured) ---")
        rows = []
        for sym in SYMBOLS:
            for audit in run_synthetic_audit(sym, events):
                rows.append(audit)
                print(
                    f"  {sym} [{audit['null_type']}]: n={audit['n']} "
                    f"E[gross]={audit['e_gross']:.6f} E[net]={audit['e_net']:.6f} "
                    f"pass={audit['pass']}"
                )
        out = os.path.join(RESULTS_DIR, "h1_m2_synthetic_injection.csv")
        pd.DataFrame(rows).to_csv(out, index=False)
        print(f"\n[OUTPUT] {out}")
        uniform = [r for r in rows if r["null_type"] == "uniform"]
        structured = [r for r in rows if r["null_type"] == "structured"]
        if uniform and structured:
            u_mean = np.mean([r["e_net"] for r in uniform])
            s_mean = np.mean([r["e_net"] for r in structured])
            print(
                f"\n[NOTE] Structured null E[net]={s_mean:.6f} vs uniform={u_mean:.6f} "
                "(structured should be <= uniform + 5bps when news clusters in volatile hours)"
            )
    else:
        print("\nHint: --synthetic-audit for §6.2 bias dry run; --shadow-backtest for lag PnL.")


if __name__ == "__main__":
    main()
