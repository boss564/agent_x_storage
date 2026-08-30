#!/usr/bin/env python3
"""H0/H1/H_inv/H2 from feed_gaps.jsonl + paper_edges.jsonl (Pre-Reg concordance).

Usage:
  PYTHONPATH=. python3 scripts/count_feed_gap_concordance.py \\
    --gaps ./data/audit/feed_gaps.jsonl --edges ./data/audit/paper_edges.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.feed_gap import (  # noqa: E402
    analyze_concordance,
    load_gaps,
)
from prototypes.raas_paper_trading.paper_edge_sample import load_edges  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gaps", type=Path, required=True)
    p.add_argument("--edges", type=Path, required=True)
    p.add_argument("--freeze-k", type=int, default=None)
    p.add_argument("--max-delta-s", type=float, default=30.0)
    p.add_argument("--window-start", default=None, help="ISO-8601 Dual-Start UTC")
    p.add_argument("--window-end", default=None, help="ISO-8601 window end UTC")
    p.add_argument("--worm", type=Path, default=None, help="WORM for null-gap / writer audit (W-Studie)")
    args = p.parse_args()
    freeze = args.freeze_k
    if freeze is None:
        import os

        freeze = int(os.environ.get("PAPER_HOLD_SECONDS", "4966"))
    gaps = load_gaps(args.gaps)
    worm_audit = None
    if args.worm is not None:
        from prototypes.raas_paper_trading.feed_gap import audit_gap_writer_against_worm

        worm_audit = audit_gap_writer_against_worm(
            gaps=gaps,
            worm_path=args.worm,
            window_start_ts=args.window_start,
            window_end_ts=args.window_end,
        )
    report = analyze_concordance(
        gaps=gaps,
        edges=load_edges(args.edges),
        freeze_k=freeze,
        max_delta_s=args.max_delta_s,
        window_start_ts=args.window_start,
        window_end_ts=args.window_end,
        worm_audit=worm_audit,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
