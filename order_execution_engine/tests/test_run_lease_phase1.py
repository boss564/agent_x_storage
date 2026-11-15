"""Phase-1 scratch: run_lease Abnahmekriterium + F1–F3 / BI-Trigger.

Scratch only — refuses Application Support/agentx paths.
Does not touch RUN.lock, LIVE_DB, or installed plists.
"""

from __future__ import annotations

import hashlib
import multiprocessing as mp
import sqlite3
import tempfile
import time
import traceback
from pathlib import Path

from order_execution_engine.control_plane_lease import (
    ISSUED_AT_FUTURE_SKEW_S,
    RUN_ID_FLOOR,
    SCHEMA_CONTROL,
    SCHEMA_V10,
    TTL_MAX_S,
    LeaseError,
    LivePathRefused,
    assert_scratch_db_path,
    claim_run,
    connect_scratch,
    issue_token,
    migrate_control_plane,
    next_run_id,
    revoke_token,
    trigger_manifest_sha256,
)
from order_execution_engine.persistence import SCHEMA_VERSION, SQLiteShadowStorage

# Gate #6 + E-1 residual pin (fail-closed claim / forbid only while LOCKED=1).
# Pre-Gate-6 baseline was 2157113ad64c88c0e5c2ab346e2c6b3530b869440981aa5a708a3f73c6faefb3.
GUARD_SHA_PRE_PHASE1 = (
    "1c65b0be2925da85fee6ce090a1fe817f93b61ed6be4a2a0a2cfc0d80e2b8d77"
)


def _schema(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT value FROM schema_meta WHERE key='schema_version'"
    ).fetchone()
    return int(row[0]) if row else 0


def _triggers(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger'"
    ).fetchall()
    return {r[0] for r in rows}


def _v9_store() -> tuple[Path, SQLiteShadowStorage]:
    tmp = Path(tempfile.mkdtemp(prefix="phase1_lease_"))
    assert_scratch_db_path(tmp)
    store = SQLiteShadowStorage.for_user(tmp, "scratch")
    assert _schema(store._conn) == SCHEMA_VERSION  # noqa: SLF001
    return store._db_path, store  # noqa: SLF001


def _v10_conn() -> tuple[Path, sqlite3.Connection]:
    """Fresh scratch DB migrated to SCHEMA_CONTROL."""
    db_path, store = _v9_store()
    migrate_control_plane(store._conn, db_path=db_path)  # noqa: SLF001
    assert _schema(store._conn) == SCHEMA_CONTROL  # noqa: SLF001
    store._conn.close()  # noqa: SLF001
    conn = connect_scratch(db_path)
    assert _schema(conn) == SCHEMA_CONTROL
    assert "trg_run_lease_before_insert" in _triggers(conn)
    return db_path, conn


def test_live_path_refused() -> None:
    fake = Path(
        "/Users/olivermueller/Library/Application Support/agentx/"
        "shadow_live/shadow.db"
    )
    try:
        assert_scratch_db_path(fake)
        raise AssertionError("expected LivePathRefused")
    except LivePathRefused:
        pass
    print("OK test_live_path_refused")


def _claim_worker(db_path: str, token: str, queue: mp.Queue) -> None:
    try:
        conn = connect_scratch(Path(db_path))
        rid = claim_run(
            conn,
            git_commit="c",
            config_json="{}",
            token=token,
            started_at=time.time(),
        )
        queue.put(("ok", rid))
    except Exception as exc:  # noqa: BLE001
        queue.put(("err", f"{type(exc).__name__}: {exc}"))


