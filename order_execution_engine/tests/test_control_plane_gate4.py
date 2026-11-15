"""Gate #4 Lücken-Schnitt — Scratch-only coverage for all 8 building blocks."""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from order_execution_engine.control_plane_audit import (
    AppendOnlyAuditChain,
    AuditChainError,
    SnapshotError,
    assert_skip_disk_check_allowed,
    compute_jsonl_prefix_sha256,
    sha256_file_streaming,
    verify_audit_mirror,
)
from order_execution_engine.control_plane_lease import (
    LivePathRefused,
    claim_run,
    connect_scratch,
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


def _bundle(tmp_path: Path) -> dict[str, Path]:
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    store = SQLiteShadowStorage.for_user(data, "scratch")
    db_path = store._db_path  # noqa: SLF001
    migrate_control_plane(store._conn, db_path=db_path)  # noqa: SLF001
    store.close()
    runner = tmp_path / "shadow_runner.py"
    runner.write_text("# scratch stand-in\n", encoding="utf-8")
    lock = tmp_path / "RUN.lock"
    lock.write_text("LOCKED=1\nforbid_run_id_gt=14\n", encoding="utf-8")
    root = tmp_path / "data_root"
    root.mkdir()
    return {
        "db": db_path,
        "runner": runner,
        "lock": lock,
        "data_root": root,
        "journal": root / "audit_chain.jsonl",
        "repo": tmp_path,
    }


def _argv(paths: dict[str, Path], *extra: str) -> list[str]:
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
        "--skip-disk-check",
        *extra,
    ]


def _fake_rclone_ok(cmd, **kwargs):  # noqa: ANN001
    m = MagicMock()
    m.returncode = 0
    m.stdout = "[]" if len(cmd) > 1 and cmd[1] == "lsjson" else ""
    m.stderr = ""
    return m


# --- 1. Streaming digest -------------------------------------------------


def test_streaming_digest_matches_full_hash(tmp_path: Path) -> None:
    blob = tmp_path / "artefact.bin"
    blob.write_bytes(b"x" * (2 * 1024 * 1024 + 17))
    streamed = sha256_file_streaming(blob, chunk_size=64 * 1024)
    full = hashlib.sha256(blob.read_bytes()).hexdigest()
    assert streamed == full
    with pytest.raises(SnapshotError):
        sha256_file_streaming(blob, chunk_size=0)


# --- 2. Disk-space / --skip-disk-check -----------------------------------


def test_skip_disk_check_refuses_live_path_without_freigabe(
    tmp_path: Path,
) -> None:
    live = tmp_path / "Application Support" / "agentx" / "shadow.db"
    live.parent.mkdir(parents=True)
    live.write_text("x", encoding="utf-8")
    with pytest.raises(LivePathRefused, match="skip-disk-check"):
        assert_skip_disk_check_allowed(live, allow_live=False)
    assert_skip_disk_check_allowed(live, allow_live=True)  # Freigabe


def test_skip_disk_check_allows_scratch(tmp_path: Path) -> None:
    assert_skip_disk_check_allowed(tmp_path / "scratch.db", allow_live=False)


# --- 3. JSONL prefix SHA -------------------------------------------------


