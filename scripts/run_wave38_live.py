#!/usr/bin/env python3
"""Run Wave 38 first --live cycle (3d-ix).

Usage:
  python3 scripts/run_wave38_live.py --freeze-only
  python3 scripts/run_wave38_live.py
  python3 scripts/run_wave38_live.py --mev-stride 200 --mev-max-blocks 4000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents_b2g.diagnostic.wave38_live_pipeline import Wave38LivePipeline  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Wave 38 --live cycle (3d-ix)")
    parser.add_argument("--user-id", default="wave38")
    parser.add_argument("--job-id", default="live-first")
    parser.add_argument("--freeze-only", action="store_true")
    parser.add_argument("--force-freeze", action="store_true")
    parser.add_argument("--mev-stride", type=int, default=120)
    parser.add_argument("--mev-max-blocks", type=int, default=4000)
    parser.add_argument(
        "--capture-tail-days",
        type=int,
        default=10,
        help="First-cycle: capture last N days of frozen window (default 10). "
        "0 = full frozen 90d (hours).",
    )
    parser.add_argument(
        "--mev-full",
        action="store_true",
        help="Do not cap MEV subsample (very slow)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse existing SQLite/checkpoint (skip RPC capture)",
    )
    parser.add_argument(
        "--capture-resume",
        action="store_true",
        help="Resume in-progress capture from checkpoint (or bootstrap target)",
    )
    parser.add_argument(
        "--capture-resume-from-target",
        type=int,
        default=None,
        metavar="N",
        help="1-based log target index when no checkpoint exists (e.g. 16)",
    )
    parser.add_argument(
        "--require-etherscan",
        action="store_true",
        help="Fail if ETHERSCAN_API_KEY missing (ethereum getLogs uses Etherscan-first)",
    )
    args = parser.parse_args()

    pipe = Wave38LivePipeline(user_id=args.user_id)
    window = pipe.freeze_window(job_id=args.job_id, force=args.force_freeze)
    print(
        json.dumps(
            {
                "frozen": True,
                "window_start_utc": window.window_start_utc,
                "window_end_utc": window.window_end_utc,
                "n_bins": window.n_bins,
                "seed": window.seed,
            },
            indent=2,
        ),
        flush=True,
    )
    if args.freeze_only:
        return 0

    mev_max = None if args.mev_full else args.mev_max_blocks
    tail = None if args.capture_tail_days == 0 else args.capture_tail_days
    ingest = None
    if args.resume:
        from agents_b2g.diagnostic.live_ingestion import rebuild_ingest_from_sqlite

        ingest = rebuild_ingest_from_sqlite(
            window, user_id=args.user_id, job_id=args.job_id
        )
        print(
            json.dumps(
                {
                    "resume": True,
                    "n_events": ingest.n_events,
                    "n_tx": ingest.n_transactions,
                    "n_bins": ingest.n_bins,
                },
                indent=2,
            ),
            flush=True,
        )
    result = pipe.run_live(
        job_id=args.job_id,
        mev_stride=args.mev_stride,
        mev_max_blocks=mev_max,
        capture_tail_days=tail,
        capture_resume=args.capture_resume,
        capture_resume_from_target=args.capture_resume_from_target,
        require_etherscan=args.require_etherscan,
        skip_capture=bool(args.resume),
        ingest_result=ingest,
    )
    print(json.dumps(result, indent=2, default=str), flush=True)
    return 0 if result.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