def test_concurrency_one_claim_one_reject() -> None:
    db_path, conn = _v10_conn()
    rid = next_run_id(conn)
    assert rid == RUN_ID_FLOOR + 1
    tok = issue_token(conn, run_id=rid, ttl_s=60)
    q: mp.Queue = mp.Queue()
    procs = [
        mp.Process(target=_claim_worker, args=(str(db_path), tok, q)),
        mp.Process(target=_claim_worker, args=(str(db_path), tok, q)),
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
        assert not p.is_alive()
    results = [q.get(timeout=5) for _ in range(2)]
    oks = [r for r in results if r[0] == "ok"]
    errs = [r for r in results if r[0] == "err"]
    assert len(oks) == 1 and len(errs) == 1, results
    assert oks[0][1] == rid
    print("OK test_concurrency_one_claim_one_reject")


def test_expired_token_rejects_claim() -> None:
    _, conn = _v10_conn()
    rid = next_run_id(conn)
    now = int(time.time())
    tok = issue_token(conn, run_id=rid, ttl_s=1, now=now - 10)
    try:
        claim_run(conn, git_commit="c", config_json="{}", token=tok)
        raise AssertionError("expected LeaseError on expired lease")
    except LeaseError:
        pass
    print("OK test_expired_token_rejects_claim")


def test_issue_token_rejects_non_next_run_id() -> None:
    _, conn = _v10_conn()
    try:
        tok = issue_token(conn, run_id=99, ttl_s=60)
        raise AssertionError("expected LeaseError for run_id!=MAX+1")
    except LeaseError as exc:
        assert "next is" in str(exc)
    print("OK test_issue_token_rejects_non_next_run_id")


def test_ttl_cap_rejects_duration_grant() -> None:
    _, conn = _v10_conn()
    rid = next_run_id(conn)
    try:
        tok = issue_token(conn, run_id=rid, ttl_s=10**9)
        raise AssertionError("expected LeaseError for ttl > TTL_MAX_S")
    except LeaseError as exc:
        assert str(TTL_MAX_S) in str(exc)
    print("OK test_ttl_cap_rejects_duration_grant")


def test_reused_token_rejects_second_claim() -> None:
    _, conn = _v10_conn()
    rid = next_run_id(conn)
    tok = issue_token(conn, run_id=rid, ttl_s=60)
    assert claim_run(conn, git_commit="c", config_json="{}", token=tok) == rid
    try:
        claim_run(conn, git_commit="c", config_json="{}", token=tok)
        raise AssertionError("expected LeaseError on reused lease")
    except LeaseError:
        pass
    print("OK test_reused_token_rejects_second_claim")


def test_insert_without_lease_aborts() -> None:
    _, conn = _v10_conn()
    rid = next_run_id(conn)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO telemetry_runs"
            " (run_id, started_at, git_commit, config_json, status, closed_at)"
            " VALUES (?, ?, 'c', '{}', 'RUNNING', NULL)",
            (rid, time.time()),
        )
        conn.execute("COMMIT")
        raise AssertionError("expected ABORT without lease")
    except sqlite3.DatabaseError:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
    print("OK test_insert_without_lease_aborts")


def test_revoke_and_reissue() -> None:
    _, conn = _v10_conn()
    rid = next_run_id(conn)
    t1 = issue_token(conn, run_id=rid, ttl_s=60)
    revoke_token(conn, t1)
    t2 = issue_token(conn, run_id=rid, ttl_s=60)
    assert t1 != t2
    assert claim_run(conn, git_commit="c", config_json="{}", token=t2) == rid
    print("OK test_revoke_and_reissue")


def test_f1_reopen_preserves_v10_and_store_open_run() -> None:
    """F1 + Integration: reopen Store must keep SCHEMA_CONTROL; open_run claims."""
    db_path, store = _v9_store()
    migrate_control_plane(store._conn, db_path=db_path)  # noqa: SLF001
    assert _schema(store._conn) == SCHEMA_CONTROL  # noqa: SLF001
    store.close()

    store2 = SQLiteShadowStorage(db_path)
    assert _schema(store2._conn) == SCHEMA_CONTROL  # noqa: SLF001
    rid = next_run_id(store2._conn)  # noqa: SLF001
    tok = issue_token(store2._conn, run_id=rid, ttl_s=60)  # noqa: SLF001
    got = store2.open_run(
        git_commit="integ", config_json={"phase": 1}, lease_token=tok
    )
    assert got == rid
    row = store2._conn.execute(  # noqa: SLF001
        "SELECT status FROM telemetry_runs WHERE run_id = ?", (got,)
    ).fetchone()
    assert row[0] == "RUNNING"
    store2.close()
    print("OK test_f1_reopen_preserves_v10_and_store_open_run")


