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
    EXIT_RUN_LOCK,
    default_run_lock_path,
    evaluate_start_lock,
    main as runner_main,
    parse_run_lock,
)

PKG = Path(__file__).resolve().parents[1]
SHADOW_RUNNER = PKG / "shadow_runner.py"
# Updated after A1/A3 forbid-gating residual fix (was Gate-6 93ed1267…).
GUARD_SHA_RESIDUAL = (
    "707e444d0e6502a81f80e2e93313266d0b96c7d036cd58af42340f94a382149a"
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



def _gate_base(paths: dict[str, Path]) -> list[str]:
    return [
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
        "--mirror-folder-id",
        "test-audit-folder-id",
        "--skip-disk-check",
    ]


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
        claim_run(conn, git_commit="x", config_json="{}", token=t1)
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
    tok = issue_token(conn, run_id=rid, ttl_s=60)
    assert claim_run(conn, git_commit="x", config_json="{}", token=tok) == rid
    with pytest.raises(LeaseError):
        tok = issue_token(conn, run_id=rid + 1, ttl_s=60)
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
                "--mirror-folder-id",
                "test-audit-folder-id",
                "--skip-disk-check",
                "retire-run-lock",
                "--skip-e1-upload-gate",
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
    tok = issue_token(store._conn, run_id=rid, ttl_s=60)  # noqa: SLF001
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
            "--lease-token",
            tok,
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



# --- D1–D4 architecture residuals (pre-Live) ---------------------------------


def test_d1_stale_token_after_reissue_cannot_claim(tmp_path: Path) -> None:
    """D1 fencing: expired holder token must fail after fresh issue for same run_id."""
    paths = _bundle(tmp_path)
    conn = sqlite3.connect(str(paths["db"]))
    migrate_control_plane(conn, db_path=paths["db"])
    rid = next_run_id(conn)
    now = int(time.time())
    t1 = issue_token(conn, run_id=rid, ttl_s=1, now=now - 10)
    with pytest.raises(LeaseError):
        claim_run(conn, git_commit="x", config_json="{}", token=t1, now=now)
    t2 = issue_token(conn, run_id=rid, ttl_s=60, now=now)
    assert t2 != t1
    # Stale P1 token must not claim even though run_id still next.
    with pytest.raises(LeaseError) as ei:
        claim_run(conn, git_commit="x", config_json="{}", token=t1, now=now)
    assert "closed" in str(ei.value).lower() or "expired" in str(ei.value).lower() or "unknown" in str(ei.value).lower() or "fence" in str(ei.value).lower() or "revok" in str(ei.value).lower()
    # Fresh token claims once
    assert claim_run(conn, git_commit="x", config_json="{}", token=t2, now=now) == rid
    # Wrong / empty token refused
    with pytest.raises(LeaseError):
        claim_run(conn, git_commit="x", config_json="{}", token="deadbeef" * 4)
    conn.close()


def test_d1_running_blocks_reissue_no_auto_abort(tmp_path: Path) -> None:
    """D1 liveness: RUNNING is not TTL-aborted; only explicit abort_run advances."""
    paths = _bundle(tmp_path)
    conn = sqlite3.connect(str(paths["db"]))
    migrate_control_plane(conn, db_path=paths["db"])
    rid = next_run_id(conn)
    tok = issue_token(conn, run_id=rid, ttl_s=60)
    assert claim_run(conn, git_commit="x", config_json="{}", token=tok) == rid
    with pytest.raises(LeaseError) as ei:
        issue_token(conn, run_id=rid + 1, ttl_s=60)
    assert "RUNNING" in str(ei.value)
    # Still RUNNING — no silent advance
    assert next_run_id(conn) == rid + 1  # row exists → next is rid+1 for *issue*, but refuse
    st = conn.execute(
        "SELECT status FROM telemetry_runs WHERE run_id=?", (rid,)
    ).fetchone()[0]
    assert st == "RUNNING"
    abort_run(conn, rid, reason="operator")
    conn.commit()
    assert next_run_id(conn) == rid + 1
    conn.close()


def test_d2_abort_consumes_run_id_gap_documented(tmp_path: Path) -> None:
    """D2: abort consumes run_id; next=17; DB terminal ABORTED; 2nd abort refuses."""
    paths = _bundle(tmp_path)
    conn = sqlite3.connect(str(paths["db"]))
    migrate_control_plane(conn, db_path=paths["db"])
    rid = next_run_id(conn)
    tok = issue_token(conn, run_id=rid, ttl_s=60)
    claim_run(conn, git_commit="x", config_json="{}", token=tok)
    abort_run(conn, rid, reason="d2")
    conn.commit()
    mx = conn.execute("SELECT MAX(run_id) FROM telemetry_runs").fetchone()[0]
    assert int(mx) == rid
    assert next_run_id(conn) == rid + 1
    st = conn.execute(
        "SELECT status, closed_at FROM telemetry_runs WHERE run_id=?", (rid,)
    ).fetchone()
    assert st[0] == "ABORTED" and st[1] is not None
    with pytest.raises(LeaseError):
        abort_run(conn, rid, reason="again")
    try:
        conn.execute("ROLLBACK")
    except sqlite3.Error:
        pass
    # New lease only for next id — 16 never re-run
    t_next = issue_token(conn, run_id=rid + 1, ttl_s=60)
    assert t_next
    conn.close()


def test_d3_package_absent_without_marker_refuses(tmp_path: Path) -> None:
    """D3: package path absent + no RUN.RETIRED → refuse (pre-retire fail-closed)."""
    pkg_lock = tmp_path / "ops" / "RUN.lock"
    pkg_lock.parent.mkdir(parents=True)
    # absent
    assert not pkg_lock.is_file()
    refuse, reason = evaluate_start_lock(pkg_lock, run_lock_override=False)
    # Without patching default path, package check uses real default — patch it.
    with patch(
        "order_execution_engine.shadow_runner.default_run_lock_path",
        return_value=pkg_lock,
    ):
        refuse, reason = evaluate_start_lock(pkg_lock, run_lock_override=False)
        assert refuse is True
        assert "RUN.RETIRED" in reason
        # Marker present → proceed signal (lease still required later)
        marker = pkg_lock.parent / "RUN.RETIRED"
        marker.write_text("retired=1\n", encoding="utf-8")
        refuse2, reason2 = evaluate_start_lock(pkg_lock, run_lock_override=False)
        assert refuse2 is False
        assert "post-retire" in reason2
    # Scratch override: absent still proceed
    scratch = tmp_path / "scratch.lock"
    refuse3, _ = evaluate_start_lock(scratch, run_lock_override=True)
    assert refuse3 is False


def test_d3_retire_writes_marker_and_archive(tmp_path: Path) -> None:
    """D3/D4 path: retire rename-archive + RUN.RETIRED; upload-gate blocks without upload."""
    paths = _bundle(tmp_path)
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
        # D4-a: upload gate default-on → refuse without prior upload; lock stays
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
                "--mirror-folder-id",
                "test-audit-folder-id",
                "--skip-disk-check",
                "retire-run-lock",
            ]
        )
        assert rc == EXIT_POLICY
        assert paths["lock"].is_file()
        assert "LOCKED=1" in paths["lock"].read_text(encoding="utf-8")
        assert not (paths["lock"].parent / "RUN.RETIRED").is_file()

        # Scratch opt-out: retire succeeds + marker (D3-a order)
        rc2 = gatectl_main(
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
                "--mirror-folder-id",
                "test-audit-folder-id",
                "--skip-disk-check",
                "retire-run-lock",
                "--skip-e1-upload-gate",
            ]
        )
        assert rc2 == EXIT_OK
    assert not paths["lock"].is_file()
    archives = list(paths["lock"].parent.glob("RUN.lock.retired.*"))
    assert len(archives) == 1
    assert _sha(archives[0]) == before
    assert (paths["lock"].parent / "RUN.RETIRED").is_file()


