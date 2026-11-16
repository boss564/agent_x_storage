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
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

from order_execution_engine.control_plane_audit import (
    DEFAULT_AUDIT_MIRROR_REMOTE_PREFIX,
    AppendOnlyAuditChain,
    AuditChainError,
    ManifestMismatchError,
    QuiescenceError,
    SnapshotError,
    assert_skip_disk_check_allowed,
    build_snapshot_manifest,
    compute_jsonl_prefix_sha256,
    compute_logical_digest_sha256,
    compute_trigger_manifest_sha256,
    expected_control_plane_manifest_sha256,
    mirror_audit_entry,
    require_audit_objects_folder_id,
    _list_shadow_runner_pids,
    sha256_file_streaming,
    token_sha256,
    verify_audit_mirror,
)
from order_execution_engine.control_plane_watchdog import (
    DEFAULT_T_MAX_S,
    check_running_leases,
    report_exit_code,
)
from order_execution_engine.control_plane_authz import (
    AuthzError,
    authorize,
    authz_enforced,
)
from order_execution_engine.control_plane_lease import (
    SCHEMA_CONTROL,
    LeaseError,
    LivePathRefused,
    abort_run,
    connect_control_plane,
    connect_control_plane_ro,
    connect_scratch,
    is_live_agentx_path,
    issue_token,
    migrate_control_plane,
    next_run_id,
    revoke_token,
)


def _conn(args: argparse.Namespace) -> sqlite3.Connection:
    """RW DB open for writers — LIVE only with ``--allow-live-db`` (M4)."""
    return connect_control_plane(
        Path(args.db),
        allow_live=bool(getattr(args, "allow_live_db", False)),
    )


def _conn_ro(args: argparse.Namespace) -> sqlite3.Connection:
    """RO DB open — no WAL pragma (E-0 / status / retire prechecks)."""
    return connect_control_plane_ro(
        Path(args.db),
        allow_live=bool(getattr(args, "allow_live_db", False)),
    )


def lease_token_path(data_root: Path, run_id: int) -> Path:
    """M1: exclusive token file under data-root (not argv / not env)."""
    return Path(data_root) / "leases" / f"run_{int(run_id)}.token"