def test_f2_migrate_abort_rolls_back() -> None:
    """Forced mid-migration abort → still v9, no lease triggers."""
    db_path, store = _v9_store()
    conn = store._conn  # noqa: SLF001
    try:
        migrate_control_plane(
            conn, db_path=db_path, _abort_after="trg_bi_lease"
        )
        raise AssertionError("expected forced abort")
    except RuntimeError as exc:
        assert "forced migrate abort" in str(exc)
    assert _schema(conn) == SCHEMA_VERSION
    names = _triggers(conn)
    assert "trg_telemetry_runs_bi_lease" not in names
    assert "trg_telemetry_runs_ai_consume" not in names
    store.close()
    store2 = SQLiteShadowStorage(db_path)
    assert _schema(store2._conn) == SCHEMA_VERSION  # noqa: SLF001
    migrate_control_plane(store2._conn, db_path=db_path)  # noqa: SLF001
    assert _schema(store2._conn) == SCHEMA_CONTROL  # noqa: SLF001
    store2.close()
    print("OK test_f2_migrate_abort_rolls_back")


def test_f3_issue_token_refuses_live_path_via_conn() -> None:
    """issue_token refuses when PRAGMA database_list points at Application Support."""
    base = (
        Path(tempfile.mkdtemp(prefix="f3_"))
        / "Library"
        / "Application Support"
        / "agentx"
    )
    base.mkdir(parents=True)
    db = base / "probe.db"
    try:
        connect_scratch(db)
        raise AssertionError("connect_scratch should refuse")
    except LivePathRefused:
        pass
    raw = sqlite3.connect(str(db), isolation_level=None)
    try:
        tok = issue_token(raw, run_id=1, ttl_s=60)
        raise AssertionError("issue_token should refuse LIVE path via conn")
    except LivePathRefused:
        pass
    finally:
        raw.close()
    print("OK test_f3_issue_token_refuses_live_path_via_conn")


def test_run_lease_delete_forbidden() -> None:
    _, conn = _v10_conn()
    rid = next_run_id(conn)
    tok = issue_token(conn, run_id=rid, ttl_s=60)
    try:
        conn.execute("DELETE FROM run_lease")
        raise AssertionError("expected DELETE forbidden")
    except sqlite3.DatabaseError:
        pass
    print("OK test_run_lease_delete_forbidden")


def test_run_lease_bi_rejects_bad_run_id() -> None:
    """Direct INSERT: run_id=15, 17, or jump after a run → IntegrityError."""
    _, conn = _v10_conn()
    now = int(time.time())
    expect = next_run_id(conn)
    assert expect == RUN_ID_FLOOR + 1  # 16 on empty scratch

    for bad_id in (15, 17, expect + 5):
        try:
            conn.execute(
                "INSERT INTO run_lease"
                " (token, run_id, issued_at, expires_at, consumed_at, revoked_at)"
                f" VALUES ('tok-bad-{bad_id}', ?, ?, ?, NULL, NULL)",
                (bad_id, now, now + 60),
            )
            raise AssertionError(f"expected ABORT for run_id={bad_id}")
        except sqlite3.IntegrityError as exc:
            assert "not next" in str(exc)

    # After a claimed run, jump still rejected
    tok = issue_token(conn, run_id=expect, ttl_s=60)
    claim_run(conn, git_commit="c", config_json="{}", token=tok)
    nxt = next_run_id(conn)
    try:
        conn.execute(
            "INSERT INTO run_lease"
            " (token, run_id, issued_at, expires_at, consumed_at, revoked_at)"
            " VALUES ('tok-jump', ?, ?, ?, NULL, NULL)",
            (nxt + 2, now, now + 60),
        )
        raise AssertionError("expected ABORT for jump after run")
    except sqlite3.IntegrityError as exc:
        assert "not next" in str(exc)
    print("OK test_run_lease_bi_rejects_bad_run_id")


def test_run_lease_bi_rejects_bad_ttl_and_timestamps() -> None:
    """Direct INSERT: TTL>MAX, expires<=issued, NULL ts → IntegrityError."""
    _, conn = _v10_conn()
    now = int(time.time())
    rid = next_run_id(conn)

    try:
        conn.execute(
            "INSERT INTO run_lease"
            " (token, run_id, issued_at, expires_at, consumed_at, revoked_at)"
            " VALUES ('tok-ttl', ?, ?, ?, NULL, NULL)",
            (rid, now, now + TTL_MAX_S + 1),
        )
        raise AssertionError("expected ABORT for TTL > MAX")
    except sqlite3.IntegrityError as exc:
        assert "TTL" in str(exc)

    try:
        conn.execute(
            "INSERT INTO run_lease"
            " (token, run_id, issued_at, expires_at, consumed_at, revoked_at)"
            " VALUES ('tok-eq', ?, ?, ?, NULL, NULL)",
            (rid, now, now),
        )
        raise AssertionError("expected ABORT for expires_at <= issued_at")
    except sqlite3.IntegrityError as exc:
        assert "expires_at" in str(exc) or "TTL" in str(exc)

    try:
        conn.execute(
            "INSERT INTO run_lease"
            " (token, run_id, issued_at, expires_at, consumed_at, revoked_at)"
            " VALUES ('tok-null', ?, NULL, ?, NULL, NULL)",
            (rid, now + 60),
        )
        raise AssertionError("expected ABORT for NULL issued_at")
    except sqlite3.IntegrityError as exc:
        assert "timestamp" in str(exc).lower() or "NOT NULL" in str(exc)
    print("OK test_run_lease_bi_rejects_bad_ttl_and_timestamps")


