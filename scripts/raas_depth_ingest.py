#!/usr/bin/env python3
"""Phase B — passive Binance depth ingest into WORM (no order send).

Usage:
  PYTHONPATH=. python3 scripts/raas_depth_ingest.py
  PYTHONPATH=. python3 scripts/raas_depth_ingest.py --symbol ETHUSDC
  make raas-depth-ingest
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.config_loader import (  # noqa: E402
    PaperTradingSettings,
    config_manifest_hash,
)
from prototypes.raas_paper_trading.depth_worm import DepthWormLog  # noqa: E402
from prototypes.raas_paper_trading.feed import fetch_binance_depth  # noqa: E402

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"


def ingest(*, symbols: list[str], limit: int, worm_path: Path) -> dict:
    worm = DepthWormLog(worm_path)
    rows = []
    for sym in symbols:
        book = fetch_binance_depth(sym, limit=limit)
        row = worm.append_snapshot(symbol=sym, orderbook=book, source="binance_rest_depth")
        rows.append(
            {
                "symbol": sym,
                "hash": row["hash"],
                "levels": len(book.get("asks") or []),
            }
        )
    return {
        "schema": "raas_depth_ingest_v0",
        "scope": SCOPE,
        "live_execution": False,
        "order_send": False,
        "symbols": rows,
        "worm_path": str(worm.path),
        "config_hash": config_manifest_hash(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Passive Binance depth → WORM")
    parser.add_argument("--symbol", action="append", default=[], help="Override config symbols")
    parser.add_argument("--limit", type=int, default=None, help="Depth levels (default: config)")
    parser.add_argument("--worm-path", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Fetch only, do not append WORM")
    args = parser.parse_args(argv)

    settings = PaperTradingSettings.from_file()
    symbols = [s.upper() for s in (args.symbol or list(settings.depth_symbols))]
    limit = args.limit if args.limit is not None else settings.depth_rest_limit
    worm_path = args.worm_path or Path(settings.depth_worm_path)

    print("RaaS Depth Ingest (passive · no order send)")
    print("=" * 60)
    print(f"symbols={symbols} limit={limit} worm={worm_path}")

    if args.dry_run:
        for sym in symbols:
            book = fetch_binance_depth(sym, limit=limit)
            print(f"  dry-run {sym}: {len(book['asks'])} ask levels")
        print("VERDICT: RAAS_DEPTH_INGEST_DRY_RUN_PASS")
        return 0

    result = ingest(symbols=symbols, limit=limit, worm_path=worm_path)
    for row in result["symbols"]:
        print(f"  {row['symbol']}: {row['levels']} levels hash={row['hash'][:12]}…")
    print(f"worm: {result['worm_path']}")
    print("=" * 60)
    print("VERDICT: RAAS_DEPTH_INGEST_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