def test_jsonl_prefix_sha_stable_and_grows(tmp_path: Path) -> None:
    p = tmp_path / "news_scores.jsonl"
    line1 = '{"a":1}\n'
    line2 = '{"b":2}\n'
    p.write_text(line1 + line2, encoding="utf-8")
    pref = compute_jsonl_prefix_sha256(p, byte_length=len(line1.encode()))
    assert pref["byte_offset"] == 0
    assert pref["byte_length"] == len(line1.encode())
    assert pref["sha256"] == hashlib.sha256(line1.encode()).hexdigest()
    whole = compute_jsonl_prefix_sha256(p)
    assert whole["byte_length"] == p.stat().st_size
    assert whole["sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()
    with pytest.raises(SnapshotError):
        compute_jsonl_prefix_sha256(p, byte_offset=10_000)


# --- 4. verify-mirror ----------------------------------------------------


def test_verify_mirror_pass_and_mismatch(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    chain = AppendOnlyAuditChain(paths["journal"])
    e1 = chain.append("probe", "a" * 64, {"n": 1})
    remote_store: dict[str, str] = {}

    def run_upload(cmd, **kwargs):  # noqa: ANN001
        m = MagicMock()
        m.returncode = 0
        m.stderr = ""
        if cmd[1] == "lsjson":
            m.stdout = "[]"
        elif cmd[1] == "copyto":
            src = Path(cmd[2])
            remote = cmd[3]
            remote_store[remote] = src.read_text(encoding="utf-8")
            m.stdout = ""
        else:
            m.stdout = ""
        return m

    from order_execution_engine.control_plane_audit import mirror_audit_entry

    mirror_audit_entry(
        e1, "gdrive:gate4_test", run_rclone=run_upload
    )

    def run_verify(cmd, **kwargs):  # noqa: ANN001
        m = MagicMock()
        m.stderr = ""
        if cmd[1] == "cat":
            remote = cmd[2]
            if remote not in remote_store:
                m.returncode = 3
                m.stdout = ""
                return m
            m.returncode = 0
            m.stdout = remote_store[remote]
            return m
        m.returncode = 0
        m.stdout = "[]"
        return m

    ok = verify_audit_mirror(
        paths["journal"], "gdrive:gate4_test", run_rclone=run_verify
    )
    assert ok["entries"] == 1
    assert ok["checked"][0]["seq"] == 1

    # Tamper remote → refuse
    remote_store[next(iter(remote_store))] = '{"tampered":true}\n'
    with pytest.raises(AuditChainError, match="SHA mismatch"):
        verify_audit_mirror(
            paths["journal"], "gdrive:gate4_test", run_rclone=run_verify
        )


def test_gatectl_verify_mirror_cli(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    remote_store: dict[str, str] = {}

    def run_side(cmd, **kwargs):  # noqa: ANN001
        m = MagicMock()
        m.stderr = ""
        if cmd[1] == "lsjson":
            m.returncode = 0
            m.stdout = "[]"
        elif cmd[1] == "copyto":
            remote_store[cmd[3]] = Path(cmd[2]).read_text(encoding="utf-8")
            m.returncode = 0
            m.stdout = ""
        elif cmd[1] == "cat":
            if cmd[2] not in remote_store:
                m.returncode = 3
                m.stdout = ""
            else:
                m.returncode = 0
                m.stdout = remote_store[cmd[2]]
        else:
            m.returncode = 0
            m.stdout = ""
        return m

    with patch(
        "order_execution_engine.control_plane_audit.subprocess.run",
        side_effect=run_side,
    ), patch(
        "order_execution_engine.control_plane_audit._list_shadow_runner_pids",
        return_value=[],
    ):
        # Seed one mirrored entry via verify-snapshot
        rc = gatectl_main(
            _argv(paths, "--mirror-remote", "gdrive:gate4_vm", "verify-snapshot")
        )
        assert rc == EXIT_OK
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = gatectl_main(
                _argv(
                    paths, "--mirror-remote", "gdrive:gate4_vm", "verify-mirror"
                )
            )
        assert rc == EXIT_OK
        out = json.loads(buf.getvalue().strip().splitlines()[-1])
        assert out["ok"] is True
        assert out["entries"] >= 1


# --- 5. migrate ----------------------------------------------------------


def test_gatectl_migrate_idempotent_with_audit(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    with patch(
        "order_execution_engine.control_plane_audit.subprocess.run",
        side_effect=_fake_rclone_ok,
    ), patch(
        "order_execution_engine.control_plane_audit._list_shadow_runner_pids",
        return_value=[],
    ):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = gatectl_main(_argv(paths, "migrate"))
        assert rc == EXIT_OK
        out = json.loads(buf.getvalue().strip().splitlines()[-1])
        assert out["schema_version"] == 12
        assert out["audit_seq"] >= 1
        # Idempotent second call
        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = gatectl_main(_argv(paths, "migrate"))
        assert rc2 == EXIT_OK
    actions = [e["action"] for e in AppendOnlyAuditChain(paths["journal"]).read_entries()]
    assert actions.count("migrate") == 2


# --- 6. retire-run-lock --------------------------------------------------


def test_retire_scratch_ok_and_package_ops_refused(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    with patch(
        "order_execution_engine.control_plane_audit.subprocess.run",
        side_effect=_fake_rclone_ok,
    ):
        rc = gatectl_main(_argv(paths, "retire-run-lock", "--skip-e1-upload-gate"))
    assert rc == EXIT_OK
    assert not paths["lock"].is_file()  # renamed away (reversible archive)
    archives = list(paths["lock"].parent.glob(paths["lock"].name + ".retired.*"))
    assert len(archives) == 1
    assert "LOCKED=1" in archives[0].read_text(encoding="utf-8")
    entries = AppendOnlyAuditChain(paths["journal"]).read_entries()
    retire = [e for e in entries if e["action"] == "retire_run_lock"]
    assert len(retire) == 1
    assert retire[0]["payload"]["before_sha256"]
    assert retire[0]["payload"]["after_state"] == "absent"

    # Fake lock under package ops/ must be refused (TABU path)
    ops = Path(__file__).resolve().parents[1] / "ops"
    decoy = ops / f".scratch_retire_decoy_{tmp_path.name}.lock"
    try:
        decoy.write_text("LOCKED=1\n", encoding="utf-8")
        rc = gatectl_main(
            [
                "--db",
                str(paths["db"]),
                "--data-root",
                str(paths["data_root"]),
                "--runner",
                str(paths["runner"]),
                "--lock",
                str(decoy),
                "--repo-root",
                str(paths["repo"]),
                "--journal",
                str(paths["journal"]),
                "retire-run-lock",
            ]
        )
        assert rc == EXIT_POLICY
    finally:
        if decoy.exists():
            decoy.unlink()


# --- 7. abort-run --------------------------------------------------------


def test_abort_run_atomic_and_audit_rollback(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    conn = connect_scratch(paths["db"])
    rid = next_run_id(conn)
    tok = issue_token(conn, run_id=rid, ttl_s=60)
    assert claim_run(conn, git_commit="c", config_json="{}", token=tok) == rid
    conn.close()

    with patch(
        "order_execution_engine.control_plane_audit.subprocess.run",
        side_effect=_fake_rclone_ok,
    ):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = gatectl_main(
                _argv(
                    paths,
                    "abort-run",
                    "--run-id",
                    str(rid),
                    "--confirm-abort",
                    str(rid),
                    "--reason",
                    "gate4",
                )
            )
        assert rc == EXIT_OK
        out = json.loads(buf.getvalue().strip().splitlines()[-1])
        assert out["run_id"] == rid
        assert out["reason"] == "gate4"

    conn = connect_scratch(paths["db"])
    row = conn.execute(
        "SELECT status FROM telemetry_runs WHERE run_id=?", (rid,)
    ).fetchone()
    assert row["status"] == "ABORTED"
    open_leases = conn.execute(
        "SELECT COUNT(*) FROM run_lease"
        " WHERE run_id=? AND consumed_at IS NULL AND revoked_at IS NULL",
        (rid,),
    ).fetchone()[0]
    conn.close()
    assert open_leases == 0

    # Fail-closed: audit error rolls back DB change
    paths2 = _bundle(tmp_path / "rollback")
    conn = connect_scratch(paths2["db"])
    rid2 = next_run_id(conn)
    tok = issue_token(conn, run_id=rid2, ttl_s=60)
    assert claim_run(conn, git_commit="c", config_json="{}", token=tok) == rid2
    conn.close()

    real_append = AppendOnlyAuditChain.append

    def boom(self, action, manifest_sha256, payload=None):  # noqa: ANN001
        if action == "abort_run":
            raise AuditChainError("disk full")
        return real_append(self, action, manifest_sha256, payload)

    with patch.object(AppendOnlyAuditChain, "append", boom):
        rc = gatectl_main(
            _argv(
                paths2,
                "abort-run",
                "--run-id",
                str(rid2),
                "--confirm-abort",
                str(rid2),
                "--reason",
                "x",
            )
        )
    assert rc == EXIT_POLICY
    conn = connect_scratch(paths2["db"])
    st = conn.execute(
        "SELECT status FROM telemetry_runs WHERE run_id=?", (rid2,)
    ).fetchone()["status"]
    conn.close()
    assert st == "RUNNING"  # rolled back


# --- 8. post-run-check --run-id ------------------------------------------


def test_post_run_check_run_id_pass_and_fail(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    conn = connect_scratch(paths["db"])
    rid = next_run_id(conn)
    tok = issue_token(conn, run_id=rid, ttl_s=60)
    assert claim_run(conn, git_commit="c", config_json="{}", token=tok) == rid
    conn.close()

    news = paths["data_root"] / "news_scores.jsonl"
    news.write_text('{"s":1}\n{"s":2}\n', encoding="utf-8")

    with patch(
        "order_execution_engine.control_plane_audit.subprocess.run",
        side_effect=_fake_rclone_ok,
    ), patch(
        "order_execution_engine.control_plane_audit._list_shadow_runner_pids",
        return_value=[],
    ):
        # Still RUNNING → fail
        rc = gatectl_main(
            _argv(paths, "post-run-check", "--run-id", str(rid))
        )
        assert rc == EXIT_POLICY

        # Abort then PASS
        assert (
            gatectl_main(
                _argv(
                    paths,
                    "abort-run",
                    "--run-id",
                    str(rid),
                    "--confirm-abort",
                    str(rid),
                    "--reason",
                    "done",
                )
            )
            == EXIT_OK
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = gatectl_main(
                _argv(
                    paths,
                    "--news-jsonl",
                    str(news),
                    "post-run-check",
                    "--run-id",
                    str(rid),
                )
            )
        assert rc == EXIT_OK
        out = json.loads(buf.getvalue().strip().splitlines()[-1])
        assert out["verdict"] == "PASS"
        assert out["run_id"] == rid
        assert out["news_jsonl_prefix"]["sha256"]
        assert len(out["runner_sha256"]) == 64
