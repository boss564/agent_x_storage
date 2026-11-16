"""L4 role authorization — gatectl config layer (not persistence schema)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from order_execution_engine.control_plane_authz import (
    AuthzError,
    assert_no_persistence_schema_touch,
    authorize,
)
from order_execution_engine.gatectl import EXIT_POLICY, main as gatectl_main

FROZEN_RUNNER_SHA256 = (
    "cfc79b2b46191ab54b7850f063242d2ad19f03424951ab182b93ecfd0f6dcf01"
)
FROZEN_PERSISTENCE_SHA256 = (
    "ce9cc2f88b6202a9cd098b86ed756b2c69f83e5ad6b7819311d8b8f06b36c47f"
)
_REPO = Path(__file__).resolve().parents[2]


def _sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_l4_allow_operator_migrate() -> None:
    decisions: list = []
    dec = authorize(
        "operator",
        "migrate",
        target="scratch.db",
        audit=decisions.append,
    )
    assert dec.allowed is True
    assert decisions[-1].allowed is True


def test_l4_deny_runner_migrate() -> None:
    decisions: list = []
    with pytest.raises(AuthzError, match="denied"):
        authorize(
            "runner",
            "migrate",
            target="scratch.db",
            audit=decisions.append,
        )
    assert decisions[-1].allowed is False
    assert decisions[-1].operation == "migrate"


def test_l4_deny_unknown_role() -> None:
    decisions: list = []
    with pytest.raises(AuthzError, match="unknown role"):
        authorize("root", "status", audit=decisions.append)
    assert decisions[-1].allowed is False


def test_l4_deny_missing_role() -> None:
    decisions: list = []
    with pytest.raises(AuthzError, match="missing role"):
        authorize("", "status", audit=decisions.append)
    assert decisions[-1].allowed is False


def test_l4_deny_produces_audit_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "authz.jsonl"
    monkeypatch.setenv("CONTROL_PLANE_AUTHZ_AUDIT_LOG", str(log))
    with pytest.raises(AuthzError):
        authorize("auditor", "migrate", target="t")
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1
    rec = json.loads(lines[-1])
    assert rec["allowed"] is False
    assert rec["role"] == "auditor"
    assert rec["operation"] == "migrate"
    assert "ts" in rec


def test_l4_no_persistence_schema_touch() -> None:
    out = assert_no_persistence_schema_touch()
    assert out["ok"] is True
    assert out["banned_hits"] == []


def test_l4_gatectl_deny_watchdog_on_migrate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONTROL_PLANE_AUTHZ_ENFORCE", "1")
    monkeypatch.setenv("CONTROL_PLANE_ROLE", "watchdog")
    db = tmp_path / "x.db"
    db.write_bytes(b"")  # parse only — authz fires before open
    data = tmp_path / "data"
    data.mkdir()
    rc = gatectl_main(
        ["--db", str(db), "--data-root", str(data), "migrate"]
    )
    assert rc == EXIT_POLICY


def test_l4_freeze_pins_unchanged() -> None:
    assert (
        _sha(_REPO / "order_execution_engine" / "shadow_runner.py")
        == FROZEN_RUNNER_SHA256
    )
    assert (
        _sha(_REPO / "order_execution_engine" / "persistence.py")
        == FROZEN_PERSISTENCE_SHA256
    )
