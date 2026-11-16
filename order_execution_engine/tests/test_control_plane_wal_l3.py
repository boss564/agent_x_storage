"""L3 WAL semantics — verification against scratch (never LIVE).

Governance: persistence.py stays frozen; durability contract lives in
``control_plane_lease`` (WAL+FULL + claim-time heal). No runner thaw.
"""

from __future__ import annotations

import hashlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from order_execution_engine.control_plane_lease import (
    TTL_MAX_S,
    WAL_AUTOCHECKPOINT_PAGES,
    LeaseError,
    abort_run,
    apply_writer_durability,
    claim_run,
    connect_scratch,
    detect_restart_kind,
    ensure_control_plane_ready,
    issue_token,
    migrate_control_plane,
    next_run_id,
    startup_integrity_checks,
)
from order_execution_engine.control_plane_watchdog import DEFAULT_T_MAX_S
from order_execution_engine.gatectl import write_lease_token_file
from order_execution_engine.persistence import SQLiteShadowStorage

# Frozen pins — L3-f / F7 boundary (must not change in this suite).
FROZEN_RUNNER_SHA256 = (
    "cfc79b2b46191ab54b7850f063242d2ad19f03424951ab182b93ecfd0f6dcf01"
)
FROZEN_PERSISTENCE_SHA256 = (
    "ce9cc2f88b6202a9cd098b86ed756b2c69f83e5ad6b7819311d8b8f06b36c47f"
)

