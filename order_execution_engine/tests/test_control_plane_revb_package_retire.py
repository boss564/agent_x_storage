"""Rev. B / N1–N2: RO status, package retire, L4 TTY+nonce, no GATECTL_PACKAGE_ROOT."""

from __future__ import annotations

import hashlib
import io
import json
import os
import pty
import re
import select
import shutil
import sqlite3
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from order_execution_engine.control_plane_audit import AppendOnlyAuditChain
from order_execution_engine.control_plane_lease import (
    SCHEMA_CONTROL,
    connect_scratch,
    issue_token,
    migrate_control_plane,
)
from order_execution_engine.gatectl import (
    EXIT_OK,
    EXIT_POLICY,
    _is_package_lock,
    _package_root,
    _real_lock_path,
    main as gatectl_main,
)
from order_execution_engine.persistence import SQLiteShadowStorage

REPO = Path(__file__).resolve().parents[2]
PKG_SRC = Path(__file__).resolve().parents[1]


def _fake_rclone_ok(cmd, **kwargs):  # noqa: ANN001
    m = MagicMock()
    m.returncode = 0
    m.stdout = "[]" if len(cmd) > 1 and cmd[1] == "lsjson" else ""
    m.stderr = ""
    return m


def _fake_rclone_fail(cmd, **kwargs):  # noqa: ANN001
    m = MagicMock()
    m.returncode = 1
    m.stdout = ""
    m.stderr = "mirror unreachable (test)"
    return m


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _v9_live_marked(tmp_path: Path) -> dict[str, Path]:
    live_root = tmp_path / "Library" / "Application Support" / "agentx" / "shadow"
    live_root.mkdir(parents=True)
    db = live_root / "shadow.db"
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA user_version = 9")
    conn.execute(
        "CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO schema_meta(key, value) VALUES ('schema_version', '9')"
    )
    conn.execute(
        "CREATE TABLE telemetry_runs ("
        "run_id INTEGER PRIMARY KEY, status TEXT, started_at REAL, closed_at REAL,"
        "git_commit TEXT, config_json TEXT)"
    )
    conn.commit()
    conn.close()
    runner = tmp_path / "shadow_runner.py"
    runner.write_text("# stand-in\n", encoding="utf-8")
    lock = tmp_path / "RUN.lock"
    lock.write_text("LOCKED=1\nforbid_run_id_gt=14\n", encoding="utf-8")
    data_root = tmp_path / "data_root"
    data_root.mkdir()
    return {
        "db": db,
        "runner": runner,
        "lock": lock,
        "data_root": data_root,
        "journal": data_root / "audit_chain.jsonl",
        "repo": tmp_path,
    }


def _scratch_migrated(tmp_path: Path) -> dict[str, Path]:
    data = tmp_path / "data"
    data.mkdir(parents=True)
    store = SQLiteShadowStorage.for_user(data, "scratch")
    db_path = store._db_path  # noqa: SLF001
    migrate_control_plane(store._conn, db_path=db_path)  # noqa: SLF001
    store.close()
    runner = tmp_path / "shadow_runner.py"
    runner.write_text("# stand-in\n", encoding="utf-8")
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
        "--mirror-folder-id",
        "test-audit-folder-id",
        "--skip-disk-check",
        *extra,
    ]