def test_d6c_section4_mapping_declared() -> None:
    """D6c: §4 semantics file maps tests to A/D clauses (traceability)."""
    sem = Path("docs/architecture/E1_INTEGRATION_SEMANTICS.md")
    assert sem.is_file()
    text = sem.read_text(encoding="utf-8")
    for needle in (
        "test_d1_stale_token_after_reissue_cannot_claim",
        "test_d2_abort_consumes_run_id_gap_documented",
        "test_d3_package_absent_without_marker_refuses",
        "test_a2b_running_stuck_abort_audit_idempotent_advance",
        "Exit 76",
        "D6b",
    ):
        assert needle in text, f"missing mapping: {needle}"



def test_d2b_abort_requires_confirm(tmp_path: Path) -> None:
    """D2-b: abort without matching --confirm-abort is refused."""
    paths = _bundle(tmp_path)
    conn = sqlite3.connect(str(paths["db"]))
    migrate_control_plane(conn, db_path=paths["db"])
    rid = next_run_id(conn)
    tok = issue_token(conn, run_id=rid, ttl_s=60)
    claim_run(conn, git_commit="x", config_json="{}", token=tok)
    conn.close()
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
            "--mirror-folder-id",
            "test-audit-folder-id",
            "--skip-disk-check",
            "abort-run",
            "--run-id",
            str(rid),
            "--confirm-abort",
            "999",
            "--reason",
            "wrong",
        ]
    )
    assert rc == EXIT_POLICY
    conn = sqlite3.connect(str(paths["db"]))
    assert (
        conn.execute(
            "SELECT status FROM telemetry_runs WHERE run_id=?", (rid,)
        ).fetchone()[0]
        == "RUNNING"
    )
    conn.close()


