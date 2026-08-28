#!/usr/bin/env python3
"""Replay WORM SIM_FILL tuples under fixed vs dynamic slippage (P3).

Post-processing only — no live loop. Fixed (side, qty, mark_price) per fill;
metrics: slippage_cost_delta, fee_delta (dynamic − fixed).

Usage:
  PYTHONPATH=. python3 scripts/raas_paper_slippage_replay.py
  PYTHONPATH=. python3 scripts/raas_paper_slippage_replay.py --worm-dir logs/worm/paper_runs
  make raas-paper-slippage-replay
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.config_loader import (  # noqa: E402
    PaperTradingSettings,
    config_manifest_hash,
)
from prototypes.raas_paper_trading.replay import (  # noqa: E402
    load_all_fills,
    replay_interpretation,
    replay_slippage_ab,
)
from prototypes.raas_paper_trading.slippage import (  # noqa: E402
    SYNTHETIC_QTY_PER_LEVEL,
    SYNTHETIC_SPREAD_BPS,
)

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"
DEFAULT_AUDIT = _ROOT / "logs" / "worm" / "paper_trading_audit.jsonl"
DEFAULT_PERSIST = _ROOT / "logs" / "worm" / "paper_runs"
DEFAULT_OUT = _ROOT / "exports" / "reports" / "paper_slippage_replay_latest.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WORM fill slippage replay (fixed-tuple A/B)")
    parser.add_argument(
        "--worm",
        action="append",
        default=[],
        help="WORM JSONL file or directory (repeatable)",
    )
    parser.add_argument(
        "--worm-dir",
        type=Path,
        default=DEFAULT_PERSIST,
        help=f"Directory with persisted run worms (default: {DEFAULT_PERSIST})",
    )
    parser.add_argument(
        "--audit",
        type=Path,
        default=DEFAULT_AUDIT,
        help="paper_trading_audit.jsonl for worm_path discovery",
    )
    parser.add_argument(
        "--spread-bps",
        type=float,
        default=SYNTHETIC_SPREAD_BPS,
        help="Synthetic book spread when no depth snapshot in WORM",
    )
    parser.add_argument(
        "--qty-per-level",
        type=float,
        default=SYNTHETIC_QTY_PER_LEVEL,
        help="Synthetic depth per level (base asset units)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="JSON report path",
    )
    args = parser.parse_args(argv)

    print("RaaS Paper Slippage Replay (WORM fixed-tuple A/B)")
    print("=" * 60)

    settings = PaperTradingSettings.from_file()
    fills = load_all_fills(
        worm_paths=args.worm or None,
        worm_dir=args.worm_dir if args.worm_dir.is_dir() else None,
        audit_path=args.audit if args.audit.is_file() else None,
        persist_dir=args.worm_dir if args.audit.is_file() and args.worm_dir.is_dir() else None,
    )

    if not fills:
        print("  WARN  no SIM_FILL tuples found")
        print(f"        persist dir: {args.worm_dir}")
        print(f"        audit:       {args.audit}")
        print("        Run: make raas-paper-trading-smoke  (persists worms to logs/worm/paper_runs/)")
        result = {
            "schema": "raas_paper_slippage_replay_v0",
            "scope": SCOPE,
            "live_execution": False,
            "fill_count": 0,
            "verdict": "RAAS_PAPER_SLIPPAGE_REPLAY_EMPTY",
            "config_hash": config_manifest_hash(),
            "note": "No fills — run paper dry-run first",
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"report: {args.out}")
        print("=" * 60)
        print("VERDICT: RAAS_PAPER_SLIPPAGE_REPLAY_EMPTY")
        return 0

    result = replay_slippage_ab(
        fills,
        settings=settings,
        spread_bps=args.spread_bps,
        qty_per_level=args.qty_per_level,
    )
    result["scope"] = SCOPE
    result["verdict"] = "RAAS_PAPER_SLIPPAGE_REPLAY_PASS"

    m = result["metrics"]
    print(f"fills={result['fill_count']} config_hash={result['config_hash'][:16]}…")
    sb = result.get("synthetic_book", {})
    print(
        f"  book: spread_bps={sb.get('spread_bps')} "
        f"qty_per_level={sb.get('qty_per_level')} "
        f"fills_past_level_1={sb.get('fills_past_level_1')}"
    )
    print(f"  slippage_cost_delta (dyn−fix): {m['slippage_cost_delta_eur']} €")
    print(f"  fee_delta (dyn−fix):           {m['fee_delta_eur']} €")
    for line in result.get("interpretation", replay_interpretation(
        spread_bps=args.spread_bps,
        fallback_percent=settings.fallback_percent,
        qty_per_level=args.qty_per_level,
    )):
        print(f"  · {line}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"report: {args.out}")
    print("=" * 60)
    print("VERDICT: RAAS_PAPER_SLIPPAGE_REPLAY_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
