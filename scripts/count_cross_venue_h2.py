#!/usr/bin/env python3
"""H2 report from cross_venue_slots.jsonl (Pre-Reg connectivity).

Usage:
  PYTHONPATH=. python3 scripts/count_cross_venue_h2.py --slots path/to/cross_venue_slots.jsonl
"""
from __future__ import annotations

import argparse
import json
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
    p.add_argument("--min-disturbed", type=int, default=20)
    args = p.parse_args()
    report = analyze_cross_venue_h2(
        load_jsonl(args.slots), min_disturbed=args.min_disturbed
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
