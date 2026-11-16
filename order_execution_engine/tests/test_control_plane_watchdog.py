"""L2 Watchdog — stuck RUNNING detection (read-only; no launchd)."""

from __future__ import annotations

import hashlib
import io
import json
import time
from pathlib import Path

import pytest

from order_execution_engine.control_plane_lease import (
    TTL_MAX_S,
    claim_run,
    connect_scratch,
    issue_token,
    migrate_control_plane,
    next_run_id,
)
from order_execution_engine.control_plane_watchdog import (
    DEFAULT_T_MAX_S,
    EXIT_OK,
    EXIT_STUCK,
    EXIT_WATCHDOG_ERROR,
    check_running_leases,
    report_exit_code,
    resolve_t_max_s,
    scan_stuck_running,
)
from order_execution_engine.gatectl import main as gatectl_main
from order_execution_engine.persistence import SQLiteShadowStorage

assert DEFAULT_T_MAX_S == 2 * TTL_MAX_S


def _scratch_db(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    store = SQLiteShadowStorage.for_user(data, "shadow")
    db = store._db_path  # noqa: SLF001
    migrate_control_plane(store._conn, db_path=db)  # noqa: SLF001
    store.close()
    return db


def test_l2a_t_max_is_two_times_ttl_ceiling() -> None:
    assert DEFAULT_T_MAX_S == 2 * TTL_MAX_S
    assert resolve_t_max_s(None) == float(DEFAULT_T_MAX_S)


def test_l2e_stuck_running_triggers_alarm(tmp_path: Path) -> None:
    """Synthetic hung RUNNING (age > T_max) → alarm + EXIT_STUCK."""
    db = _scratch_db(tmp_path)
    conn = connect_scratch(db)
    rid = next_run_id(conn)
    now = int(time.time())
    tok = issue_token(conn, run_id=rid, ttl_s=60, now=now)
    claim_run(
        conn,
        git_commit="wd1",
        config_json="{}",
        token=tok,
        now=now,
        started_at=float(now - 10_000),
    )
    conn.close()

    alarm_buf = io.StringIO()
    alarm_log = tmp_path / "alarms.jsonl"
    report = check_running_leases(
        db,
        t_max_s=100.0,
        now=float(now),
        alarm_log=alarm_log,
        alarm_stream=alarm_buf,
    )
    assert report.alarm is True
    assert report.ok is False
    assert len(report.stuck) == 1
    assert report.stuck[0].run_id == rid
    assert report.stuck[0].age_s > 100.0
    assert report_exit_code(report) == EXIT_STUCK
    assert "control_plane_watchdog" in alarm_buf.getvalue()
    assert alarm_log.is_file()
    line = alarm_log.read_text(encoding="utf-8").strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["alarm"] is True
    assert payload["stuck"][0]["run_id"] == rid


def test_l2e_fresh_running_no_alarm(tmp_path: Path) -> None:
    """Negativ: frischer RUNNING-Lease → kein Alarm."""
    db = _scratch_db(tmp_path)
    conn = connect_scratch(db)
    rid = next_run_id(conn)
    now = int(time.time())
    tok = issue_token(conn, run_id=rid, ttl_s=60, now=now)
    claim_run(
        conn,
        git_commit="wd2",
        config_json="{}",
        token=tok,
        now=now,
        started_at=float(now - 5),
    )
    conn.close()

    alarm_buf = io.StringIO()
    report = check_running_leases(
        db,
        t_max_s=100.0,
        now=float(now),
        alarm_stream=alarm_buf,
    )
    assert report.alarm is False
    assert report.ok is True
    assert report.stuck == []
    assert report.running_count == 1
    assert report_exit_code(report) == EXIT_OK
    assert alarm_buf.getvalue() == ""


def test_l2c_watchdog_is_read_only_on_db(tmp_path: Path) -> None:
    """Watchdog must not change DB bytes (RO URI / no writer path)."""
    db = _scratch_db(tmp_path)
    conn = connect_scratch(db)
    rid = next_run_id(conn)
    now = int(time.time())
    tok = issue_token(conn, run_id=rid, ttl_s=60, now=now)
    claim_run(
        conn,
        git_commit="wd3",
        config_json="{}",
        token=tok,
        now=now,
        started_at=float(now - 5),
    )
    conn.close()

    before = hashlib.sha256(db.read_bytes()).hexdigest()
    mtime_before = db.stat().st_mtime_ns
    check_running_leases(db, t_max_s=100.0, now=float(now))
    after = hashlib.sha256(db.read_bytes()).hexdigest()
    mtime_after = db.stat().st_mtime_ns
    assert before == after
    assert mtime_before == mtime_after


def test_l2_watchdog_error_emits_alarm_fail_open_vs_runner(
    tmp_path: Path,
) -> None:
    """Unreadable DB → watchdog_error alarm; exit EXIT_WATCHDOG_ERROR."""
    missing = tmp_path / "nope.db"
    alarm_buf = io.StringIO()
    report = check_running_leases(
        missing,
        t_max_s=100.0,
        alarm_stream=alarm_buf,
    )
    assert report.alarm is True
    assert report.error
    assert report_exit_code(report) == EXIT_WATCHDOG_ERROR
    assert "watchdog RO open failed" in alarm_buf.getvalue()


def test_l2_gatectl_watchdog_check_cli(tmp_path: Path) -> None:
    db = _scratch_db(tmp_path)
    conn = connect_scratch(db)
    rid = next_run_id(conn)
    now = int(time.time())
    tok = issue_token(conn, run_id=rid, ttl_s=60, now=now)
    claim_run(
        conn,
        git_commit="wd4",
        config_json="{}",
        token=tok,
        now=now,
        started_at=float(now - 9_000),
    )
    conn.close()

    lock = tmp_path / "RUN.lock"
    lock.write_text("LOCKED=0\n", encoding="utf-8")
    alarm_log = tmp_path / "alarms.jsonl"
    buf = io.StringIO()
    import contextlib

    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        rc = gatectl_main(
            [
                "--db",
                str(db),
                "--data-root",
                str(tmp_path),
                "--runner",
                str(Path(__file__).resolve().parents[1] / "shadow_runner.py"),
                "--lock",
                str(lock),
                "--repo-root",
                str(Path(__file__).resolve().parents[2]),
                "--journal",
                str(tmp_path / "audit.jsonl"),
                "--mirror-folder-id",
                "1knskUdopb-6E9eNhoXnuO5V6ULSzCwVe",
                "watchdog-check",
                "--t-max-s",
                "60",
                "--alarm-log",
                str(alarm_log),
            ]
        )
    assert rc == EXIT_STUCK
    out = json.loads(buf.getvalue())
    assert out["alarm"] is True
    assert out["stuck"][0]["run_id"] == rid
    assert alarm_log.is_file()


def test_scan_stuck_running_unit() -> None:
    class _Conn:
        def execute(self, _sql: str):  # noqa: ANN001
            class R:
                def fetchall(self_inner):  # noqa: ANN001,N805
                    return [(1, 100.0), (2, 500.0)]

            return R()

    stuck = scan_stuck_running(_Conn(), t_max_s=50.0, now=200.0)
    assert [s.run_id for s in stuck] == [1]
    assert stuck[0].age_s == 100.0