def write_lease_token_file(
    data_root: Path,
    run_id: int,
    token: str,
    *,
    conn: Optional[sqlite3.Connection] = None,
) -> Path:
    """Write raw token with O_EXCL + mode 0600.

    Stale file for same run_id: replace only if on-disk token is revoked/expired
    or unknown to an open lease (gap). Caller must revoke on any OSError.
    """
    path = lease_token_path(data_root, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and conn is not None:
        try:
            old = path.read_text(encoding="utf-8").strip()
        except OSError:
            old = ""
        if old:
            row = conn.execute(
                "SELECT consumed_at, revoked_at, expires_at FROM run_lease"
                " WHERE token = ?",
                (old,),
            ).fetchone()
            now = int(time.time())
            stale = row is None or row[0] is not None or row[1] is not None or (
                row[2] is not None and int(row[2]) <= now
            )
            if stale:
                path.unlink(missing_ok=True)
            else:
                raise OSError(
                    f"lease token file exists for open lease: {path}"
                )
        else:
            path.unlink(missing_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(str(path), flags, 0o600)
    try:
        os.write(fd, token.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(path, 0o600)
    return path


def _allow_live(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "allow_live_db", False))


# Production Drive audit folder — refused in test mode only (L1 Drive-Boundary
# bandage). Live/operator path may legally use this id; architecture fix
# (separate credentials/mounts/CI) remains open.
PROD_AUDIT_OBJECTS_FOLDER_ID = "1IBXL-lIrXTvnleZMvhv7Er1IJf5VAjla"


def _control_plane_test_mode() -> bool:
    """True under pytest or explicit CONTROL_PLANE_TEST_MODE (not live ops)."""
    flag = os.environ.get("CONTROL_PLANE_TEST_MODE", "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        return True
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    return False


def _require_audit_folder_id(args: argparse.Namespace) -> str:
    """Require explicit audit folder id ≠ incr-bundle; deny Prod-ID in test mode."""
    fid = getattr(args, "mirror_folder_id", None) or os.environ.get(
        "AUDIT_OBJECTS_FOLDER_ID"
    )
    resolved = require_audit_objects_folder_id(fid)
    if (
        _control_plane_test_mode()
        and resolved == PROD_AUDIT_OBJECTS_FOLDER_ID
    ):
        raise AuditChainError(
            f"refuse prod audit folder_id={resolved} in test mode "
            "(CONTROL_PLANE_TEST_MODE / pytest); use test folder, not Prod"
        )
    return resolved

EXIT_OK = 0
EXIT_POLICY = 2
EXIT_REVOKE_FAILED = 3

def _package_root() -> Path:
    """Package dir next to this file — identical rule to runner ``__file__``/ops.

    No env override (N1): an env package-root must not redefine the package
    boundary; Temp-Paket-Abnahme runs the *copied* ``gatectl.py`` so ``__file__``
    already points at the copy.
    """
    return Path(__file__).resolve().parent


def _real_lock_path() -> Path:
    return (_package_root() / "ops" / "RUN.lock").resolve()


_PKG = Path(__file__).resolve().parent  # import-site defaults (runner path)


def _is_package_lock(lock: Path) -> bool:
    """True iff lock is the package ``ops/RUN.lock`` or any path under package ``ops/``."""
    lock_r = lock.resolve()
    if lock_r == _real_lock_path():
        return True
    ops_dir = (_package_root() / "ops").resolve()
    try:
        lock_r.relative_to(ops_dir)
        return True
    except ValueError:
        return False


def _require_typed_confirm(args: argparse.Namespace, phrase_stem: str) -> Optional[str]:
    """L4 human gate — return error message or None if confirmation satisfied.

    Live-marked DB **or** package lock (strict):
      - ``--i-am-a-test`` refused
      - ``--typed-confirm`` refused (not a second flag)
      - interactive TTY required
      - challenge = ``{stem}:{8 hex}`` shown on stderr, typed back exactly

    Scratch only:
      - ``--i-am-a-test`` or ``--typed-confirm {stem}`` (fixed, no nonce) for suite
    """
    live_db = is_live_agentx_path(Path(args.db))
    pkg_lock = _is_package_lock(Path(args.lock))
    strict = live_db or pkg_lock

    if bool(getattr(args, "i_am_a_test", False)):
        if strict:
            return (
                "refuse --i-am-a-test on live-marked DB path or package lock"
            )
        return None

    provided = getattr(args, "typed_confirm", None)
    if strict:
        if provided is not None:
            return (
                "refuse --typed-confirm on live-marked DB or package lock "
                "(interactive TTY required)"
            )
        if not sys.stdin.isatty():
            return (
                "typed confirm required: interactive TTY on live/package "
                f"(challenge stem {phrase_stem!r})"
            )
        nonce = secrets.token_hex(4)
        expected = f"{phrase_stem}:{nonce}"
        sys.stderr.write(f"Type exactly: {expected}\n")
        sys.stderr.flush()
        try:
            got = sys.stdin.readline().strip()
        except EOFError:
            return "typed confirm refused: EOF"
        if got != expected:
            return f"typed confirm refused: got {got!r}"
        return None

    # Scratch / suite path
    if provided is not None:
        if str(provided) == phrase_stem:
            return None
        return f"typed confirm mismatch: expected {phrase_stem!r}"
    if not sys.stdin.isatty():
        return (
            "typed confirm required (non-TTY scratch): pass "
            f"--typed-confirm {phrase_stem} or --i-am-a-test"
        )
    sys.stderr.write(f"Type exactly: {phrase_stem}\n")
    sys.stderr.flush()
    try:
        got = sys.stdin.readline().strip()
    except EOFError:
        return "typed confirm refused: EOF"
    if got != phrase_stem:
        return f"typed confirm refused: got {got!r}"
    return None


def _probe_mirror_reachable(args: argparse.Namespace) -> None:
    """V7: fail-closed rclone reachability (no mutation)."""
    remote = getattr(args, "mirror_remote", None) or DEFAULT_AUDIT_MIRROR_REMOTE_PREFIX
    folder_id = _require_audit_folder_id(args)
    flags = ["--drive-root-folder-id", folder_id]
    proc = subprocess.run(
        ["rclone", "lsjson", remote.rstrip("/") + "/", *flags],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise AuditChainError(f"mirror unreachable: {err}")


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
        folder_id=_require_audit_folder_id(args),
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

    journal = AppendOnlyAuditChain(_journal_path(args))
    conn = None
    token: Optional[str] = None
    token_file: Optional[Path] = None
    try:
        mirror_folder = _require_audit_folder_id(args)
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

        allow_live = _allow_live(args)
        token = issue_token(
            conn, run_id=run_id, ttl_s=ttl_s, allow_live=allow_live
        )
        digest = token_sha256(token)
        # M1: handoff via exclusive file; revoke if write fails (gap).
        try:
            token_file = write_lease_token_file(
                Path(args.data_root), run_id, token, conn=conn
            )
        except OSError:
            try:
                revoke_token(conn, token, allow_live=allow_live)
            except Exception:  # noqa: BLE001
                pass
            raise
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
                revoke_token(conn, token, allow_live=_allow_live(args))
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



def _open_audit_intents(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Intents lacking confirm/refused closure (L3 observability)."""
    closed: set[int] = set()
    intents: list[dict[str, Any]] = []
    for e in entries:
        action = e.get("action")
        payload = e.get("payload") or {}
        if action in (
            "abort_run_confirm",
            "abort_run_refused",
            "issue_token_confirm",
            "retire_run_lock_confirm",
            "restore_run_lock_confirm",
            "restore_db_artefact_confirm",
        ):
            seq = payload.get("intent_seq")
            if seq is not None:
                try:
                    closed.add(int(seq))
                except (TypeError, ValueError):
                    pass
        if action in (
            "abort_run_intent",
            "issue_token_intent",
            "retire_run_lock_intent",
            "restore_run_lock_intent",
            "restore_db_artefact_intent",
        ):
            intents.append(e)
    open_rows: list[dict[str, Any]] = []
    for e in intents:
        try:
            seq = int(e["seq"])
        except (KeyError, TypeError, ValueError):
            continue
        if seq in closed:
            continue
        payload = e.get("payload") or {}
        open_rows.append(
            {
                "action": e.get("action"),
                "seq": seq,
                "run_id": payload.get("run_id"),
                "reason": payload.get("reason"),
                "ttl_s": payload.get("ttl_s"),
                "path": payload.get("path"),
            }
        )
    return open_rows


def cmd_watchdog_check(args: argparse.Namespace) -> int:
    """L2-a…d: RO stuck-RUNNING scan; alarm channel; never writes lease DB."""
    report = check_running_leases(
        Path(args.db),
        t_max_s=getattr(args, "t_max_s", None),
        allow_live=_allow_live(args),
        alarm_log=getattr(args, "alarm_log", None),
    )
    _print_json(report.to_dict())
    return report_exit_code(report)


def cmd_status(args: argparse.Namespace) -> int:
    """Describe control-plane state via RO open — never flips journal_mode."""
    out: dict[str, Any] = {"ok": True, "action": "status"}
    try:
        out["lock"] = _load_lock_readonly(Path(args.lock))
    except OSError as exc:
        _print_json({"ok": False, "error": f"lock read failed: {exc}"})
        return EXIT_POLICY

    journal = AppendOnlyAuditChain(_journal_path(args))
    audit_entries: list[dict[str, Any]] = []
    try:
        count = journal.verify()
        audit_entries = journal.read_entries()
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

    # Schema / open leases / RUNNING — RO only (Rev. B §A)
    try:
        conn = _conn_ro(args)
        try:
            uv = int(conn.execute("PRAGMA user_version").fetchone()[0])
            has_lease = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='run_lease'"
            ).fetchone()
            row = None
            try:
                row = conn.execute(
                    "SELECT value FROM schema_meta WHERE key='schema_version'"
                ).fetchone()
            except sqlite3.Error:
                row = None
            schema_version = int(row[0]) if row else 0

            if not has_lease or schema_version < SCHEMA_CONTROL or uv < SCHEMA_CONTROL:
                out["db_state"] = {
                    "schema": "not_migrated",
                    "user_version": uv,
                    "schema_version": schema_version,
                    "control_plane": False,
                    "schema_ok": False,
                    "open_leases": 0,
                    "running_runs": 0,
                    "running": [],
                }
                out["expected_trigger_manifest_sha256"] = (
                    expected_control_plane_manifest_sha256()
                )
                # Descriptive ok=true for pre-migrate; open intents still fail closed.
                open_intents = _open_audit_intents(audit_entries)
                out["open_intents"] = open_intents
                if open_intents:
                    out["ok"] = False
                _print_json(out)
                return EXIT_OK if out.get("ok") else EXIT_POLICY

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
                "schema": "migrated",
                "user_version": uv,
                "schema_version": schema_version,
                "control_plane": True,
                "schema_ok": schema_version >= SCHEMA_CONTROL,
                "open_leases": int(open_leases),
                "running_runs": len(running_detail),
                "running": running_detail,
            }
            if running_detail:
                out["ok"] = False

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

            open_intents = _open_audit_intents(audit_entries)
            enriched: list[dict[str, Any]] = []
            for oi in open_intents:
                row_oi = dict(oi)
                rid = oi.get("run_id")
                if rid is not None:
                    try:
                        r = conn.execute(
                            "SELECT status, closed_at FROM telemetry_runs"
                            " WHERE run_id=?",
                            (int(rid),),
                        ).fetchone()
                        if r is None:
                            row_oi["db_status"] = None
                            row_oi["db_closed_at"] = None
                        else:
                            row_oi["db_status"] = r[0]
                            row_oi["db_closed_at"] = r[1]
                    except (TypeError, ValueError, sqlite3.Error):
                        row_oi["db_status"] = "lookup_error"
                enriched.append(row_oi)
            out["open_intents"] = enriched
            if enriched:
                out["ok"] = False
        finally:
            conn.close()
    except (LivePathRefused, sqlite3.Error, OSError, TypeError, ValueError) as exc:
        out["ok"] = False
        out["db_state_error"] = str(exc)
        if audit_entries:
            out["open_intents"] = _open_audit_intents(audit_entries)

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
            migrate_control_plane(conn, db_path=Path(args.db), allow_live=_allow_live(args))
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
                folder_id=_require_audit_folder_id(args),
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
    """Abort RUNNING run (L3: local intent → COMMIT → confirm; mirror after).

    Network mirror never gates the abort (plan: refuse/abort must not depend
    on the network). Mirror both audit rows only *after* COMMIT; mirror errors
    are reported, DB abort stands.

    Liveness: refuse while ``shadow_runner`` PIDs are present (process would
    keep writing under an ABORTED run_id).

    Refused abort (not RUNNING / lease error after intent): writes
    ``abort_run_refused`` closing the intent pair.
    """
    journal = AppendOnlyAuditChain(_journal_path(args))
    conn = None
    intent: Optional[dict[str, Any]] = None
    confirm_entry: Optional[dict[str, Any]] = None
    refused_entry: Optional[dict[str, Any]] = None
    info: Optional[dict[str, Any]] = None
    rid = 0
    reason = ""
    db_aborted = False
    mirror_error: Optional[str] = None
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
        tc_err = _require_typed_confirm(args, f"ABORT_RUN_{rid}")
        if tc_err:
            _print_json({"ok": False, "error": tc_err})
            return EXIT_POLICY
        journal.verify()
        reason = str(getattr(args, "reason", "") or "")

        # Liveness gate (local pgrep — not network).
        try:
            pids = _list_shadow_runner_pids()
        except Exception as exc:  # noqa: BLE001 — QuiescenceError etc.
            _print_json(
                {
                    "ok": False,
                    "error": f"abort-run refused: cannot attest runner liveness: {exc}",
                }
            )
            return EXIT_POLICY
        if pids:
            _print_json(
                {
                    "ok": False,
                    "error": (
                        "abort-run refused: shadow_runner still running "
                        f"(pids={','.join(pids)}); stop process before abort"
                    ),
                    "runner_pids": pids,
                }
            )
            return EXIT_POLICY

        ph_intent = hashlib.sha256(
            f"abort-run-intent:{rid}:{reason}".encode("utf-8")
        ).hexdigest()
        # Local journal only — no mirror yet (network must not block abort).
        intent = journal.append(
            "abort_run_intent",
            ph_intent,
            {"run_id": rid, "reason": reason},
        )

        conn = _conn(args)
        try:
            conn.execute("BEGIN IMMEDIATE")
            info = abort_run(
                conn, rid, reason=reason, allow_live=_allow_live(args)
            )
            conn.execute("COMMIT")
            db_aborted = True
        except LeaseError as lease_exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            ph_ref = hashlib.sha256(
                f"abort-run-refused:{rid}:{reason}:{lease_exc}".encode("utf-8")
            ).hexdigest()
            refused_entry = journal.append(
                "abort_run_refused",
                ph_ref,
                {
                    "run_id": rid,
                    "reason": reason,
                    "intent_seq": intent["seq"],
                    "error": str(lease_exc),
                },
            )
            # Best-effort mirror of intent+refused after local close.
            if args.mirror_remote:
                try:
                    fid = _require_audit_folder_id(args)
                    mirror_audit_entry(
                        intent, args.mirror_remote, folder_id=fid
                    )
                    mirror_audit_entry(
                        refused_entry, args.mirror_remote, folder_id=fid
                    )
                except AuditChainError as mex:
                    mirror_error = str(mex)
            _print_json(
                {
                    "ok": False,
                    "error": str(lease_exc),
                    "action": "abort_run_refused",
                    "run_id": rid,
                    "intent_seq": intent["seq"],
                    "refused_seq": refused_entry["seq"],
                    "db_aborted": False,
                    "mirror_error": mirror_error,
                }
            )
            return EXIT_POLICY

        ph_confirm = hashlib.sha256(
            f"abort-run-confirm:{rid}:{reason}:{info['closed_at']}".encode(
                "utf-8"
            )
        ).hexdigest()
        confirm_entry = journal.append(
            "abort_run_confirm",
            ph_confirm,
            {
                "run_id": rid,
                "reason": reason,
                "leases_revoked": info["leases_revoked"],
                "closed_at": info["closed_at"],
                "intent_seq": intent["seq"],
            },
        )

        # Mirror only after COMMIT — failure does not undo abort.
        if args.mirror_remote:
            try:
                fid = _require_audit_folder_id(args)
                mirror_audit_entry(intent, args.mirror_remote, folder_id=fid)
                mirror_audit_entry(
                    confirm_entry, args.mirror_remote, folder_id=fid
                )
            except AuditChainError as mex:
                mirror_error = str(mex)
    except (LivePathRefused, AuditChainError, sqlite3.Error) as exc:
        if conn is not None and not db_aborted:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
        _print_json(
            {
                "ok": False,
                "error": str(exc),
                "action": "abort_run",
                "run_id": rid or None,
                "db_aborted": db_aborted,
                "intent_seq": intent["seq"] if intent else None,
            }
        )
        return EXIT_POLICY
    finally:
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass
    assert confirm_entry is not None and info is not None and intent is not None
    out = {
        "ok": True,
        "action": "abort_run",
        "run_id": rid,
        "reason": reason,
        "intent_seq": intent["seq"],
        "audit_seq": confirm_entry["seq"],
        "leases_revoked": info["leases_revoked"],
        "db_aborted": True,
        "mirror_ok": mirror_error is None,
    }
    if mirror_error is not None:
        out["mirror_error"] = mirror_error
    _print_json(out)
    return EXIT_OK


def _retire_upload_gate_ok(
    journal: AppendOnlyAuditChain, cur_digest: str
) -> bool:
    entries = journal.read_entries()
    for e in reversed(entries):
        if e.get("action") == "db_artefact_upload":
            payload = e.get("payload") or {}
            dig = payload.get("logical_digest_sha256")
            return (
                bool(payload.get("ok"))
                and bool(payload.get("sha256"))
                and isinstance(dig, str)
                and len(dig) == 64
                and dig == cur_digest
            )
    return False


def _package_retire_prechecks(args: argparse.Namespace) -> Optional[str]:
    """V1–V8 for package retire. Returns error string or None. Lock untouched."""
    # V1
    journal = AppendOnlyAuditChain(_journal_path(args))
    journal.verify()
    # V4
    pids = _list_shadow_runner_pids()
    if pids:
        return f"retire refused: shadow_runner PIDs present: {pids}"
    # V2/V3/V5/V6 + digest via RO
    conn = _conn_ro(args)
    try:
        row = conn.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
        schema_version = int(row[0]) if row else 0
        if schema_version < SCHEMA_CONTROL:
            return (
                f"retire refused: schema_version={schema_version} "
                f"< SCHEMA_CONTROL={SCHEMA_CONTROL} (V2)"
            )
        trig = compute_trigger_manifest_sha256(conn)
        expected = expected_control_plane_manifest_sha256()
        if trig != expected:
            return (
                "retire refused: trigger manifest mismatch (V3): "
                f"observed={trig} expected={expected}"
            )
        running = conn.execute(
            "SELECT COUNT(*) FROM telemetry_runs WHERE status='RUNNING'"
        ).fetchone()[0]
        if running:
            return f"retire refused: RUNNING rows present (V5): {running}"
        open_leases = conn.execute(
            "SELECT COUNT(*) FROM run_lease"
            " WHERE consumed_at IS NULL AND revoked_at IS NULL"
        ).fetchone()[0]
        if open_leases:
            return f"retire refused: open leases present (V6): {open_leases}"
        cur_digest = compute_logical_digest_sha256(conn)
    finally:
        conn.close()
    # V7
    _probe_mirror_reachable(args)
    # V8
    if not _retire_upload_gate_ok(journal, cur_digest):
        return (
            "retire refused: E-1 upload gate (V8) requires prior "
            "db_artefact_upload ok=true bound to current logical digest"
        )
    # Quiescence + manifest match required for package
    build_snapshot_manifest(
        Path(args.db),
        Path(args.runner),
        Path(args.lock),
        Path(args.repo_root),
        check_quiescent=True,
        snapshot_dir=_snapshot_dir(args),
        persist_artefact=False,
        check_disk_headroom=_check_disk(args),
        require_manifest_match=True,
    )
    return None


def cmd_retire_run_lock(args: argparse.Namespace) -> int:
    """Retire RUN.lock → archive + RUN.RETIRED.

    Scratch: single ``retire_run_lock`` audit (legacy).
    Package (``--allow-package-retire``): Intent→mirror→rename→marker→Confirm
    (Rev. B §4). Soft-TABU without the switch.
    """
    lock = Path(args.lock).resolve()
    package_retire = bool(getattr(args, "allow_package_retire", False))
    is_pkg = _is_package_lock(lock)

    if is_pkg and not package_retire:
        _print_json(
            {
                "ok": False,
                "error": "retire-run-lock refused for package RUN.lock (TABU)",
            }
        )
        return EXIT_POLICY
    if package_retire and not is_pkg:
        _print_json(
            {
                "ok": False,
                "error": (
                    "--allow-package-retire refused on scratch lock "
                    "(switch only for package ops/RUN.lock)"
                ),
            }
        )
        return EXIT_POLICY
    if package_retire and bool(getattr(args, "skip_e1_upload_gate", False)):
        _print_json(
            {
                "ok": False,
                "error": (
                    "--skip-e1-upload-gate refused on package retire "
                    "(Rev. B §3)"
                ),
            }
        )
        return EXIT_POLICY
    if package_retire:
        tc_err = _require_typed_confirm(args, "RETIRE_PACKAGE_LOCK")
        if tc_err:
            _print_json({"ok": False, "error": tc_err})
            return EXIT_POLICY
        if is_live_agentx_path(Path(args.db)) and not _allow_live(args):
            _print_json(
                {
                    "ok": False,
                    "error": (
                        "package retire refused: --allow-live-db required "
                        "for RO prechecks on live-marked DB (Rev. B §A.4)"
                    ),
                }
            )
            return EXIT_POLICY

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
        if package_retire:
            err = _package_retire_prechecks(args)
            if err:
                _print_json({"ok": False, "error": err})
                return EXIT_POLICY
        else:
            journal.verify()
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
            skip_upload = bool(getattr(args, "skip_e1_upload_gate", False))
            if not skip_upload:
                conn_r = _conn_ro(args)
                try:
                    cur_digest = compute_logical_digest_sha256(conn_r)
                finally:
                    conn_r.close()
                if not _retire_upload_gate_ok(journal, cur_digest):
                    _print_json(
                        {
                            "ok": False,
                            "error": (
                                "retire refused: E-1 upload gate (default-on) "
                                "requires prior db_artefact_upload ok=true bound "
                                "to current logical digest; "
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

        mirror_remote = (
            getattr(args, "mirror_remote", None)
            or DEFAULT_AUDIT_MIRROR_REMOTE_PREFIX
        )
        mirror_folder = _require_audit_folder_id(args)
        mirror_error: Optional[str] = None

        if package_retire:
            # Intent → mirror (fail-closed, lock untouched) → mutate → Confirm
            ph_intent = hashlib.sha256(
                f"retire-run-lock-intent:{lock}:{before_sha}:{archive}".encode(
                    "utf-8"
                )
            ).hexdigest()
            intent = journal.append(
                "retire_run_lock_intent",
                ph_intent,
                {
                    "path": str(lock),
                    "before_sha256": before_sha,
                    "archive_path": str(archive),
                    "retired_marker": str(marker),
                },
            )
            mirror_audit_entry(
                intent, mirror_remote, folder_id=mirror_folder
            )
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
            ph_confirm = hashlib.sha256(
                f"retire-run-lock-confirm:{lock}:{before_sha}:{archive}".encode(
                    "utf-8"
                )
            ).hexdigest()
            confirm = journal.append(
                "retire_run_lock_confirm",
                ph_confirm,
                {
                    "path": str(lock),
                    "before_sha256": before_sha,
                    "archive_path": str(archive),
                    "method": "rename_archive",
                    "after_state": "absent",
                    "retired_marker": str(marker),
                    "intent_seq": intent["seq"],
                },
            )
            try:
                mirror_audit_entry(
                    confirm, mirror_remote, folder_id=mirror_folder
                )
            except AuditChainError as mex:
                mirror_error = str(mex)
            out = {
                "ok": True,
                "action": "retire_run_lock",
                "path": str(lock),
                "archive_path": str(archive),
                "before_sha256": before_sha,
                "retired_marker": str(marker),
                "intent_seq": intent["seq"],
                "audit_seq": confirm["seq"],
                "after_state": "absent",
                "package_retire": True,
            }
            if mirror_error is not None:
                out["ok"] = False
                out["mirror_error"] = mirror_error
                out["error"] = (
                    "retire confirm mirror failed; lock already absent+marker; "
                    "status shows open intent; undo via restore-run-lock"
                )
                _print_json(out)
                return EXIT_POLICY
            _print_json(out)
            return EXIT_OK

        # Scratch path — single retire_run_lock entry (suite compatibility)
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
                folder_id=_require_audit_folder_id(args),
            )
    except (
        AuditChainError,
        QuiescenceError,
        SnapshotError,
        ManifestMismatchError,
        LivePathRefused,
        OSError,
        sqlite3.Error,
    ) as exc:
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


def _last_retire_before_sha(
    journal: AppendOnlyAuditChain,
) -> Optional[tuple[str, str]]:
    """Return (before_sha256, archive_path) from last retire confirm/legacy."""
    entries = journal.read_entries()
    for e in reversed(entries):
        action = e.get("action")
        if action in ("retire_run_lock_confirm", "retire_run_lock"):
            payload = e.get("payload") or {}
            sha = payload.get("before_sha256")
            arch = payload.get("archive_path")
            if isinstance(sha, str) and len(sha) == 64 and isinstance(arch, str):
                return sha, arch
    return None


def _revoke_all_open_leases(
    conn: sqlite3.Connection, *, allow_live: bool
) -> list[str]:
    """Revoke every unconsumed open token; return token digests revoked."""
    rows = conn.execute(
        "SELECT token FROM run_lease"
        " WHERE consumed_at IS NULL AND revoked_at IS NULL"
    ).fetchall()
    digests: list[str] = []
    for row in rows:
        tok = row[0]
        revoke_token(conn, tok, allow_live=allow_live)
        digests.append(token_sha256(tok))
    return digests


def cmd_restore_run_lock(args: argparse.Namespace) -> int:
    """Undo package/scratch retire: marker-first, then archive→RUN.lock (Rev. B §5)."""
    lock = Path(args.lock).resolve()
    marker = lock.parent / "RUN.RETIRED"
    clear_stale = bool(getattr(args, "clear_stale_marker", False))

    tc_err = _require_typed_confirm(args, "RESTORE_PACKAGE_LOCK")
    if tc_err:
        # Scratch restore: allow --i-am-a-test (already handled inside helper)
        _print_json({"ok": False, "error": tc_err})
        return EXIT_POLICY

    # Lock+Marker heal path
    if lock.is_file() and marker.is_file():
        if not clear_stale:
            _print_json(
                {
                    "ok": False,
                    "error": (
                        "restore refused: lock and RUN.RETIRED both present; "
                        "use --clear-stale-marker to audit-remove marker only"
                    ),
                }
            )
            return EXIT_POLICY
        journal = AppendOnlyAuditChain(_journal_path(args))
        try:
            journal.verify()
            ph = hashlib.sha256(
                f"restore-clear-marker:{lock}:{marker}".encode("utf-8")
            ).hexdigest()
            entry = journal.append(
                "restore_run_lock_clear_marker",
                ph,
                {"path": str(lock), "marker": str(marker)},
            )
            if args.mirror_remote:
                mirror_audit_entry(
                    entry,
                    args.mirror_remote,
                    folder_id=_require_audit_folder_id(args),
                )
            marker.unlink()
        except (AuditChainError, OSError) as exc:
            _print_json({"ok": False, "error": str(exc)})
            return EXIT_POLICY
        _print_json(
            {
                "ok": True,
                "action": "restore_run_lock_clear_marker",
                "path": str(lock),
                "audit_seq": entry["seq"],
            }
        )
        return EXIT_OK

    if lock.is_file():
        _print_json(
            {
                "ok": False,
                "error": "restore refused: RUN.lock already present (R1)",
            }
        )
        return EXIT_POLICY

    journal = AppendOnlyAuditChain(_journal_path(args))
    try:
        journal.verify()
        pids = _list_shadow_runner_pids()
        if pids:
            _print_json(
                {
                    "ok": False,
                    "error": f"restore refused: shadow_runner PIDs: {pids}",
                }
            )
            return EXIT_POLICY

        retire_info = _last_retire_before_sha(journal)
        if retire_info is None:
            _print_json(
                {
                    "ok": False,
                    "error": "restore refused: no retire audit with before_sha256",
                }
            )
            return EXIT_POLICY
        before_sha, audit_archive = retire_info

        archive_arg = getattr(args, "archive", None)
        archive: Path
        if archive_arg:
            archive = Path(archive_arg).resolve()
        else:
            archives = sorted(
                lock.parent.glob(f"{lock.name}.retired.*"),
                key=lambda p: p.stat().st_mtime,
            )
            if marker.is_file():
                archive = Path(audit_archive)
                for line in marker.read_text(encoding="utf-8").splitlines():
                    if line.startswith("archive="):
                        archive = Path(line.split("=", 1)[1].strip())
                        break
            elif len(archives) == 0:
                archive = Path(audit_archive)
            elif len(archives) == 1:
                archive = archives[0]
            else:
                _print_json(
                    {
                        "ok": False,
                        "error": (
                            "restore refused: multiple archives without marker; "
                            "pass --archive <path>"
                        ),
                        "archives": [str(a) for a in archives],
                    }
                )
                return EXIT_POLICY

        if not archive.is_file():
            _print_json(
                {"ok": False, "error": f"restore refused: archive missing: {archive}"}
            )
            return EXIT_POLICY
        arch_sha = sha256_file_streaming(archive)
        if arch_sha != before_sha:
            _print_json(
                {
                    "ok": False,
                    "error": (
                        "restore refused: archive SHA mismatch (R3): "
                        f"archive={arch_sha} audit={before_sha}"
                    ),
                }
            )
            return EXIT_POLICY

        # Revoke open tokens before bringing lock back
        revoked: list[str] = []
        conn = _conn(args)
        try:
            revoked = _revoke_all_open_leases(
                conn, allow_live=_allow_live(args)
            )
            if revoked:
                ph_rev = hashlib.sha256(
                    f"restore-revoke:{lock}:{','.join(revoked)}".encode("utf-8")
                ).hexdigest()
                rev_entry = journal.append(
                    "restore_run_lock_revoke_open",
                    ph_rev,
                    {"path": str(lock), "revoked_token_sha256": revoked},
                )
                if args.mirror_remote:
                    mirror_audit_entry(
                        rev_entry,
                        args.mirror_remote,
                        folder_id=_require_audit_folder_id(args),
                    )
        finally:
            conn.close()

        mirror_remote = (
            getattr(args, "mirror_remote", None)
            or DEFAULT_AUDIT_MIRROR_REMOTE_PREFIX
        )
        mirror_folder = _require_audit_folder_id(args)
        ph_intent = hashlib.sha256(
            f"restore-run-lock-intent:{lock}:{archive}:{before_sha}".encode(
                "utf-8"
            )
        ).hexdigest()
        intent = journal.append(
            "restore_run_lock_intent",
            ph_intent,
            {
                "path": str(lock),
                "archive_path": str(archive),
                "before_sha256": before_sha,
                "marker_present": marker.is_file(),
            },
        )
        mirror_audit_entry(intent, mirror_remote, folder_id=mirror_folder)

        # Marker first (if present), then archive → lock
        if marker.is_file():
            marker.unlink()
        archive.rename(lock)

        ph_confirm = hashlib.sha256(
            f"restore-run-lock-confirm:{lock}:{before_sha}".encode("utf-8")
        ).hexdigest()
        confirm = journal.append(
            "restore_run_lock_confirm",
            ph_confirm,
            {
                "path": str(lock),
                "archive_path": str(archive),
                "before_sha256": before_sha,
                "intent_seq": intent["seq"],
                "revoked_token_sha256": revoked,
            },
        )
        mirror_error: Optional[str] = None
        try:
            mirror_audit_entry(
                confirm, mirror_remote, folder_id=mirror_folder
            )
        except AuditChainError as mex:
            mirror_error = str(mex)
    except (
        AuditChainError,
        LivePathRefused,
        LeaseError,
        OSError,
        sqlite3.Error,
    ) as exc:
        _print_json({"ok": False, "error": str(exc)})
        return EXIT_POLICY

    out: dict[str, Any] = {
        "ok": True,
        "action": "restore_run_lock",
        "path": str(lock),
        "intent_seq": intent["seq"],
        "audit_seq": confirm["seq"],
        "revoked_tokens": len(revoked),
    }
    if mirror_error is not None:
        out["mirror_error"] = mirror_error
    _print_json(out)
    return EXIT_OK


def cmd_restore_db_artefact(args: argparse.Namespace) -> int:
    """E-1 rollback: replace DB only after pre-snapshot SHA match + L4."""
    tc_err = _require_typed_confirm(args, "ALLOW_LIVE_DB")
    if tc_err:
        _print_json({"ok": False, "error": tc_err})
        return EXIT_POLICY
    if not _allow_live(args) and is_live_agentx_path(Path(args.db)):
        _print_json(
            {
                "ok": False,
                "error": "restore-db-artefact requires --allow-live-db on LIVE",
            }
        )
        return EXIT_POLICY
    artefact = Path(args.artefact).resolve()
    db = Path(args.db).resolve()
    if not artefact.is_file():
        _print_json({"ok": False, "error": f"artefact missing: {artefact}"})
        return EXIT_POLICY
    expected = str(getattr(args, "expected_sha256", "") or "")
    if len(expected) != 64:
        _print_json(
            {
                "ok": False,
                "error": "--expected-sha256 (64 hex) required (pre-snapshot)",
            }
        )
        return EXIT_POLICY
    journal = AppendOnlyAuditChain(_journal_path(args))
    try:
        journal.verify()
        art_sha = sha256_file_streaming(artefact)
        if art_sha != expected:
            _print_json(
                {
                    "ok": False,
                    "error": (
                        "restore-db-artefact refused: artefact SHA mismatch: "
                        f"got={art_sha} expected={expected}"
                    ),
                }
            )
            return EXIT_POLICY
        before_sha = (
            sha256_file_streaming(db) if db.is_file() else None
        )
        ph_intent = hashlib.sha256(
            f"restore-db-artefact-intent:{db}:{art_sha}".encode("utf-8")
        ).hexdigest()
        intent = journal.append(
            "restore_db_artefact_intent",
            ph_intent,
            {
                "db": str(db),
                "artefact": str(artefact),
                "artefact_sha256": art_sha,
                "before_sha256": before_sha,
            },
        )
        if args.mirror_remote:
            mirror_audit_entry(
                intent,
                args.mirror_remote,
                folder_id=_require_audit_folder_id(args),
            )
        # Replace via tempfile + rename
        tmp = db.with_suffix(db.suffix + ".restore_tmp")
        shutil.copy2(artefact, tmp)
        os.replace(str(tmp), str(db))
        after_sha = sha256_file_streaming(db)
        if after_sha != art_sha:
            raise SnapshotError(
                f"post-restore SHA drift: {after_sha} != {art_sha}"
            )
        ph_confirm = hashlib.sha256(
            f"restore-db-artefact-confirm:{db}:{after_sha}".encode("utf-8")
        ).hexdigest()
        confirm = journal.append(
            "restore_db_artefact_confirm",
            ph_confirm,
            {
                "db": str(db),
                "artefact_sha256": art_sha,
                "after_sha256": after_sha,
                "intent_seq": intent["seq"],
            },
        )
        if args.mirror_remote:
            mirror_audit_entry(
                confirm,
                args.mirror_remote,
                folder_id=_require_audit_folder_id(args),
            )
    except (AuditChainError, SnapshotError, OSError) as exc:
        _print_json({"ok": False, "error": str(exc)})
        return EXIT_POLICY
    _print_json(
        {
            "ok": True,
            "action": "restore_db_artefact",
            "db": str(db),
            "artefact_sha256": art_sha,
            "after_sha256": after_sha,
            "intent_seq": intent["seq"],
            "audit_seq": confirm["seq"],
        }
    )
    return EXIT_OK


def cmd_post_run_check(args: argparse.Namespace) -> int:
    """Post-run invariants; optional ``--run-id`` scopes the terminal check.

    DB reads use RO connect (no WAL flip). Snapshot artefact persist is file-only.
    """
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
        conn = _conn_ro(args)
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
                if run_row["status"] not in ("ABORTED", "COMMITTED", "STOPPED"):
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
                folder_id=_require_audit_folder_id(args),
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
            folder_id=_require_audit_folder_id(args),
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
    p = argparse.ArgumentParser(prog="gatectl", allow_abbrev=False)
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
        default=None,
        help=(
            "Drive folder for audit objects (required: env "
            "AUDIT_OBJECTS_FOLDER_ID or this flag; no incr-bundle fallback)"
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
        "--typed-confirm",
        type=str,
        default=None,
        help=(
            "L4 scratch/suite only: fixed phrase stem; "
            "refused on live-marked DB and package lock (TTY+nonce required)"
        ),
    )
    p.add_argument(
        "--i-am-a-test",
        action="store_true",
        help=(
            "L4 test hook: bypass typed confirm on scratch only; "
            "refused on live-marked DB and package lock"
        ),
    )
    p.add_argument(
        "--news-jsonl",
        type=Path,
        default=None,
        help="Optional news_scores.jsonl for post-run-check prefix SHA",
    )
    p.add_argument(
        "--role",
        type=str,
        default=None,
        help=(
            "L4 role: runner|watchdog|auditor|operator "
            "(or CONTROL_PLANE_ROLE; deny-by-default when Authz enforced)"
        ),
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
    p_retire.add_argument(
        "--allow-package-retire",
        action="store_true",
        help="Rev. B: lift soft-TABU for package ops/RUN.lock (V1–V8 + L4)",
    )
    p_retire.set_defaults(
        func=cmd_retire_run_lock,
        skip_e1_upload_gate=False,
        allow_package_retire=False,
    )

    p_restore = sub.add_parser("restore-run-lock")
    p_restore.add_argument(
        "--archive",
        type=Path,
        default=None,
        help="Explicit archive path when multiple .retired.* exist",
    )
    p_restore.add_argument(
        "--clear-stale-marker",
        action="store_true",
        help="Heal Lock+Marker: audit-remove RUN.RETIRED only",
    )
    p_restore.set_defaults(func=cmd_restore_run_lock)

    p_rdb = sub.add_parser("restore-db-artefact")
    p_rdb.add_argument(
        "--artefact",
        type=Path,
        required=True,
        help="Pre-migrate snapshot artefact to restore onto --db",
    )
    p_rdb.add_argument(
        "--expected-sha256",
        type=str,
        required=True,
        help="Pre-snapshot SHA-256; refuse on mismatch",
    )
    p_rdb.set_defaults(func=cmd_restore_db_artefact)

    p_post = sub.add_parser("post-run-check")
    p_post.add_argument("--run-id", type=int, default=None)
    p_post.set_defaults(func=cmd_post_run_check)

    p_vm = sub.add_parser("verify-mirror")
    p_vm.set_defaults(func=cmd_verify_mirror)

    p_wd = sub.add_parser(
        "watchdog-check",
        help=(
            "L2: RO scan for stuck RUNNING runs (age_s > T_max); "
            "alarm to stderr (+ optional --alarm-log). No launchd."
        ),
    )
    p_wd.add_argument(
        "--t-max-s",
        type=float,
        default=None,
        help=f"Stuck threshold seconds (default {DEFAULT_T_MAX_S}=2×TTL_MAX_S)",
    )
    p_wd.add_argument(
        "--alarm-log",
        type=Path,
        default=None,
        help="Optional append-only JSONL alarm channel path",
    )
    p_wd.set_defaults(func=cmd_watchdog_check)

    return p


def _l4_allow_live_gate(args: argparse.Namespace) -> Optional[str]:
    """L4 for --allow-live-db on commands that do not have a more specific phrase."""
    if not getattr(args, "allow_live_db", False):
        return None
    cmd = getattr(args, "command", "")
    # Specific phrases already cover these; skip double-confirm.
    if cmd in (
        "retire-run-lock",
        "restore-run-lock",
        "abort-run",
        "restore-db-artefact",
    ):
        return None
    return _require_typed_confirm(args, "ALLOW_LIVE_DB")


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "allow_busy"):
        args.allow_busy = False
    if not hasattr(args, "allow_live_skip_disk_check"):
        args.allow_live_skip_disk_check = False
    if not hasattr(args, "news_jsonl"):
        args.news_jsonl = None
    if not hasattr(args, "typed_confirm"):
        args.typed_confirm = None
    if not hasattr(args, "i_am_a_test"):
        args.i_am_a_test = False
    if not hasattr(args, "role"):
        args.role = None
    # L4-C1: default enforce (unset ⇒ Deny). No Allow-All when env forgotten.
    if authz_enforced():
        role = getattr(args, "role", None)
        env_role = os.environ.get("CONTROL_PLANE_ROLE", "").strip()
        try:
            authorize(
                role if role is not None else (env_role or None),
                str(getattr(args, "command", "")),
                target=str(getattr(args, "db", "") or ""),
            )
        except AuthzError as exc:
            _print_json({"ok": False, "error": f"authz deny: {exc}"})
            return EXIT_POLICY
    live_err = _l4_allow_live_gate(args)
    if live_err:
        _print_json({"ok": False, "error": live_err})
        return EXIT_POLICY
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
