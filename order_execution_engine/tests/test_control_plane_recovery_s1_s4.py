"""Phase-4 Recovery S1–S4 — Scratch + optional LIVE Canary copy.

Additive only: does not modify freeze core modules @ c0996759.

Default ``pytest`` runs **Scratch only**. LIVE is never opened unless the
operator explicitly opts in:

* ``CONTROL_PLANE_CANARY=1`` — enable Canary tests (copy LIVE once, RO attest)
* ``CANARY_LIVE_SHA=<64hex>`` — optional override of the LIVE SHA pin
  (after run16 the default pin will fail by design; pass the new SHA)
* ``CANARY_S14_ROOT=/tmp/...`` — optional durable canary workdir

Canary paths under ``/tmp`` are **not** LIVE-marked; they do **not** prove
``--allow-live-db``, package-lock retire, or ``--run-lock`` refuse on LIVE.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from order_execution_engine.control_plane_audit import (
    compute_trigger_manifest_sha256,
    expected_control_plane_manifest_sha256,
)
from order_execution_engine.control_plane_lease import (
    SCHEMA_CONTROL,
    LeaseError,
    claim_run,
    connect_scratch,
    issue_token,
    migrate_control_plane,
    next_run_id,
)
from order_execution_engine.gatectl import (
    EXIT_OK,
    main as gatectl_main,
)
from order_execution_engine.persistence import SQLiteShadowStorage
from order_execution_engine.shadow_runner import (
    EXIT_CONTROL_PLANE,
    EXIT_RUN_LOCK,
    main as runner_main,
)

PKG = Path(__file__).resolve().parents[1]
REPO = PKG.parent
SHADOW_RUNNER = PKG / "shadow_runner.py"
LIVE_DB = Path.home() / (
    "Library/Application Support/agentx/shadow_live/shadow/shadow/shadow.db"
)
# Default pin = pre-run16 LIVE. Override via CANARY_LIVE_SHA after cutover.
_DEFAULT_LIVE_SHA = (
    "2a7915ef0eff5dea4b3e67332cbb117bf1b738190fbd9304c5dceaa3b54008ed"
)
TRIGGER_SOLL = (
    "8f75665569a0daacac189c43a297154d4907b058f5866d0436b2577bf3528a95"
)


def _canary_enabled() -> bool:
    return os.environ.get("CONTROL_PLANE_CANARY", "").strip() in (
        "1",
        "true",
        "TRUE",
        "yes",
        "YES",
    )


def _live_sha_pin() -> str:
    override = os.environ.get("CANARY_LIVE_SHA", "").strip().lower()
    if override:
        if len(override) != 64 or any(c not in "0123456789abcdef" for c in override):
            raise AssertionError(
                f"CANARY_LIVE_SHA must be 64 lowercase hex, got {override!r}"
            )
        return override
    return _DEFAULT_LIVE_SHA


requires_canary = pytest.mark.skipif(
    not _canary_enabled(),
    reason=(
        "Canary/LIVE copy gated: set CONTROL_PLANE_CANARY=1 "
        "(optional CANARY_LIVE_SHA=… / CANARY_S14_ROOT=…)"
    ),
)
FREEZE_PINS = {
    "control_plane_lease.py": (
        "ea5a179c3ffa22438670257ba26e00fef98fc33d04535b85b559e388a102fcc9"
    ),
    "control_plane_audit.py": (
        "4af2307f40b9101c727ac286b8f2bbd910ba646770abe2bfa42a6ca7bc2e58cf"
    ),
    "gatectl.py": (
        "178b9dabffac12add9b01ffa1f0cc840fb5235a4a89d0f3a1b35abfb7e6b738e"
    ),
    "persistence.py": (
        "ce9cc2f88b6202a9cd098b86ed756b2c69f83e5ad6b7819311d8b8f06b36c47f"
    ),
    "shadow_runner.py": (
        "cfc79b2b46191ab54b7850f063242d2ad19f03424951ab182b93ecfd0f6dcf01"
    ),
}

AUDIT_FOLDER_ID = "1knskUdopb-6E9eNhoXnuO5V6ULSzCwVe"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fake_rclone_ok(cmd: list[str], **kwargs: Any) -> MagicMock:
    m = MagicMock()
    m.returncode = 0
    m.stdout = "[]" if len(cmd) > 1 and cmd[1] == "lsjson" else ""
    m.stderr = ""
    return m


def _assert_freeze_pins() -> None:
    for name, exp in FREEZE_PINS.items():
        got = _sha(PKG / name)
        assert got == exp, f"{name}: {got} != {exp}"


def _bundle_scratch(tmp_path: Path) -> dict[str, Path]:
    data = tmp_path / "data"
    data.mkdir()
    store = SQLiteShadowStorage.for_user(data, "shadow")
    db = store._db_path  # noqa: SLF001
    migrate_control_plane(store._conn, db_path=db)  # noqa: SLF001
    store.close()
    lock = tmp_path / "RUN.lock"
    lock.write_text("LOCKED=0\n", encoding="utf-8")
    allow = tmp_path / "allowlist.json"
    allow.write_text(
        json.dumps(
            {"BTC": {"token_id": "tok_s14", "market_id": "mkt_s14"}},
            indent=2,
        ),
        encoding="utf-8",
    )
    news = tmp_path / "news_scores.jsonl"
    news.write_text("", encoding="utf-8")
    # Real runner for claim path; gatectl snapshot uses SHADOW_RUNNER pin.
    return {
        "root": tmp_path,
        "data": data,
        "data_root": tmp_path,
        "db": db,
        "lock": lock,
        "allow": allow,
        "news": news,
        "runner": SHADOW_RUNNER,
        "repo": REPO,
        "journal": tmp_path / "audit_chain.jsonl",
    }


def _runner_argv(paths: dict[str, Path], *extra: str) -> list[str]:
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


def _gate_argv(paths: dict[str, Path], *extra: str) -> list[str]:
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
        AUDIT_FOLDER_ID,
        "--mirror-remote",
        f"gdrive:s14_recovery_{paths['root'].name}",
        *extra,
    ]


def _open_count(conn: sqlite3.Connection) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM run_lease"
            " WHERE consumed_at IS NULL AND revoked_at IS NULL"
        ).fetchone()[0]
    )


def _run_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM telemetry_runs").fetchone()[0])


# ---------------------------------------------------------------------------
# Scratch S1–S4
# ---------------------------------------------------------------------------


def test_s1_scratch_abort_before_issue_token(tmp_path: Path) -> None:
    """S1: no lease, no new run, runner without token → Exit 76."""
    _assert_freeze_pins()
    paths = _bundle_scratch(tmp_path)
    conn = connect_scratch(paths["db"])
    before_runs = _run_count(conn)
    before_leases = conn.execute("SELECT COUNT(*) FROM run_lease").fetchone()[0]
    conn.close()

    rc = runner_main(_runner_argv(paths))
    assert rc == EXIT_CONTROL_PLANE

    conn = connect_scratch(paths["db"])
    assert _run_count(conn) == before_runs
    assert conn.execute("SELECT COUNT(*) FROM run_lease").fetchone()[0] == before_leases
    assert _open_count(conn) == 0
    conn.close()


def test_s2_scratch_ttl_expired_reissue_revokes_old(tmp_path: Path) -> None:
    """S2: expired token refuse; re-issue same run_id revokes old (L1)."""
    _assert_freeze_pins()
    paths = _bundle_scratch(tmp_path)
    conn = connect_scratch(paths["db"])
    rid = next_run_id(conn)
    now = int(time.time())
    t1 = issue_token(conn, run_id=rid, ttl_s=1, now=now - 30)
    with pytest.raises(LeaseError, match="expired"):
        claim_run(conn, git_commit="s2", config_json="{}", token=t1, now=now)
    # Runner path with expired token also fail-closed
    conn.close()
    rc = runner_main(_runner_argv(paths, "--lease-token", t1))
    assert rc == EXIT_CONTROL_PLANE

    conn = connect_scratch(paths["db"])
    assert next_run_id(conn) == rid
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM telemetry_runs WHERE run_id=?", (rid,)
        ).fetchone()[0]
        == 0
    )
    t2 = issue_token(conn, run_id=rid, ttl_s=60, now=now)
    assert t2 != t1
    row = conn.execute(
        "SELECT revoked_at FROM run_lease WHERE token=?", (t1,)
    ).fetchone()
    assert row is not None and row[0] is not None
    assert (
        conn.execute(
            "SELECT revoked_at FROM run_lease WHERE token=?", (t2,)
        ).fetchone()[0]
        is None
    )
    conn.close()


def test_s3_scratch_running_abort_then_next_token(tmp_path: Path) -> None:
    """S3: RUNNING blocks issue; gatectl abort-run → ABORTED; next run_id token ok."""
    _assert_freeze_pins()
    paths = _bundle_scratch(tmp_path)
    conn = connect_scratch(paths["db"])
    rid = next_run_id(conn)
    tok = issue_token(conn, run_id=rid, ttl_s=120)
    assert claim_run(conn, git_commit="s3", config_json="{}", token=tok) == rid
    status = conn.execute(
        "SELECT status FROM telemetry_runs WHERE run_id=?", (rid,)
    ).fetchone()[0]
    assert status == "RUNNING"
    with pytest.raises(LeaseError, match="RUNNING"):
        issue_token(conn, run_id=rid + 1, ttl_s=60)
    conn.close()

    with patch(
        "order_execution_engine.gatectl._list_shadow_runner_pids",
        return_value=[],
    ), patch(
        "order_execution_engine.control_plane_audit.subprocess.run",
        side_effect=_fake_rclone_ok,
    ):
        rc = gatectl_main(
            _gate_argv(
                paths,
                "--typed-confirm",
                f"ABORT_RUN_{rid}",
                "abort-run",
                "--run-id",
                str(rid),
                "--confirm-abort",
                str(rid),
                "--reason",
                "s3_sigkill_sim",
            )
        )
    assert rc == EXIT_OK

    conn = connect_scratch(paths["db"])
    row = conn.execute(
        "SELECT status, closed_at FROM telemetry_runs WHERE run_id=?", (rid,)
    ).fetchone()
    assert row[0] == "ABORTED" and row[1] is not None
    nxt = next_run_id(conn)
    assert nxt == rid + 1
    t_next = issue_token(conn, run_id=nxt, ttl_s=60)
    assert t_next
    conn.close()


def test_s4_scratch_lock_blocks_then_retire_token_path(tmp_path: Path) -> None:
    """S4: LOCKED=1 → Exit 75; after retire-run-lock → Exit 76 without token; token path ok."""
    _assert_freeze_pins()
    paths = _bundle_scratch(tmp_path)
    paths["lock"].write_text(
        "LOCKED=1\nforbid_run_id_gt=14\n", encoding="utf-8"
    )
    rc = runner_main(_runner_argv(paths))
    assert rc == EXIT_RUN_LOCK

    with patch(
        "order_execution_engine.control_plane_audit.subprocess.run",
        side_effect=_fake_rclone_ok,
    ):
        rc = gatectl_main(
            _gate_argv(paths, "retire-run-lock", "--skip-e1-upload-gate")
        )
    assert rc == EXIT_OK
    assert not paths["lock"].is_file()
    assert list(paths["lock"].parent.glob("RUN.lock.retired.*"))

    # Post-retire: no token → control-plane refuse (76), not lock (75)
    rc = runner_main(_runner_argv(paths))
    assert rc == EXIT_CONTROL_PLANE

    conn = connect_scratch(paths["db"])
    rid = next_run_id(conn)
    tok = issue_token(conn, run_id=rid, ttl_s=120)
    conn.close()
    rc = runner_main(_runner_argv(paths, "--lease-token", tok))
    assert rc == 0
    conn = connect_scratch(paths["db"])
    row = conn.execute(
        "SELECT status, closed_at FROM telemetry_runs WHERE run_id=?", (rid,)
    ).fetchone()
    assert row is not None and row[0] == "COMMITTED" and row[1] is not None
    conn.close()


# ---------------------------------------------------------------------------
# Canary (LIVE copy) — one shared DB, S1→S4 sequenced
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def canary_bundle(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """One RO copy of LIVE → migrate v13; cleaned up after module.

    Hard-gated by ``CONTROL_PLANE_CANARY=1``. Without it this fixture is never
    entered (tests marked ``requires_canary`` skip first).
    """
    if not _canary_enabled():
        pytest.skip("CONTROL_PLANE_CANARY not set")
    if not LIVE_DB.is_file():
        pytest.skip(f"LIVE_DB absent: {LIVE_DB}")
    _assert_freeze_pins()
    live_pin = _live_sha_pin()
    live_before = _sha(LIVE_DB)
    assert live_before == live_pin, (
        f"LIVE SHA {live_before} != pin {live_pin} "
        "(set CANARY_LIVE_SHA after run16 / schema change)"
    )

    root = tmp_path_factory.mktemp("canary_s14_")
    # Use /tmp-visible path for operator cleanup visibility when env set
    env_root = os.environ.get("CANARY_S14_ROOT")
    if env_root:
        root = Path(env_root)
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)

    data = root / "data"
    db = data / "shadow" / "shadow" / "shadow.db"
    db.parent.mkdir(parents=True)
    shutil.copy2(LIVE_DB, db)

    live_after = _sha(LIVE_DB)
    assert live_after == live_before == live_pin
    assert _sha(db) == live_pin

    # Pre-migrate checks
    conn = sqlite3.connect(str(db))
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == 9
    assert (
        int(
            conn.execute(
                "SELECT COALESCE(MAX(run_id),0) FROM telemetry_runs"
            ).fetchone()[0]
        )
        == 15
    )
    conn.close()

    conn = connect_scratch(db)
    migrate_control_plane(conn, db_path=db)
    assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == SCHEMA_CONTROL
    assert SCHEMA_CONTROL == 13
    ist = compute_trigger_manifest_sha256(conn)
    soll = expected_control_plane_manifest_sha256()
    assert ist == soll == TRIGGER_SOLL
    assert (
        int(
            conn.execute(
                "SELECT COALESCE(MAX(run_id),0) FROM telemetry_runs"
            ).fetchone()[0]
        )
        == 15
    )
    conn.close()

    # LIVE still untouched after migrate of copy
    assert _sha(LIVE_DB) == live_pin

    lock = root / "RUN.lock"
    lock.write_text("LOCKED=0\n", encoding="utf-8")
    allow = root / "allowlist.json"
    allow.write_text(
        json.dumps(
            {"BTC": {"token_id": "tok_canary_s14", "market_id": "mkt_canary_s14"}},
            indent=2,
        ),
        encoding="utf-8",
    )
    news = root / "news_scores.jsonl"
    news.write_text("", encoding="utf-8")

    paths: dict[str, Any] = {
        "root": root,
        "data": data,
        "data_root": root,
        "db": db,
        "lock": lock,
        "allow": allow,
        "news": news,
        "runner": SHADOW_RUNNER,
        "repo": REPO,
        "journal": root / "audit_chain.jsonl",
        "live_sha": live_before,
        "live_pin": live_pin,
    }
    yield paths

    # Cleanup + LIVE/pin attestation
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    if env_root and Path(env_root).exists():
        shutil.rmtree(env_root, ignore_errors=True)
    assert _sha(LIVE_DB) == live_pin
    _assert_freeze_pins()


@requires_canary
def test_s1_canary_abort_before_issue_token(canary_bundle: dict[str, Any]) -> None:
    paths = canary_bundle
    conn = connect_scratch(paths["db"])
    before_runs = _run_count(conn)
    before_leases = conn.execute("SELECT COUNT(*) FROM run_lease").fetchone()[0]
    mx = int(
        conn.execute(
            "SELECT COALESCE(MAX(run_id),0) FROM telemetry_runs"
        ).fetchone()[0]
    )
    conn.close()
    assert mx == 15

    rc = runner_main(_runner_argv(paths))
    assert rc == EXIT_CONTROL_PLANE

    conn = connect_scratch(paths["db"])
    assert _run_count(conn) == before_runs
    assert conn.execute("SELECT COUNT(*) FROM run_lease").fetchone()[0] == before_leases
    assert _open_count(conn) == 0
    assert (
        int(
            conn.execute(
                "SELECT COALESCE(MAX(run_id),0) FROM telemetry_runs"
            ).fetchone()[0]
        )
        == 15
    )
    conn.close()
    assert _sha(LIVE_DB) == paths["live_pin"]


@requires_canary
def test_s2_canary_ttl_expired_reissue_revokes_old(
    canary_bundle: dict[str, Any],
) -> None:
    paths = canary_bundle
    conn = connect_scratch(paths["db"])
    rid = next_run_id(conn)
    assert rid == 16
    now = int(time.time())
    t1 = issue_token(conn, run_id=rid, ttl_s=1, now=now - 30)
    with pytest.raises(LeaseError, match="expired"):
        claim_run(conn, git_commit="s2c", config_json="{}", token=t1, now=now)
    conn.close()

    rc = runner_main(_runner_argv(paths, "--lease-token", t1))
    assert rc == EXIT_CONTROL_PLANE

    conn = connect_scratch(paths["db"])
    assert next_run_id(conn) == rid
    t2 = issue_token(conn, run_id=rid, ttl_s=120, now=now)
    assert t2 != t1
    assert (
        conn.execute(
            "SELECT revoked_at FROM run_lease WHERE token=?", (t1,)
        ).fetchone()[0]
        is not None
    )
    # Leave t2 open for S3 claim
    paths["_s2_token"] = t2
    paths["_s2_run_id"] = rid
    conn.close()
    assert _sha(LIVE_DB) == paths["live_pin"]


@requires_canary
def test_s3_canary_running_abort_then_next_token(
    canary_bundle: dict[str, Any],
) -> None:
    paths = canary_bundle
    tok = paths.get("_s2_token")
    rid = paths.get("_s2_run_id")
    assert tok and rid == 16

    conn = connect_scratch(paths["db"])
    assert claim_run(conn, git_commit="s3c", config_json="{}", token=tok) == rid
    assert (
        conn.execute(
            "SELECT status FROM telemetry_runs WHERE run_id=?", (rid,)
        ).fetchone()[0]
        == "RUNNING"
    )
    with pytest.raises(LeaseError, match="RUNNING"):
        issue_token(conn, run_id=17, ttl_s=60)
    conn.close()

    with patch(
        "order_execution_engine.gatectl._list_shadow_runner_pids",
        return_value=[],
    ), patch(
        "order_execution_engine.control_plane_audit.subprocess.run",
        side_effect=_fake_rclone_ok,
    ):
        rc = gatectl_main(
            _gate_argv(
                paths,
                "--typed-confirm",
                f"ABORT_RUN_{rid}",
                "abort-run",
                "--run-id",
                str(rid),
                "--confirm-abort",
                str(rid),
                "--reason",
                "s3_canary_sigkill_sim",
            )
        )
    assert rc == EXIT_OK

    conn = connect_scratch(paths["db"])
    row = conn.execute(
        "SELECT status, closed_at FROM telemetry_runs WHERE run_id=?", (rid,)
    ).fetchone()
    assert row[0] == "ABORTED" and row[1] is not None
    nxt = next_run_id(conn)
    assert nxt == 17
    t_next = issue_token(conn, run_id=nxt, ttl_s=120)
    paths["_s3_next_token"] = t_next
    paths["_s3_next_run_id"] = nxt
    conn.close()
    assert _sha(LIVE_DB) == paths["live_pin"]


@requires_canary
def test_s4_canary_lock_blocks_then_retire_token_path(
    canary_bundle: dict[str, Any],
) -> None:
    paths = canary_bundle
    paths["lock"].write_text(
        "LOCKED=1\nforbid_run_id_gt=14\n", encoding="utf-8"
    )
    rc = runner_main(_runner_argv(paths))
    assert rc == EXIT_RUN_LOCK

    with patch(
        "order_execution_engine.control_plane_audit.subprocess.run",
        side_effect=_fake_rclone_ok,
    ):
        rc = gatectl_main(
            _gate_argv(paths, "retire-run-lock", "--skip-e1-upload-gate")
        )
    assert rc == EXIT_OK
    assert not paths["lock"].is_file()

    rc = runner_main(_runner_argv(paths))
    assert rc == EXIT_CONTROL_PLANE

    tok = paths.get("_s3_next_token")
    rid = paths.get("_s3_next_run_id")
    assert tok and rid == 17
    rc = runner_main(_runner_argv(paths, "--lease-token", tok))
    assert rc == 0

    conn = connect_scratch(paths["db"])
    row = conn.execute(
        "SELECT status FROM telemetry_runs WHERE run_id=?", (rid,)
    ).fetchone()
    assert row is not None and row[0] == "COMMITTED"
    conn.close()

    assert _sha(LIVE_DB) == paths["live_pin"]
    _assert_freeze_pins()
