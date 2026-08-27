#!/usr/bin/env python3
"""§4.3 Public-Ingest sondierung — distribution profiles only.

Fetches a bounded Binance Vision kline sample and a Flashbots blocks sample,
writes descriptive JSON profiles under exports/open_data/.

Never uses public rows as training labels. Never emits severity/gateway verdicts.
Purpose: calibrate synth generator input distributions (Gate-Map §4.3).

Usage:
  PYTHONPATH=. python3 scripts/ingest_public_distributions.py
  make raas-public-ingest-sondierung
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = _ROOT / "exports" / "open_data"
CACHE_DIR = OUT_DIR / "_cache"
SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"
PURPOSE = "calibration_profile_not_training_labels"
UA = "agent-x-raas-public-ingest/0.1 (+research; no trading)"


def _pctiles(values: Sequence[float], ps: Sequence[float] = (50, 90, 99)) -> Dict[str, float]:
    if not values:
        return {f"p{int(p)}": float("nan") for p in ps} | {"max": float("nan"), "mean": float("nan"), "n": 0}
    arr = sorted(float(v) for v in values)
    n = len(arr)

    def _at(p: float) -> float:
        if n == 1:
            return arr[0]
        idx = min(n - 1, max(0, int(math.ceil(p / 100.0 * n) - 1)))
        return arr[idx]

    return {
        **{f"p{int(p)}": round(_at(p), 6) for p in ps},
        "max": round(arr[-1], 6),
        "mean": round(sum(arr) / n, 6),
        "n": n,
    }


def _http_get(url: str, *, timeout: float = 60.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _binance_daily_klines_url(symbol: str, interval: str, day: date) -> str:
    name = f"{symbol}-{interval}-{day.isoformat()}"
    return (
        f"https://data.binance.vision/data/spot/daily/klines/"
        f"{symbol}/{interval}/{name}.zip"
    )


def fetch_binance_klines(
    symbol: str,
    interval: str,
    days: int,
    *,
    end: Optional[date] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Download daily zip klines; return row dicts + fetch log."""
    end = end or (datetime.now(timezone.utc).date() - timedelta(days=1))
    start = end - timedelta(days=days - 1)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    log: List[str] = []
    day = start
    while day <= end:
        url = _binance_daily_klines_url(symbol, interval, day)
        cache_zip = CACHE_DIR / f"{symbol}-{interval}-{day.isoformat()}.zip"
        try:
            if not cache_zip.is_file():
                data = _http_get(url)
                cache_zip.write_bytes(data)
                log.append(f"OK download {url} ({len(data)} B)")
            else:
                log.append(f"OK cache {cache_zip.name}")
            with zipfile.ZipFile(cache_zip) as zf:
                names = [n for n in zf.namelist() if n.endswith(".csv")]
                if not names:
                    log.append(f"WARN empty zip {cache_zip.name}")
                    day += timedelta(days=1)
                    continue
                raw = zf.read(names[0]).decode("utf-8", errors="replace")
            reader = csv.reader(io.StringIO(raw))
            for parts in reader:
                if not parts or parts[0].startswith("open_time"):
                    continue
                # Binance kline: open_time, open, high, low, close, volume, ...
                if len(parts) < 6:
                    continue
                o, h, l, c = (float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4]))
                vol = float(parts[5])
                rows.append(
                    {
                        "open_time": int(float(parts[0])),
                        "open": o,
                        "high": h,
                        "low": l,
                        "close": c,
                        "volume": vol,
                    }
                )
        except urllib.error.HTTPError as exc:
            log.append(f"FAIL HTTP {exc.code} {url}")
        except Exception as exc:  # noqa: BLE001 — sondierung must continue
            log.append(f"FAIL {url}: {exc}")
        day += timedelta(days=1)
    return rows, log


