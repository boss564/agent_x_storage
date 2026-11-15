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
import sqlite3
from pathlib import Path
from typing import Any, Optional

from order_execution_engine.control_plane_audit import (
    AppendOnlyAuditChain,
    AuditChainError,
    ManifestMismatchError,
    QuiescenceError,
    SnapshotError,
    build_snapshot_manifest,
    expected_control_plane_manifest_sha256,
    mirror_audit_entry,
    token_sha256,
)
from order_execution_engine.control_plane_lease import (
    SCHEMA_CONTROL,
    LeaseError,
    LivePathRefused,
    connect_scratch,
    issue_token,
    migrate_control_plane,
    next_run_id,
    revoke_token,
)

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
    """Production default True; Scratch tests may set --skip-disk-check."""
    return not bool(getattr(args, "skip_disk_check", False))


def _mirror_required_entry(
    args: argparse.Namespace, entry: dict[str, Any]
) -> Optional[str]:
    remote = getattr(args, "mirror_remote", None)
    if not remote:
        return None
    return mirror_audit_entry(entry, remote)


def cmd_verify_snapshot(args: argparse.Namespace) -> int:
    journal = AppendOnlyAuditChain(_journal_path(args))
    try:
        journal.verify()
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
        entry = journal.append(
            "verify_snapshot",
            manifest["manifest_sha256"],
            {
                "max_run_id": manifest["max_run_id"],
                "logical_digest_sha256": manifest["logical_digest_sha256"],
                "artefact_sha256": manifest["artefact_sha256"],
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
    """Intent → issue → confirm (+ optional immutable mirror). No raw token."""
    if not args.mirror_remote:
        _print_json(
            {
                "ok": False,
                "error": "issue-token requires --mirror-remote (off-host anchor)",
            }
        )
        return EXIT_POLICY

    journal = AppendOnlyAuditChain(_journal_path(args))
    conn = None
    token: Optional[str] = None
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
        conn = connect_scratch(Path(args.db))
        run_id = int(args.run_id) if args.run_id is not None else next_run_id(conn)
        ttl_s = int(args.ttl)

        intent = journal.append(
            "issue_token_intent",
            manifest["manifest_sha256"],
            {"run_id": run_id, "ttl_s": ttl_s},
        )
        mirror_audit_entry(intent, args.mirror_remote)

        token = issue_token(conn, run_id=run_id, ttl_s=ttl_s)
        digest = token_sha256(token)
        try:
            confirm = journal.append(
                "issue_token_confirm",
                manifest["manifest_sha256"],
                {
                    "run_id": run_id,
                    "ttl_s": ttl_s,
                    "token_sha256": digest,
                    "intent_seq": intent["seq"],
                },
            )
            mirror_audit_entry(confirm, args.mirror_remote)
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
        conn = connect_scratch(Path(args.db))
        try:
            row = conn.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()
            schema_version = int(row[0]) if row else 0
            open_leases = conn.execute(
                "SELECT COUNT(*) FROM run_lease"
                " WHERE consumed_at IS NULL AND revoked_at IS NULL"
            ).fetchone()[0]
            running = conn.execute(
                "SELECT COUNT(*) FROM telemetry_runs WHERE status='RUNNING'"
            ).fetchone()[0]
            out["db_state"] = {
                "schema_version": schema_version,
                "schema_ok": schema_version >= SCHEMA_CONTROL,
                "open_leases": int(open_leases),
                "running_runs": int(running),
            }
            if schema_version < SCHEMA_CONTROL or running:
                out["ok"] = False
        finally:
            conn.close()
    except (LivePathRefused, sqlite3.Error, OSError, TypeError, ValueError) as exc:
        out["ok"] = False
        out["db_state_error"] = str(exc)

    _print_json(out)
    return EXIT_OK if out.get("ok") else EXIT_POLICY


def cmd_migrate(args: argparse.Namespace) -> int:
    try:
        conn = connect_scratch(Path(args.db))
        try:
            migrate_control_plane(conn, db_path=Path(args.db))
            row = conn.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()
            ver = int(row[0]) if row else 0
        finally:
            conn.close()
    except (LeaseError, LivePathRefused, sqlite3.Error, OSError) as exc:
        _print_json({"ok": False, "error": str(exc)})
        return EXIT_POLICY
    _print_json(
        {
            "ok": True,
            "action": "migrate",
            "schema_version": ver,
            "expected_manifest": expected_control_plane_manifest_sha256(),
        }
    )
    return EXIT_OK


def cmd_abort_run(args: argparse.Namespace) -> int:
    journal = AppendOnlyAuditChain(_journal_path(args))
    try:
        journal.verify()
        conn = connect_scratch(Path(args.db))
        try:
            rid = int(args.run_id)
            cur = conn.execute(
                "UPDATE telemetry_runs SET status='ABORTED',"
                " closed_at=CAST(strftime('%s','now') AS INTEGER)"
                " WHERE run_id=? AND status='RUNNING'",
                (rid,),
            )
            if cur.rowcount != 1:
                raise LeaseError(
                    f"abort-run refused: run_id={rid} not RUNNING"
                )
            # Placeholder manifest hash when snapshot skipped (still chainable).
            ph = hashlib.sha256(
                f"abort-run:{rid}".encode("utf-8")
            ).hexdigest()
            entry = journal.append(
                "abort_run",
                ph,
                {"run_id": rid},
            )
            if args.mirror_remote:
                mirror_audit_entry(entry, args.mirror_remote)
        finally:
            conn.close()
    except (LeaseError, LivePathRefused, AuditChainError, sqlite3.Error) as exc:
        _print_json({"ok": False, "error": str(exc)})
        return EXIT_POLICY
    _print_json({"ok": True, "action": "abort_run", "run_id": rid, "audit_seq": entry["seq"]})
    return EXIT_OK


def cmd_retire_run_lock(args: argparse.Namespace) -> int:
    """Refuse production ops/RUN.lock; scratch locks only (TABU)."""
    lock = Path(args.lock).resolve()
    if lock == _REAL_LOCK:
        _print_json(
            {
                "ok": False,
                "error": "retire-run-lock refused for package RUN.lock (TABU)",
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
    new = text.replace("LOCKED=1", "LOCKED=0", 1)
    lock.write_text(new, encoding="utf-8")
    _print_json({"ok": True, "action": "retire_run_lock", "path": str(lock)})
    return EXIT_OK


def cmd_post_run_check(args: argparse.Namespace) -> int:
    journal = AppendOnlyAuditChain(_journal_path(args))
    try:
        journal.verify()
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
        conn = connect_scratch(Path(args.db))
        try:
            running = conn.execute(
                "SELECT COUNT(*) FROM telemetry_runs WHERE status='RUNNING'"
            ).fetchone()[0]
            open_leases = conn.execute(
                "SELECT COUNT(*) FROM run_lease"
                " WHERE consumed_at IS NULL AND revoked_at IS NULL"
            ).fetchone()[0]
        finally:
            conn.close()
        if running or open_leases:
            raise SnapshotError(
                f"post-run-check failed: running={running} open_leases={open_leases}"
            )
        entry = journal.append(
            "post_run_check",
            manifest["manifest_sha256"],
            {
                "max_run_id": manifest["max_run_id"],
                "logical_digest_sha256": manifest["logical_digest_sha256"],
            },
        )
        if args.mirror_remote:
            mirror_audit_entry(entry, args.mirror_remote)
    except (
        QuiescenceError,
        SnapshotError,
        ManifestMismatchError,
        AuditChainError,
        LivePathRefused,
    ) as exc:
        _print_json({"ok": False, "error": str(exc)})
        return EXIT_POLICY
    _print_json(
        {
            "ok": True,
            "action": "post_run_check",
            "max_run_id": manifest["max_run_id"],
            "audit_seq": entry["seq"],
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
        default=None,
        help="rclone remote prefix for immutable per-entry mirrors",
    )
    p.add_argument(
        "--skip-disk-check",
        action="store_true",
        help="Scratch/tests only: allow persist artefacts when volume is nearly full",
    )

    sub = p.add_subparsers(dest="command", required=True)

    p_verify = sub.add_parser("verify-snapshot")
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
    p_abort.set_defaults(func=cmd_abort_run)

    p_retire = sub.add_parser("retire-run-lock")
    p_retire.set_defaults(func=cmd_retire_run_lock)

    p_post = sub.add_parser("post-run-check")
    p_post.set_defaults(func=cmd_post_run_check)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "allow_busy"):
        args.allow_busy = False
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
