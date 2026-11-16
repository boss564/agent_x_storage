"""L3 WAL semantics — verification against scratch (never LIVE).

Governance: persistence.py stays frozen; durability contract lives in
``control_plane_lease._open_sqlite`` (WAL+FULL). No runner thaw.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from order_execution_engine.control_plane_lease import (
    TTL_MAX_S,
    WAL_AUTOCHECKPOINT_PAGES,
    LeaseError,
    abort_run,
    claim_run,
    connect_scratch,
    ensure_control_plane_ready,
    issue_token,
    migrate_control_plane,
    next_run_id,
    startup_integrity_checks,
)
from order_execution_engine.control_plane_watchdog import DEFAULT_T_MAX_S
from order_execution_engine.gatectl import write_lease_token_file
from order_execution_engine.persistence import SQLiteShadowStorage


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


def test_l3b_startup_integrity_and_ensure(tmp_path: Path) -> None:
    db = _db(tmp_path)
    conn = connect_scratch(db)
    dur = startup_integrity_checks(conn)
    assert dur["integrity_check"] == "ok"
    assert dur["journal_mode"] == "wal"
    ready = ensure_control_plane_ready(conn)
    assert ready["durability"]["integrity_check"] == "ok"
    conn.close()


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
    """F7: raw --lease-token is debug/scratch; LIVE-marked data-root refuses.

    Architecture decision (no runner thaw): ``--lease-token`` remains scratch/
    unit-test only; LIVE already hard-refuses. L5 prod start must use
    ``--lease-token-file`` only. Avoid ``--run-lock`` here (M2 would fire first).
    """
    from unittest.mock import patch

    from order_execution_engine.shadow_runner import (
        EXIT_CONTROL_PLANE,
        default_run_lock_path,
        main as runner_main,
    )

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
    # Source contract still present (frozen runner).
    src = Path(default_run_lock_path.__code__.co_filename).read_text(
        encoding="utf-8"
    )
    assert "refuse --lease-token on LIVE data-root" in src
    assert "Scratch/unit-test only" in src


def test_f6_m1_oexcl_0600_micro_verified(tmp_path: Path) -> None:
    """F6: M1 exclusivity via gatectl O_EXCL 0600 (suite path; not canary)."""
    p1 = write_lease_token_file(tmp_path, 16, "a" * 40)
    assert p1.stat().st_mode & 0o777 == 0o600
    with pytest.raises(OSError):
        write_lease_token_file(tmp_path, 16, "b" * 40)
