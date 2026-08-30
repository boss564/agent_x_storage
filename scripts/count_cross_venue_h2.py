#!/usr/bin/env python3
"""H2 report from cross_venue_slots.jsonl (Pre-Reg connectivity).

Usage:
  PYTHONPATH=. python3 scripts/count_cross_venue_h2.py \\
    --slots path/to/cross_venue_slots.jsonl \\
    --gaps path/to/cross_venue_gaps.jsonl

Without --gaps (and without CROSS_VENUE_GAPS_PATH env): H2=UNVERIFIED, exit 2.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.cross_venue import (  # noqa: E402
    analyze_cross_venue_h2,
    load_jsonl,
)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--slots", type=Path, required=True)
    p.add_argument(
        "--gaps",
        type=Path,
        default=None,
        help="cross_venue_gaps.jsonl — required for H2 verdict (or set CROSS_VENUE_GAPS_PATH)",
    )
    p.add_argument("--min-disturbed", type=int, default=20)
    args = p.parse_args()
    if args.gaps is not None:
        gaps = load_jsonl(args.gaps)
    elif os.environ.get("CROSS_VENUE_GAPS_PATH", "").strip():
        gaps = load_jsonl(Path(os.environ["CROSS_VENUE_GAPS_PATH"]))
    else:
        gaps = None
    report = analyze_cross_venue_h2(
        load_jsonl(args.slots), gaps=gaps, min_disturbed=args.min_disturbed
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if report.get("observer_check") == "NOT_GATED":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
