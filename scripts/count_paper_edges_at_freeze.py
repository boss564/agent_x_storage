#!/usr/bin/env python3
"""Count B2-eligible paper edges at frozen k (not raw SELL count).

Usage:
  PYTHONPATH=. python3 scripts/count_paper_edges_at_freeze.py \\
    --edges /data/audit/paper_edges.jsonl --freeze-k 4966
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.paper_edge_sample import (  # noqa: E402
    DEFAULT_FREEZE_K,
    DEFAULT_HOLD_CLEAN_MAX_DELTA_S,
    count_eligible,
    load_edges,
)


def main() -> int:
    p = argparse.ArgumentParser(description="B2 eligible edge counter (freeze-k only)")
    p.add_argument("--edges", type=Path, required=True)
    p.add_argument("--freeze-k", type=int, default=DEFAULT_FREEZE_K)
    p.add_argument("--max-delta-s", type=float, default=DEFAULT_HOLD_CLEAN_MAX_DELTA_S)
    args = p.parse_args()
    edges = load_edges(args.edges)
    report = count_eligible(edges, freeze_k=args.freeze_k, max_delta_s=args.max_delta_s)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
