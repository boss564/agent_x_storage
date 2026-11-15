"""Phase-2 scratch tests after H1–H4 hardening (K4 snapshot / mirror)."""

from __future__ import annotations

import hashlib
import json
import plistlib
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from order_execution_engine.control_plane_audit import (
    GENESIS_HASH,
    AppendOnlyAuditChain,
    AuditChainError,
    QuiescenceError,
    assert_db_writer_quiescent,
    build_snapshot_manifest,
    compute_control_plane_manifest_sha256,
    compute_logical_digest_sha256,
    expected_control_plane_manifest_sha256,
    mirror_audit_entry,
    mirror_audit_journal,
    token_sha256,
)
from order_execution_engine.control_plane_lease import (
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


def _quiet_snapshot(paths: dict[str, Path], **kwargs):
    kwargs.setdefault("check_disk_headroom", False)
    return build_snapshot_manifest(
        paths["db"],
        paths["runner"],
        paths["lock"],
        paths["repo"],
        check_quiescent=True,
        list_pids=lambda: [],
        snapshot_dir=paths["data_root"] / "snapshots",
        **kwargs,
    )


def test_h1_snapshot_hashes_backup_not_live_wal(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    m1 = _quiet_snapshot(paths)
    assert "artefact_sha256" in m1
    assert "logical_digest_sha256" in m1
    assert "db_sha256" not in m1  # live-file hash removed (H1)

    live_before = hashlib.sha256(paths["db"].read_bytes()).hexdigest()
    conn = connect_scratch(paths["db"])
    rid = next_run_id(conn)
    issue_token(conn, run_id=rid, ttl_s=60)
    conn.close()
    live_after = hashlib.sha256(paths["db"].read_bytes()).hexdigest()
    # WAL-mode: main file SHA often unchanged after commit (auditor finding).
    # Snapshot artefact / logical digest must still move.
    m2 = _quiet_snapshot(paths)
    assert m2["logical_digest_sha256"] != m1["logical_digest_sha256"] or (
        m2["artefact_sha256"] != m1["artefact_sha256"]
    )
    # Document H1: live file hash is not the signal we rely on.
    _ = live_before, live_after


def test_h2_pgrep_pattern_is_shadow_runner_without_py() -> None:
    from order_execution_engine import control_plane_audit as audit

    assert audit._RUNNER_PGREP_PATTERN == "shadow_runner"
    assert ".py" not in audit._RUNNER_PGREP_PATTERN


def test_h2_busy_runner_and_db_lock(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    with pytest.raises(QuiescenceError, match="still running"):
        build_snapshot_manifest(
            paths["db"],
            paths["runner"],
            paths["lock"],
            paths["repo"],
            check_quiescent=True,
            list_pids=lambda: ["99901"],
            snapshot_dir=paths["data_root"] / "snapshots",
            check_disk_headroom=False,
        )

    # Source lock held → refuse
    holder = sqlite3.connect(str(paths["db"]))
    holder.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(QuiescenceError, match="locked"):
            assert_db_writer_quiescent(paths["db"], busy_ms=30)
    finally:
        holder.execute("ROLLBACK")
        holder.close()


def test_h3_manifest_covers_index_and_matches_sollwert(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    conn = sqlite3.connect(str(paths["db"]))
    before = compute_control_plane_manifest_sha256(conn)
    expected = expected_control_plane_manifest_sha256()
    assert before == expected
    conn.execute("DROP INDEX ux_run_lease_open_run")
    conn.commit()
    after = compute_control_plane_manifest_sha256(conn)
    conn.close()
    assert after != before
    assert after != expected

    with pytest.raises(Exception, match="manifest mismatch"):
        _quiet_snapshot(paths, require_manifest_match=True)


def test_h4_mirror_is_immutable_per_entry(tmp_path: Path) -> None:
    journal = tmp_path / "audit_chain.jsonl"
    chain = AppendOnlyAuditChain(journal)
    fake = "b" * 64
    e1 = chain.append("one", fake, {"n": 1})
    e2 = chain.append("two", fake, {"n": 2})

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        calls.append(list(cmd))
        m = MagicMock()
        m.returncode = 0
        m.stdout = "[]" if cmd[1] == "lsjson" else ""
        m.stderr = ""
        return m

    remotes = mirror_audit_journal(
        journal, "gdrive:backup/audit_entries", run_rclone=fake_run
    )
    assert len(remotes) == 2
    copy_cmds = [c for c in calls if len(c) > 1 and c[1] == "copyto"]
    assert len(copy_cmds) == 2
    for cmd, entry in zip(copy_cmds, (e1, e2), strict=True):
        assert cmd[0] == "rclone"
        assert "--immutable" in cmd
        assert "--checksum" in cmd
        assert "--drive-root-folder-id" in cmd
        assert f"{entry['seq']:08d}_{entry['entry_hash']}.json" in cmd[3]

    # Existing remote with different content → refuse (H4; Drive ignores --immutable)
    def conflicting_run(cmd, **kwargs):  # noqa: ANN001
        m = MagicMock()
        if cmd[1] == "lsjson":
            m.returncode = 0
            m.stdout = '[{"Name":"x"}]'
        elif cmd[1] == "cat":
            m.returncode = 0
            m.stdout = '{"tampered":true}\n'
        else:
            m.returncode = 0
            m.stdout = ""
        m.stderr = ""
        return m

    with pytest.raises(AuditChainError, match="refuse overwrite"):
        mirror_audit_entry(
            e1, "gdrive:backup/audit_entries", run_rclone=conflicting_run
        )


def test_audit_chain_tamper_truncate_swap(tmp_path: Path) -> None:
    journal_path = tmp_path / "chain.jsonl"
    chain = AppendOnlyAuditChain(journal_path)
    fake = "a" * 64
    chain.append("one", fake, {"n": 1})
    chain.append("two", fake, {"n": 2})
    chain.append("three", fake, {"n": 3})
    assert chain.verify() == 3

    lines = journal_path.read_text(encoding="utf-8").splitlines()
    e0 = json.loads(lines[0])
    e0["payload"] = {"n": 999}
    lines[0] = json.dumps(e0, sort_keys=True, separators=(",", ":"))
    journal_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(AuditChainError):
        chain.verify()

    journal_path.write_text("", encoding="utf-8")
    chain = AppendOnlyAuditChain(journal_path)
    chain.append("one", fake, {"n": 1})
    chain.append("two", fake, {"n": 2})
    chain.append("three", fake, {"n": 3})
    lines = journal_path.read_text(encoding="utf-8").splitlines()
    journal_path.write_text(lines[0] + "\n" + lines[2] + "\n", encoding="utf-8")
    with pytest.raises(AuditChainError):
        chain.verify()

    journal_path.write_text("", encoding="utf-8")
    chain = AppendOnlyAuditChain(journal_path)
    chain.append("one", fake, {"n": 1})
    chain.append("two", fake, {"n": 2})
    lines = journal_path.read_text(encoding="utf-8").splitlines()
    journal_path.write_text(lines[1] + "\n" + lines[0] + "\n", encoding="utf-8")
    with pytest.raises(AuditChainError):
        chain.verify()
    assert GENESIS_HASH == "0" * 64


def test_gatectl_issue_token_intent_confirm_no_raw_token(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    remote = "gdrive:backup/audit_entries"

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        m = MagicMock()
        m.returncode = 0
        m.stdout = "[]" if len(cmd) > 1 and cmd[1] == "lsjson" else ""
        m.stderr = ""
        return m

    with patch(
        "order_execution_engine.control_plane_audit.subprocess.run",
        side_effect=fake_run,
    ), patch(
        "order_execution_engine.control_plane_audit._list_shadow_runner_pids",
        return_value=[],
    ):
        rc = gatectl_main(
            _argv(
                paths,
                "--mirror-remote",
                remote,
                "verify-snapshot",
            )
        )
        assert rc == EXIT_OK

        conn = sqlite3.connect(str(paths["db"]))
        rid = next_run_id(conn)
        conn.close()

        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = gatectl_main(
                _argv(
                    paths,
                    "--mirror-remote",
                    remote,
                    "issue-token",
                    "--run-id",
                    str(rid),
                    "--ttl",
                    "60",
                )
            )
        assert rc == EXIT_OK
        out = json.loads(buf.getvalue().strip().splitlines()[-1])
        assert "token" not in out
        assert "token_sha256" in out
        assert out["run_id"] == rid

    entries = AppendOnlyAuditChain(paths["journal"]).read_entries()
    actions = [e["action"] for e in entries]
    assert "issue_token_intent" in actions
    assert "issue_token_confirm" in actions
    confirm = [e for e in entries if e["action"] == "issue_token_confirm"][0]
    assert "token" not in confirm["payload"]
    assert len(confirm["payload"]["token_sha256"]) == 64


def test_gatectl_issue_token_fail_closed_revoke(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    remote = "gdrive:backup/audit_entries"

    def ok_run(cmd, **kwargs):  # noqa: ANN001
        m = MagicMock()
        m.returncode = 0
        m.stdout = "[]" if len(cmd) > 1 and cmd[1] == "lsjson" else ""
        m.stderr = ""
        return m

    with patch(
        "order_execution_engine.control_plane_audit.subprocess.run",
        side_effect=ok_run,
    ), patch(
        "order_execution_engine.control_plane_audit._list_shadow_runner_pids",
        return_value=[],
    ):
        assert (
            gatectl_main(
                _argv(paths, "--mirror-remote", remote, "verify-snapshot")
            )
            == EXIT_OK
        )
        conn = sqlite3.connect(str(paths["db"]))
        rid = next_run_id(conn)
        conn.close()

        real_append = AppendOnlyAuditChain.append
        calls = {"n": 0}

        def flaky_append(self, action, manifest_sha256, payload=None):  # noqa: ANN001
            calls["n"] += 1
            if action == "issue_token_confirm":
                raise AuditChainError("disk full")
            return real_append(self, action, manifest_sha256, payload)

        with patch.object(AppendOnlyAuditChain, "append", flaky_append):
            rc = gatectl_main(
                _argv(
                    paths,
                    "--mirror-remote",
                    remote,
                    "issue-token",
                    "--run-id",
                    str(rid),
                    "--ttl",
                    "60",
                )
            )
        assert rc == EXIT_POLICY

    conn = sqlite3.connect(str(paths["db"]))
    open_lease = conn.execute(
        "SELECT token FROM run_lease"
        " WHERE consumed_at IS NULL AND revoked_at IS NULL"
    ).fetchall()
    conn.close()
    assert open_lease == []


def test_allow_busy_only_on_status(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    # issue-token must not accept --allow-busy (argparse error → SystemExit)
    with pytest.raises(SystemExit):
        gatectl_main(
            _argv(
                paths,
                "--mirror-remote",
                "gdrive:x",
                "--allow-busy",
                "issue-token",
            )
        )


def test_retire_run_lock_refuses_package_lock(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    # Use real default lock path by pointing --lock at package lock → refuse
    pkg_lock = (
        Path(__file__).resolve().parents[1] / "ops" / "RUN.lock"
    )
    if not pkg_lock.is_file():
        pytest.skip("package RUN.lock absent in this tree")
    rc = gatectl_main(
        [
            "--db",
            str(paths["db"]),
            "--data-root",
            str(paths["data_root"]),
            "--runner",
            str(paths["runner"]),
            "--lock",
            str(pkg_lock),
            "--repo-root",
            str(paths["repo"]),
            "retire-run-lock",
        ]
    )
    assert rc == EXIT_POLICY

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        m = MagicMock()
        m.returncode = 0
        m.stdout = "[]" if len(cmd) > 1 and cmd[1] == "lsjson" else ""
        m.stderr = ""
        return m

    # Scratch lock can be retired (mirror mocked — default remote always set)
    with patch(
        "order_execution_engine.control_plane_audit.subprocess.run",
        side_effect=fake_run,
    ):
        rc = gatectl_main(_argv(paths, "retire-run-lock"))
    assert rc == EXIT_OK
    assert not paths["lock"].is_file()
    assert list(paths["lock"].parent.glob(paths["lock"].name + ".retired.*"))


def test_i1_logical_digest_sees_all_measurement_tables(tmp_path: Path) -> None:
    """I1: each measurement table / schema_meta / config_json moves the digest."""
    paths = _bundle(tmp_path)
    conn = connect_scratch(paths["db"])
    rid = next_run_id(conn)
    issue_token(conn, run_id=rid, ttl_s=60)
    assert claim_run(conn, git_commit="c", config_json="{}") == rid

    def digest() -> str:
        return compute_logical_digest_sha256(conn)

    # Lease-only change must NOT move the logical digest (run_lease excluded).
    before_lease = digest()
    conn.execute(
        "UPDATE telemetry_runs SET status = 'ABORTED',"
        " closed_at = CAST(strftime('%s', 'now') AS INTEGER)"
        " WHERE run_id = ?",
        (rid,),
    )
    # status/closed_at ARE digested — capture after terminalization
    after_abort = digest()
    assert after_abort != before_lease
    rid2 = next_run_id(conn)
    issue_token(conn, run_id=rid2, ttl_s=60)
    assert digest() == after_abort

    mutations: list[tuple[str, object]] = [
        (
            "schema_meta",
            lambda: conn.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value)"
                " VALUES ('digest_probe', '1')"
            ),
        ),
        (
            "telemetry_runs.config_json",
            lambda: conn.execute(
                "UPDATE telemetry_runs SET config_json = ?"
                " WHERE run_id = ?",
                ('{"probe":true}', rid),
            ),
        ),
        (
            "telemetry",
            lambda: conn.execute(
                "INSERT INTO telemetry"
                " (signal_id, latency_ms, approved, run_id)"
                " VALUES ('sig-1', 1.0, 1, ?)",
                (rid,),
            ),
        ),
        (
            "fills",
            lambda: conn.execute(
                "INSERT INTO fills"
                " (order_id, fill_idx, execution_price, executed_size,"
                "  slippage, fee, filled_at)"
                " VALUES ('o1', 0, '1', '1', '0', '0', 't')"
            ),
        ),
        (
            "portfolio_snapshots",
            lambda: conn.execute(
                "INSERT INTO portfolio_snapshots"
                " (taken_at, cash, start_balance, realized_pnl,"
                "  peak_equity, positions_json)"
                " VALUES ('t', '0', '0', '0', '0', '[]')"
            ),
        ),
        (
            "peak_events",
            lambda: conn.execute(
                "INSERT INTO peak_events"
                " (seq, raised_at, journal_pos, peak_equity, marks_json)"
                " VALUES (1, 't', 0, '0', '{}')"
            ),
        ),
        (
            "telemetry_fill_metrics",
            lambda: conn.execute(
                "INSERT INTO telemetry_fill_metrics"
                " (telemetry_seq, payload_json)"
                " VALUES ("
                "  (SELECT seq FROM telemetry ORDER BY seq LIMIT 1), '{}')"
            ),
        ),
        (
            "dispatched_signals",
            lambda: conn.execute(
                "INSERT INTO dispatched_signals (item_id, dispatched_at)"
                " VALUES ('item-1', 1.0)"
            ),
        ),
        (
            "bridge_discards",
            lambda: conn.execute(
                "INSERT INTO bridge_discards"
                " (item_id, reason, discarded_at)"
                " VALUES ('item-2', 'x', 1.0)"
            ),
        ),
        (
            "funnel_events",
            lambda: conn.execute(
                "INSERT INTO funnel_events (recorded_at, stage, run_id)"
                " VALUES (1.0, 'probe', ?)",
                (rid,),
            ),
        ),
    ]

    for label, mut in mutations:
        before = digest()
        mut()
        after = digest()
        assert after != before, f"digest unchanged after mutation: {label}"

    conn.close()


def test_i2_status_uses_temp_snapshot_verify_persists(tmp_path: Path) -> None:
    """I2: status leaves no artefact; verify-snapshot keeps one under data-root."""
    paths = _bundle(tmp_path)
    snap_dir = paths["data_root"] / "snapshots"

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        m = MagicMock()
        m.returncode = 0
        m.stdout = "[]" if len(cmd) > 1 and cmd[1] == "lsjson" else ""
        m.stderr = ""
        return m

    with patch(
        "order_execution_engine.control_plane_audit._list_shadow_runner_pids",
        return_value=[],
    ), patch(
        "order_execution_engine.control_plane_audit.subprocess.run",
        side_effect=fake_run,
    ):
        for _ in range(3):
            rc = gatectl_main(_argv(paths, "status", "--allow-busy"))
            # status may be non-OK if audit empty / schema checks — still must
            # not leave snapshot files.
            assert rc in (EXIT_OK, EXIT_POLICY)
        assert not snap_dir.exists() or list(snap_dir.glob("*.sqlite3")) == []

        rc = gatectl_main(
            _argv(paths, "--mirror-remote", "gdrive:backup/x", "verify-snapshot")
        )
        assert rc == EXIT_OK
        files = list(snap_dir.glob("*.sqlite3"))
        assert len(files) == 1

        # Second verify keeps artefacts (no auto-delete); count grows by one.
        rc = gatectl_main(
            _argv(paths, "--mirror-remote", "gdrive:backup/x", "verify-snapshot")
        )
        assert rc == EXIT_OK
        assert len(list(snap_dir.glob("*.sqlite3"))) == 2


def test_token_sha256_helper() -> None:
    assert token_sha256("abc") == hashlib.sha256(b"abc").hexdigest()


def test_shadow_runner_plist_daemon_off_until_e1() -> None:
    """Gate #3: repo LaunchAgent must not auto-start (no launchctl in test)."""
    plist_path = (
        Path(__file__).resolve().parents[1] / "ops" / "com.agentx.shadow-runner.plist"
    )
    with plist_path.open("rb") as fh:
        data = plistlib.load(fh)
    assert data.get("KeepAlive") is False
    assert data.get("RunAtLoad") is False
    assert "WatchPaths" not in data
    assert data.get("Label") == "com.agentx.shadow-runner"
