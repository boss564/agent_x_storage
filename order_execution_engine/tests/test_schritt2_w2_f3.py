"""S2-W2: F3 instance_id/cycle_seq + heartbeat + derived streak (GP-S2-3/4/5)."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from order_execution_engine.event_log import JsonlEventLog, iter_events
from order_execution_engine.probe_f3 import (
    PROBE_WATCHDOG_S,
    detect_cycle_gaps,
    heartbeat_stale,
    load_or_birth_identity,
    next_cycle,
    report_gap_findings,
    streak_wall_s_from_events,
    write_heartbeat,
)


def test_w2_probe_watchdog_constant() -> None:
    assert PROBE_WATCHDOG_S >= 12 * 60
    assert PROBE_WATCHDOG_S >= 13 * 60
    print("OK test_w2_probe_watchdog_constant")


def test_w2_a_b4_cycle_seq_and_gap() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        log_dir = Path(tmp)
        elog_path = log_dir / "events.jsonl"
        ident0 = load_or_birth_identity(log_dir)
        iid = ident0["instance_id"]
        for _ in range(3):
            ident = next_cycle(log_dir)
            assert ident["instance_id"] == iid
            elog = JsonlEventLog(
                elog_path,
                producer="probe",
                instance_id=ident["instance_id"],
                cycle_seq=int(ident["cycle_seq"]),
            )
            elog.emit("cycle_start")
            elog.emit("cycle_end", books_ok_full=True)
        events = iter_events(elog_path)
        seqs = [e["cycle_seq"] for e in events if e["event_type"] == "cycle_start"]
        assert seqs == [1, 2, 3]
        assert report_gap_findings(events)["ok"] is True

        # Delete seq=2 lines → Report recognizes gap (A-B4).
        kept = [
            e for e in events
            if not (e.get("cycle_seq") == 2)
        ]
        elog_path.write_text(
            "".join(json.dumps(e, sort_keys=True) + "\n" for e in kept),
            encoding="utf-8",
        )
        gaps = detect_cycle_gaps(iter_events(elog_path))
        assert any(
            g.get("kind") == "missing_cycle_seq" and g.get("cycle_seq") == 2
            for g in gaps
        ), gaps
        print("OK test_w2_a_b4_cycle_seq_and_gap")


def test_w2_restart_new_instance_seq_resets() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        log_dir = Path(tmp)
        a = next_cycle(log_dir)
        # Simulate new process: rewrite state with foreign pid.
        state = json.loads((log_dir / "night_probe.cycle_state.json").read_text())
        state["pid"] = state["pid"] + 99999
        (log_dir / "night_probe.cycle_state.json").write_text(
            json.dumps(state), encoding="utf-8",
        )
        b = load_or_birth_identity(log_dir)
        assert b["instance_id"] != a["instance_id"]
        assert int(b["cycle_seq"]) == 0
        c = next_cycle(log_dir)
        assert c["instance_id"] == b["instance_id"]
        assert int(c["cycle_seq"]) == 1
        print("OK test_w2_restart_new_instance_seq_resets")


def test_w2_a_b2_streak_from_event_log_not_baked() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        t0 = time.time()
        rows = [
            {
                "event_type": "cycle_end",
                "books_ok_full": True,
                "wall_ts": t0,
                "ts_mono": 1.0,
                "producer": "probe",
            },
            {
                "event_type": "cycle_end",
                "books_ok_full": True,
                "wall_ts": t0 + 300,
                "ts_mono": 2.0,
                "producer": "probe",
            },
            {
                "event_type": "cycle_end",
                "books_ok_full": True,
                "wall_ts": t0 + 600,
                "ts_mono": 3.0,
                "producer": "probe",
            },
        ]
        path.write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows),
            encoding="utf-8",
        )
        events = iter_events(path)
        assert all("streak_min" not in e for e in events)
        streak = streak_wall_s_from_events(events)
        assert streak is not None
        assert abs(streak - 600.0) <= 1.0  # A-B2' ±1 s
        print("OK test_w2_a_b2_streak_from_event_log_not_baked")


def test_w2_heartbeat_stale_threshold() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        log_dir = Path(tmp)
        write_heartbeat(log_dir, instance_id="i", cycle_seq=1)
        assert heartbeat_stale(log_dir, watchdog_s=PROBE_WATCHDOG_S) is False
        hb = log_dir / "night_probe.heartbeat"
        old = time.time() - (PROBE_WATCHDOG_S + 30)
        os.utime(hb, (old, old))
        assert heartbeat_stale(log_dir, watchdog_s=PROBE_WATCHDOG_S) is True
        print("OK test_w2_heartbeat_stale_threshold")


def test_w2_wrapper_has_no_ram_streak_counter() -> None:
    """GP-S2-3: night_probe.sh must not keep STREAK_MIN += STEP."""
    sh = (
        Path(__file__).resolve().parents[2]
        / "newsagent"
        / "scripts"
        / "night_probe.sh"
    )
    text = sh.read_text(encoding="utf-8")
    assert "STREAK_MIN=" not in text or "STREAK_MIN" not in text.split("streak_ux")[0]
    assert "STREAK_STEP_MIN" not in text
    assert "streak_ux" in text
    assert "PROBE_WATCHDOG_S=780" in text
    assert "instance_id" in text
    assert "cycle_seq" in text
    print("OK test_w2_wrapper_has_no_ram_streak_counter")


if __name__ == "__main__":
    os.environ.setdefault("SHADOW_EVENT_LOG", "off")
    for fn in list(globals().values()):
        if callable(fn) and fn.__name__.startswith("test_"):
            fn()
    print("S2-W2 NACHWEIS grün")