def test_g1_issued_at_far_future_rejected() -> None:
    """G1: issued_at far ahead of now cannot grant a long-lived lease."""
    _, conn = _v10_conn()
    now = int(time.time())
    rid = next_run_id(conn)
    issued = now + 10 * 365 * 86400  # ~10 years ahead
    try:
        conn.execute(
            "INSERT INTO run_lease"
            " (token, run_id, issued_at, expires_at, consumed_at, revoked_at)"
            " VALUES ('tok-future', ?, ?, ?, NULL, NULL)",
            (rid, issued, issued + TTL_MAX_S),
        )
        raise AssertionError("expected ABORT for issued_at far in future")
    except sqlite3.IntegrityError as exc:
        assert "issued_at" in str(exc)
    # Past issued_at still allowed (shortens validity); expired claim fails later.
    past = now - 10
    conn.execute(
        "INSERT INTO run_lease"
        " (token, run_id, issued_at, expires_at, consumed_at, revoked_at)"
        " VALUES ('tok-past', ?, ?, ?, NULL, NULL)",
        (rid, past, past + 1),
    )
    try:
        claim_run(conn, git_commit="c", config_json="{}", token="tok-past")
        raise AssertionError("expected LeaseError on past/expired lease")
    except LeaseError:
        pass
    # Skew window itself remains usable.
    assert ISSUED_AT_FUTURE_SKEW_S == 5
    print("OK test_g1_issued_at_far_future_rejected")


def test_run_lease_bi_accepts_valid_and_manifest_stable() -> None:
    """issue_token + valid INSERT; manifest SHA stable across data writes."""
    _, conn = _v10_conn()
    now = int(time.time())
    rid = next_run_id(conn)

    h1 = trigger_manifest_sha256(conn)
    assert len(h1) == 64 and all(c in "0123456789abcdef" for c in h1)
    h1b = trigger_manifest_sha256(conn)
    assert h1 == h1b

    tok = issue_token(conn, run_id=rid, ttl_s=60)
    assert tok
    assert claim_run(conn, git_commit="c", config_json="{}", token=tok) == rid

    rid2 = next_run_id(conn)
    conn.execute(
        "INSERT INTO run_lease"
        " (token, run_id, issued_at, expires_at, consumed_at, revoked_at)"
        " VALUES ('tok-ok-direct', ?, ?, ?, NULL, NULL)",
        (rid2, now, now + 60),
    )
    h2 = trigger_manifest_sha256(conn)
    assert h2 == h1
    print("OK test_run_lease_bi_accepts_valid_and_manifest_stable")


def test_g2_manifest_changes_on_each_structural_drop() -> None:
    """G2: dropping any covered trigger/index changes the manifest hash."""
    drops = (
        "DROP TRIGGER trg_run_lease_before_insert",
        "DROP TRIGGER trg_telemetry_runs_bi_lease",
        "DROP INDEX ux_run_lease_open_run",
        "DROP TRIGGER trg_telemetry_runs_ai_consume",
        "DROP TRIGGER trg_run_lease_bd_forbid",
    )
    for sql in drops:
        _, conn = _v10_conn()
        h0 = trigger_manifest_sha256(conn)
        conn.execute(sql)
        h1 = trigger_manifest_sha256(conn)
        assert h1 != h0, f"manifest unchanged after {sql}"
        assert len(h1) == 64
        conn.close()
    print("OK test_g2_manifest_changes_on_each_structural_drop")


