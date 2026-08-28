#!/usr/bin/env python3
"""Long-running paper collection — live ticks + depth at fill (no order send).

Usage:
  PYTHONPATH=. python3 scripts/raas_paper_collect.py --duration-s 86400
  PYTHONPATH=. python3 scripts/raas_paper_collect.py --depth-mode worm --interval-s 60
  make raas-paper-collect
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.config_loader import PaperTradingSettings  # noqa: E402
from prototypes.raas_paper_trading.depth_snapshot import (  # noqa: E402
    make_live_depth_fetcher,
    make_worm_depth_fetcher,
)
from prototypes.raas_paper_trading.feed import fetch_binance_ticker  # noqa: E402
from prototypes.raas_paper_trading.ledger import ledger_from_config  # noqa: E402
from prototypes.raas_paper_trading.runner import PaperTradingRunner  # noqa: E402

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"
PERSIST_ROOT = _ROOT / "logs" / "worm" / "paper_runs"
MANIFEST = _ROOT / "logs" / "worm" / "paper_collect_manifest.jsonl"
EVENTS = _ROOT / "logs" / "worm" / "paper_collect_events.jsonl"
PID_FILE = _ROOT / "logs" / "paper_collect.pid"

_stop = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _on_signal(_signum: int, _frame: object) -> None:
    global _stop
    _stop = True


def _persist_worm(run_id: str, worm_path: str) -> Optional[Path]:
    src = Path(worm_path)
    if not src.is_file():
        return None
    dest = PERSIST_ROOT / run_id / "paper_trades.worm.jsonl"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest


def _append_manifest(row: Dict[str, Any]) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def _log_event(row: Dict[str, Any]) -> None:
    EVENTS.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps({**row, "ts": _now()}, default=str) + "\n")


def _git_head() -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=_ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def _make_runner(
    *,
    settings: PaperTradingSettings,
    run_id: str,
    symbol: str,
    break_floor: float,
    depth_mode: str,
) -> PaperTradingRunner:
    if depth_mode == "worm":
        fetcher = make_worm_depth_fetcher(Path(settings.depth_worm_path))
    else:
        fetcher = make_live_depth_fetcher(
            limit=settings.depth_rest_limit,
            fallback_on_error=True,
        )
    data_root = _ROOT / "data" / "raas"
    os.environ["RAAS_DATA_ROOT"] = str(data_root)
    worm_run_id = f"{run_id}-{symbol.lower()}"
    return PaperTradingRunner(
        tenant_id="paper_collect",
        run_id=worm_run_id,
        ledger=ledger_from_config(settings),
        worm=None,
        break_price_below=break_floor,
        shadow_notional_eur=settings.notional_for(symbol),
        attach_orderbook=settings.attach_orderbook,
        depth_fetcher=fetcher,
        volatility_profile=settings.volatility_profile_for(symbol),
        pair_manifest_hash=settings.pair_manifest_hash_for(symbol),
        config_hash=settings.config_hash,
    )


def _build_manifest(
    *,
    settings: PaperTradingSettings,
    run_id: str,
    depth_mode: str,
    tick_total: int,
    fill_count: int,
    tick_errors: int,
    started: float,
    runners: Dict[str, PaperTradingRunner],
    last_prices: Dict[str, float],
    status: str,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    summaries: Dict[str, Dict[str, Any]] = {}
    for sym, runner in runners.items():
        mark = Decimal(str(last_prices.get(sym, 1.0)))
        snap = runner.ledger.snapshot(mark)
        persisted = _persist_worm(runner.run_id, str(runner.worm.path))
        summaries[sym] = {
            "run_id": runner.run_id,
            "worm_path": str(runner.worm.path),
            "persisted_path": str(persisted) if persisted else None,
            "fills": len(runner.ledger.fills),
            "equity_eur": snap["equity_eur"],
            "pair_manifest_hash": settings.pair_manifest_hash_for(sym),
            "volatility_profile": settings.volatility_profile_for(sym),
        }

    manifest: Dict[str, Any] = {
        "schema": "raas_paper_collect_v1",
        "scope": SCOPE,
        "live_execution": False,
        "order_send": False,
        "not_investment_advice": True,
        "run_id": run_id,
        "status": status,
        "depth_mode": depth_mode,
        "tick_total": tick_total,
        "fill_count": fill_count,
        "tick_errors": tick_errors,
        "duration_s": round(time.monotonic() - started, 2),
        "symbols": summaries,
        "config_hash": settings.config_hash,
        "git_commit": _git_head(),
        "pair_manifest_note": (
            "SIM_FILL rows carry pair_manifest_hash + config_hash at write time; "
            "git_commit references code revision at collect start"
        ),
        "ts": _now(),
    }
    if error:
        manifest["error"] = error
    return manifest


def collect(
    *,
    settings: PaperTradingSettings,
    symbols: list[str],
    interval_s: float,
    duration_s: float,
    max_ticks: Optional[int],
    depth_mode: str,
    break_pct: float,
    run_id: str,
) -> Dict[str, Any]:
    global _stop
    runners: Dict[str, PaperTradingRunner] = {}
    floors: Dict[str, float] = {}
    last_prices: Dict[str, float] = {}
    started = time.monotonic()
    tick_total = 0
    fill_count = 0
    tick_errors = 0

    _log_event(
        {
            "action": "COLLECT_START",
            "run_id": run_id,
            "depth_mode": depth_mode,
            "symbols": symbols,
            "config_hash": settings.config_hash,
            "git_commit": _git_head(),
        }
    )

    try:
        while not _stop:
            elapsed = time.monotonic() - started
            if elapsed >= duration_s:
                break
            if max_ticks is not None and tick_total >= max_ticks:
                break

            for sym in symbols:
                if _stop:
                    break
                try:
                    tick = fetch_binance_ticker(sym)
                except Exception as exc:  # noqa: BLE001
                    tick_errors += 1
                    _log_event(
                        {
                            "action": "TICK_ERROR",
                            "run_id": run_id,
                            "symbol": sym,
                            "error": str(exc),
                        }
                    )
                    print(f"TICK_ERROR {sym}: {exc}", flush=True)
                    continue
                last_prices[sym] = float(tick.price)
                if sym not in runners:
                    floors[sym] = tick.price * break_pct
                    runners[sym] = _make_runner(
                        settings=settings,
                        run_id=run_id,
                        symbol=sym,
                        break_floor=floors[sym],
                        depth_mode=depth_mode,
                    )
                result = runners[sym].on_tick(tick)
                tick_total += 1
                if result.get("fill"):
                    fill_count += 1

            if tick_total > 0 and tick_total % max(1, len(symbols)) == 0:
                print(
                    f"heartbeat ticks={tick_total} fills={fill_count} "
                    f"errors={tick_errors} elapsed_s={round(time.monotonic() - started, 0)}",
                    flush=True,
                )

            if _stop or (max_ticks is not None and tick_total >= max_ticks):
                break
            if time.monotonic() - started >= duration_s:
                break
            time.sleep(max(1.0, interval_s))

        status = "complete" if not _stop else "stopped"
        manifest = _build_manifest(
            settings=settings,
            run_id=run_id,
            depth_mode=depth_mode,
            tick_total=tick_total,
            fill_count=fill_count,
            tick_errors=tick_errors,
            started=started,
            runners=runners,
            last_prices=last_prices,
            status=status,
        )
        _append_manifest(manifest)
        _log_event({"action": "COLLECT_END", "run_id": run_id, "status": status})
        return manifest
    except Exception as exc:  # noqa: BLE001
        manifest = _build_manifest(
            settings=settings,
            run_id=run_id,
            depth_mode=depth_mode,
            tick_total=tick_total,
            fill_count=fill_count,
            tick_errors=tick_errors,
            started=started,
            runners=runners,
            last_prices=last_prices,
            status="aborted",
            error=str(exc),
        )
        _append_manifest(manifest)
        _log_event(
            {
                "action": "COLLECT_ABORT",
                "run_id": run_id,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
        print(f"COLLECT_ABORT: {exc}", flush=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live paper collection loop (no order send)")
    parser.add_argument("--run-id", default=None, help="Collection run id (default: collect-UTC)")
    parser.add_argument("--duration-s", type=float, default=86400.0, help="Max runtime (default 24h)")
    parser.add_argument("--interval-s", type=float, default=None, help="Tick interval (default: config)")
    parser.add_argument("--max-ticks", type=int, default=None, help="Stop after N ticks (all symbols)")
    parser.add_argument(
        "--depth-mode",
        choices=("live", "worm"),
        default="live",
        help="live=fetch at fill; worm=ingest WORM (up to interval_s stale)",
    )
    parser.add_argument(
        "--break-pct",
        type=float,
        default=0.92,
        help="Sell trigger floor as fraction of first seen price",
    )
    parser.add_argument("--symbol", action="append", default=[])
    args = parser.parse_args(argv)

    settings = PaperTradingSettings.from_file()
    symbols = [s.upper() for s in (args.symbol or list(settings.depth_symbols))]
    interval_s = args.interval_s if args.interval_s is not None else float(settings.depth_interval_s)
    run_id = args.run_id or f"collect-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()) + "\n", encoding="utf-8")

    print("RaaS Paper Collect (live_execution=false)")
    print("=" * 60)
    print(f"run_id={run_id} depth_mode={args.depth_mode} interval_s={interval_s}")
    print(f"symbols={symbols} duration_s={args.duration_s} max_ticks={args.max_ticks}")
    print(f"git_commit={_git_head()} config_hash={settings.config_hash[:16]}…")

    try:
        manifest = collect(
            settings=settings,
            symbols=symbols,
            interval_s=interval_s,
            duration_s=args.duration_s,
            max_ticks=args.max_ticks,
            depth_mode=args.depth_mode,
            break_pct=args.break_pct,
            run_id=run_id,
        )
    finally:
        if PID_FILE.is_file():
            PID_FILE.unlink(missing_ok=True)

    print(f"ticks={manifest['tick_total']} fills={manifest['fill_count']}")
    for sym, info in manifest["symbols"].items():
        print(f"  {sym}: fills={info['fills']} worm={info.get('persisted_path')}")
    print(f"manifest: {MANIFEST}")
    print("=" * 60)
    print("VERDICT: RAAS_PAPER_COLLECT_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