def profile_from_klines(
    rows: Sequence[Dict[str, Any]],
    *,
    symbol: str,
    interval: str,
) -> Dict[str, Any]:
    """Derive feature-aligned distribution stats (no labels)."""
    abs_ret_pct: List[float] = []
    hl_dev_pct: List[float] = []
    vol_proxy: List[float] = []
    # 1-bar absolute return as slippage proxy; (H-L)/mid as oracle-range proxy
    for i, r in enumerate(rows):
        mid = (r["high"] + r["low"]) / 2.0 or r["close"]
        if mid > 0:
            hl_dev_pct.append(100.0 * (r["high"] - r["low"]) / mid)
        if i > 0:
            prev = rows[i - 1]["close"]
            if prev > 0:
                abs_ret_pct.append(100.0 * abs(r["close"] - prev) / prev)
    # rolling 24h vol if 1m: 1440 bars; for 1s would be huge — use window by interval
    window = 1440 if interval == "1m" else (86400 if interval == "1s" else 24)
    closes = [r["close"] for r in rows]
    for i in range(window, len(closes)):
        chunk = closes[i - window : i]
        rets = []
        for j in range(1, len(chunk)):
            if chunk[j - 1] > 0:
                rets.append((chunk[j] - chunk[j - 1]) / chunk[j - 1])
        if len(rets) >= 2:
            m = sum(rets) / len(rets)
            var = sum((x - m) ** 2 for x in rets) / (len(rets) - 1)
            vol_proxy.append(math.sqrt(max(var, 0.0)))

    return {
        "source": "binance_vision",
        "symbol": symbol,
        "interval": interval,
        "n_rows": len(rows),
        "purpose": PURPOSE,
        "label_mode": None,
        "live_execution": False,
        "scope": SCOPE,
        "banned": ["training_label", "gateway_verdict", "risk_forecast_claim"],
        "features": {
            "slippage_pct": _pctiles(abs_ret_pct),
            "oracle_deviation_pct": _pctiles(hl_dev_pct),
            "volatility_24h": _pctiles(vol_proxy),
            "latency_ms": None,
            "gas_price_gwei": None,
            "mev_bundle_activity": None,
            "note": (
                "slippage_pct ← abs 1-bar return %; "
                "oracle_deviation_pct ← (high-low)/mid %; "
                "volatility_24h ← rolling std of returns; "
                "not a market-risk label"
            ),
        },
        "generator_hints": {
            "slippage_pct": "use p50/p90/p99 as synth draw anchors",
            "oracle_deviation_pct": "stress tail from p90/p99",
            "volatility_24h": "scale extremes profile toward these percentiles",
        },
    }


def fetch_flashbots_blocks(limit: int = 100) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Flashbots public sample.

    blocks.flashbots.net returned HTTP 410 (Gone) as of 2026-08 — use
    boost-relay bidtraces (proposer_payload_delivered) instead.
    """
    url = (
        "https://boost-relay.flashbots.net/relay/v1/data/bidtraces/"
        f"proposer_payload_delivered?limit={limit}"
    )
    log: List[str] = []
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"flashbots_bidtraces_limit{limit}.json"
    try:
        if not cache.is_file():
            raw = _http_get(url, timeout=45.0)
            cache.write_bytes(raw)
            log.append(f"OK download {url} ({len(raw)} B)")
        else:
            raw = cache.read_bytes()
            log.append(f"OK cache {cache.name}")
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, list):
            log.append("FAIL unexpected JSON shape (want list)")
            return [], log
        log.append(f"OK bidtraces={len(payload)}")
        return payload, log
    except urllib.error.HTTPError as exc:
        log.append(f"FAIL HTTP {exc.code} {url}")
        return [], log
    except Exception as exc:  # noqa: BLE001
        log.append(f"FAIL {url}: {exc}")
        return [], log


def profile_from_flashbots(blocks: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Profile from relay bidtraces (gas value / slot activity proxies)."""
    gas_gwei: List[float] = []
    bundle_activity: List[float] = []
    value_eth: List[float] = []
    for b in blocks:
        # bidtrace fields: gas_used, gas_limit, value (wei), num_tx, ...
        gu = b.get("gas_used")
        gl = b.get("gas_limit")
        val = b.get("value")
        ntx = b.get("num_tx") or b.get("num_transactions")
        try:
            if gu is not None and gl is not None and float(gl) > 0:
                # utilization as activity proxy (0–1 → scale *100 for feature-ish)
                bundle_activity.append(100.0 * float(gu) / float(gl))
            elif ntx is not None:
                bundle_activity.append(float(ntx))
        except (TypeError, ValueError):
            pass
        try:
            if val is not None:
                # wei → ETH
                value_eth.append(float(val) / 1e18)
        except (TypeError, ValueError):
            pass
        # no direct gwei in bidtrace; derive coarse proxy from value/gas if both present
        try:
            if val is not None and gu is not None and float(gu) > 0:
                # value(wei)/gas_used ≈ wei per gas → /1e9 = gwei-ish effective
                gas_gwei.append((float(val) / float(gu)) / 1e9)
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    return {
        "source": "flashbots_boost_relay_bidtraces",
        "endpoint": (
            "https://boost-relay.flashbots.net/relay/v1/data/bidtraces/"
            "proposer_payload_delivered"
        ),
        "n_blocks": len(blocks),
        "purpose": PURPOSE,
        "label_mode": None,
        "live_execution": False,
        "scope": SCOPE,
        "banned": ["training_label", "gateway_verdict", "risk_forecast_claim"],
        "features": {
            "gas_price_gwei": _pctiles(gas_gwei) if gas_gwei else None,
            "mev_bundle_activity": _pctiles(bundle_activity) if bundle_activity else None,
            "builder_value_eth": _pctiles(value_eth) if value_eth else None,
            "latency_ms": None,
            "slippage_pct": None,
            "oracle_deviation_pct": None,
            "volatility_24h": None,
            "note": (
                "gas_price_gwei ← value/gas_used (effective); "
                "mev_bundle_activity ← gas_used/gas_limit %; "
                "blocks.flashbots.net deprecated (410); "
                "not a training label"
            ),
        },
        "generator_hints": {
            "gas_price_gwei": "anchor synth gas draws to p50–p99",
            "mev_bundle_activity": "scale mev_bundle_activity feature",
            "latency_ms": "unavailable from bidtraces — keep plugin base_latency",
        },
    }


