"""L5-g: Trockenprobe des Prod-Start-Runbooks gegen Kopie (nie LIVE schreiben).

No launchctl. No migrate on LIVE. Pins must stay frozen.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from order_execution_engine.control_plane_authz import authz_enforced, authorize, AuthzError
from order_execution_engine.control_plane_lease import (
    apply_writer_durability,
    detect_restart_kind,
    issue_token,
    migrate_control_plane,
    next_run_id,
)
from order_execution_engine.gatectl import write_lease_token_file
from order_execution_engine.persistence import SQLiteShadowStorage

FROZEN_RUNNER_SHA256 = (
    "cfc79b2b46191ab54b7850f063242d2ad19f03424951ab182b93ecfd0f6dcf01"
)
FROZEN_PERSISTENCE_SHA256 = (
    "ce9cc2f88b6202a9cd098b86ed756b2c69f83e5ad6b7819311d8b8f06b36c47f"
)
_REPO = Path(__file__).resolve().parents[2]
_RUNBOOK = _REPO / "docs" / "architecture" / "L5_PROD_START_RUNBOOK.md"
_LIVE = Path.home() / (
    "Library/Application Support/agentx/shadow_live/shadow/shadow/shadow.db"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_l5a_runner_pin_gate() -> None:
    got = _sha(_REPO / "order_execution_engine" / "shadow_runner.py")
    assert got == FROZEN_RUNNER_SHA256


def test_l5a_persistence_pin_gate() -> None:
    got = _sha(_REPO / "order_execution_engine" / "persistence.py")
    assert got == FROZEN_PERSISTENCE_SHA256


def test_l5_runbook_exists_no_klarname_credentials() -> None:
    assert _RUNBOOK.is_file()
    text = _RUNBOOK.read_text(encoding="utf-8")
    assert "L5-a" in text and "L5-h" in text
    # F3 / L5-f: no production Drive folder ids, no oauth tokens
    assert "1IBXL-" not in text
    assert "1knskUdopb" not in text
    assert "client_secret" not in text.lower()
    assert "BEGIN PRIVATE KEY" not in text


def test_l5c_restart_kind_zero_byte_wal_is_clean(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    store = SQLiteShadowStorage.for_user(data, "shadow")
    db = store._db_path  # noqa: SLF001
    migrate_control_plane(store._conn, db_path=db)  # noqa: SLF001
    store._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")  # noqa: SLF001
    store.close()
    wal = Path(str(db) + "-wal")
    wal.write_bytes(b"")
    assert detect_restart_kind(db) == "clean_start"
    wal.write_bytes(b"x" * 64)
    assert detect_restart_kind(db) == "crash_or_open_wal"


def test_l5g_dry_sequence_on_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end dry: pins → copy migrate → token file → F7 refuse; LIVE SHA stable."""
    live_pre = _sha(_LIVE) if _LIVE.is_file() else None

    assert _sha(_REPO / "order_execution_engine" / "shadow_runner.py") == FROZEN_RUNNER_SHA256
    assert (
        _sha(_REPO / "order_execution_engine" / "persistence.py")
        == FROZEN_PERSISTENCE_SHA256
    )

    data = tmp_path / "data"
    data.mkdir()
    store = SQLiteShadowStorage.for_user(data, "shadow")
    db = store._db_path  # noqa: SLF001
    migrate_control_plane(store._conn, db_path=db)  # noqa: SLF001
    apply_writer_durability(store._conn)  # noqa: SLF001
    store._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")  # noqa: SLF001
    assert detect_restart_kind(db) == "clean_start"

    now = int(time.time())
    rid = next_run_id(store._conn)  # noqa: SLF001
    tok = issue_token(store._conn, run_id=rid, ttl_s=120, now=now)  # noqa: SLF001
    token_path = write_lease_token_file(tmp_path, rid, tok, conn=store._conn)  # noqa: SLF001
    assert token_path.stat().st_mode & 0o777 == 0o600
    store.close()

    # L5-b: unset enforce still Deny without role
    monkeypatch.delenv("CONTROL_PLANE_AUTHZ_ENFORCE", raising=False)
    monkeypatch.delenv("CONTROL_PLANE_ROLE", raising=False)
    assert authz_enforced() is True
    with pytest.raises(AuthzError, match="missing role"):
        authorize(None, "status")

    # F7: LIVE-marked root refuses raw --lease-token (Exit 76)
    from order_execution_engine.shadow_runner import (
        EXIT_CONTROL_PLANE,
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
                "must_refuse",
                "--once",
                "--no-ws",
            ]
        )
    assert rc == EXIT_CONTROL_PLANE == 76

    if live_pre is not None:
        assert _sha(_LIVE) == live_pre

    # Docs-only delta marker: runbook present (L5-h)
    assert _RUNBOOK.is_file()


def test_l5d_runbook_forbids_launchctl_before_e1() -> None:
    text = _RUNBOOK.read_text(encoding="utf-8")
    assert "kein launchctl" in text.lower() or "kein `launchctl`" in text
    assert "nicht ausführen vor E-1" in text or "nicht ausführen" in text
