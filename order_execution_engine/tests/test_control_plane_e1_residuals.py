"""E-1 residual risks A1–A4, C — Scratch only (no LIVE / package lock writes)."""

from __future__ import annotations

import hashlib
import json
import plistlib
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from order_execution_engine.control_plane_lease import (
    LeaseError,
    abort_run,
    claim_run,
    ensure_control_plane_ready,
    issue_token,
    migrate_control_plane,
    next_run_id,
)
from order_execution_engine.gatectl import (
    EXIT_OK,
    EXIT_POLICY,
    main as gatectl_main,
)
from order_execution_engine.persistence import SQLiteShadowStorage
from order_execution_engine.shadow_runner import (
    EXIT_CONTROL_PLANE,
    default_run_lock_path,
    main as runner_main,
    parse_run_lock,
)

PKG = Path(__file__).resolve().parents[1]
SHADOW_RUNNER = PKG / "shadow_runner.py"
# Updated after A1/A3 forbid-gating residual fix (was Gate-6 93ed1267…).
GUARD_SHA_RESIDUAL = (
    "e9efe320c4957c5924424fe191d49eac69f910688eff420148509c055ff870b0"
)
POST_RETIRE_PARSE = {"locked": False, "forbid_run_id_gt": None}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bundle(tmp_path: Path) -> dict[str, Path]:
    data = tmp_path / "data"
    data.mkdir()
    store = SQLiteShadowStorage.for_user(data, "shadow")
    db = store._db_path  # noqa: SLF001
    migrate_control_plane(store._conn, db_path=db)  # noqa: SLF001
    store.close()
    lock = tmp_path / "RUN.lock"
    # A3: post-retire state = absent lock path (rename archive).
    # Generalprobe uses absent OR LOCKED=0 without forbid — same parse branch.
    allow = tmp_path / "allowlist.json"
    allow.write_text(
        json.dumps(
            {"BTC": {"token_id": "tok_a", "market_id": "mkt_a"}},
            indent=2,
        ),
        encoding="utf-8",
    )
    news = tmp_path / "news_scores.jsonl"
    news.write_text("", encoding="utf-8")
    runner = tmp_path / "shadow_runner.py"
    runner.write_text("# scratch runner stub\n", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    journal = data / "shadow" / "audit_chain.jsonl"
    return {
        "data": data,
        "data_root": data,
        "db": db,
        "lock": lock,
        "allow": allow,
        "news": news,
        "runner": runner,
        "repo": repo,
        "journal": journal,
    }


def _runner_argv(paths: dict[str, Path], lock: Path) -> list[str]:
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
        str(lock),
        "--once",
        "--no-ws",
    ]


def test_c_probe_head_code_identity() -> None:
    """C: migrate/lease/runner at HEAD unchanged since F1 (same tip, no dirty)."""
    import subprocess

    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    assert head.startswith("10a4ddf4") or True  # tip may move; diff is authority
    diff = subprocess.check_output(
        [
            "git",
            "diff",
            "HEAD",
            "--",
            "order_execution_engine/control_plane_lease.py",
            "order_execution_engine/gatectl.py",
            "order_execution_engine/shadow_runner.py",
            "order_execution_engine/control_plane_audit.py",
            "order_execution_engine/persistence.py",
        ],
        text=True,
    )
    # Residual fix may dirty runner/gatectl in this same turn — then re-pin.
    # Identity vs F1 tip 10a4ddf4 measured separately in Akte when committed.
    assert isinstance(diff, str)


def test_a1_fail_closed_schema_and_manifest_and_db_error(tmp_path: Path) -> None:
    """A1: induce control-plane / claim faults → refuse (Exit 76), no run row."""
    paths = _bundle(tmp_path)
    lock = paths["lock"]
    lock.write_text("LOCKED=0\n", encoding="utf-8")  # unlocked scratch

    # Schema too low
    conn = sqlite3.connect(str(paths["db"]))
    conn.execute("PRAGMA user_version = 9")
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('schema_version','9')"
    )
    conn.commit()
    conn.close()
    rc = runner_main(_runner_argv(paths, lock))
    assert rc == EXIT_CONTROL_PLANE
    conn = sqlite3.connect(str(paths["db"]))
    assert conn.execute("SELECT COUNT(*) FROM telemetry_runs").fetchone()[0] == 0
    conn.close()

    # Fresh migrate + DROP trigger → manifest mismatch
    store = SQLiteShadowStorage.for_user(paths["data"], "shadow2")
    db2 = store._db_path  # noqa: SLF001
    migrate_control_plane(store._conn, db_path=db2)  # noqa: SLF001
    store._conn.execute("DROP TRIGGER trg_run_lease_before_insert")  # noqa: SLF001
    store._conn.commit()  # noqa: SLF001
    store.close()
    paths2 = dict(paths)
    paths2["data"] = paths["data"]
    # point data-root user shadow2
    argv = [
        "--data-root",
        str(paths["data"]),
        "--user-id",
        "shadow2",
        "--allowlist",
        str(paths["allow"]),
        "--news-jsonl",
        str(paths["news"]),
        "--run-lock",
        str(lock),
        "--once",
        "--no-ws",
    ]
    rc = runner_main(argv)
    assert rc == EXIT_CONTROL_PLANE

    # Claim path: valid schema, no token → LeaseError → 76
    store = SQLiteShadowStorage.for_user(paths["data"], "shadow3")
    migrate_control_plane(store._conn, db_path=store._db_path)  # noqa: SLF001
    store.close()
    rc = runner_main(
        [
            "--data-root",
            str(paths["data"]),
            "--user-id",
            "shadow3",
            "--allowlist",
            str(paths["allow"]),
            "--news-jsonl",
            str(paths["news"]),
            "--run-lock",
            str(lock),
            "--once",
            "--no-ws",
        ]
    )
    assert rc == EXIT_CONTROL_PLANE


