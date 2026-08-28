"""Depth snapshot provenance — Paket 2.1 snapshot_ts / snapshot_age_s."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from prototypes.raas_paper_trading.feed import fetch_binance_depth, parse_orderbook_snapshot
from prototypes.raas_paper_trading.slippage import OrderBook, synthetic_orderbook

DepthFetcher = Callable[[str, float, str], "DepthSnapshot"]

AGE_STRATA_LT_5 = "lt_5s"
AGE_STRATA_5_30 = "5_30s"
AGE_STRATA_GT_30 = "gt_30s"
AGE_STRATA_UNKNOWN = "unknown"


@dataclass(frozen=True)
class DepthSnapshot:
    """Order book plus provenance for SIM_FILL WORM lines."""

    orderbook: OrderBook
    snapshot_ts: str
    source: str
    snapshot_age_s: Optional[float] = None
    depth_snapshot_hash: Optional[str] = None


def _parse_iso(ts: str) -> datetime:
    text = ts.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def snapshot_age_seconds(fill_ts: str, snapshot_ts: str) -> float:
    """Seconds from snapshot to fill: fill_ts − snapshot_ts (positive = stale book)."""
    return (_parse_iso(fill_ts) - _parse_iso(snapshot_ts)).total_seconds()


def age_stratum(snapshot_age_s: Optional[float]) -> str:
    """Report buckets: < 5 s · 5–30 s · > 30 s."""
    if snapshot_age_s is None:
        return AGE_STRATA_UNKNOWN
    age = float(snapshot_age_s)
    if age < 5.0:
        return AGE_STRATA_LT_5
    if age <= 30.0:
        return AGE_STRATA_5_30
    return AGE_STRATA_GT_30


def make_live_depth_fetcher(
    *,
    limit: int = 10,
    fallback_on_error: bool = True,
) -> DepthFetcher:
    """Fetch public depth at fill time — snapshot_age_s ≈ API latency.

    On REST failure, optional synthetic fallback (depth_source=synthetic_fallback).
    """

    def _fetch(symbol: str, mid: float, fill_ts: str) -> DepthSnapshot:
        snapshot_ts = datetime.now(timezone.utc).isoformat()
        try:
            book = fetch_binance_depth(symbol, limit=limit)
            age = snapshot_age_seconds(fill_ts, snapshot_ts)
            return DepthSnapshot(
                orderbook=book,
                snapshot_ts=snapshot_ts,
                source="binance_rest_depth",
                snapshot_age_s=age,
            )
        except Exception:
            if not fallback_on_error:
                raise
            book = synthetic_orderbook(mid, depth_levels=limit)
            return DepthSnapshot(
                orderbook=book,
                snapshot_ts=fill_ts,
                source="synthetic_fallback",
                snapshot_age_s=0.0,
            )

    return _fetch


def make_worm_depth_fetcher(worm_path: Path) -> DepthFetcher:
    """Use latest DEPTH_SNAPSHOT from ingest WORM (may be up to interval_s stale)."""

    def _fetch(symbol: str, _mid: float, fill_ts: str) -> DepthSnapshot:
        from prototypes.raas_paper_trading.depth_worm import latest_depth_row

        row = latest_depth_row(symbol, fill_ts=fill_ts, path=worm_path)
        if row is None:
            raise FileNotFoundError(f"no depth snapshot for {symbol} in {worm_path}")
        book = parse_orderbook_snapshot(row["orderbook_snapshot"])
        snapshot_ts = str(row["ts"])
        age = snapshot_age_seconds(fill_ts, snapshot_ts)
        return DepthSnapshot(
            orderbook=book,
            snapshot_ts=snapshot_ts,
            source=str(row.get("source", "depth_worm")),
            snapshot_age_s=age,
            depth_snapshot_hash=str(row.get("hash") or ""),
        )

    return _fetch
