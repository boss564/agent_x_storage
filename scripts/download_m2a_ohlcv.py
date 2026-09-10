#!/usr/bin/env python3
"""Download Binance USDT-M perpetual 15m OHLCV for M2a full-history backtest."""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.m2a_config import PERP_START, PREREG_FREEZE

DATA_DIR = Path("data")
FAPI_KLINES = "https://fapi.binance.com/fapi/v1/klines"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
INTERVAL = "15m"
LIMIT = 1500


def fetch_klines(symbol: str, start_ms: int, end_ms: int) -> list[list]:
    rows: list[list] = []
    since = start_ms
    while since < end_ms:
        qs = urllib.parse.urlencode(
            {
                "symbol": symbol,
                "interval": INTERVAL,
                "startTime": since,
                "limit": LIMIT,
            }
        )
        url = f"{FAPI_KLINES}?{qs}"
        with urllib.request.urlopen(url, timeout=60) as resp:
            batch = json.loads(resp.read().decode())
        if not batch:
            break
        rows.extend(batch)
        since = int(batch[-1][0]) + 1
        time.sleep(0.08)
        if len(batch) < LIMIT:
            break
    return rows


def to_dataframe(rows: list[list]) -> pd.DataFrame:
    df = pd.DataFrame(
        rows,
        columns=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_volume",
            "trades",
            "taker_buy_base",
            "taker_buy_quote",
            "ignore",
        ],
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    return df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)


def main() -> int:
    start_ms = int(PERP_START.timestamp() * 1000)
    end_ms = int(PREREG_FREEZE.timestamp() * 1000)
    DATA_DIR.mkdir(exist_ok=True)

    print("=" * 72)
    print("M2a OHLCV download — Binance USDT-M perpetual 15m")
    print(f"Window: {PERP_START.date()} .. {PREREG_FREEZE.date()}")
    print("=" * 72)

    for sym in SYMBOLS:
        slug = sym.replace("USDT", "_usdt").lower()
        out = DATA_DIR / f"{slug}_15m_perp_full.csv"
        print(f"\n--- {sym} → {out} ---")
        rows = fetch_klines(sym, start_ms, end_ms)
        df = to_dataframe(rows)
        df.to_csv(out, index=False)
        print(f"  candles={len(df)}  span={df.timestamp.min()} .. {df.timestamp.max()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
