#!/usr/bin/env python3
"""W-Studie: Null-Lücken aus WORM-SIGNAL Δt belegen; Schreiber-Versagen erkennen.

Retrospektiv (ohne Heartbeat): rekonstruiert Tick-Abstände aus paper_trades.worm.jsonl.
  - Kein beobachtbarer Abstand > gap_dt → null_gaps_proven (H0 Zweig 2)
  - Beobachtbarer Abstand > gap_dt ohne tick_spacing-Zeile → writer_failed
  - Abstand überspannt restart_marker → unbeobachtbar (weder Beleg noch Versagen)

Default-Fensterstart = Dual-Start W (feed-gap-v2 Deploy), nicht RT10-Recovery.

Usage:
  PYTHONPATH=. python3 scripts/audit_feed_gap_worm.py \\
    --worm /data/worm/live/.../paper_trades.worm.jsonl \\
    --gaps /data/audit/feed_gaps.jsonl

  # Optional explizit (identisch zum Default):
  PYTHONPATH=. python3 scripts/audit_feed_gap_worm.py \\
    --worm … --gaps … --window-start 2026-08-29T13:17:46+00:00
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
    FEED_GAP_WINDOW_W_DUAL_START_TS,
    analyze_concordance,
    audit_gap_writer_against_worm,
    load_gaps,
)
from prototypes.raas_paper_trading.paper_edge_sample import load_edges  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--worm", type=Path, required=True)
    p.add_argument("--gaps", type=Path, required=True)
    p.add_argument("--edges", type=Path, default=None)
    p.add_argument("--gap-dt-s", type=float, default=30.0)
    p.add_argument(
        "--window-start",
        default=FEED_GAP_WINDOW_W_DUAL_START_TS,
        help=f"ISO-8601 Dual-Start UTC (default: {FEED_GAP_WINDOW_W_DUAL_START_TS})",
    )
    p.add_argument("--window-end", default=None, help="ISO-8601 window end UTC")
    p.add_argument("--freeze-k", type=int, default=None)
    args = p.parse_args()

    gaps = load_gaps(args.gaps)
    worm_audit = audit_gap_writer_against_worm(
        gaps=gaps,
        worm_path=args.worm,
        gap_dt_s=args.gap_dt_s,
        window_start_ts=args.window_start,
        window_end_ts=args.window_end,
    )

    out: dict = {"worm_audit": worm_audit}

    if args.edges is not None and args.edges.is_file():
        import os

        freeze = args.freeze_k or int(os.environ.get("PAPER_HOLD_SECONDS", "4966"))
        concordance = analyze_concordance(
            gaps=gaps,
            edges=load_edges(args.edges),
            freeze_k=freeze,
            window_start_ts=args.window_start,
            window_end_ts=args.window_end,
            worm_audit=worm_audit,
        )
        out["concordance"] = concordance

    print(json.dumps(out, indent=2, sort_keys=True, default=str))
    summary = worm_audit.get("coverage_summary")
    if summary:
        print(f"# {summary}", file=sys.stderr)

    if worm_audit.get("writer_failed"):
        return 2
    if worm_audit.get("insufficient_coverage"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