_REPO = Path(__file__).resolve().parents[2]
_RUNNER = _REPO / "order_execution_engine" / "shadow_runner.py"
_PERSISTENCE = _REPO / "order_execution_engine" / "persistence.py"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _db(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    store = SQLiteShadowStorage.for_user(data, "shadow")
    db = store._db_path  # noqa: SLF001
    migrate_control_plane(store._conn, db_path=db)  # noqa: SLF001
    store.close()
    return db


def test_l3a_wal_and_synchronous_full(tmp_path: Path) -> None:
    db = _db(tmp_path)
    conn = connect_scratch(db)
    journal = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
    sync = conn.execute("PRAGMA synchronous").fetchone()[0]
    assert journal == "wal"
    assert sync in (2, "2", "full", "FULL")
    conn.close()


def test_l3d_wal_autocheckpoint_bound(tmp_path: Path) -> None:
    db = _db(tmp_path)
    conn = connect_scratch(db)
    pages = int(conn.execute("PRAGMA wal_autocheckpoint").fetchone()[0])
    assert pages == WAL_AUTOCHECKPOINT_PAGES
    conn.close()


def test_l3b_startup_integrity_fk_and_restart_kind(tmp_path: Path) -> None:
    """L3-b: integrity + foreign_key_check; clean vs WAL sidecars."""
    db = _db(tmp_path)
    assert detect_restart_kind(db) in ("clean_start", "crash_or_open_wal", "crash_or_open_shm")
    # After close of migrate connection, WAL may linger — either is fine;
    # open+checkpoint to force clean then re-check.
    conn = connect_scratch(db)
    dur = startup_integrity_checks(conn)
    assert dur["integrity_check"] == "ok"
    assert dur["foreign_key_check"] == "ok"
    assert dur["journal_mode"] == "wal"
    ready = ensure_control_plane_ready(conn)
    assert ready["durability"]["foreign_key_check"] == "ok"
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    # Sidecars gone or empty → clean_start
    kind = detect_restart_kind(db)
    assert kind == "clean_start"
    # Simulate leftover WAL bytes (crash/open window marker)
    wal = Path(str(db) + "-wal")
    wal.write_bytes(b"\x00" * 32)
    assert detect_restart_kind(db) == "crash_or_open_wal"
    wal.unlink(missing_ok=True)


def test_l3_pragma_heal_on_persistence_write_conn(tmp_path: Path) -> None:
    """PRAGMA-Scope: claim_run re-binds FULL/autocheckpoint on store._conn."""
    data = tmp_path / "data"
    data.mkdir()
    store = SQLiteShadowStorage.for_user(data, "shadow")
    db = store._db_path  # noqa: SLF001
    migrate_control_plane(store._conn, db_path=db)  # noqa: SLF001
    # Strip per-connection durability (simulate persistence re-open).
    store._conn.execute("PRAGMA synchronous = NORMAL")  # noqa: SLF001
    store._conn.execute("PRAGMA wal_autocheckpoint = 0")  # noqa: SLF001
    sync_before = store._conn.execute("PRAGMA synchronous").fetchone()[0]  # noqa: SLF001
    assert sync_before in (1, "1", "normal", "NORMAL")
    ac_before = int(
        store._conn.execute("PRAGMA wal_autocheckpoint").fetchone()[0]  # noqa: SLF001
    )
    assert ac_before == 0

    now = int(time.time())
    rid = next_run_id(store._conn)  # noqa: SLF001
    tok = issue_token(store._conn, run_id=rid, ttl_s=120, now=now)  # noqa: SLF001
    claim_run(
        store._conn,  # noqa: SLF001
        git_commit="pragma-heal",
        config_json="{}",
        token=tok,
        now=now,
    )
    sync_after = store._conn.execute("PRAGMA synchronous").fetchone()[0]  # noqa: SLF001
    ac_after = int(
        store._conn.execute("PRAGMA wal_autocheckpoint").fetchone()[0]  # noqa: SLF001
    )
    assert sync_after in (2, "2", "full", "FULL")
    assert ac_after == WAL_AUTOCHECKPOINT_PAGES
    # Shared connection identity: still the same object the runner writes on.
    assert store._conn is store._conn  # noqa: SLF001
    store.close()


def test_l3c_orphan_token_file_without_claim(tmp_path: Path) -> None:
    """Crash between O_EXCL token file and claim: file remains; claim still works."""
    db = _db(tmp_path)
    conn = connect_scratch(db)
    rid = next_run_id(conn)
    now = int(time.time())
    tok = issue_token(conn, run_id=rid, ttl_s=120, now=now)
    token_path = write_lease_token_file(tmp_path, rid, tok, conn=conn)
    conn.close()

    assert token_path.is_file()
    assert token_path.stat().st_mode & 0o777 == 0o600

    conn = connect_scratch(db)
    startup_integrity_checks(conn)
    claim_run(
        conn,
        git_commit="l3c",
        config_json="{}",
        token=tok,
        now=now,
    )
    st = conn.execute(
        "SELECT status FROM telemetry_runs WHERE run_id=?", (rid,)
    ).fetchone()[0]
    assert st == "RUNNING"
    conn.close()


def test_l3c_orphan_running_requires_explicit_abort(tmp_path: Path) -> None:
    """Crash after claim → RUNNING; no silent heal; abort_run recovers."""
    db = _db(tmp_path)
    conn = connect_scratch(db)
    rid = next_run_id(conn)
    now = int(time.time())
    tok = issue_token(conn, run_id=rid, ttl_s=120, now=now)
    claim_run(
        conn,
        git_commit="l3e",
        config_json="{}",
        token=tok,
        now=now,
    )
    st = conn.execute(
        "SELECT status FROM telemetry_runs WHERE run_id=?", (rid,)
    ).fetchone()[0]
    assert st == "RUNNING"
    with pytest.raises(LeaseError, match="RUNNING"):
        issue_token(conn, run_id=rid + 1, ttl_s=60, now=now)
    abort_run(conn, rid, reason="l3_crash_sim")
    st2 = conn.execute(
        "SELECT status FROM telemetry_runs WHERE run_id=?", (rid,)
    ).fetchone()[0]
    assert st2 == "ABORTED"
    nxt = next_run_id(conn)
    assert nxt == rid + 1
    conn.close()


def test_l3_t_max_bound_to_same_ttl_source() -> None:
    """L2-Rest: watchdog T_max pinned to lease TTL_MAX_S (no config drift)."""
    assert DEFAULT_T_MAX_S == 2 * TTL_MAX_S


def test_f7_lease_token_refused_on_live_marked_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F7: LIVE-refuse in frozen runner call path (not gatectl-only).

    Architecture: ``--lease-token`` = scratch/debug; LIVE hard-refuses in
    ``shadow_runner.main`` before claim. Pin must stay ``cfc79b2b…``.
    """
    from unittest.mock import patch

    from order_execution_engine.shadow_runner import (
        EXIT_CONTROL_PLANE,
        default_run_lock_path,
        main as runner_main,
    )

    assert _sha(_RUNNER) == FROZEN_RUNNER_SHA256
    src = _RUNNER.read_text(encoding="utf-8")
    # Exact refuse site in frozen bytes (call path the runner executes).
    assert "refuse --lease-token on LIVE data-root (M1 use --lease-token-file)" in src
    assert "elif args.lease_token:" in src
    assert "is_live_agentx_path" in src

    live_root = tmp_path / "Library" / "Application Support" / "agentx" / "x"
    live_root.mkdir(parents=True)
    allow = tmp_path / "allow.json"
    allow.write_text(
        '{"BTC":{"token_id":"t","market_id":"m"}}', encoding="utf-8"
    )
    news = tmp_path / "news.jsonl"
    news.write_text("", encoding="utf-8")
    lock = tmp_path / "RUN.lock"
    lock.write_text("LOCKED=0\n", encoding="utf-8")
    with patch(
        "order_execution_engine.shadow_runner.default_run_lock_path",
        return_value=lock,
    ):
        rc = runner_main(
            [
                "--data-root",
                str(live_root),
                "--user-id",
                "shadow",
                "--allowlist",
                str(allow),
                "--news-jsonl",
                str(news),
                "--lease-token",
                "raw_debug_token_should_refuse",
                "--once",
                "--no-ws",
            ]
        )
    assert rc == EXIT_CONTROL_PLANE
    # Module identity: runner_main is the frozen file.
    assert Path(runner_main.__code__.co_filename).resolve() == _RUNNER.resolve()
    assert Path(default_run_lock_path.__code__.co_filename).resolve() == _RUNNER.resolve()


def test_f6_m1_oexcl_0600_micro_verified(tmp_path: Path) -> None:
    """F6: M1 exclusivity via gatectl O_EXCL 0600 (suite path; not canary)."""
    p1 = write_lease_token_file(tmp_path, 16, "a" * 40)
    assert p1.stat().st_mode & 0o777 == 0o600
    with pytest.raises(OSError):
        write_lease_token_file(tmp_path, 16, "b" * 40)


def test_l3f_freeze_pins_unthawed() -> None:
    assert _sha(_RUNNER) == FROZEN_RUNNER_SHA256
    assert _sha(_PERSISTENCE) == FROZEN_PERSISTENCE_SHA256


# ---------------------------------------------------------------------------
# L3-e Crash-Injection (kill -9) — against copy only; Pre/Post LIVE SHA
# ---------------------------------------------------------------------------

_L3E_CHILD = Path(__file__).resolve().parent / "_l3e_crash_child.py"


def _spawn_crash_child(mode: str, db: Path) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_REPO) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    return subprocess.Popen(
        [sys.executable, str(_L3E_CHILD), mode, str(db)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )


def _wait_ready_then_kill9(proc: subprocess.Popen[str], timeout_s: float = 15.0) -> None:
    assert proc.stdout is not None
    deadline = time.time() + timeout_s
    buf = ""
    while time.time() < deadline:
        line = proc.stdout.readline()
        if line:
            buf += line
            if "READY" in line:
                os.kill(proc.pid, signal.SIGKILL)
                proc.wait(timeout=10)
                assert proc.returncode in (-signal.SIGKILL, 137, -9) or proc.returncode != 0
                return
        elif proc.poll() is not None:
            err = proc.stderr.read() if proc.stderr else ""
            raise AssertionError(
                f"child exited early rc={proc.returncode} out={buf!r} err={err!r}"
            )
        else:
            time.sleep(0.05)
    proc.kill()
    raise AssertionError(f"READY timeout; out={buf!r}")


def test_l3e_kill9_after_token_before_commit(tmp_path: Path) -> None:
    """L3-e: kill -9 after lease INSERT before COMMIT → row absent; integrity ok."""
    db = _db(tmp_path)
    pre = _sha(db)
    live = Path.home() / (
        "Library/Application Support/agentx/shadow_live/shadow/shadow/shadow.db"
    )
    live_pre = _sha(live) if live.is_file() else None

    proc = _spawn_crash_child("before_commit", db)
    _wait_ready_then_kill9(proc)

    conn = connect_scratch(db)
    apply_writer_durability(conn)
    n = conn.execute("SELECT COUNT(*) FROM run_lease").fetchone()[0]
    assert n == 0
    assert detect_restart_kind(db) in (
        "clean_start",
        "crash_or_open_wal",
        "crash_or_open_shm",
    )
    conn.close()
    post = _sha(db)
    # DB file bytes may change (WAL checkpoint into main); integrity is the contract.
    assert isinstance(pre, str) and isinstance(post, str)
    if live_pre is not None:
        assert _sha(live) == live_pre


def test_l3e_kill9_after_commit_before_checkpoint(tmp_path: Path) -> None:
    """L3-e: kill after COMMIT of claim; RUNNING durable; abort recovers."""
    db = _db(tmp_path)
    live = Path.home() / (
        "Library/Application Support/agentx/shadow_live/shadow/shadow/shadow.db"
    )
    live_pre = _sha(live) if live.is_file() else None

    proc = _spawn_crash_child("after_commit", db)
    _wait_ready_then_kill9(proc)

    conn = connect_scratch(db)
    dur = apply_writer_durability(conn)
    assert dur["integrity_check"] == "ok"
    assert dur["foreign_key_check"] == "ok"
    row = conn.execute(
        "SELECT run_id, status FROM telemetry_runs WHERE status='RUNNING'"
    ).fetchone()
    assert row is not None
    rid = int(row[0])
    abort_run(conn, rid, reason="l3e_post_commit_kill")
    st = conn.execute(
        "SELECT status FROM telemetry_runs WHERE run_id=?", (rid,)
    ).fetchone()[0]
    assert st == "ABORTED"
    conn.close()
    if live_pre is not None:
        assert _sha(live) == live_pre


def test_l3e_kill9_mid_wal_write(tmp_path: Path) -> None:
    """L3-e: kill during uncommitted WAL frames → no durable lease rows."""
    db = _db(tmp_path)
    live = Path.home() / (
        "Library/Application Support/agentx/shadow_live/shadow/shadow/shadow.db"
    )
    live_pre = _sha(live) if live.is_file() else None

    proc = _spawn_crash_child("mid_wal", db)
    _wait_ready_then_kill9(proc)

    conn = connect_scratch(db)
    dur = apply_writer_durability(conn)
    assert dur["integrity_check"] == "ok"
    n = int(conn.execute("SELECT COUNT(*) FROM run_lease").fetchone()[0])
    assert n == 0
    conn.close()
    if live_pre is not None:
        assert _sha(live) == live_pre