def test_status_cannot_revert_to_running() -> None:
    _, conn = _v10_conn()
    rid = next_run_id(conn)
    tok = issue_token(conn, run_id=rid, ttl_s=60)
    claim_run(conn, git_commit="c", config_json="{}", token=tok)
    conn.execute(
        "UPDATE telemetry_runs SET status = 'COMMITTED',"
        " closed_at = CAST(strftime('%s', 'now') AS INTEGER)"
        " WHERE run_id = ?",
        (rid,),
    )
    try:
        conn.execute(
            "UPDATE telemetry_runs SET status = 'RUNNING' WHERE run_id = ?",
            (rid,),
        )
        raise AssertionError("expected status revert ABORT")
    except sqlite3.DatabaseError:
        pass
    print("OK test_status_cannot_revert_to_running")


def test_guard_sha_pin_still_matches_tree() -> None:
    root = Path(__file__).resolve().parents[1]
    got = hashlib.sha256((root / "shadow_runner.py").read_bytes()).hexdigest()
    assert got == GUARD_SHA_PRE_PHASE1, (got, GUARD_SHA_PRE_PHASE1)
    print("OK test_guard_sha_pin_still_matches_tree")


def test_v10_to_v11_upgrade_replaces_lease_bi() -> None:
    """Existing stamp=10 DBs get hardened BI via migrate_control_plane."""
    db_path, store = _v9_store()
    conn = store._conn  # noqa: SLF001
    # Manual minimal v10 stamp without new trigger name
    conn.execute(
        "CREATE TABLE IF NOT EXISTS run_lease ("
        " token TEXT PRIMARY KEY, run_id INTEGER NOT NULL,"
        " issued_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,"
        " consumed_at INTEGER, revoked_at INTEGER)"
    )
    conn.execute(
        "CREATE TRIGGER IF NOT EXISTS trg_run_lease_bi_guard"
        " BEFORE INSERT ON run_lease BEGIN"
        " SELECT RAISE(ABORT, 'old guard'); END"
    )
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value)"
        " VALUES ('schema_version', ?)",
        (str(SCHEMA_V10),),
    )
    conn.commit()
    store.close()
    conn = connect_scratch(db_path)
    assert _schema(conn) == SCHEMA_V10
    migrate_control_plane(conn, db_path=db_path)
    assert _schema(conn) == SCHEMA_CONTROL
    names = _triggers(conn)
    assert "trg_run_lease_before_insert" in names
    assert "trg_run_lease_bi_guard" not in names
    # G1 present after upgrade
    now = int(time.time())
    future = now + 10 * 365 * 86400
    rid = next_run_id(conn)
    try:
        conn.execute(
            "INSERT INTO run_lease"
            " (token, run_id, issued_at, expires_at, consumed_at, revoked_at)"
            " VALUES ('tok-upg-future', ?, ?, ?, NULL, NULL)",
            (rid, future, future + 60),
        )
        raise AssertionError("expected G1 abort after upgrade")
    except sqlite3.IntegrityError as exc:
        assert "issued_at" in str(exc)
    conn.close()
    print("OK test_v10_to_v11_upgrade_replaces_lease_bi")


def main() -> int:
    tests = [
        test_live_path_refused,
        test_concurrency_one_claim_one_reject,
        test_expired_token_rejects_claim,
        test_issue_token_rejects_non_next_run_id,
        test_ttl_cap_rejects_duration_grant,
        test_reused_token_rejects_second_claim,
        test_insert_without_lease_aborts,
        test_revoke_and_reissue,
        test_f1_reopen_preserves_v10_and_store_open_run,
        test_f2_migrate_abort_rolls_back,
        test_f3_issue_token_refuses_live_path_via_conn,
        test_run_lease_delete_forbidden,
        test_run_lease_bi_rejects_bad_run_id,
        test_run_lease_bi_rejects_bad_ttl_and_timestamps,
        test_g1_issued_at_far_future_rejected,
        test_run_lease_bi_accepts_valid_and_manifest_stable,
        test_g2_manifest_changes_on_each_structural_drop,
        test_status_cannot_revert_to_running,
        test_guard_sha_pin_still_matches_tree,
        test_v10_to_v11_upgrade_replaces_lease_bi,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
        except Exception:
            failed += 1
            traceback.print_exc()
            print(f"FAIL {fn.__name__}")
    print(f"RESULT {len(tests) - failed}/{len(tests)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