def run_sondierung(
    *,
    symbol: str = "ETHUSDT",
    interval: str = "1m",
    days: int = 14,
    flashbots_limit: int = 100,
    out_dir: Path = OUT_DIR,
) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    sources: Dict[str, Any] = {}
    errors: List[str] = []

    # Binance — try requested symbol, then ETHUSDT fallback
    symbols_try = [symbol]
    if symbol.upper() != "ETHUSDT":
        symbols_try.append("ETHUSDT")
    binance_profile = None
    binance_log: List[str] = []
    used_symbol = symbol
    for sym in symbols_try:
        rows, blog = fetch_binance_klines(sym, interval, days)
        binance_log.extend(blog)
        if rows:
            used_symbol = sym
            binance_profile = profile_from_klines(rows, symbol=sym, interval=interval)
            break
    if binance_profile is None:
        errors.append("binance: no rows")
    else:
        path = out_dir / f"binance_{used_symbol.lower()}_klines_profile.json"
        path.write_text(json.dumps(binance_profile, indent=2), encoding="utf-8")
        sources["binance"] = {"path": str(path), "n_rows": binance_profile["n_rows"], "symbol": used_symbol}
    sources["binance_fetch_log"] = binance_log[-20:]

    blocks, flog = fetch_flashbots_blocks(flashbots_limit)
    sources["flashbots_fetch_log"] = flog[-20:]
    if blocks:
        fb_profile = profile_from_flashbots(blocks)
        path = out_dir / "flashbots_latency_profile.json"
        path.write_text(json.dumps(fb_profile, indent=2), encoding="utf-8")
        sources["flashbots"] = {"path": str(path), "n_blocks": fb_profile["n_blocks"]}
    else:
        errors.append("flashbots: no blocks")

    # Combined index for later generator wiring (profiles only)
    index = {
        "purpose": PURPOSE,
        "label_mode": None,
        "scope": SCOPE,
        "live_execution": False,
        "gate_map": "docs/RaaS_BUS_EXPANSION_v0.md §4.3",
        "success_next": "paired seed mean(Δ)>2·SEM(Δ) after generator calibration",
        "sources": {k: v for k, v in sources.items() if k in ("binance", "flashbots")},
        "profiles": [
            p
            for p in (
                sources.get("binance", {}).get("path"),
                sources.get("flashbots", {}).get("path"),
            )
            if p
        ],
        "errors": errors,
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    index_path = out_dir / "calibration_profiles_index.json"
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")

    ok = bool(sources.get("binance") or sources.get("flashbots"))
    return {
        "verdict": "PUBLIC_INGEST_SONDIERUNG_PASS" if ok else "PUBLIC_INGEST_SONDIERUNG_FAIL",
        "index_path": str(index_path),
        "sources": sources,
        "errors": errors,
        "purpose": PURPOSE,
        "note": "Profiles only — not training labels; model still approximates gate for sorting",
    }


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="§4.3 Public-Ingest sondierung (profiles only)")
    p.add_argument("--symbol", default="ETHUSDC", help="Binance spot symbol (fallback ETHUSDT)")
    p.add_argument("--interval", default="1m", choices=("1m", "1s", "5m", "1h"))
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--flashbots-limit", type=int, default=100)
    p.add_argument("--out", type=Path, default=OUT_DIR)
    args = p.parse_args(argv)

    print("Public-Ingest sondierung (Gate-Map §4.3)")
    print("=" * 60)
    print(f"symbol={args.symbol} interval={args.interval} days={args.days}")
    print("purpose=calibration_profile_not_training_labels")
    result = run_sondierung(
        symbol=args.symbol.upper(),
        interval=args.interval,
        days=args.days,
        flashbots_limit=args.flashbots_limit,
        out_dir=args.out,
    )
    for err in result.get("errors") or []:
        print(f"  warn: {err}")
    src = result.get("sources") or {}
    if "binance" in src:
        print(f"binance: {src['binance']}")
    if "flashbots" in src:
        print(f"flashbots: {src['flashbots']}")
    print(f"index: {result['index_path']}")
    print("=" * 60)
    print(f"VERDICT: {result['verdict']}")
    return 0 if str(result["verdict"]).endswith("_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