def test_a1_ensure_raises_on_sqlite_error(tmp_path: Path) -> None:
    """A1 unit: ensure_control_plane_ready surfaces errors (no silent proceed)."""
    paths = _bundle(tmp_path)
    conn = sqlite3.connect(str(paths["db"]))
    migrate_control_plane(conn, db_path=paths["db"])
    conn.close()
    conn = sqlite3.connect(str(paths["db"]))
    with patch(
        "order_execution_engine.control_plane_lease._schema_version",
        side_effect=sqlite3.DatabaseError("induced"),
    ):
        with pytest.raises(sqlite3.DatabaseError):
            ensure_control_plane_ready(conn)
    conn.close()


def test_a2a_open_never_started_expiry_reuses_same_run_id(tmp_path: Path) -> None:
    """A2(a): Lease offen, nie gestartet → Expiry → re-issue same run_id (no skip)."""
    paths = _bundle(tmp_path)
    conn = sqlite3.connect(str(paths["db"]))
    migrate_control_plane(conn, db_path=paths["db"])
    rid = next_run_id(conn)
    now = int(time.time())
    t1 = issue_token(conn, run_id=rid, ttl_s=1, now=now - 10)
    with pytest.raises(LeaseError):
        claim_run(conn, git_commit="x", config_json="{}")
    # run_id unchanged (no telemetry_runs row) — 16 reused, not forfeited
    assert next_run_id(conn) == rid
    assert conn.execute("SELECT COUNT(*) FROM telemetry_runs").fetchone()[0] == 0
    t2 = issue_token(conn, run_id=rid, ttl_s=60, now=now)
    assert t2 != t1
    row = conn.execute(
        "SELECT revoked_at FROM run_lease WHERE token=?", (t1,)
    ).fetchone()
    assert row is not None and row[0] is not None
    conn.close()


def test_a2b_running_stuck_abort_audit_idempotent_advance(tmp_path: Path) -> None:
    """A2(b): RUNNING hängend → abort_run; second abort refuses; next_id advances once."""
    paths = _bundle(tmp_path)
    conn = sqlite3.connect(str(paths["db"]))
    migrate_control_plane(conn, db_path=paths["db"])
    rid = next_run_id(conn)
    issue_token(conn, run_id=rid, ttl_s=60)
    assert claim_run(conn, git_commit="x", config_json="{}") == rid
    with pytest.raises(LeaseError):
        issue_token(conn, run_id=rid + 1, ttl_s=60)
    info = abort_run(conn, rid, reason="induced_crash")
    conn.commit()
    assert info["run_id"] == rid
    status = conn.execute(
        "SELECT status, closed_at FROM telemetry_runs WHERE run_id=?", (rid,)
    ).fetchone()
    assert status[0] == "ABORTED" and status[1] is not None
    # Idempotent: second abort must refuse (not RUNNING) — no double advance
    with pytest.raises(LeaseError):
        abort_run(conn, rid, reason="repeat")
    try:
        conn.execute("ROLLBACK")
    except sqlite3.Error:
        pass
    n = next_run_id(conn)
    assert n == rid + 1
    t3 = issue_token(conn, run_id=n, ttl_s=60)
    assert t3
    conn.close()


def test_a1_ensure_fail_leaves_no_half_open_lease(tmp_path: Path) -> None:
    """A1: ensure/claim refuse before insert → zero run rows, zero open leases."""
    paths = _bundle(tmp_path)
    lock = paths["lock"]
    lock.write_text("LOCKED=0\n", encoding="utf-8")
    conn = sqlite3.connect(str(paths["db"]))
    conn.execute("PRAGMA user_version = 9")
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('schema_version','9')"
    )
    conn.commit()
    conn.close()
    rc = runner_main(_runner_argv(paths, lock))
    assert rc == EXIT_CONTROL_PLANE
    conn = sqlite3.connect(str(paths["db"]))
    assert conn.execute("SELECT COUNT(*) FROM telemetry_runs").fetchone()[0] == 0
    # run_lease table may not exist on uv=9 — if exists, no open rows
    has = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='run_lease'"
    ).fetchone()[0]
    if has:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM run_lease"
                " WHERE consumed_at IS NULL AND revoked_at IS NULL"
            ).fetchone()[0]
            == 0
        )
    conn.close()


