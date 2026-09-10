#!/usr/bin/env python3
"""Run the swarm gap detector once (price anomaly + untracked cashtags).

Public Binance via ccxt — no API key. Network errors are swallowed per asset.
Does not touch the cluster.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.gap_detector.detector import run_once


def main() -> int:
    parser = argparse.ArgumentParser(description="Swarm gap detector (diagnostic_only)")
    parser.add_argument("--once", action="store_true", default=True)
    parser.add_argument("--news", default=None)
    parser.add_argument("--events", default=None)
    parser.add_argument("--md", default=None)
    args = parser.parse_args()
    _ = args.once
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    os.chdir(_ROOT)
    result = run_once(
        news_path=Path(args.news) if args.news else None,
        events_path=Path(args.events) if args.events else None,
        md_path=Path(args.md) if args.md else None,
    )
    printable = {k: v for k, v in result.items() if k != "events"}
    print(json.dumps(printable, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
