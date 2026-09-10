#!/usr/bin/env python3
"""Hourly RT verification — W_xv heartbeats, Feed-Gap (W), AstroCore hook.

Designed to run inside the regime-swarm pod (no kubectl/make required).
Typical schedule: CronJob at minute 14 each hour (UTC).

Paper-tick liveness uses feed_gap_state.last_tick_ts (per tick), not heartbeat.ts.
A live writer heartbeat with a frozen last_tick_ts is FAIL (feed dead, check green was the bug).

Usage:
    python3 scripts/raas_hourly_rt_check.py
    python3 scripts/raas_hourly_rt_check.py --json --append-log
    RAAS_AUDIT_DIR=/data/audit python3 scripts/raas_hourly_rt_check.py --max-age-s 300
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.cross_venue import load_jsonl, writer_liveness_status as xv_liveness
from prototypes.raas_paper_trading.feed_gap import (
    feed_gap_paths_from_env,
    load_gaps,
    writer_liveness_status as feed_liveness,
)
from prototypes.raas_paper_trading.paper_exit import parse_ts_unix


def _audit_dir() -> Path:
    return Path(os.environ.get("RAAS_AUDIT_DIR", "/data/audit"))


def _cross_venue_path(audit: Path) -> Path:
    env = os.environ.get("CROSS_VENUE_GAPS_PATH")
    return Path(env) if env else audit / "cross_venue_gaps.jsonl"


def _feed_gaps_path(audit: Path) -> Path:
    env = os.environ.get("PAPER_FEED_GAPS_PATH")
    return Path(env) if env else audit / "feed_gaps.jsonl"


def _feed_gap_state_path() -> Path:
    env = os.environ.get("PAPER_FEED_GAP_STATE_PATH")
    if env:
        return Path(env)
    return feed_gap_paths_from_env()["state_path"]


def _last_heartbeat_last_tick_ts(gaps: List[Dict[str, Any]]) -> Optional[str]:
    """Paper tick time snapped on the last heartbeat — not heartbeat.ts."""
    last: Optional[str] = None
    for row in gaps:
        if str(row.get("source") or "") != "heartbeat":
            continue
        raw = row.get("last_tick_ts")
        if raw:
            last = str(raw)
    return last


def _state_last_tick_ts(state_path: Path) -> Optional[str]:
    if not state_path.is_file():
        return None
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    ts = raw.get("last_tick_ts")
    return str(ts) if ts else None


def paper_tick_liveness(
    *,
    gaps: List[Dict[str, Any]],
    state_path: Path,
    max_age_s: float,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Fail when paper ticks are stale — independent of writer heartbeat.ts.

    Prefer feed_gap_state.json (updated per tick). Heartbeat.last_tick_ts is a
    snapshot at emit time; using heartbeat.ts would stay green with a dead feed.
    """
    now_u = time.time() if now is None else now
    state_ts = _state_last_tick_ts(state_path)
    hb_tick_ts = _last_heartbeat_last_tick_ts(gaps)
    if state_ts:
        last_tick_ts, source = state_ts, "feed_gap_state"
    else:
        last_tick_ts, source = hb_tick_ts, "heartbeat.last_tick_ts"

    if not last_tick_ts:
        return {
            "name": "paper_tick",
            "status": "FAIL",
            "reason": "missing_last_tick_ts",
            "age_s": None,
            "last_tick_ts": None,
            "source": source if hb_tick_ts or state_path.is_file() else "none",
            "max_age_s": max_age_s,
        }
    try:
        age = now_u - parse_ts_unix(last_tick_ts)
    except ValueError:
        return {
            "name": "paper_tick",
            "status": "FAIL",
            "reason": "unparseable_last_tick_ts",
            "age_s": None,
            "last_tick_ts": last_tick_ts,
            "source": source,
            "max_age_s": max_age_s,
        }
    ok = age <= max_age_s
    return {
        "name": "paper_tick",
        "status": "PASS" if ok else "FAIL",
        "reason": None if ok else "tick_stale",
        "age_s": round(age, 3),
        "last_tick_ts": last_tick_ts,
        "source": source,
        "max_age_s": max_age_s,
    }