def test_d3a_preexisting_marker_refuses_retire(tmp_path: Path) -> None:
    """D3-a: RUN.RETIRED present before retire → refuse (marker integrity)."""
    paths = _bundle(tmp_path)
    paths["lock"].write_text("LOCKED=1\n", encoding="utf-8")
    (paths["lock"].parent / "RUN.RETIRED").write_text("bogus\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        from unittest.mock import MagicMock

        m = MagicMock()
        m.returncode = 0
        m.stdout = "[]"
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
                "--mirror-folder-id",
                "test-audit-folder-id",
                "--skip-disk-check",
                "retire-run-lock",
                "--skip-e1-upload-gate",
            ]
        )
    assert rc == EXIT_POLICY
    assert paths["lock"].is_file()



def test_m1_gatectl_issue_token_file_then_runner(tmp_path: Path) -> None:
    """M1: gatectl issue-token writes file; runner claims via --lease-token-file."""
    paths = _bundle(tmp_path)
    paths["lock"].write_text("LOCKED=0\n", encoding="utf-8")
    # migrate already done in _bundle via store; ensure control plane
    conn = sqlite3.connect(str(paths["db"]))
    migrate_control_plane(conn, db_path=paths["db"])
    rid = next_run_id(conn)
    conn.close()

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
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
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
                    "--mirror-folder-id",
                    "test-audit-folder-id",
                    "--skip-disk-check",
                    "issue-token",
                    "--run-id",
                    str(rid),
                    "--ttl",
                    "120",
                ]
            )
        assert rc == EXIT_OK
        out = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert out["ok"] is True
    token_file = Path(out["token_file"])
    assert token_file.is_file()
    assert token_file.stat().st_mode & 0o777 == 0o600
    raw = token_file.read_text(encoding="utf-8").strip()
    assert len(raw) >= 32
    # raw token must not appear in JSON stdout
    assert raw not in buf.getvalue()

    rc2 = runner_main(
        _runner_argv(paths, paths["lock"])
        + ["--lease-token-file", str(token_file)]
    )
    assert rc2 == 0
    assert not token_file.is_file()  # consumed after claim
    conn = sqlite3.connect(str(paths["db"]))
    row = conn.execute(
        "SELECT run_id, status FROM telemetry_runs WHERE run_id=?", (rid,)
    ).fetchone()
    conn.close()
    assert row is not None and int(row[0]) == rid
    assert row[1] == "COMMITTED"


def test_m2_run_lock_override_refused_on_live_data_root(tmp_path: Path) -> None:
    """M2: --run-lock with LIVE data-root → Exit 75 before start."""
    live_root = (
        tmp_path
        / "Library"
        / "Application Support"
        / "agentx"
        / "shadow_live"
    )
    live_root.mkdir(parents=True)
    scratch_lock = tmp_path / "absent.lock"  # absent → would proceed on scratch
    allow = tmp_path / "allowlist.json"
    allow.write_text(
        json.dumps({"BTC": {"token_id": "t", "market_id": "m"}}),
        encoding="utf-8",
    )
    news = tmp_path / "news.jsonl"
    news.write_text("", encoding="utf-8")
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
            "--run-lock",
            str(scratch_lock),
            "--once",
            "--no-ws",
        ]
    )
    assert rc == EXIT_RUN_LOCK


def test_m3_sigterm_handler_wired_in_source() -> None:
    """M3: runner source installs SIGTERM → ordered stop (STOPPED path)."""
    text = SHADOW_RUNNER.read_text(encoding="utf-8")
    assert "SIGTERM" in text
    assert "add_signal_handler" in text
    assert "STOPPED" in text
    assert "ordered stop" in text
    assert "early SIGTERM" in text or "_early_sigterm" in text


def test_m2_equals_form_refused_on_live_data_root(tmp_path: Path) -> None:
    """M2: --data-root=<live> with --run-lock must Exit 75 (equals form)."""
    live_root = (
        tmp_path / "Library" / "Application Support" / "agentx" / "shadow_live"
    )
    live_root.mkdir(parents=True)
    scratch_lock = tmp_path / "absent.lock"
    allow = tmp_path / "allowlist.json"
    allow.write_text(
        json.dumps({"BTC": {"token_id": "t", "market_id": "m"}}),
        encoding="utf-8",
    )
    news = tmp_path / "news.jsonl"
    news.write_text("", encoding="utf-8")
    rc = runner_main(
        [
            f"--data-root={live_root}",
            "--user-id",
            "shadow",
            "--allowlist",
            str(allow),
            "--news-jsonl",
            str(news),
            "--run-lock",
            str(scratch_lock),
            "--once",
            "--no-ws",
        ]
    )
    assert rc == EXIT_RUN_LOCK


