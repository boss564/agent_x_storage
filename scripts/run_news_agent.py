#!/usr/bin/env python3
"""Run the isolated News-Agent once (or --loop). Writes logs/audit/news_scores.jsonl.

Does not touch the regime-swarm cluster.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agents_b2g.news import NewsAgent, default_jsonl_path  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="News-Agent: RSS → JSONL (diagnostic_only)")
    parser.add_argument("--once", action="store_true", default=True)
    parser.add_argument("--loop", action="store_true", help="Poll every --interval-s seconds")
    parser.add_argument("--interval-s", type=int, default=300)
    parser.add_argument("--jsonl", default=None)
    parser.add_argument("--all-items", action="store_true", help="Do not filter to configured tokens/MACRO")
    args = parser.parse_args()

    agent = NewsAgent(
        jsonl_path=Path(args.jsonl) if args.jsonl else default_jsonl_path(),
        relevant_only=not args.all_items,
    )
    if args.loop:
        while True:
            result = agent.run_once()
            print(json.dumps(result, indent=2))
            time.sleep(max(30, args.interval_s))
    result = agent.run_once()
    print(json.dumps(result, indent=2))
    preview = result.get("preview") or []
    if preview:
        print("\n--- first 5 (assets) ---")
        for row in preview:
            print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