def _pkg_copy(tmp_path: Path) -> dict[str, Path]:
    """Temp package with copied gatectl.py so ``__file__`` defines package ops/."""
    pkg = tmp_path / "order_execution_engine"
    pkg.mkdir()
    shutil.copy2(PKG_SRC / "gatectl.py", pkg / "gatectl.py")
    # Minimal package surface for imports via PYTHONPATH=REPO
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    ops = pkg / "ops"
    ops.mkdir()
    lock = ops / "RUN.lock"
    lock.write_text("LOCKED=1\nforbid_run_id_gt=14\n", encoding="utf-8")
    shutil.copy2(PKG_SRC / "shadow_runner.py", pkg / "shadow_runner.py")
    data = tmp_path / "data"
    data.mkdir()
    store = SQLiteShadowStorage.for_user(data, "scratch")
    db_path = store._db_path  # noqa: SLF001
    migrate_control_plane(store._conn, db_path=db_path)  # noqa: SLF001
    store.close()
    root = tmp_path / "data_root"
    root.mkdir()
    journal = AppendOnlyAuditChain(root / "audit_chain.jsonl")
    conn = connect_scratch(db_path)
    from order_execution_engine.control_plane_audit import (
        compute_logical_digest_sha256,
    )

    dig = compute_logical_digest_sha256(conn)
    conn.close()
    journal.append(
        "db_artefact_upload",
        dig,
        {"ok": True, "sha256": dig, "logical_digest_sha256": dig},
    )
    return {
        "pkg": pkg,
        "gatectl": pkg / "gatectl.py",
        "db": db_path,
        "runner": pkg / "shadow_runner.py",
        "lock": lock,
        "data_root": root,
        "journal": root / "audit_chain.jsonl",
        "repo": tmp_path,
    }


