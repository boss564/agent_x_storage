#!/usr/bin/env python3
"""Einmaliges Gamma-Resolve → allowlist.freeze.json (BTC/ETH).

Charter: diagnostic_only — nur Marktdaten-Lookup, kein Trading.
Fail-closed wenn ein Asset nicht auflösbar ist.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

GAMMA_BASE = "https://gamma-api.polymarket.com"
USER_AGENT = "AgentX-Shadow/1.0 (+diagnostic_only; allowlist-freeze)"
ASSETS = (
    ("BTC", "bitcoin"),
    ("ETH", "ethereum"),
)


def _get_json(url: str, *, timeout: float = 30.0) -> Any:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def parse_clob_token_ids(market: dict[str, Any]) -> list[str]:
    raw = market.get("clobTokenIds")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, list):
        return []
    return [str(t) for t in raw if t]


def _mentions_asset(text: str, asset: str) -> bool:
    if asset == "BTC":
        return bool(re.search(r"\b(bitcoin|btc)\b", text, re.I))
    if asset == "ETH":
        return bool(re.search(r"\b(ethereum|eth)\b", text, re.I))
    return False


def _end_ts(market: dict[str, Any], event: dict[str, Any]) -> float:
    raw = market.get("endDate") or event.get("endDate") or ""
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def resolve_asset(
    asset: str,
    tag_slug: str,
    *,
    min_horizon_days: float = 14.0,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Wählt den liquidesten offenen Markt mit Orderbook und genügend Restlaufzeit."""
    now = now or datetime.now(timezone.utc)
    min_end = now.timestamp() + min_horizon_days * 86400.0
    url = (
        f"{GAMMA_BASE}/events?active=true&closed=false"
        f"&limit=80&tag_slug={tag_slug}"
    )
    events = _get_json(url)
    if not isinstance(events, list):
        raise RuntimeError(f"Gamma events response unexpected for {asset}")

    scored: list[tuple[float, dict[str, Any], dict[str, Any], list[str]]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        title = str(event.get("title") or "")
        for market in event.get("markets") or []:
            if not isinstance(market, dict):
                continue
            if market.get("closed"):
                continue
            if not market.get("enableOrderBook") or not market.get("acceptingOrders"):
                continue
            tokens = parse_clob_token_ids(market)
            if not tokens:
                continue
            question = str(market.get("question") or title)
            slug = str(market.get("slug") or event.get("slug") or "")
            text = f"{question} {slug}"
            if not _mentions_asset(text, asset):
                continue
            end = _end_ts(market, event)
            if end and end < min_end:
                continue
            vol = float(market.get("volume24hr") or 0.0)
            scored.append((vol, event, market, tokens))

    if not scored:
        raise RuntimeError(
            f"No durable open Gamma market for {asset} "
            f"(tag={tag_slug}, min_horizon_days={min_horizon_days})"
        )

    scored.sort(key=lambda row: -row[0])
    _vol, event, market, tokens = scored[0]
    resolved_at = now.astimezone(timezone.utc).isoformat()
    return {
        "asset": asset,
        "market_question": market.get("question") or event.get("title"),
        "slug": market.get("slug") or event.get("slug"),
        "token_id": tokens[0],
        "market_id": str(market.get("conditionId") or market.get("id")),
        "resolved_at": resolved_at,
        "source": "gamma",
        "end_date": market.get("endDate") or event.get("endDate"),
        "volume_24hr": float(market.get("volume24hr") or 0.0),
    }


def build_freeze(
    *,
    min_horizon_days: float = 14.0,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    entries: dict[str, dict[str, Any]] = {}
    for asset, tag in ASSETS:
        entries[asset] = resolve_asset(
            asset, tag, min_horizon_days=min_horizon_days, now=now,
        )
    missing = [a for a, _ in ASSETS if a not in entries]
    if missing:
        raise RuntimeError(f"Freeze incomplete, missing: {missing}")
    return {
        "schema": "allowlist.freeze/v1",
        "frozen_at": (now or datetime.now(timezone.utc))
        .astimezone(timezone.utc)
        .isoformat(),
        "min_horizon_days": min_horizon_days,
        "entries": entries,
    }


def main(argv: Optional[list[str]] = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=root / "ops" / "allowlist.freeze.json",
    )
    parser.add_argument("--min-horizon-days", type=float, default=14.0)
    args = parser.parse_args(argv)

    try:
        freeze = build_freeze(min_horizon_days=args.min_horizon_days)
    except (RuntimeError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n")
    print(f"OK wrote {args.out}")
    for asset, entry in freeze["entries"].items():
        print(
            f"  {asset}: {entry['slug']} token={entry['token_id'][:16]}… "
            f"end={entry.get('end_date')}"
        )
    # Horizon hint (Halbwertszeit)
    horizon = datetime.now(timezone.utc) + timedelta(days=args.min_horizon_days)
    print(f"note: markets preferred with end_date >= {horizon.date()} (no ad-hoc refresh)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
