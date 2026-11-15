"""Gate #6 Runner-Anbindung — Scratch-only (no LIVE_DB / package RUN.lock writes)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from order_execution_engine.control_plane_lease import (
    SCHEMA_CONTROL,
    issue_token,
    migrate_control_plane,
    next_run_id,
)
from order_execution_engine.persistence import SQLiteShadowStorage
from order_execution_engine.shadow_runner import (
    EXIT_CONTROL_PLANE,
    EXIT_RUN_LOCK,
    main as runner_main,
    parse_run_lock,
    run_lock_blocks,
)

PKG = Path(__file__).resolve().parents[1]
SHADOW_RUNNER = PKG / "shadow_runner.py"
PACKAGE_LOCK = PKG / "ops" / "RUN.lock"
# Pre-Gate-6 freeze Guard (historical).
GUARD_SHA_BASELINE = (
    "2157113ad64c88c0e5c2ab346e2c6b3530b869440981aa5a708a3f73c6faefb3"
)
# Gate #6 pin after runner control-plane binding + E-1 residual A1/A3 fix.
GUARD_SHA_GATE6 = (
    "cfc79b2b46191ab54b7850f063242d2ad19f03424951ab182b93ecfd0f6dcf01"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _scratch_bundle(tmp_path: Path) -> dict[str, Path]:
    data = tmp_path / "data"
    data.mkdir()
    store = SQLiteShadowStorage.for_user(data, "shadow")
    db = store._db_path  # noqa: SLF001
    migrate_control_plane(store._conn, db_path=db)  # noqa: SLF001
    store.close()
    lock = tmp_path / "RUN.lock"
    lock.write_text("LOCKED=0\n", encoding="utf-8")
    allow = tmp_path / "allowlist.json"
    # Minimal freeze-shaped allowlist (single asset)
    allow.write_text(
        json.dumps(
            {
                "BTC": {
                    "token_id": "tok_btc_gate6",
                    "market_id": "mkt_btc_gate6",
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    news = tmp_path / "news_scores.jsonl"
    news.write_text("", encoding="utf-8")
    return {
        "data": data,
        "db": db,
        "lock": lock,
        "allow": allow,
        "news": news,
    }


def _argv(paths: dict[str, Path], *extra: str) -> list[str]:
    return [
        "--data-root",
        str(paths["data"]),
        "--user-id",
        "shadow",
        "--allowlist",
        str(paths["allow"]),
        "--news-jsonl",
        str(paths["news"]),
        "--run-lock",
        str(paths["lock"]),
        "--once",
        "--no-ws",
        *extra,
    ]


def test_guard_pin_and_package_lock_intact() -> None:
    """Pin is commit-bound; package RUN.lock is a freeze fixture (may be untracked).

    Clean worktree / detached tip has no untracked ``ops/RUN.lock`` — pin still
    binds. Lock body is asserted only when the freeze file is present on disk.
    """
    got = _sha(SHADOW_RUNNER)
    assert got == GUARD_SHA_GATE6
    assert got != GUARD_SHA_BASELINE
    text_py = SHADOW_RUNNER.read_text(encoding="utf-8")
    assert "ensure_control_plane_ready" in text_py
    assert "EXIT_CONTROL_PLANE" in text_py
    if not PACKAGE_LOCK.is_file():
        pytest.skip(
            "package RUN.lock absent (untracked freeze fixture; pin already checked)"
        )
    text = PACKAGE_LOCK.read_text(encoding="utf-8")
    assert "LOCKED=1" in text
    assert "forbid_run_id_gt=14" in text
    assert run_lock_blocks(PACKAGE_LOCK) is True
    info = parse_run_lock(PACKAGE_LOCK)
    assert info["locked"] is True
    assert info["forbid_run_id_gt"] == 14


def test_runner_refuses_without_token(tmp_path: Path) -> None:
    paths = _scratch_bundle(tmp_path)
    conn = sqlite3.connect(str(paths["db"]))
    before = conn.execute("SELECT COUNT(*) FROM telemetry_runs").fetchone()[0]
    conn.close()
    rc = runner_main(_argv(paths))
    assert rc == EXIT_CONTROL_PLANE
    conn = sqlite3.connect(str(paths["db"]))
    after = conn.execute("SELECT COUNT(*) FROM telemetry_runs").fetchone()[0]
    open_leases = conn.execute(
        "SELECT COUNT(*) FROM run_lease"
        " WHERE consumed_at IS NULL AND revoked_at IS NULL"
    ).fetchone()[0]
    conn.close()
    assert after == before
    assert open_leases == 0


def test_runner_refuses_when_lock_locked_token_untouched(tmp_path: Path) -> None:
    paths = _scratch_bundle(tmp_path)
    # Issue token first, then lock — start must refuse before claim.
    store = SQLiteShadowStorage.for_user(paths["data"], "shadow")
    conn = store._conn  # noqa: SLF001
    rid = next_run_id(conn)
    token = issue_token(conn, run_id=rid, ttl_s=120)
    store.close()
    paths["lock"].write_text(
        "LOCKED=1\nforbid_run_id_gt=14\n", encoding="utf-8"
    )
    rc = runner_main(_argv(paths))
    assert rc == EXIT_RUN_LOCK
    conn = sqlite3.connect(str(paths["db"]))
    row = conn.execute(
        "SELECT consumed_at, revoked_at FROM run_lease WHERE token=?",
        (token,),
    ).fetchone()
    runs = conn.execute("SELECT COUNT(*) FROM telemetry_runs").fetchone()[0]
    conn.close()
    assert row is not None
    assert row[0] is None  # not consumed
    assert row[1] is None
    assert runs == 0


def test_runner_refuses_tampered_trigger_manifest(tmp_path: Path) -> None:
    paths = _scratch_bundle(tmp_path)
    conn = sqlite3.connect(str(paths["db"]))
    conn.execute("DROP TRIGGER trg_run_lease_before_insert")
    conn.commit()
    # Keep schema_version stamped so we still enter control-plane path.
    ver = int(
        conn.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0]
    )
    assert ver == SCHEMA_CONTROL
    conn.close()
    rc = runner_main(_argv(paths))
    assert rc == EXIT_CONTROL_PLANE
    conn = sqlite3.connect(str(paths["db"]))
    assert conn.execute("SELECT COUNT(*) FROM telemetry_runs").fetchone()[0] == 0
    conn.close()


def test_runner_positive_claim_once_close_scratch(tmp_path: Path) -> None:
    paths = _scratch_bundle(tmp_path)
    store = SQLiteShadowStorage.for_user(paths["data"], "shadow")
    conn = store._conn  # noqa: SLF001
    rid = next_run_id(conn)
    tok = issue_token(conn, run_id=rid, ttl_s=120)
    store.close()
    paths["lock"].write_text("LOCKED=0\n", encoding="utf-8")
    rc = runner_main(_argv(paths, "--lease-token", tok))
    assert rc == 0
    conn = sqlite3.connect(str(paths["db"]))
    row = conn.execute(
        "SELECT run_id, status, closed_at FROM telemetry_runs WHERE run_id=?",
        (rid,),
    ).fetchone()
    lease = conn.execute(
        "SELECT consumed_at, revoked_at FROM run_lease WHERE run_id=?",
        (rid,),
    ).fetchone()
    conn.close()
    assert row is not None
    assert int(row[0]) == rid
    assert row[1] == "COMMITTED"
    assert row[2] is not None
    assert lease is not None
    assert lease[0] is not None  # consumed on claim
    assert lease[1] is None