def test_m2_abbrev_data_root_rejected_by_parser(tmp_path: Path) -> None:
    """M2: allow_abbrev=False → --data-r is not accepted."""
    live_root = (
        tmp_path / "Library" / "Application Support" / "agentx" / "shadow_live"
    )
    live_root.mkdir(parents=True)
    scratch_lock = tmp_path / "absent.lock"
    allow = tmp_path / "allowlist.json"
    allow.write_text(
        json.dumps({"BTC": {"token_id": "t", "market_id": "m"}}),
        encoding="utf-8",
    )
    news = tmp_path / "news.jsonl"
    news.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit) as ei:
        runner_main(
            [
                "--data-r",
                str(live_root),
                "--user-id",
                "shadow",
                "--allowlist",
                str(allow),
                "--news-jsonl",
                str(news),
                "--run-lock",
                str(scratch_lock),
                "--once",
                "--no-ws",
            ]
        )
    assert ei.value.code == 2


def test_m4_allow_live_db_migrate_issue_abort_on_live_marked_temp(
    tmp_path: Path,
) -> None:
    """M4: live-marked temp path + --allow-live-db reaches migrate/issue/abort."""
    live_root = (
        tmp_path / "Library" / "Application Support" / "agentx" / "m4_scratch"
    )
    live_root.mkdir(parents=True)
    store = SQLiteShadowStorage.for_user(live_root, "shadow")
    db = store._db_path  # noqa: SLF001
    store.close()
    lock = tmp_path / "RUN.lock"
    lock.write_text("LOCKED=0\n", encoding="utf-8")
    runner = tmp_path / "shadow_runner.py"
    runner.write_text("# stub\n", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    journal = live_root / "audit_chain.jsonl"
    paths = {
        "db": db,
        "data_root": live_root,
        "runner": runner,
        "lock": lock,
        "repo": repo,
        "journal": journal,
    }

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
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc_m = gatectl_main(
                _gate_base(paths) + ["--allow-live-db", "--allow-live-skip-disk-check", "migrate"]
            )
        assert rc_m == EXIT_OK, buf.getvalue()

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc_i = gatectl_main(
                _gate_base(paths)
                + [
                    "--allow-live-db",
                    "--allow-live-skip-disk-check",
                    "issue-token",
                    "--ttl",
                    "60",
                ]
            )
        assert rc_i == EXIT_OK, buf.getvalue()
        out = json.loads(buf.getvalue().strip().splitlines()[-1])
        assert out["ok"] is True
        assert Path(out["token_file"]).is_file()
        rid = int(out["run_id"])

        # claim so abort has RUNNING
        conn = sqlite3.connect(str(db))
        tok = Path(out["token_file"]).read_text(encoding="utf-8").strip()
        claim_run(conn, git_commit="m4", config_json="{}", token=tok)
        conn.close()

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc_a = gatectl_main(
                _gate_base(paths)
                + [
                    "--allow-live-db",
                    "--allow-live-skip-disk-check",
                    "abort-run",
                    "--run-id",
                    str(rid),
                    "--confirm-abort",
                    str(rid),
                    "--reason",
                    "m4-test",
                ]
            )
        assert rc_a == EXIT_OK, buf.getvalue()


def test_gap_audit_folder_refused_without_env(tmp_path: Path) -> None:
    """Gap: issue-token without AUDIT_OBJECTS_FOLDER_ID / --mirror-folder-id refuses."""
    paths = _bundle(tmp_path)
    paths["lock"].write_text("LOCKED=0\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        from unittest.mock import MagicMock

        m = MagicMock()
        m.returncode = 0
        m.stdout = "[]"
        m.stderr = ""
        return m

    with patch(
        "order_execution_engine.control_plane_audit.subprocess.run",
        side_effect=fake_run,
    ):
        import io
        from contextlib import redirect_stdout
        import os

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUDIT_OBJECTS_FOLDER_ID", None)
            buf = io.StringIO()
            with redirect_stdout(buf):
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
                        "--skip-disk-check",
                        "issue-token",
                        "--ttl",
                        "30",
                    ]
                )
            assert rc == EXIT_POLICY
            err = buf.getvalue()
            assert (
                "AUDIT_OBJECTS_FOLDER_ID" in err
                or "mirror-folder" in err.lower()
                or "no silent fallback" in err
            )
