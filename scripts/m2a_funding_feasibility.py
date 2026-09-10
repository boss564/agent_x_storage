#!/usr/bin/env python3
"""
M2a Machbarkeitsprüfung: Funding-Extremwerte über volle Binance-Perp-Historie.

Zählt Slots und unabhängige Episoden (|fr| >= Schwelle) ohne OHLCV-Download.
Episoden = zusammenhängende 8h-Slots über Schwelle (ein Squeeze-Lauf = 1 Episode).

Mindestbesetzung (vorab, nicht post-hoc):
  MIN_EPISODES_GRID     = 10  — unteres Grid-Gate (MIN_TRADES_GRID)
  MIN_EPISODES_ADEQUATE = 30  — unterhalb: volle Historie wahrscheinlich unterbesetzt
  MIN_EPISODES_STRONG   = 60  — darüber: OHLCV-Abruf (210k Kerzen) lohnt sich
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd

from scripts.m2a_config import OOS_SPLIT_TS, PREREG_PRIMARY_THRESHOLD

BINANCE_FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
RESULTS_DIR = Path("results")
THRESHOLD_PREREG = PREREG_PRIMARY_THRESHOLD
START_DATE = datetime(2019, 9, 1, tzinfo=timezone.utc)  # BTCUSDT perp ~Sep 2019

MIN_EPISODES_GRID = 10
MIN_EPISODES_ADEQUATE = 30
MIN_EPISODES_STRONG = 60

SYMBOLS = ["BTCUSDT", "ETHUSDT"]


def download_funding(symbol: str) -> pd.DataFrame:
    since = int(START_DATE.timestamp() * 1000)
    end = int(datetime.now(timezone.utc).timestamp() * 1000)
    rows: list[dict] = []
    while since < end:
        qs = urllib.parse.urlencode({"symbol": symbol, "startTime": since, "limit": 1000})
        url = f"{BINANCE_FUNDING_URL}?{qs}"
        with urllib.request.urlopen(url, timeout=30) as resp:
            batch = json.loads(resp.read().decode())
        if not batch:
            break
        rows.extend(batch)
        since = int(batch[-1]["fundingTime"]) + 1
        time.sleep(0.05)
        if len(batch) < 1000:
            break

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True)
    df["funding_rate"] = df["fundingRate"].astype(float)
    return df.sort_values("timestamp").reset_index(drop=True)


def count_episodes(df: pd.DataFrame, threshold: float) -> tuple[int, int, list[dict]]:
    """Returns (n_slots, n_episodes, episode_list)."""
    extreme = df["funding_rate"].abs() >= threshold
    n_slots = int(extreme.sum())

    episodes: list[dict] = []
    in_ep = False
    start_ts = end_ts = None
    peak_abs = 0.0

    for ts, fr, is_ext in zip(df["timestamp"], df["funding_rate"], extreme):
        if is_ext:
            if not in_ep:
                in_ep = True
                start_ts = ts
                peak_abs = abs(fr)
            else:
                peak_abs = max(peak_abs, abs(fr))
            end_ts = ts
        elif in_ep:
            episodes.append(
                {
                    "start": str(start_ts),
                    "end": str(end_ts),
                    "peak_abs_fr": peak_abs,
                    "duration_slots": int((end_ts - start_ts).total_seconds() / 28800) + 1,
                }
            )
            in_ep = False

    if in_ep and start_ts is not None:
        episodes.append(
            {
                "start": str(start_ts),
                "end": str(end_ts),
                "peak_abs_fr": peak_abs,
                "duration_slots": int((end_ts - start_ts).total_seconds() / 28800) + 1,
            }
        )

    return n_slots, len(episodes), episodes


def episodes_by_split(episodes: list[dict]) -> dict[str, int]:
    """Assign episodes to train/oos by episode start vs frozen OOS_SPLIT_TS."""
    split = pd.Timestamp(OOS_SPLIT_TS)
    train = oos = 0
    for ep in episodes:
        start = pd.Timestamp(ep["start"])
        if start.tzinfo is None:
            start = start.tz_localize("UTC")
        else:
            start = start.tz_convert("UTC")
        if start < split:
            train += 1
        else:
            oos += 1
    return {"train_60pct": train, "oos_40pct": oos}


def verdict(n_episodes: int) -> str:
    if n_episodes < MIN_EPISODES_GRID:
        return "UNDERPOWERED: < grid minimum (10)"
    if n_episodes < MIN_EPISODES_ADEQUATE:
        return "MARGINAL: 10–29 episodes — full OHLCV likely underpowered"
    if n_episodes < MIN_EPISODES_STRONG:
        return "ADEQUATE: 30–59 episodes — full OHLCV download justified"
    return "STRONG: >= 60 episodes — full OHLCV download recommended"


def main() -> int:
    print("=" * 72)
    print("M2a Funding Feasibility — full history, no OHLCV")
    print(f"Threshold: |fr| >= {THRESHOLD_PREREG} ({THRESHOLD_PREREG*100:.2f}% per 8h)")
    print(f"Window: {START_DATE.date()} .. today")
    print(f"OOS split (frozen): {OOS_SPLIT_TS.isoformat()}")
    print(
        f"Min episodes: grid={MIN_EPISODES_GRID}, adequate={MIN_EPISODES_ADEQUATE}, "
        f"strong={MIN_EPISODES_STRONG}"
    )
    print("=" * 72)

    report: dict = {
        "threshold": THRESHOLD_PREREG,
        "start_date": str(START_DATE.date()),
        "min_episodes_grid": MIN_EPISODES_GRID,
        "min_episodes_adequate": MIN_EPISODES_ADEQUATE,
        "min_episodes_strong": MIN_EPISODES_STRONG,
        "assets": {},
    }

    for sym in SYMBOLS:
        print(f"\n--- {sym} ---")
        df = download_funding(sym)
        span_days = (df["timestamp"].max() - df["timestamp"].min()).days
        max_abs = float(df["funding_rate"].abs().max())
        n_slots, n_ep, episodes = count_episodes(df, THRESHOLD_PREREG)
        by_split = episodes_by_split(episodes)
        by_thresh: dict[str, dict[str, int]] = {}
        for thr in (0.0005, 0.001, 0.0015):
            _, n_thr, eps_thr = count_episodes(df, thr)
            by_thresh[str(thr)] = {**episodes_by_split(eps_thr), "total": n_thr}
        v = verdict(n_ep)

        print(f"  rows={len(df)}  span={span_days}d  max|fr|={max_abs:.8f} ({max_abs*100:.4f}%)")
        print(f"  slots >= {THRESHOLD_PREREG}: {n_slots}")
        print(f"  independent episodes @0.10%: {n_ep}  (train={by_split['train_60pct']}, oos={by_split['oos_40pct']})")
        print(f"  episodes by threshold (train/oos/total):")
        for thr, counts in by_thresh.items():
            print(
                f"    {float(thr)*100:.2f}%: train={counts['train_60pct']} "
                f"oos={counts['oos_40pct']} total={counts['total']}"
            )
        print(f"  → {v}")

        if episodes:
            top = sorted(episodes, key=lambda e: e["peak_abs_fr"], reverse=True)[:5]
            print("  top episodes (peak |fr|):")
            for e in top:
                print(f"    {e['start'][:10]} .. {e['end'][:10]}  peak={e['peak_abs_fr']*100:.4f}%")

        report["assets"][sym] = {
            "rows": len(df),
            "span_days": span_days,
            "max_abs_fr": max_abs,
            "slots_ge_threshold": n_slots,
            "independent_episodes": n_ep,
            "episodes_by_split": by_split,
            "episodes_by_threshold_and_split": by_thresh,
            "verdict": v,
            "episodes": episodes,
        }

    combined_ep = sum(report["assets"][s]["independent_episodes"] for s in SYMBOLS)
    combined_train = sum(report["assets"][s]["episodes_by_split"]["train_60pct"] for s in SYMBOLS)
    combined_oos = sum(report["assets"][s]["episodes_by_split"]["oos_40pct"] for s in SYMBOLS)
    report["combined_independent_episodes"] = combined_ep
    report["combined_episodes_by_split"] = {"train_60pct": combined_train, "oos_40pct": combined_oos}
    report["oos_split_ts"] = OOS_SPLIT_TS.isoformat()
    report["combined_verdict"] = verdict(combined_ep)

    print(f"\n{'=' * 72}")
    print(f"Combined independent episodes (BTC+ETH): {combined_ep}")
    print(f"  train 60%: {combined_train}  |  oos 40%: {combined_oos}")
    print(f"Combined: {report['combined_verdict']}")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / "m2a_funding_feasibility.json"
    # trim episode list in JSON for size — keep full in file but user can read summary
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n[OUTPUT] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
