#!/usr/bin/env python3
"""Recover stuck paper RT after crash/OOM: IDLE reset + WORM RESTART_MARKER + feed gap marker.

Usage (cluster paths):
  PYTHONPATH=. python3 scripts/recover_regime_swarm_rt_abort.py \\
    --position /data/state/paper_position.json \\
    --worm-root /data/worm/live \\
    --gaps /data/audit/feed_gaps.jsonl \\
    --gap-state /data/state/feed_gap_state.json \\
    --reason oom_recovery
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.feed_gap import FeedGapMonitor  # noqa: E402
from prototypes.raas_paper_trading.paper_exit import PaperPositionStore, PositionState  # noqa: E402
from prototypes.raas_paper_trading.worm_log import PaperWormLog  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--position",
        type=Path,
        default=Path(os.environ.get("PAPER_POSITION_STATE_PATH", "/data/state/paper_position.json")),
    )
    p.add_argument(
        "--worm-root",
        type=Path,
        default=Path(os.environ.get("LIVE_FEED_WORM_DIR", "/data/worm/live")),
    )
    p.add_argument(
        "--symbol",
        default=os.environ.get("LIVE_FEED_SYMBOL", "ETHUSDT"),
    )
    p.add_argument(
        "--gaps",
        type=Path,
        default=Path(os.environ.get("PAPER_FEED_GAPS_PATH", "/data/audit/feed_gaps.jsonl")),
    )
    p.add_argument(
        "--gap-state",
        type=Path,
        default=Path(os.environ.get("PAPER_FEED_GAP_STATE_PATH", "/data/state/feed_gap_state.json")),
    )
    p.add_argument("--reason", default="oom_recovery")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    store = PaperPositionStore(path=args.position)
    store.load()
    prev = {
        "state": store.state,
        "entry_signal_id": store.entry_signal_id,
        "entry_tick_ts": store.entry_tick_ts,
        "entry_price": store.entry_price,
    }

    if store.state == PositionState.IDLE.value:
        print(json.dumps({"status": "noop", "message": "already IDLE", "position": prev}, indent=2))
        return 0

    rt_n = None
    edges_path = Path(os.environ.get("PAPER_EDGES_PATH", "/data/audit/paper_edges.jsonl"))
    if edges_path.is_file():
        rt_n = sum(1 for ln in edges_path.read_text(encoding="utf-8").splitlines() if ln.strip()) + 1

    worm_row = {
        "action": "RESTART_MARKER",
        "symbol": args.symbol.upper(),
        "reason": args.reason,
        "aborted_round_trip": rt_n,
        "prior_state": prev["state"],
        "entry_signal_id": prev["entry_signal_id"],
        "entry_tick_ts": prev["entry_tick_ts"],
        "entry_price": prev["entry_price"],
        "recovery_ts": _now(),
        "diagnostic_only": True,
    }

    report = {
        "status": "recover",
        "prior": prev,
        "aborted_round_trip": rt_n,
        "worm_action": "RESTART_MARKER",
        "dry_run": args.dry_run,
    }

    if args.dry_run:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    worm = PaperWormLog(
        tenant_id="live",
        run_id=args.symbol.lower(),
        data_root=args.worm_root,
    )
    appended = worm.append(worm_row)
    report["worm_hash"] = appended.get("hash")

    store.set_idle()
    report["position_after"] = PositionState.IDLE.value

    gap_dt = float(os.environ.get("PAPER_EXIT_GAP_DT_S", "30"))
    mon = FeedGapMonitor.from_paths(
        gaps_path=args.gaps,
        state_path=args.gap_state,
        gap_dt_s=gap_dt,
        symbol=args.symbol,
        emit_restart_marker=True,
    )
    marker = mon.emit_restart_marker()
    if marker:
        report["feed_gap_restart_marker"] = marker.get("source")

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
