"""Stufe A driver capture: ETH gas, BTC price, CEX volume at 1-minute resolution."""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bridge_stufe_a_config import (
    CEX_VENUES,
    WINDOW_END_UTC,
    WINDOW_START_UTC,
    n_minute_bins,
)
from bridge_stufe_a_rpc import (
    DEFAULT_RPCS,
    USER_AGENT,
    as_int,
    block_timestamp,
    fee_history,
    redact_url,
    timestamp_to_block,
)
from bridge_stufe_a_stats import interpolate_short_gaps

START_TS = int(WINDOW_START_UTC.timestamp())
END_TS = int(WINDOW_END_UTC.timestamp())
N_BINS = n_minute_bins()


def http_get_json(url: str, timeout: float = 30.0) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def minute_index(ts: int | float) -> int | None:
    idx = int((int(ts) - START_TS) // 60)
    if 0 <= idx < N_BINS:
        return idx
    return None


def empty_series() -> list[float | None]:
    return [None] * N_BINS


def capture_gas(rpc_url: str | None = None) -> tuple[list[float | None], dict]:
    """Median baseFeePerGas (gwei) per minute via eth_feeHistory."""
    from bridge_stufe_a_rpc import ETH_HTTP_FALLBACKS

    urls = [rpc_url] if rpc_url else []
    for u in ETH_HTTP_FALLBACKS:
        if u and u not in urls:
            urls.append(u)
    last_err: Exception | None = None
    for url in urls:
        try:
            return _capture_gas_on(url)
        except Exception as exc:
            last_err = exc
            print(f"gas RPC {redact_url(url)} failed: {exc}", file=sys.stderr)
    raise last_err or RuntimeError("no ETH RPC for gas")


def _capture_gas_on(rpc_url: str) -> tuple[list[float | None], dict]:
    cache: dict[int, int] = {}
    from_block = timestamp_to_block(rpc_url, START_TS, cache)
    to_block = timestamp_to_block(rpc_url, END_TS, cache)
    print(
        f"gas feeHistory blocks {from_block}-{to_block} via {redact_url(rpc_url)}",
        flush=True,
    )
    buckets: dict[int, list[float]] = {}
    newest = to_block
    chunks = 0
    while newest >= from_block:
        count = min(1024, newest - from_block + 1)
        hist = fee_history(rpc_url, count, newest)
        oldest = as_int(hist["oldestBlock"])
        fees = [as_int(x) for x in hist["baseFeePerGas"]]
        n_blocks = min(count, len(fees) - 1 if len(fees) > 1 else len(fees))
        if n_blocks <= 0:
            break
        ts_lo = block_timestamp(rpc_url, oldest, cache)
        last_block = oldest + n_blocks - 1
        ts_hi = block_timestamp(rpc_url, last_block, cache)
        span = max(1, last_block - oldest)
        for i in range(n_blocks):
            ts = ts_lo + (ts_hi - ts_lo) * i / span
            idx = minute_index(ts)
            if idx is None:
                continue
            gwei = fees[i] / 1e9
            buckets.setdefault(idx, []).append(gwei)
        chunks += 1
        if chunks == 1 or chunks % 25 == 0:
            print(
                f"  gas chunk {chunks} block {oldest}-{last_block} "
                f"minutes={len(buckets)}/{N_BINS}",
                flush=True,
            )
        if oldest <= from_block:
            break
        newest = oldest - 1
        time.sleep(0.05)
    series = empty_series()
    for idx, vals in buckets.items():
        series[idx] = statistics.median(vals)
    filled = interpolate_short_gaps(series, max_gap=5)
    meta = {
        "from_block": from_block,
        "to_block": to_block,
        "chunks": chunks,
        "rpc_url": redact_url(rpc_url),
        "minutes_raw": sum(1 for v in series if v is not None),
    }
    return filled, meta


def _binance_klines(symbol: str, start_ms: int, end_ms: int) -> list:
    rows: list = []
    cursor = start_ms
    while cursor <= end_ms:
        qs = urllib.parse.urlencode(
            {
                "symbol": symbol,
                "interval": "1m",
                "startTime": cursor,
                "endTime": end_ms,
                "limit": 1000,
            }
        )
        url = f"https://api.binance.com/api/v3/klines?{qs}"
        batch = http_get_json(url)
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(batch)
        last_open = int(batch[-1][0])
        nxt = last_open + 60_000
        if nxt <= cursor:
            break
        cursor = nxt
        if len(batch) < 1000:
            break
        time.sleep(0.05)
    return rows


def capture_btc_binance() -> tuple[list[float | None], list[float | None], dict]:
    """BTC close USD + Binance BTCUSDT+ETHUSDT quote volume."""
    start_ms = START_TS * 1000
    end_ms = END_TS * 1000
    btc = empty_series()
    vol = empty_series()
    vol_acc: dict[int, float] = {}
    n_btc = 0
    for row in _binance_klines("BTCUSDT", start_ms, end_ms):
        ts = int(row[0]) // 1000
        idx = minute_index(ts)
        if idx is None:
            continue
        btc[idx] = float(row[4])
        vol_acc[idx] = vol_acc.get(idx, 0.0) + float(row[7])
        n_btc += 1
    n_eth = 0
    for row in _binance_klines("ETHUSDT", start_ms, end_ms):
        ts = int(row[0]) // 1000
        idx = minute_index(ts)
        if idx is None:
            continue
        vol_acc[idx] = vol_acc.get(idx, 0.0) + float(row[7])
        n_eth += 1
    for idx, v in vol_acc.items():
        vol[idx] = v
    return (
        interpolate_short_gaps(btc, max_gap=5),
        interpolate_short_gaps(vol, max_gap=5),
        {"btc_klines": n_btc, "eth_klines": n_eth, "venue": "binance"},
    )


def _add_quote_volume(series: list[float | None], idx: int, quote: float) -> None:
    if series[idx] is None:
        series[idx] = quote
    else:
        series[idx] = float(series[idx]) + quote


def capture_venue_coinbase() -> list[float | None]:
    """Coinbase BTC-USD + ETH-USD; quote ≈ close * volume."""
    series = empty_series()

    def pull(product: str) -> None:
        cursor = START_TS
        while cursor <= END_TS:
            end = min(cursor + 300 * 60, END_TS)
            start_iso = datetime.fromtimestamp(cursor, tz=timezone.utc).isoformat()
            end_iso = datetime.fromtimestamp(end, tz=timezone.utc).isoformat()
            qs = urllib.parse.urlencode(
                {"granularity": 60, "start": start_iso, "end": end_iso}
            )
            url = f"https://api.exchange.coinbase.com/products/{product}/candles?{qs}"
            batch = http_get_json(url)
            if not isinstance(batch, list) or not batch:
                cursor = end + 60
                continue
            for row in batch:
                ts, _low, _high, _op, close, vol = row[0], row[1], row[2], row[3], row[4], row[5]
                idx = minute_index(int(ts))
                if idx is None:
                    continue
                _add_quote_volume(series, idx, float(close) * float(vol))
            cursor = end + 60
            time.sleep(0.1)

    pull("BTC-USD")
    pull("ETH-USD")
    return interpolate_short_gaps(series, max_gap=5)


def capture_venue_okx() -> list[float | None]:
    series = empty_series()

    def pull(inst: str) -> None:
        after = END_TS * 1000
        guard = 0
        while guard < 500:
            qs = urllib.parse.urlencode(
                {"instId": inst, "bar": "1m", "after": after, "limit": 100}
            )
            url = f"https://www.okx.com/api/v5/market/history-candles?{qs}"
            body = http_get_json(url)
            rows = body.get("data") if isinstance(body, dict) else None
            if not rows:
                break
            oldest = None
            for row in rows:
                ts = int(row[0]) // 1000
                oldest = ts if oldest is None else min(oldest, ts)
                idx = minute_index(ts)
                if idx is None:
                    continue
                close = float(row[4])
                vol = float(row[5])
                _add_quote_volume(series, idx, close * vol)
            if oldest is None or oldest * 1000 <= START_TS * 1000:
                break
            after = oldest * 1000
            guard += 1
            time.sleep(0.05)

    pull("BTC-USDT")
    pull("ETH-USDT")
    return interpolate_short_gaps(series, max_gap=5)


def capture_venue_bybit() -> list[float | None]:
    series = empty_series()

    def pull(symbol: str) -> None:
        end_ms = END_TS * 1000
        guard = 0
        while guard < 400:
            qs = urllib.parse.urlencode(
                {
                    "category": "spot",
                    "symbol": symbol,
                    "interval": "1",
                    "end": end_ms,
                    "limit": 1000,
                }
            )
            url = f"https://api.bybit.com/v5/market/kline?{qs}"
            body = http_get_json(url)
            rows = (body.get("result") or {}).get("list") if isinstance(body, dict) else None
            if not rows:
                break
            oldest = None
            for row in rows:
                ts = int(row[0]) // 1000
                oldest = ts if oldest is None else min(oldest, ts)
                idx = minute_index(ts)
                if idx is None:
                    continue
                _add_quote_volume(series, idx, float(row[6]) if len(row) > 6 else float(row[5]) * float(row[4]))
            if oldest is None or oldest <= START_TS:
                break
            end_ms = oldest * 1000 - 1
            guard += 1
            time.sleep(0.05)

    pull("BTCUSDT")
    pull("ETHUSDT")
    return interpolate_short_gaps(series, max_gap=5)


def capture_venue_kraken() -> list[float | None]:
    """Kraken OHLC since= is limited; best-effort, may be sparse."""
    series = empty_series()

    def pull(pair: str) -> None:
        qs = urllib.parse.urlencode({"pair": pair, "interval": 1, "since": START_TS})
        url = f"https://api.kraken.com/0/public/OHLC?{qs}"
        body = http_get_json(url)
        result = body.get("result") if isinstance(body, dict) else None
        if not isinstance(result, dict):
            return
        rows = None
        for key, val in result.items():
            if key != "last" and isinstance(val, list):
                rows = val
                break
        if not rows:
            return
        for row in rows:
            ts = int(row[0])
            idx = minute_index(ts)
            if idx is None:
                continue
            close = float(row[4])
            vol = float(row[6])
            _add_quote_volume(series, idx, close * vol)

    pull("XBTUSDT")
    pull("ETHUSDT")
    return interpolate_short_gaps(series, max_gap=5)


VENUE_FETCHERS: dict[str, Callable[[], list[float | None]]] = {
    "coinbase": capture_venue_coinbase,
    "okx": capture_venue_okx,
    "bybit": capture_venue_bybit,
    "kraken": capture_venue_kraken,
}


def merge_volumes(parts: list[list[float | None]]) -> list[float | None]:
    out = empty_series()
    for i in range(N_BINS):
        vals = [p[i] for p in parts if p[i] is not None]
        out[i] = sum(vals) if vals else None
    return interpolate_short_gaps(out, max_gap=5)


def write_drivers(path: str, gas, btc, cex) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for i in range(N_BINS):
            ts = START_TS + i * 60
            rec = {
                "timestamp": ts,
                "gas_price_gwei": gas[i],
                "btc_price_usd": btc[i],
                "cex_volume_usd": cex[i],
            }
            fh.write(json.dumps(rec, separators=(",", ":")) + "\n")


def capture_drivers(output: str, rpc_url: str | None) -> dict:
    rpc = rpc_url or os.environ.get("ETH_RPC") or os.environ.get("ETHEREUM_RPC") or DEFAULT_RPCS["ethereum"]
    gas, gas_meta = capture_gas(rpc)
    btc, binance_vol, btc_meta = capture_btc_binance()
    venue_ok: dict[str, str] = {"binance": "ok"}
    parts = [binance_vol]
    for name in CEX_VENUES:
        if name == "binance":
            continue
        fetcher = VENUE_FETCHERS.get(name)
        if fetcher is None:
            venue_ok[name] = "no_adapter"
            continue
        try:
            parts.append(fetcher())
            venue_ok[name] = "ok"
        except Exception as exc:
            venue_ok[name] = f"{type(exc).__name__}: {exc}"
            print(f"venue {name} failed: {exc}", file=sys.stderr)
    cex = merge_volumes(parts)
    write_drivers(output, gas, btc, cex)
    covered = sum(
        1
        for g, b, c in zip(gas, btc, cex)
        if g is not None and b is not None and c is not None
    )
    manifest = {
        "window_start": WINDOW_START_UTC.isoformat(),
        "window_end": WINDOW_END_UTC.isoformat(),
        "n_bins": N_BINS,
        "coverage": covered / N_BINS if N_BINS else 0.0,
        "gas": gas_meta,
        "btc": btc_meta,
        "venues": venue_ok,
        "cex_venues_frozen": list(CEX_VENUES),
        "utc_captured_at": datetime.now(timezone.utc).isoformat(),
        "output": output,
    }
    with open(output + ".manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")
    print(f"drivers: {N_BINS} minutes, coverage={manifest['coverage']:.3f} -> {output}")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Stufe A driver capture")
    parser.add_argument("--output", default="drivers_90d.jsonl")
    parser.add_argument("--rpc", help="ETH JSON-RPC override")
    args = parser.parse_args()
    capture_drivers(args.output, args.rpc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