def _last_heartbeat_row(gaps: List[Dict[str, Any]], *, venue: Optional[str] = None) -> Optional[Dict[str, Any]]:
    last: Optional[Dict[str, Any]] = None
    for row in gaps:
        if str(row.get("source") or "") != "heartbeat":
            continue
        if venue is not None and str(row.get("venue") or "") != venue:
            continue
        last = row
    return last


def _last_feed_alive_row(gaps: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    last: Optional[Dict[str, Any]] = None
    for row in gaps:
        if str(row.get("source") or "") != "heartbeat":
            continue
        if str(row.get("fsm_state") or "") == "ALIVE":
            last = row
    return last


def _probe_astrocore(audit: Path) -> Dict[str, Any]:
    enabled = os.environ.get("ASTROCORE_HOOK_ENABLED", "").strip().lower() in ("1", "true", "yes")
    if not enabled:
        return {"status": "SKIPPED", "reason": "ASTROCORE_HOOK_ENABLED!=true"}

    try:
        from agents_b2g.astrocore_hook import AstrocoreHookClient, parse_gap_logs

        lookback = int(os.environ.get("ASTROCORE_NEO4J_LOOKBACK_DAYS", "7"))
        data_source = os.environ.get("ASTROCORE_DATA_SOURCE", "worm")
        _, meta = parse_gap_logs(audit, lookback_days=lookback)
        client = AstrocoreHookClient(data_source=data_source, audit_dir=str(audit), strict=False)
        env = client.analyze_liquidations()
        prov = str(env.get("data_provenance") or "")
        verdict = str(env.get("verdict") or "")
        events = int(env.get("stats", {}).get("events_read") or 0)
        ok = prov in ("worm", "gap_synthetic", "synthetic", "neo4j")
        if prov == "worm" and verdict == "CLUSTER_DETECTED":
            ok = False
        return {
            "status": "PASS" if ok else "FAIL",
            "data_provenance": prov,
            "verdict": verdict,
            "events_read": events,
            "source_files": meta.get("source_files", []),
        }
    except Exception as exc:  # noqa: BLE001 — diagnostic probe must not crash the job
        return {"status": "FAIL", "reason": str(exc)[:240]}


def run_check(
    *,
    max_age_s: float,
    probe_astrocore: bool,
    paper_tick_max_age_s: float = 300.0,
) -> Dict[str, Any]:
    audit = _audit_dir()
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    checks: List[Dict[str, Any]] = []
    failures: List[str] = []

    xv_path = _cross_venue_path(audit)
    feed_path = _feed_gaps_path(audit)

    xv_gaps: List[Dict[str, Any]] = []
    if xv_path.is_file():
        xv_gaps = load_jsonl(xv_path)

    for venue in ("v1", "v2"):
        live = xv_liveness(gaps=xv_gaps, venue=venue, heartbeat_stale_s=max_age_s)
        hb = _last_heartbeat_row(xv_gaps, venue=venue)
        entry = {
            "name": f"cross_venue_{venue}",
            "status": live.get("status"),
            "age_s": live.get("age_s"),
            "last_ts": (hb or {}).get("ts"),
            "path": str(xv_path),
        }
        checks.append(entry)
        if live.get("status") != "ACTIVE":
            failures.append(f"cross_venue_{venue}={live.get('status')}")

    feed_gaps = load_gaps(feed_path) if feed_path.is_file() else []
    feed_live = feed_liveness(gaps=feed_gaps, heartbeat_stale_s=max_age_s)
    feed_hb = _last_feed_alive_row(feed_gaps)
    feed_entry = {
        "name": "feed_gap_w",
        "status": feed_live.get("status"),
        "age_s": feed_live.get("age_s"),
        "last_tick_ts": (feed_hb or {}).get("ts"),
        "fsm_state": (feed_hb or {}).get("fsm_state"),
        "path": str(feed_path),
    }
    checks.append(feed_entry)
    if feed_live.get("status") != "ACTIVE":
        failures.append(f"feed_gap_w={feed_live.get('status')}")

    tick = paper_tick_liveness(
        gaps=feed_gaps,
        state_path=_feed_gap_state_path(),
        max_age_s=paper_tick_max_age_s,
    )
    checks.append(tick)
    if tick.get("status") != "PASS":
        failures.append(f"paper_tick={tick.get('reason') or tick.get('status')}")

    astro: Optional[Dict[str, Any]] = None
    if probe_astrocore:
        astro = _probe_astrocore(audit)
        checks.append({"name": "astrocore_hook", **astro})
        if astro.get("status") == "FAIL":
            failures.append("astrocore_hook=FAIL")

    overall = "PASS" if not failures else "FAIL"
    return {
        "ts": now_iso,
        "unix_ts": round(time.time(), 3),
        "audit_dir": str(audit),
        "max_age_s": max_age_s,
        "paper_tick_max_age_s": paper_tick_max_age_s,
        "status": overall,
        "failures": failures,
        "checks": checks,
        "astrocore": astro,
    }


def _print_human(report: Dict[str, Any]) -> None:
    print(f"Hourly RT check @ {report['ts']} → {report['status']}")
    for chk in report.get("checks", []):
        name = chk.get("name", "?")
        st = chk.get("status", "?")
        age = chk.get("age_s")
        age_s = f" age={age}s" if age is not None else ""
        extra = ""
        if name.startswith("cross_venue"):
            extra = f" ts={chk.get('last_ts')}"
        elif name == "feed_gap_w":
            extra = f" fsm={chk.get('fsm_state')} ts={chk.get('last_tick_ts')}"
        elif name == "paper_tick":
            extra = (
                f" last_tick={chk.get('last_tick_ts')} src={chk.get('source')}"
                f" reason={chk.get('reason')}"
            )
        elif name == "astrocore_hook" and st == "PASS":
            extra = (
                f" prov={chk.get('data_provenance')} verdict={chk.get('verdict')}"
                f" events={chk.get('events_read')}"
            )
        print(f"  {name}: {st}{age_s}{extra}")
    if report.get("failures"):
        print("  failures:", ", ".join(report["failures"]))


def _append_log(report: Dict[str, Any], log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(report, separators=(",", ":"), ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Hourly W_xv + Feed-Gap + AstroCore RT check")
    parser.add_argument("--json", action="store_true", help="JSON stdout only")
    parser.add_argument("--quiet", action="store_true", help="No human output (implies --json for failures)")
    parser.add_argument(
        "--max-age-s",
        type=float,
        default=float(os.environ.get("HOURLY_RT_MAX_AGE_S", "3900")),
        help="Max heartbeat age in seconds (default 3900 ≈ hourly :14 cadence + slack)",
    )
    parser.add_argument(
        "--append-log",
        action="store_true",
        help="Append JSONL line to RAAS_AUDIT_DIR/hourly_rt_checks.jsonl",
    )
    parser.add_argument(
        "--no-astrocore",
        action="store_true",
        help="Skip AstroCore hook probe",
    )
    parser.add_argument(
        "--paper-tick-max-age-s",
        type=float,
        default=float(os.environ.get("HOURLY_RT_PAPER_TICK_MAX_AGE_S", "300")),
        help="Max paper last_tick_ts age in seconds (default 300; independent of heartbeat.ts)",
    )
    parser.add_argument(
        "--alert-on-fail",
        action="store_true",
        help="Send ops alert on FAIL (also when RAAS_ALERT_ENABLED=true)",
    )
    args = parser.parse_args()

    report = run_check(
        max_age_s=args.max_age_s,
        probe_astrocore=not args.no_astrocore,
        paper_tick_max_age_s=args.paper_tick_max_age_s,
    )

    if args.append_log:
        log_path = _audit_dir() / "hourly_rt_checks.jsonl"
        _append_log(report, log_path)

    if report["status"] == "FAIL":
        try:
            from scripts.raas_alert import maybe_alert_rt_failure

            maybe_alert_rt_failure(report, force=args.alert_on_fail)
        except Exception as exc:  # noqa: BLE001 — alert must not mask check exit code
            if not args.quiet and not args.json:
                print(f"  alert_error: {exc}", file=sys.stderr)

    if args.json or args.quiet:
        print(json.dumps(report, separators=(",", ":")))
    else:
        _print_human(report)

    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
