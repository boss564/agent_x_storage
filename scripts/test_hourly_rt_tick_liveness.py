#!/usr/bin/env python3
"""Hourly RT: paper last_tick_ts vs heartbeat.ts (writer vs feed).

Usage:
  PYTHONPATH=. python3 scripts/test_hourly_rt_tick_liveness.py
  make raas-hourly-rt-tick-smoke
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.raas_hourly_rt_check import paper_tick_liveness  # noqa: E402

_PASS = 0
_FAIL = 0


def _ok(name: str) -> None:
    global _PASS
    _PASS += 1
    print(f"  PASS  {name}")


def _fail(name: str, detail: str) -> None:
    global _FAIL
    _FAIL += 1
    print(f"  FAIL  {name}: {detail}")


def _iso(delta_s: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=delta_s)).isoformat()


def _heartbeat(*, hb_age_s: float, last_tick_age_s: float) -> dict:
    return {
        "source": "heartbeat",
        "fsm_state": "ALIVE",
        "ts": _iso(hb_age_s),
        "gap_start_ts": _iso(hb_age_s),
        "last_tick_ts": _iso(last_tick_age_s),
    }


def test_fresh_state_pass() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "feed_gap_state.json"
        ts = _iso(12)
        state.write_text(json.dumps({"last_tick_ts": ts}), encoding="utf-8")
        out = paper_tick_liveness(
            gaps=[_heartbeat(hb_age_s=10, last_tick_age_s=12)],
            state_path=state,
            max_age_s=300,
        )
        if out["status"] != "PASS" or out["source"] != "feed_gap_state":
            _fail("fresh_state_pass", str(out))
            return
        _ok("fresh_state_pass")


def test_stale_state_fail() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "feed_gap_state.json"
        state.write_text(json.dumps({"last_tick_ts": _iso(7200)}), encoding="utf-8")
        out = paper_tick_liveness(
            gaps=[_heartbeat(hb_age_s=10, last_tick_age_s=12)],
            state_path=state,
            max_age_s=300,
        )
        if out["status"] != "FAIL" or out.get("reason") != "tick_stale":
            _fail("stale_state_fail", str(out))
            return
        _ok("stale_state_fail")


def test_heartbeat_ts_fresh_tick_stale_fail() -> None:
    """09:18 case: writer heartbeat fresh, last_tick_ts frozen."""
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "missing.json"
        out = paper_tick_liveness(
            gaps=[_heartbeat(hb_age_s=10, last_tick_age_s=21600)],
            state_path=state,
            max_age_s=300,
        )
        if out["status"] != "FAIL" or out["source"] != "heartbeat.last_tick_ts":
            _fail("heartbeat_fresh_tick_stale", str(out))
            return
        _ok("heartbeat_fresh_tick_stale")


def test_missing_last_tick_fail() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "feed_gap_state.json"
        state.write_text(json.dumps({"last_tick_ts": None}), encoding="utf-8")
        out = paper_tick_liveness(
            gaps=[{"source": "heartbeat", "ts": _iso(10), "fsm_state": "ALIVE"}],
            state_path=state,
            max_age_s=300,
        )
        if out["status"] != "FAIL" or out.get("reason") != "missing_last_tick_ts":
            _fail("missing_last_tick", str(out))
            return
        _ok("missing_last_tick")


def test_state_beats_stale_heartbeat_snapshot() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "feed_gap_state.json"
        ts = _iso(5)
        state.write_text(json.dumps({"last_tick_ts": ts}), encoding="utf-8")
        out = paper_tick_liveness(
            gaps=[_heartbeat(hb_age_s=3500, last_tick_age_s=3500)],
            state_path=state,
            max_age_s=300,
        )
        if out["status"] != "PASS" or out["source"] != "feed_gap_state":
            _fail("state_beats_heartbeat_snapshot", str(out))
            return
        _ok("state_beats_heartbeat_snapshot")


def main() -> int:
    print("Hourly RT paper-tick liveness")
    test_fresh_state_pass()
    test_stale_state_fail()
    test_heartbeat_ts_fresh_tick_stale_fail()
    test_missing_last_tick_fail()
    test_state_beats_stale_heartbeat_snapshot()
    print(f"{_PASS}/{_PASS + _FAIL} passed")
    if _FAIL:
        print("HOURLY_RT_TICK_LIVENESS_FAIL")
        return 1
    print("HOURLY_RT_TICK_LIVENESS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