def _run_copied_gatectl(
    pkg_paths: dict[str, Path],
    *extra: str,
    rclone_side_effect=_fake_rclone_ok,
    answer_challenge: bool = True,
) -> tuple[int, dict, str]:
    """Run copied gatectl.py under a PTY; answer L4 challenge when present."""
    argv = [
        sys.executable,
        str(pkg_paths["gatectl"]),
        "--db",
        str(pkg_paths["db"]),
        "--data-root",
        str(pkg_paths["data_root"]),
        "--runner",
        str(pkg_paths["runner"]),
        "--lock",
        str(pkg_paths["lock"]),
        "--repo-root",
        str(pkg_paths["repo"]),
        "--journal",
        str(pkg_paths["journal"]),
        "--mirror-folder-id",
        "test-audit-folder-id",
        "--skip-disk-check",
        "--mirror-remote",
        "gdrive:revb_test",
        *extra,
    ]
    env = {**os.environ, "PYTHONPATH": str(REPO), "AUDIT_OBJECTS_FOLDER_ID": "test-audit-folder-id"}
    # Patch rclone inside the child by injecting sitecustomize? Simpler: mock via
    # env flag not available. Use unit-test path that imports after chdir…
    # For subprocess we patch by wrapping: run via python -c that patches then main.
    # Prefer: importlib run with __file__ spoof is hard. Keep subprocess + real rclone
    # fail for unreachable; for success patch by running in-process with renamed module.
    #
    # In-process: exec gatectl source with manipulated globals __file__.
    code = pkg_paths["gatectl"].read_text(encoding="utf-8")
    # Ensure child sees package root = pkg: run as __main__ with __file__ set.
    ns: dict = {"__name__": "__main__", "__file__": str(pkg_paths["gatectl"])}
    # Build argv for main()
    main_argv = argv[2:]  # drop python and script path

    master, slave = pty.openpty()
    pid = os.fork()
    if pid == 0:
        os.close(master)
        os.dup2(slave, 0)
        os.dup2(slave, 1)
        os.dup2(slave, 2)
        os.close(slave)
        os.environ.update(env)
        sys.path.insert(0, str(REPO))
        # Patch rclone before importing gatectl as the script file
        import order_execution_engine.control_plane_audit as audit_mod
        import order_execution_engine.gatectl as gmod

        # Re-bind package root by running the COPIED file as the gatectl module
        # identity: load copied source into a fresh module named gatectl_copy
        import types

        mod = types.ModuleType("gatectl_copy")
        mod.__file__ = str(pkg_paths["gatectl"])
        sys.modules["gatectl_copy"] = mod
        with patch.object(audit_mod, "subprocess") as sp_a, patch(
            "subprocess.run", side_effect=rclone_side_effect
        ):
            sp_a.run.side_effect = rclone_side_effect
            exec(compile(code, str(pkg_paths["gatectl"]), "exec"), mod.__dict__)
            # Override list_pids
            mod._list_shadow_runner_pids = lambda: []  # noqa: E731
            try:
                rc = int(mod.main(main_argv))
            except SystemExit as exc:
                rc = int(exc.code or 0)
        os._exit(rc)

    os.close(slave)
    buf = b""
    answered = False
    deadline = time.time() + 30
    while time.time() < deadline:
        r, _, _ = select.select([master], [], [], 0.2)
        if r:
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            if answer_challenge and not answered:
                text = buf.decode("utf-8", errors="replace")
                m = re.search(r"Type exactly: (\S+)", text)
                if m:
                    os.write(master, (m.group(1) + "\n").encode("utf-8"))
                    answered = True
        else:
            # check child
            waited = os.waitpid(pid, os.WNOHANG)
            if waited[0] == pid:
                break
    # drain
    while True:
        r, _, _ = select.select([master], [], [], 0.1)
        if not r:
            break
        try:
            chunk = os.read(master, 4096)
        except OSError:
            break
        if not chunk:
            break
        buf += chunk
    try:
        _, status = os.waitpid(pid, 0)
        rc = os.WEXITSTATUS(status) if os.WIFEXITED(status) else 1
    except ChildProcessError:
        rc = 1
    os.close(master)
    out_text = buf.decode("utf-8", errors="replace")
    # last JSON line
    parsed: dict = {}
    for line in reversed(out_text.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                parsed = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    return rc, parsed, out_text


# --- N1: no GATECTL_PACKAGE_ROOT; package = __file__/ops -----------------


def test_n1_no_package_root_env_and_path_identity() -> None:
    src = (PKG_SRC / "gatectl.py").read_text(encoding="utf-8")
    assert "GATECTL_PACKAGE_ROOT" not in src
    assert _package_root() == PKG_SRC.resolve()
    assert _real_lock_path() == (PKG_SRC / "ops" / "RUN.lock").resolve()
    assert _is_package_lock(PKG_SRC / "ops" / "RUN.lock") is True


def test_n1_env_cannot_reclassify_package_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Even if env is set (legacy), package detection ignores it — still TABU."""
    monkeypatch.setenv("GATECTL_PACKAGE_ROOT", str(tmp_path / "elsewhere"))
    (tmp_path / "elsewhere" / "ops").mkdir(parents=True)
    # Real package lock must still be package lock
    assert _is_package_lock(PKG_SRC / "ops" / "RUN.lock") is True
    paths = _scratch_migrated(tmp_path / "scratch")
    # Point --lock at real package lock → TABU without --allow-package-retire
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
                str(PKG_SRC / "ops" / "RUN.lock"),
                "--repo-root",
                str(paths["repo"]),
                "--journal",
                str(paths["journal"]),
                "--mirror-folder-id",
                "test-audit-folder-id",
                "--skip-disk-check",
                "--i-am-a-test",
                "retire-run-lock",
                "--skip-e1-upload-gate",
            ]
        )
    assert rc == EXIT_POLICY
    assert "TABU" in buf.getvalue() or "refused for package" in buf.getvalue()
    assert (PKG_SRC / "ops" / "RUN.lock").is_file()
    assert "LOCKED=1" in (PKG_SRC / "ops" / "RUN.lock").read_text(encoding="utf-8")


# --- status v9 RO ---------------------------------------------------------


def test_status_v9_ro_no_sha_drift_no_wal(tmp_path: Path) -> None:
    paths = _v9_live_marked(tmp_path)
    before = _sha(paths["db"])
    wal = Path(str(paths["db"]) + "-wal")
    # Live: --typed-confirm must be refused; without TTY → policy fail (no WAL).
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = gatectl_main(
            _argv(
                paths,
                "--allow-live-db",
                "--typed-confirm",
                "ALLOW_LIVE_DB",
                "status",
                "--allow-busy",
            )
        )
    assert rc == EXIT_POLICY
    assert "refuse --typed-confirm" in buf.getvalue()
    assert _sha(paths["db"]) == before
    assert not wal.exists()

    # Non-TTY without typed-confirm also refuses — still no WAL drift
    buf2 = io.StringIO()
    with redirect_stdout(buf2):
        rc2 = gatectl_main(
            _argv(paths, "--allow-live-db", "status", "--allow-busy")
        )
    assert rc2 == EXIT_POLICY
    assert "interactive TTY" in buf2.getvalue()
    assert _sha(paths["db"]) == before
    assert not wal.exists()
    jm = sqlite3.connect(str(paths["db"])).execute(
        "PRAGMA journal_mode"
    ).fetchone()[0]
    assert jm.lower() == "delete"


def test_status_v9_ro_with_tty_challenge(tmp_path: Path) -> None:
    """Positive: TTY + nonce unlocks status on live-marked v9 without WAL flip."""
    paths = _v9_live_marked(tmp_path)
    before = _sha(paths["db"])
    # Use fork/pty against imported main by temporarily swapping stdin/stdout —
    # drive via copied gatectl is overkill; patch isatty + readline.
    challenge_holder: list[str] = []

    def fake_write(s: str) -> int:
        m = re.search(r"Type exactly: (\S+)", s)
        if m:
            challenge_holder.append(m.group(1))
        return len(s)

    class _TTY:
        def isatty(self) -> bool:
            return True

        def readline(self) -> str:
            return challenge_holder[-1] + "\n"

        def write(self, s: str) -> int:
            return fake_write(s)

        def flush(self) -> None:
            return None

    buf = io.StringIO()
    with patch("sys.stdin", _TTY()), patch("sys.stderr", _TTY()), redirect_stdout(buf):
        rc = gatectl_main(
            _argv(paths, "--allow-live-db", "status", "--allow-busy")
        )
    assert rc == EXIT_OK, buf.getvalue()
    out = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert out["db_state"]["schema"] == "not_migrated"
    assert _sha(paths["db"]) == before


# --- L4: --i-am-a-test / --typed-confirm refused on live & package --------


def test_i_am_a_test_refused_on_live_and_package(tmp_path: Path) -> None:
    paths = _v9_live_marked(tmp_path)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = gatectl_main(
            _argv(paths, "--allow-live-db", "--i-am-a-test", "status")
        )
    assert rc == EXIT_POLICY
    assert "refuse --i-am-a-test" in buf.getvalue()

    # Package lock (real ops) + i-am-a-test + retire → refuse
    paths2 = _scratch_migrated(tmp_path / "s2")
    buf2 = io.StringIO()
    with redirect_stdout(buf2):
        rc2 = gatectl_main(
            [
                "--db",
                str(paths2["db"]),
                "--data-root",
                str(paths2["data_root"]),
                "--runner",
                str(paths2["runner"]),
                "--lock",
                str(PKG_SRC / "ops" / "RUN.lock"),
                "--repo-root",
                str(paths2["repo"]),
                "--journal",
                str(paths2["journal"]),
                "--mirror-folder-id",
                "test-audit-folder-id",
                "--i-am-a-test",
                "retire-run-lock",
                "--allow-package-retire",
            ]
        )
    assert rc2 == EXIT_POLICY
    assert "refuse --i-am-a-test" in buf2.getvalue()


def test_typed_confirm_refused_on_package(tmp_path: Path) -> None:
    paths = _scratch_migrated(tmp_path)
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
                str(PKG_SRC / "ops" / "RUN.lock"),
                "--repo-root",
                str(paths["repo"]),
                "--journal",
                str(paths["journal"]),
                "--mirror-folder-id",
                "test-audit-folder-id",
                "--typed-confirm",
                "RETIRE_PACKAGE_LOCK",
                "retire-run-lock",
                "--allow-package-retire",
            ]
        )
    assert rc == EXIT_POLICY
    assert "refuse --typed-confirm" in buf.getvalue()


# --- package retire via copied gatectl (__file__ = copy) -------------------


def test_package_retire_mirror_fail_leaves_lock(tmp_path: Path) -> None:
    pkg = _pkg_copy(tmp_path)
    before_sha = _sha(pkg["lock"])

    # In-process with __file__ of copy: load and call
    import types

    code = pkg["gatectl"].read_text(encoding="utf-8")
    mod = types.ModuleType("gatectl_pkg_copy")
    mod.__file__ = str(pkg["gatectl"])
    sys.modules["gatectl_pkg_copy"] = mod
    exec(compile(code, str(pkg["gatectl"]), "exec"), mod.__dict__)

    challenge: list[str] = []

    class _TTY:
        def isatty(self) -> bool:
            return True

        def readline(self) -> str:
            return challenge[-1] + "\n"

        def write(self, s: str) -> int:
            m = re.search(r"Type exactly: (\S+)", s)
            if m:
                challenge.append(m.group(1))
            return len(s)

        def flush(self) -> None:
            return None

    argv = _argv(
        pkg,
        "retire-run-lock",
        "--allow-package-retire",
    )
    buf = io.StringIO()
    with patch.object(mod, "subprocess") as sp, patch(
        "order_execution_engine.control_plane_audit.subprocess.run",
        side_effect=_fake_rclone_fail,
    ), patch.object(mod, "_list_shadow_runner_pids", return_value=[]), patch(
        "sys.stdin", _TTY()
    ), patch("sys.stderr", _TTY()), redirect_stdout(buf):
        sp.run.side_effect = _fake_rclone_fail
        rc = mod.main(argv)
    assert rc == EXIT_POLICY, buf.getvalue()
    assert pkg["lock"].is_file()
    assert _sha(pkg["lock"]) == before_sha
    assert not (pkg["lock"].parent / "RUN.RETIRED").exists()


def test_package_retire_restore_token_revoke(tmp_path: Path) -> None:
    pkg = _pkg_copy(tmp_path)
    import types

    code = pkg["gatectl"].read_text(encoding="utf-8")
    mod = types.ModuleType("gatectl_pkg_copy2")
    mod.__file__ = str(pkg["gatectl"])
    sys.modules["gatectl_pkg_copy2"] = mod
    exec(compile(code, str(pkg["gatectl"]), "exec"), mod.__dict__)

    challenge: list[str] = []

    class _TTY:
        def isatty(self) -> bool:
            return True

        def readline(self) -> str:
            return challenge[-1] + "\n"

        def write(self, s: str) -> int:
            m = re.search(r"Type exactly: (\S+)", s)
            if m:
                challenge.append(m.group(1))
            return len(s)

        def flush(self) -> None:
            return None

    with patch.object(mod, "subprocess") as sp, patch(
        "order_execution_engine.control_plane_audit.subprocess.run",
        side_effect=_fake_rclone_ok,
    ), patch.object(mod, "_list_shadow_runner_pids", return_value=[]), patch(
        "sys.stdin", _TTY()
    ), patch("sys.stderr", _TTY()):
        sp.run.side_effect = _fake_rclone_ok
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = mod.main(_argv(pkg, "retire-run-lock", "--allow-package-retire"))
        assert rc == EXIT_OK, buf.getvalue()
        assert not pkg["lock"].is_file()
        assert (pkg["lock"].parent / "RUN.RETIRED").is_file()
        entries = AppendOnlyAuditChain(pkg["journal"]).read_entries()
        actions = [e["action"] for e in entries]
        assert "retire_run_lock_intent" in actions
        assert "retire_run_lock_confirm" in actions

        conn = connect_scratch(pkg["db"])
        tok = issue_token(conn, run_id=16, ttl_s=120, allow_live=False)
        conn.close()
        assert tok

        challenge.clear()
        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = mod.main(_argv(pkg, "restore-run-lock"))
        assert rc2 == EXIT_OK, buf2.getvalue()
        assert pkg["lock"].is_file()
        out = json.loads(buf2.getvalue().strip().splitlines()[-1])
        assert out["revoked_tokens"] >= 1


def test_restore_clear_stale_marker(tmp_path: Path) -> None:
    pkg = _pkg_copy(tmp_path)
    marker = pkg["lock"].parent / "RUN.RETIRED"
    marker.write_text("before_sha256=abc\narchive=x\n", encoding="utf-8")
    import types

    code = pkg["gatectl"].read_text(encoding="utf-8")
    mod = types.ModuleType("gatectl_pkg_copy3")
    mod.__file__ = str(pkg["gatectl"])
    sys.modules["gatectl_pkg_copy3"] = mod
    exec(compile(code, str(pkg["gatectl"]), "exec"), mod.__dict__)
    challenge: list[str] = []

    class _TTY:
        def isatty(self) -> bool:
            return True

        def readline(self) -> str:
            return challenge[-1] + "\n"

        def write(self, s: str) -> int:
            m = re.search(r"Type exactly: (\S+)", s)
            if m:
                challenge.append(m.group(1))
            return len(s)

        def flush(self) -> None:
            return None

    with patch.object(mod, "subprocess") as sp, patch(
        "order_execution_engine.control_plane_audit.subprocess.run",
        side_effect=_fake_rclone_ok,
    ), patch("sys.stdin", _TTY()), patch("sys.stderr", _TTY()):
        sp.run.side_effect = _fake_rclone_ok
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = mod.main(
                _argv(pkg, "restore-run-lock", "--clear-stale-marker")
            )
    assert rc == EXIT_OK, buf.getvalue()
    assert pkg["lock"].is_file()
    assert not marker.exists()


def test_abort_requires_typed_confirm(tmp_path: Path) -> None:
    paths = _scratch_migrated(tmp_path)
    conn = connect_scratch(paths["db"])
    tok = issue_token(conn, run_id=16, ttl_s=60)
    from order_execution_engine.control_plane_lease import claim_run

    claim_run(conn, git_commit="c", config_json="{}", token=tok)
    conn.close()
    with patch(
        "order_execution_engine.gatectl._list_shadow_runner_pids",
        return_value=[],
    ):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = gatectl_main(
                _argv(
                    paths,
                    "abort-run",
                    "--run-id",
                    "16",
                    "--confirm-abort",
                    "16",
                )
            )
    assert rc == EXIT_POLICY
    assert "typed confirm" in buf.getvalue()


def test_restore_db_artefact_sha_mismatch_and_ok(tmp_path: Path) -> None:
    paths = _scratch_migrated(tmp_path)
    artefact = tmp_path / "pre.sqlite3"
    shutil.copy2(paths["db"], artefact)
    good = _sha(artefact)
    with patch(
        "order_execution_engine.control_plane_audit.subprocess.run",
        side_effect=_fake_rclone_ok,
    ):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = gatectl_main(
                _argv(
                    paths,
                    "--i-am-a-test",
                    "restore-db-artefact",
                    "--artefact",
                    str(artefact),
                    "--expected-sha256",
                    "0" * 64,
                )
            )
        assert rc == EXIT_POLICY
        assert "mismatch" in buf.getvalue()

        conn = connect_scratch(paths["db"])
        conn.execute(
            "INSERT INTO schema_meta(key, value) VALUES('probe','1')"
            " ON CONFLICT(key) DO UPDATE SET value='1'"
        )
        conn.commit()
        conn.close()
        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = gatectl_main(
                _argv(
                    paths,
                    "--i-am-a-test",
                    "restore-db-artefact",
                    "--artefact",
                    str(artefact),
                    "--expected-sha256",
                    good,
                )
            )
        assert rc2 == EXIT_OK, buf2.getvalue()
        assert _sha(paths["db"]) == good


def test_skip_e1_refused_on_package(tmp_path: Path) -> None:
    paths = _scratch_migrated(tmp_path)
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
                str(PKG_SRC / "ops" / "RUN.lock"),
                "--repo-root",
                str(paths["repo"]),
                "--journal",
                str(paths["journal"]),
                "--mirror-folder-id",
                "test-audit-folder-id",
                "--typed-confirm",
                "RETIRE_PACKAGE_LOCK",
                "retire-run-lock",
                "--allow-package-retire",
                "--skip-e1-upload-gate",
            ]
        )
    # typed-confirm refused first on package (N2), or skip-e1 if somehow past
    assert rc == EXIT_POLICY
    err = buf.getvalue()
    assert (
        "refuse --typed-confirm" in err
        or "skip-e1-upload-gate refused" in err
    )


def test_schema_control_pin() -> None:
    assert SCHEMA_CONTROL == 13
