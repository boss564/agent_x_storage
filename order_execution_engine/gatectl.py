#!/usr/bin/env python3
"""gatectl — Phase-2 Control-Plane CLI.

Exit codes:
  0 = OK
  2 = policy / integrity failure
  3 = revoke failed after audit failure (token may still be open)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from order_execution_engine.control_plane_audit import (
    DEFAULT_AUDIT_MIRROR_FOLDER_ID,
    DEFAULT_AUDIT_MIRROR_REMOTE_PREFIX,
    DEFAULT_AUDIT_OBJECTS_FOLDER_ID,
    AppendOnlyAuditChain,
    AuditChainError,
    ManifestMismatchError,
    QuiescenceError,
    SnapshotError,
    assert_skip_disk_check_allowed,
    build_snapshot_manifest,
    compute_jsonl_prefix_sha256,
    compute_logical_digest_sha256,
    expected_control_plane_manifest_sha256,
    mirror_audit_entry,
    sha256_file_streaming,
    token_sha256,
    verify_audit_mirror,
)
from order_execution_engine.control_plane_lease import (
    SCHEMA_CONTROL,
    LeaseError,
    LivePathRefused,
    abort_run,
    connect_control_plane,
    connect_scratch,
    issue_token,
    migrate_control_plane,
    next_run_id,
    revoke_token,
)


def _conn(args: argparse.Namespace) -> sqlite3.Connection:
    """DB open for gatectl — LIVE only with ``--allow-live-db`` (M4)."""
    return connect_control_plane(
        Path(args.db),
        allow_live=bool(getattr(args, "allow_live_db", False)),
    )


def lease_token_path(data_root: Path, run_id: int) -> Path:
    """M1: exclusive token file under data-root (not argv / not env)."""
    return Path(data_root) / "leases" / f"run_{int(run_id)}.token"


def write_lease_token_file(data_root: Path, run_id: int, token: str) -> Path:
    """Write raw token with O_EXCL + mode 0600; never overwrite."""
    path = lease_token_path(data_root, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(str(path), flags, 0o600)
    try:
        os.write(fd, token.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(path, 0o600)
    return path

EXIT_OK = 0
EXIT_POLICY = 2
EXIT_REVOKE_FAILED = 3

_PKG = Path(__file__).resolve().parent
_REAL_LOCK = (_PKG / "ops" / "RUN.lock").resolve()


def _print_json(obj: Any) -> None:
    print(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )


def _load_lock_readonly(lock_path: Path) -> dict[str, Any]:
    raw = lock_path.read_bytes()
    try:
        text: Optional[str] = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    return {
        "path": str(lock_path.resolve()),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size": len(raw),
        "text": text,
    }


def _journal_path(args: argparse.Namespace) -> Path:
    if getattr(args, "journal", None):
        return Path(args.journal)
    return Path(args.data_root) / "audit_chain.jsonl"


def _snapshot_dir(args: argparse.Namespace) -> Path:
    return Path(args.data_root) / "snapshots"


def _check_disk(args: argparse.Namespace) -> bool:
    """True → enforce ≥85% refuse. ``--skip-disk-check`` Scratch-only.

    Skipping on LIVE ``Application Support/agentx`` paths requires explicit
    ``--allow-live-skip-disk-check`` Freigabe (Gate #4 fail-closed).
    """
    if not bool(getattr(args, "skip_disk_check", False)):
        return True
    assert_skip_disk_check_allowed(
        Path(args.db),
        Path(args.data_root),
        Path(args.lock),
        allow_live=bool(getattr(args, "allow_live_skip_disk_check", False)),
    )
    return False


def _mirror_required_entry(
    args: argparse.Namespace, entry: dict[str, Any]
) -> Optional[str]:
    remote = getattr(args, "mirror_remote", None)
    if not remote:
        return None
    return mirror_audit_entry(
        entry,
        remote,
        folder_id=getattr(
            args, "mirror_folder_id", DEFAULT_AUDIT_MIRROR_FOLDER_ID
        ),
    )


def cmd_verify_snapshot(args: argparse.Namespace) -> int:
    journal = AppendOnlyAuditChain(_journal_path(args))
    try:
        journal.verify()
        # Canary/pre-migrate: v9 LIVE copies lack control-plane DDL until migrate.
        require_match = not bool(
            getattr(args, "allow_manifest_mismatch", False)
        )
        manifest = build_snapshot_manifest(
            Path(args.db),
            Path(args.runner),
            Path(args.lock),
            Path(args.repo_root),
            check_quiescent=True,
            snapshot_dir=_snapshot_dir(args),
            persist_artefact=True,
            check_disk_headroom=_check_disk(args),
            require_manifest_match=require_match,
        )
        entry = journal.append(
            "verify_snapshot",
            manifest["manifest_sha256"],
            {
                "max_run_id": manifest["max_run_id"],
                "logical_digest_sha256": manifest["logical_digest_sha256"],
                "artefact_sha256": manifest["artefact_sha256"],
                "manifest_match": manifest["manifest_match"],
                "allow_manifest_mismatch": not require_match,
            },
        )
        remote = _mirror_required_entry(args, entry)
    except (
        QuiescenceError,
        SnapshotError,
        ManifestMismatchError,
        AuditChainError,
    ) as exc:
        _print_json({"ok": False, "error": str(exc)})
        return EXIT_POLICY
    out = {
        "ok": True,
        "action": "verify_snapshot",
        "manifest_sha256": manifest["manifest_sha256"],
        "trigger_manifest_sha256": manifest["trigger_manifest_sha256"],
        "manifest_match": manifest["manifest_match"],
        "logical_digest_sha256": manifest["logical_digest_sha256"],
        "artefact_sha256": manifest["artefact_sha256"],
        "max_run_id": manifest["max_run_id"],
        "audit_seq": entry["seq"],
        "manifest_match": manifest["manifest_match"],
    }
    if remote:
        out["mirrored_to"] = remote
    _print_json(out)
    return EXIT_OK


def cmd_issue_token(args: argparse.Namespace) -> int:
    """Intent → issue → confirm + M1 token-file (O_EXCL 0600). No raw token on stdout."""
    mirror_remote = args.mirror_remote or DEFAULT_AUDIT_MIRROR_REMOTE_PREFIX
    mirror_folder = (
        args.mirror_folder_id
        or DEFAULT_AUDIT_OBJECTS_FOLDER_ID
        or DEFAULT_AUDIT_MIRROR_FOLDER_ID
    )

    journal = AppendOnlyAuditChain(_journal_path(args))
    conn = None
    token: Optional[str] = None
    token_file: Optional[Path] = None
    try:
        journal.verify()
        manifest = build_snapshot_manifest(
            Path(args.db),
            Path(args.runner),
            Path(args.lock),
            Path(args.repo_root),
            check_quiescent=True,
            snapshot_dir=_snapshot_dir(args),
            persist_artefact=False,
            check_disk_headroom=_check_disk(args),
        )
        conn = _conn(args)
        run_id = int(args.run_id) if args.run_id is not None else next_run_id(conn)
        ttl_s = int(args.ttl)

        intent = journal.append(
            "issue_token_intent",
            manifest["manifest_sha256"],
            {"run_id": run_id, "ttl_s": ttl_s},
        )
        mirror_audit_entry(
            intent, mirror_remote, folder_id=mirror_folder
        )

        token = issue_token(conn, run_id=run_id, ttl_s=ttl_s)
        digest = token_sha256(token)
        # M1: handoff via exclusive file under data-root (not argv / not env).
        token_file = write_lease_token_file(Path(args.data_root), run_id, token)
        try:
            confirm = journal.append(
                "issue_token_confirm",
                manifest["manifest_sha256"],
                {
                    "run_id": run_id,
                    "ttl_s": ttl_s,
                    "token_sha256": digest,
                    "token_file": str(token_file),
                    "intent_seq": intent["seq"],
                },
            )
            mirror_audit_entry(
                confirm, mirror_remote, folder_id=mirror_folder
            )
        except AuditChainError as exc:
            try:
                revoke_token(conn, token)
            except Exception as rev_exc:  # noqa: BLE001
                _print_json(
                    {
                        "ok": False,
                        "error": str(exc),
                        "revoke_error": str(rev_exc),
                        "token_sha256": digest,
                        "run_id": run_id,
                    }
                )
                return EXIT_REVOKE_FAILED
            if token_file is not None and token_file.is_file():
                try:
                    token_file.unlink()
                except OSError:
                    pass
            token = None
            raise
    except (
        QuiescenceError,
        SnapshotError,
        ManifestMismatchError,
        AuditChainError,
        LeaseError,
        LivePathRefused,
        OSError,
        ValueError,
    ) as exc:
        _print_json({"ok": False, "error": str(exc)})
        return EXIT_POLICY
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    _print_json(
        {
            "ok": True,
            "action": "issue_token",
            "run_id": run_id,
            "ttl_s": ttl_s,
            "token_sha256": digest,
            "token_file": str(token_file),
            "manifest_sha256": manifest["manifest_sha256"],
            "intent_seq": intent["seq"],
            "confirm_seq": confirm["seq"],
        }
    )
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    out: dict[str, Any] = {"ok": True, "action": "status"}
    try:
        out["lock"] = _load_lock_readonly(Path(args.lock))
    except OSError as exc:
        _print_json({"ok": False, "error": f"lock read failed: {exc}"})
        return EXIT_POLICY

    try:
        out["manifest"] = build_snapshot_manifest(
            Path(args.db),
            Path(args.runner),
            Path(args.lock),
            Path(args.repo_root),
            check_quiescent=not args.allow_busy,
            snapshot_dir=_snapshot_dir(args),
            require_manifest_match=False,
            persist_artefact=False,
            check_disk_headroom=_check_disk(args),
        )
        out["expected_trigger_manifest_sha256"] = (
            expected_control_plane_manifest_sha256()
        )
        if not out["manifest"].get("manifest_match"):
            out["ok"] = False
            out["manifest_error"] = "DDL manifest mismatch vs code Sollwert"
    except (QuiescenceError, SnapshotError) as exc:
        out["ok"] = False
        out["manifest_error"] = str(exc)

    journal = AppendOnlyAuditChain(_journal_path(args))
    try:
        count = journal.verify()
        out["audit"] = {
            "ok": True,
            "entries": count,
            "path": str(_journal_path(args)),
        }
    except AuditChainError as exc:
        out["ok"] = False
        out["audit"] = {
            "ok": False,
            "error": str(exc),
            "path": str(_journal_path(args)),
        }

    # Schema / open leases / RUNNING
    try:
        conn = _conn(args)
        try:
            row = conn.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()
            schema_version = int(row[0]) if row else 0
            open_leases = conn.execute(
                "SELECT COUNT(*) FROM run_lease"
                " WHERE consumed_at IS NULL AND revoked_at IS NULL"
            ).fetchone()[0]
            running_rows = conn.execute(
                "SELECT run_id, started_at FROM telemetry_runs"
                " WHERE status='RUNNING' ORDER BY run_id"
            ).fetchall()
            now_s = time.time()
            running_detail = []
            for rr in running_rows:
                started = float(rr[1] or 0.0)
                running_detail.append(
                    {
                        "run_id": int(rr[0]),
                        "started_at": started,
                        "age_s": max(0.0, now_s - started),
                    }
                )
            out["db_state"] = {
                "schema_version": schema_version,
                "schema_ok": schema_version >= SCHEMA_CONTROL,
                "open_leases": int(open_leases),
                "running_runs": len(running_detail),
                # D1-a: lease age visible for operator watchdog (no auto-abort).
                "running": running_detail,
            }
            if schema_version < SCHEMA_CONTROL or running_detail:
                out["ok"] = False
        finally:
            conn.close()
    except (LivePathRefused, sqlite3.Error, OSError, TypeError, ValueError) as exc:
        out["ok"] = False
        out["db_state_error"] = str(exc)

    _print_json(out)
    return EXIT_OK if out.get("ok") else EXIT_POLICY


def cmd_migrate(args: argparse.Namespace) -> int:
    """Pre-snapshot → migrate → post manifest check → audit (Gate #4)."""
    journal = AppendOnlyAuditChain(_journal_path(args))
    try:
        journal.verify()
        pre = build_snapshot_manifest(
            Path(args.db),
            Path(args.runner),
            Path(args.lock),
            Path(args.repo_root),
            check_quiescent=True,
            snapshot_dir=_snapshot_dir(args),
            persist_artefact=True,
            check_disk_headroom=_check_disk(args),
            require_manifest_match=False,
        )
        conn = _conn(args)
        try:
            migrate_control_plane(conn, db_path=Path(args.db))
            row = conn.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()
            ver = int(row[0]) if row else 0
        finally:
            conn.close()
        post = build_snapshot_manifest(
            Path(args.db),
            Path(args.runner),
            Path(args.lock),
            Path(args.repo_root),
            check_quiescent=True,
            snapshot_dir=_snapshot_dir(args),
            persist_artefact=False,
            check_disk_headroom=False,
            require_manifest_match=True,
        )
        expected = expected_control_plane_manifest_sha256()
        if post["trigger_manifest_sha256"] != expected:
            raise ManifestMismatchError(
                "post-migrate trigger manifest mismatch: "
                f"observed={post['trigger_manifest_sha256']} expected={expected}"
            )
        entry = journal.append(
            "migrate",
            post["manifest_sha256"],
            {
                "schema_version": ver,
                "pre_artefact_sha256": pre["artefact_sha256"],
                "post_trigger_manifest_sha256": post["trigger_manifest_sha256"],
                "expected_trigger_manifest_sha256": expected,
            },
        )
        if args.mirror_remote:
            mirror_audit_entry(
                entry,
                args.mirror_remote,
                folder_id=args.mirror_folder_id
                or DEFAULT_AUDIT_MIRROR_FOLDER_ID,
            )
    except (
        LeaseError,
        LivePathRefused,
        QuiescenceError,
        SnapshotError,
        ManifestMismatchError,
        AuditChainError,
        sqlite3.Error,
        OSError,
    ) as exc:
        _print_json({"ok": False, "error": str(exc)})
        return EXIT_POLICY
    _print_json(
        {
            "ok": True,
            "action": "migrate",
            "schema_version": ver,
            "expected_manifest": expected,
            "audit_seq": entry["seq"],
            "pre_artefact_sha256": pre["artefact_sha256"],
        }
    )
    return EXIT_OK


def cmd_abort_run(args: argparse.Namespace) -> int:
    """Abort RUNNING run + revoke open leases; audit fail → DB rollback.

    D2-a (write-ahead audit): ``journal.append`` runs **before** ``COMMIT``.
    If append raises, ``ROLLBACK`` undoes the lease transition — the DB never
    reaches ABORTED without an audit row. Mirror is post-commit best-effort.

    D2-b: requires ``--confirm-abort <run_id>`` (operator intentionality gate).
    """
    journal = AppendOnlyAuditChain(_journal_path(args))
    conn = None
    entry: Optional[dict[str, Any]] = None
    info: Optional[dict[str, Any]] = None
    rid = 0
    reason = ""
    try:
        rid = int(args.run_id)
        confirm = str(getattr(args, "confirm_abort", "") or "")
        if confirm != str(rid):
            _print_json(
                {
                    "ok": False,
                    "error": (
                        "abort-run refused: --confirm-abort must equal "
                        f"--run-id ({rid}) — operator gate (D2-b)"
                    ),
                }
            )
            return EXIT_POLICY
        journal.verify()
        conn = _conn(args)
        reason = str(getattr(args, "reason", "") or "")
        conn.execute("BEGIN IMMEDIATE")
        info = abort_run(conn, rid, reason=reason)
        ph = hashlib.sha256(
            f"abort-run:{rid}:{reason}".encode("utf-8")
        ).hexdigest()
        # Write-ahead audit (D2-a): append before COMMIT so failure rolls back.
        entry = journal.append(
            "abort_run",
            ph,
            {
                "run_id": rid,
                "reason": reason,
                "leases_revoked": info["leases_revoked"],
                "closed_at": info["closed_at"],
            },
        )
        conn.execute("COMMIT")
    except (LeaseError, LivePathRefused, AuditChainError, sqlite3.Error) as exc:
        if conn is not None:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
        _print_json({"ok": False, "error": str(exc)})
        return EXIT_POLICY
    finally:
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass
    assert entry is not None and info is not None
    try:
        if args.mirror_remote:
            mirror_audit_entry(
                entry,
                args.mirror_remote,
                folder_id=args.mirror_folder_id
                or DEFAULT_AUDIT_MIRROR_FOLDER_ID,
            )
    except AuditChainError as exc:
        _print_json(
            {
                "ok": False,
                "error": str(exc),
                "action": "abort_run",
                "run_id": rid,
                "audit_seq": entry["seq"],
                "db_aborted": True,
            }
        )
        return EXIT_POLICY
    _print_json(
        {
            "ok": True,
            "action": "abort_run",
            "run_id": rid,
            "reason": reason,
            "audit_seq": entry["seq"],
            "leases_revoked": info["leases_revoked"],
        }
    )
    return EXIT_OK


def cmd_retire_run_lock(args: argparse.Namespace) -> int:
    """Refuse production ops/RUN.lock; scratch locks only (TABU + audit).

    Retire is reversible: rename/archive the lock (never delete). Writes
    ``RUN.RETIRED`` marker beside the lock (D3 post-retire). Before-SHA is
    fixed in the audit journal prior to rename.

    D4-a: upload gate is **default-on**. Prior ``db_artefact_upload`` with
    ok=true+sha256 required unless ``--skip-e1-upload-gate`` (scratch/test hook).

    D3-a: ``RUN.RETIRED`` is created **only after** rename-archive succeeds
    (exclusive create). Pre-existing marker → refuse (fail-closed).
    """
    lock = Path(args.lock).resolve()
    if lock == _REAL_LOCK:
        _print_json(
            {
                "ok": False,
                "error": "retire-run-lock refused for package RUN.lock (TABU)",
            }
        )
        return EXIT_POLICY
    # Also refuse any lock under the package ops/ directory (path tricks).
    ops_dir = (_PKG / "ops").resolve()
    try:
        lock.relative_to(ops_dir)
        _print_json(
            {
                "ok": False,
                "error": "retire-run-lock refused for package ops/ lock (TABU)",
            }
        )
        return EXIT_POLICY
    except ValueError:
        pass
    if not lock.is_file():
        _print_json({"ok": False, "error": f"lock missing: {lock}"})
        return EXIT_POLICY
    text = lock.read_text(encoding="utf-8")
    if "LOCKED=1" not in text:
        _print_json({"ok": False, "error": "lock not LOCKED=1"})
        return EXIT_POLICY
    marker = lock.parent / "RUN.RETIRED"
    if marker.is_file():
        _print_json(
            {
                "ok": False,
                "error": (
                    "retire refused: RUN.RETIRED already present "
                    "(D3-a marker integrity)"
                ),
            }
        )
        return EXIT_POLICY
    journal = AppendOnlyAuditChain(_journal_path(args))
    try:
        journal.verify()
        # Quiescence + schema preconditions (gap).
        build_snapshot_manifest(
            Path(args.db),
            Path(args.runner),
            Path(args.lock),
            Path(args.repo_root),
            check_quiescent=True,
            snapshot_dir=_snapshot_dir(args),
            persist_artefact=False,
            check_disk_headroom=_check_disk(args),
            require_manifest_match=False,
        )
        # D4-a: default-on; bind upload to current logical digest when present.
        skip_upload = bool(getattr(args, "skip_e1_upload_gate", False))
        if not skip_upload:
            conn_r = _conn(args)
            try:
                cur_digest = compute_logical_digest_sha256(conn_r)
            finally:
                conn_r.close()
            entries = journal.read_entries()
            upload_ok = False
            for e in reversed(entries):
                if e.get("action") == "db_artefact_upload":
                    payload = e.get("payload") or {}
                    digest_ok = (
                        not payload.get("logical_digest_sha256")
                        or payload.get("logical_digest_sha256") == cur_digest
                    )
                    upload_ok = (
                        bool(payload.get("ok"))
                        and bool(payload.get("sha256"))
                        and digest_ok
                    )
                    break
            if not upload_ok:
                _print_json(
                    {
                        "ok": False,
                        "error": (
                            "retire refused: E-1 upload gate (default-on) "
                            "requires prior db_artefact_upload ok=true bound to "
                            "current logical digest; "
                            "scratch opt-out: --skip-e1-upload-gate"
                        ),
                    }
                )
                return EXIT_POLICY
        if not getattr(args, "mirror_remote", None):
            _print_json(
                {
                    "ok": False,
                    "error": "retire refused: --mirror-remote required (gap)",
                }
            )
            return EXIT_POLICY
        before_sha = sha256_file_streaming(lock)
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        archive = lock.with_name(f"{lock.name}.retired.{before_sha[:12]}.{ts}")
        if archive.exists():
            _print_json(
                {
                    "ok": False,
                    "error": f"retire archive already exists: {archive}",
                }
            )
            return EXIT_POLICY
        ph = hashlib.sha256(
            f"retire-run-lock:{lock}:{before_sha}:{archive}".encode("utf-8")
        ).hexdigest()
        entry = journal.append(
            "retire_run_lock",
            ph,
            {
                "path": str(lock),
                "before_sha256": before_sha,
                "archive_path": str(archive),
                "method": "rename_archive",
                "after_state": "absent",
                "retired_marker": str(marker),
            },
        )
        # D3-a order: rename first; marker only after archive exists.
        # Crash between rename and marker → absent without marker → refuse
        # (fail-closed). Marker never pre-exists while LOCKED=1.
        lock.rename(archive)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(str(marker), flags, 0o644)
        try:
            os.write(
                fd,
                (
                    f"before_sha256={before_sha}\n"
                    f"archive={archive}\n"
                    f"ts_utc={ts}\n"
                ).encode("utf-8"),
            )
        finally:
            os.close(fd)
        if args.mirror_remote:
            mirror_audit_entry(
                entry,
                args.mirror_remote,
                folder_id=args.mirror_folder_id
                or DEFAULT_AUDIT_MIRROR_FOLDER_ID,
            )
    except (AuditChainError, OSError) as exc:
        _print_json({"ok": False, "error": str(exc)})
        return EXIT_POLICY
    _print_json(
        {
            "ok": True,
            "action": "retire_run_lock",
            "path": str(lock),
            "archive_path": str(archive),
            "before_sha256": before_sha,
            "retired_marker": str(marker),
            "audit_seq": entry["seq"],
            "after_state": "absent",
        }
    )
    return EXIT_OK


def cmd_post_run_check(args: argparse.Namespace) -> int:
    """Post-run invariants; optional ``--run-id`` scopes the terminal check."""
    journal = AppendOnlyAuditChain(_journal_path(args))
    try:
        journal.verify()
        runner_sha = sha256_file_streaming(Path(args.runner))
        manifest = build_snapshot_manifest(
            Path(args.db),
            Path(args.runner),
            Path(args.lock),
            Path(args.repo_root),
            check_quiescent=True,
            snapshot_dir=_snapshot_dir(args),
            persist_artefact=True,
            check_disk_headroom=_check_disk(args),
        )
        if manifest["runner_sha256"] != runner_sha:
            raise SnapshotError(
                "post-run-check runner SHA drift: "
                f"manifest={manifest['runner_sha256']} live={runner_sha}"
            )
        conn = _conn(args)
        try:
            running = conn.execute(
                "SELECT COUNT(*) FROM telemetry_runs WHERE status='RUNNING'"
            ).fetchone()[0]
            open_leases = conn.execute(
                "SELECT COUNT(*) FROM run_lease"
                " WHERE consumed_at IS NULL AND revoked_at IS NULL"
            ).fetchone()[0]
            run_row = None
            if getattr(args, "run_id", None) is not None:
                rid = int(args.run_id)
                run_row = conn.execute(
                    "SELECT run_id, status, closed_at FROM telemetry_runs"
                    " WHERE run_id=?",
                    (rid,),
                ).fetchone()
                if run_row is None:
                    raise SnapshotError(
                        f"post-run-check: run_id={rid} not found"
                    )
                if run_row["status"] not in ("ABORTED", "COMMITTED"):
                    raise SnapshotError(
                        f"post-run-check: run_id={rid} status="
                        f"{run_row['status']!r} not terminal"
                    )
                if run_row["closed_at"] is None:
                    raise SnapshotError(
                        f"post-run-check: run_id={rid} closed_at is NULL"
                    )
                open_for_run = conn.execute(
                    "SELECT COUNT(*) FROM run_lease"
                    " WHERE run_id=? AND consumed_at IS NULL"
                    " AND revoked_at IS NULL",
                    (rid,),
                ).fetchone()[0]
                if open_for_run:
                    raise SnapshotError(
                        f"post-run-check: run_id={rid} still has open lease"
                    )
        finally:
            conn.close()
        if running or open_leases:
            raise SnapshotError(
                f"post-run-check failed: running={running} open_leases={open_leases}"
            )
        jsonl_info = None
        news_jsonl = getattr(args, "news_jsonl", None)
        if news_jsonl is not None:
            jsonl_info = compute_jsonl_prefix_sha256(Path(news_jsonl))
        entry = journal.append(
            "post_run_check",
            manifest["manifest_sha256"],
            {
                "max_run_id": manifest["max_run_id"],
                "logical_digest_sha256": manifest["logical_digest_sha256"],
                "runner_sha256": runner_sha,
                "run_id": (
                    int(args.run_id)
                    if getattr(args, "run_id", None) is not None
                    else None
                ),
                "run_status": run_row["status"] if run_row is not None else None,
                "news_jsonl_prefix": jsonl_info,
                "verdict": "PASS",
            },
        )
        if args.mirror_remote:
            mirror_audit_entry(
                entry,
                args.mirror_remote,
                folder_id=args.mirror_folder_id
                or DEFAULT_AUDIT_MIRROR_FOLDER_ID,
            )
    except (
        QuiescenceError,
        SnapshotError,
        ManifestMismatchError,
        AuditChainError,
        LivePathRefused,
        OSError,
        ValueError,
    ) as exc:
        _print_json({"ok": False, "error": str(exc), "verdict": "FAIL"})
        return EXIT_POLICY
    out: dict[str, Any] = {
        "ok": True,
        "action": "post_run_check",
        "max_run_id": manifest["max_run_id"],
        "audit_seq": entry["seq"],
        "runner_sha256": runner_sha,
        "verdict": "PASS",
    }
    if getattr(args, "run_id", None) is not None:
        out["run_id"] = int(args.run_id)
    if jsonl_info is not None:
        out["news_jsonl_prefix"] = jsonl_info
    _print_json(out)
    return EXIT_OK


def cmd_verify_mirror(args: argparse.Namespace) -> int:
    """Compare local audit journal objects to off-host mirror (Gate #4)."""
    journal = AppendOnlyAuditChain(_journal_path(args))
    try:
        journal.verify()
        result = verify_audit_mirror(
            _journal_path(args),
            args.mirror_remote or DEFAULT_AUDIT_MIRROR_REMOTE_PREFIX,
            folder_id=args.mirror_folder_id or DEFAULT_AUDIT_MIRROR_FOLDER_ID,
        )
        entry = journal.append(
            "verify_mirror",
            hashlib.sha256(
                json.dumps(result, sort_keys=True, separators=(",", ":")).encode(
                    "utf-8"
                )
            ).hexdigest(),
            {
                "entries": result["entries"],
                "folder_id": result["folder_id"],
                "remote_prefix": result["remote_prefix"],
            },
        )
    except (AuditChainError, OSError, ValueError) as exc:
        _print_json({"ok": False, "error": str(exc)})
        return EXIT_POLICY
    _print_json(
        {
            "ok": True,
            "action": "verify_mirror",
            "entries": result["entries"],
            "audit_seq": entry["seq"],
            "folder_id": result["folder_id"],
        }
    )
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gatectl")
    p.add_argument("--db", type=Path, required=True)
    p.add_argument(
        "--data-root",
        type=Path,
        required=True,
        help="Data root for audit_chain.jsonl + snapshots (not repo ops/)",
    )
    p.add_argument(
        "--runner",
        type=Path,
        default=_PKG / "shadow_runner.py",
    )
    p.add_argument(
        "--lock",
        type=Path,
        default=_PKG / "ops" / "RUN.lock",
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=_PKG.parent,
    )
    p.add_argument(
        "--journal",
        type=Path,
        default=None,
        help="Override journal path (default: <data-root>/audit_chain.jsonl)",
    )
    p.add_argument(
        "--mirror-remote",
        type=str,
        default=DEFAULT_AUDIT_MIRROR_REMOTE_PREFIX,
        help=(
            "rclone remote prefix for per-entry mirrors "
            f"(default: {DEFAULT_AUDIT_MIRROR_REMOTE_PREFIX})"
        ),
    )
    p.add_argument(
        "--mirror-folder-id",
        type=str,
        default=DEFAULT_AUDIT_OBJECTS_FOLDER_ID,
        help=(
            "Drive folder for audit objects (set AUDIT_OBJECTS_FOLDER_ID; "
            "must differ from incr-bundle folder before E-1)"
        ),
    )
    p.add_argument(
        "--skip-disk-check",
        action="store_true",
        help="Scratch/tests only: allow persist artefacts when volume is nearly full",
    )
    p.add_argument(
        "--allow-live-skip-disk-check",
        action="store_true",
        help=(
            "Explicit LIVE Freigabe for --skip-disk-check on "
            "Application Support/agentx paths (default: refuse)"
        ),
    )
    p.add_argument(
        "--allow-live-db",
        action="store_true",
        help="M4: allow gatectl DB ops on Application Support/agentx (explicit)",
    )
    p.add_argument(
        "--news-jsonl",
        type=Path,
        default=None,
        help="Optional news_scores.jsonl for post-run-check prefix SHA",
    )

    sub = p.add_subparsers(dest="command", required=True)

    p_verify = sub.add_parser("verify-snapshot")
    p_verify.add_argument(
        "--allow-manifest-mismatch",
        action="store_true",
        help=(
            "Canary/pre-migrate only: record snapshot even when observed "
            "DDL manifest ≠ Soll (e.g. LIVE schema v9 before gatectl migrate)"
        ),
    )
    p_verify.set_defaults(func=cmd_verify_snapshot)

    p_issue = sub.add_parser("issue-token")
    p_issue.add_argument("--run-id", type=int, default=None)
    p_issue.add_argument("--ttl", type=int, default=300)
    p_issue.set_defaults(func=cmd_issue_token)

    p_status = sub.add_parser("status")
    p_status.add_argument(
        "--allow-busy",
        action="store_true",
        help="Skip quiescence (status only)",
    )
    p_status.set_defaults(func=cmd_status, allow_busy=False)

    p_mig = sub.add_parser("migrate")
    p_mig.set_defaults(func=cmd_migrate)

    p_abort = sub.add_parser("abort-run")
    p_abort.add_argument("--run-id", type=int, required=True)
    p_abort.add_argument("--reason", type=str, default="")
    p_abort.add_argument(
        "--confirm-abort",
        type=str,
        required=True,
        help="D2-b: must equal --run-id (operator intentionality gate)",
    )
    p_abort.set_defaults(func=cmd_abort_run)

    p_retire = sub.add_parser("retire-run-lock")
    p_retire.add_argument(
        "--skip-e1-upload-gate",
        action="store_true",
        help="D4-a scratch/test opt-out; production path keeps upload gate ON",
    )
    p_retire.set_defaults(func=cmd_retire_run_lock, skip_e1_upload_gate=False)

    p_post = sub.add_parser("post-run-check")
    p_post.add_argument("--run-id", type=int, default=None)
    p_post.set_defaults(func=cmd_post_run_check)

    p_vm = sub.add_parser("verify-mirror")
    p_vm.set_defaults(func=cmd_verify_mirror)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "allow_busy"):
        args.allow_busy = False
    if not hasattr(args, "allow_live_skip_disk_check"):
        args.allow_live_skip_disk_check = False
    if not hasattr(args, "news_jsonl"):
        args.news_jsonl = None
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
