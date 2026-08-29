#!/usr/bin/env python3
"""Calibrate PAPER_HOLD_SECONDS from live paper WORM (Option B, pre-reg freeze).

Usage:
  PYTHONPATH=. python3 scripts/calibrate_paper_hold.py \\
    --worm /data/worm/live/live/paper/runs/ethusdt/paper_trades.worm.jsonl

  # From host after kubectl cp:
  PYTHONPATH=. python3 scripts/calibrate_paper_hold.py --worm ./data/worm/.../paper_trades.worm.jsonl \\
    --print-freeze
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.position_sizing.hold_calibration import (  # noqa: E402
    DEFAULT_GAP_DT_S,
    DEFAULT_SUBWINDOWS,
    TARGET_ABS_RETURN,
    calibrate_hold_from_worm,
    render_freeze_markdown,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Option B hold-horizon calibration from WORM")
    p.add_argument("--worm", required=True, type=Path, help="Path to paper_trades.worm.jsonl")
    p.add_argument("--gap-dt-s", type=float, default=DEFAULT_GAP_DT_S, help="Exclude returns with dt > this (s)")
    p.add_argument("--subwindows", type=int, default=DEFAULT_SUBWINDOWS)
    p.add_argument("--target-abs-return", type=float, default=TARGET_ABS_RETURN)
    p.add_argument(
        "--bar-seconds",
        type=float,
        default=None,
        help="Resample to last-price bars of this width (e.g. 1 for 1s bars). Default: trade ticks.",
    )
    p.add_argument("--print-freeze", action="store_true", help="Print §7 markdown table")
    p.add_argument("--json-out", type=Path, default=None, help="Write full JSON result")
    args = p.parse_args()

    if not args.worm.is_file():
        print(f"FAIL worm not found: {args.worm}", file=sys.stderr)
        return 1

    result = calibrate_hold_from_worm(
        args.worm,
        gap_dt_s=args.gap_dt_s,
        n_subwindows=args.subwindows,
        target_abs_return=args.target_abs_return,
        bar_seconds=args.bar_seconds,
    )
    payload = result.to_dict()
    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.print_freeze:
        print("\n## §7 freeze draft\n")
        print(render_freeze_markdown(result))
        print(result.anti_harking_note)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if result.recommended_hold_seconds is None:
        print("WARN: insufficient data for hold recommendation", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