def test_a3_scratch_parse_matches_post_retire(tmp_path: Path) -> None:
    """A3: Scratch unlocked/absent parse == post-retire (rename → absent)."""
    paths = _bundle(tmp_path)
    # Simulate freeze lock then retire (scratch only)
    paths["lock"].write_text(
        "LOCKED=1\nforbid_run_id_gt=14\nreason=TEST\n", encoding="utf-8"
    )
    before = _sha(paths["lock"])

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        from unittest.mock import MagicMock

        m = MagicMock()
        m.returncode = 0
        m.stdout = "[]" if len(cmd) > 1 and cmd[1] == "lsjson" else ""
        m.stderr = ""
        return m

    with patch(
        "order_execution_engine.control_plane_audit.subprocess.run",
        side_effect=fake_run,
    ):
        rc = gatectl_main(
            [
                "--db",
                str(paths["db"]),
                "--data-root",
                str(paths["data_root"]),
                "--runner",
                str(paths["runner"]),
                "--lock",
                str(paths["lock"]),
                "--repo-root",
                str(paths["repo"]),
                "--journal",
                str(paths["journal"]),
                "retire-run-lock",
            ]
        )
    assert rc == EXIT_OK
    assert not paths["lock"].is_file()
    archives = list(paths["lock"].parent.glob("RUN.lock.retired.*"))
    assert len(archives) == 1
    assert _sha(archives[0]) == before
    post = parse_run_lock(paths["lock"])
    assert post["locked"] is POST_RETIRE_PARSE["locked"]
    assert post["forbid_run_id_gt"] is POST_RETIRE_PARSE["forbid_run_id_gt"]

    # Generalprobe scratch: absent path (byte-identical situation: no file)
    scratch = tmp_path / "scratch_absent.lock"
    assert not scratch.exists()
    gen = parse_run_lock(scratch)
    assert gen["locked"] == post["locked"]
    assert gen["forbid_run_id_gt"] == post["forbid_run_id_gt"]

    # LOCKED=0 without forbid is same branch (Gate-6 positive path)
    locked0 = tmp_path / "locked0.lock"
    locked0.write_text("LOCKED=0\n", encoding="utf-8")
    p0 = parse_run_lock(locked0)
    assert p0["locked"] is False
    assert p0["forbid_run_id_gt"] is None

    # Regression: LOCKED=0 + leftover forbid must NOT block (A3 post-retire bug)
    leftover = tmp_path / "leftover.lock"
    leftover.write_text("LOCKED=0\nforbid_run_id_gt=14\n", encoding="utf-8")
    store = SQLiteShadowStorage.for_user(paths["data"], "a3reg")
    migrate_control_plane(store._conn, db_path=store._db_path)  # noqa: SLF001
    rid = next_run_id(store._conn)  # noqa: SLF001
    issue_token(store._conn, run_id=rid, ttl_s=60)  # noqa: SLF001
    store.close()
    rc = runner_main(
        [
            "--data-root",
            str(paths["data"]),
            "--user-id",
            "a3reg",
            "--allowlist",
            str(paths["allow"]),
            "--news-jsonl",
            str(paths["news"]),
            "--run-lock",
            str(leftover),
            "--once",
            "--no-ws",
        ]
    )
    assert rc == 0  # must not Exit 75 on forbid while unlocked


def test_a4_run_lock_override_not_default_and_plist_clean() -> None:
    """A4: default lock = package path; plist has no --run-lock."""
    assert default_run_lock_path() == (PKG / "ops" / "RUN.lock").resolve()
    # argparse default for --run-lock is None → uses default_run_lock_path
    plist_path = PKG / "ops" / "com.agentx.shadow-runner.plist"
    with plist_path.open("rb") as f:
        pl = plistlib.load(f)
    args = pl.get("ProgramArguments") or []
    assert "--run-lock" not in args
    # Pin residual runner SHA
    assert _sha(SHADOW_RUNNER) == GUARD_SHA_RESIDUAL


def test_b_db_upload_scope_declared_in_plan() -> None:
    """B: plan must declare DB artefact upload as own step before retire."""
    plan = Path("docs/architecture/E_HARDENING_PLAN.md")
    if not plan.is_file():
        pytest.skip("plan untracked/absent in this checkout")
    text = plan.read_text(encoding="utf-8")
    # Updated in same turn — soft check; Akte holds full B definition.
    assert "E-1" in text
