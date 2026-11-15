"""Phase-2 Control-Plane: quiescent snapshot, audit chain, immutable mirror.

Scratch/gatectl helpers. Does not touch production RUN.lock, LIVE_DB, or
shadow_runner. Table ``telemetry_runs`` maps prompt ``runs``.
"""

from __future__ import annotations

import fcntl
import functools
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

GENESIS_HASH = "0" * 64
_WHITESPACE_RE = re.compile(r"\s+")
# launchd starts ``-m order_execution_engine.shadow_runner`` (no ``.py``).
_RUNNER_PGREP_PATTERN = "shadow_runner"
# Logical digest omits lease fencing rows only (K4 / I1).
_LOGICAL_DIGEST_EXCLUDE_TABLES = frozenset({"run_lease"})
# Refuse persisting snapshot artefacts when volume is this full (project rule).
_DISK_USAGE_REFUSE_RATIO = 0.85
# Gate #4: chunked file digest (1 MiB) — never load whole DB into RAM.
SHA256_CHUNK_SIZE = 1024 * 1024


class QuiescenceError(RuntimeError):
    """Runner process or DB writer still active — snapshot refused."""


class AuditChainError(RuntimeError):
    """Audit journal integrity or append failure."""


class SnapshotError(RuntimeError):
    """Snapshot / DB integrity failure."""


class ManifestMismatchError(SnapshotError):
    """Observed control-plane DDL manifest ≠ expected from code."""


def _normalize_sql(sql: Optional[str]) -> str:
    if not sql:
        return ""
    return _WHITESPACE_RE.sub(" ", sql.strip())


def _canonical_json(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def sha256_file_streaming(
    path: Path, *, chunk_size: int = SHA256_CHUNK_SIZE
) -> str:
    """Chunked SHA-256 of a file (Gate #4 streaming digest)."""
    if chunk_size < 1:
        raise SnapshotError(f"chunk_size must be >= 1, got {chunk_size}")
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_file(path: Path) -> str:
    return sha256_file_streaming(path)


def compute_jsonl_prefix_sha256(
    path: Path,
    *,
    byte_offset: int = 0,
    byte_length: Optional[int] = None,
    chunk_size: int = SHA256_CHUNK_SIZE,
) -> dict[str, Any]:
    """SHA-256 of a byte prefix of a JSONL (or any) file — Gate #4.

    Digests ``path[byte_offset : byte_offset + byte_length]`` (or to EOF when
    ``byte_length`` is None). Returns offset/size/sha so append-only growth of
    ``news_scores.jsonl`` (and similar) stays verifiable without re-hashing
    the whole file history.
    """
    p = Path(path)
    if not p.is_file():
        raise SnapshotError(f"jsonl missing: {p}")
    if byte_offset < 0:
        raise SnapshotError(f"byte_offset must be >= 0, got {byte_offset}")
    if byte_length is not None and byte_length < 0:
        raise SnapshotError(f"byte_length must be >= 0, got {byte_length}")
    file_size = p.stat().st_size
    if byte_offset > file_size:
        raise SnapshotError(
            f"byte_offset {byte_offset} beyond file size {file_size}"
        )
    remaining = file_size - byte_offset
    to_read = remaining if byte_length is None else min(byte_length, remaining)
    h = hashlib.sha256()
    with p.open("rb") as fh:
        fh.seek(byte_offset)
        left = to_read
        while left > 0:
            n = min(chunk_size, left)
            chunk = fh.read(n)
            if not chunk:
                break
            h.update(chunk)
            left -= len(chunk)
    return {
        "path": str(p.resolve()),
        "byte_offset": int(byte_offset),
        "byte_length": int(to_read),
        "file_size": int(file_size),
        "sha256": h.hexdigest(),
    }


def _git_head(repo_root: Path) -> str:
    if not (Path(repo_root) / ".git").exists():
        return "none"
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return "none"
    if proc.returncode != 0:
        return "none"
    return (proc.stdout or "").strip() or "none"


def compute_control_plane_manifest_sha256(conn: sqlite3.Connection) -> str:
    """G2 DDL manifest: tables + open-lease index + triggers (both tables).

    Same coverage as ``control_plane_lease.trigger_manifest_sha256``; kept here
    so snapshot/status can run on read-only snapshot connections.
    """
    parts: list[str] = []
    for tbl in ("run_lease", "telemetry_runs"):
        row = conn.execute(
            "SELECT sql FROM sqlite_master"
            " WHERE type = 'table' AND name = ?",
            (tbl,),
        ).fetchone()
        parts.append(
            f"TABLE {tbl}\n{_normalize_sql(row[0] if row else None)}"
        )
    idx = conn.execute(
        "SELECT name, sql FROM sqlite_master"
        " WHERE type = 'index' AND name = 'ux_run_lease_open_run'"
    ).fetchone()
    parts.append(
        "INDEX ux_run_lease_open_run\n"
        + _normalize_sql(idx[1] if idx else None)
    )
    for row in conn.execute(
        "SELECT name, sql FROM sqlite_master"
        " WHERE type = 'trigger'"
        "   AND tbl_name IN ('run_lease', 'telemetry_runs')"
        " ORDER BY name"
    ):
        parts.append(f"TRIGGER {row[0]}\n{_normalize_sql(row[1])}")
    return hashlib.sha256("\n--\n".join(parts).encode("utf-8")).hexdigest()


# Back-compat alias (Phase-2 first draft name).
def compute_trigger_manifest_sha256(conn: sqlite3.Connection) -> str:
    return compute_control_plane_manifest_sha256(conn)


# Release pin (Gate #5 / v13 DDL — STOPPED terminal). Code mutations that change triggers must
# update this constant in the same commit — otherwise ensure/gatectl refuse.
PINNED_CONTROL_PLANE_MANIFEST_SHA256 = (
    "8f75665569a0daacac189c43a297154d4907b058f5866d0436b2577bf3528a95"
)

@functools.lru_cache(maxsize=1)
def expected_control_plane_manifest_sha256() -> str:
    """Sollwert: migrate a scratch v9 DB with module code, then G2-hash.

    Temp dir is always removed (disk headroom). Result must equal
    ``PINNED_CONTROL_PLANE_MANIFEST_SHA256`` or the release pin is stale.
    """
    from order_execution_engine.control_plane_lease import migrate_control_plane
    from order_execution_engine.persistence import SQLiteShadowStorage

    with tempfile.TemporaryDirectory(prefix="cp_manifest_expected_") as tmp_s:
        tmp = Path(tmp_s)
        store = SQLiteShadowStorage.for_user(tmp, "expected")
        try:
            db_path = store._db_path  # noqa: SLF001
            migrate_control_plane(store._conn, db_path=db_path)  # noqa: SLF001
            digest = compute_control_plane_manifest_sha256(store._conn)  # noqa: SLF001
        finally:
            store.close()
    if digest != PINNED_CONTROL_PLANE_MANIFEST_SHA256:
        raise RuntimeError(
            "control-plane Soll-manifest drifted from release pin: "
            f"computed={digest} pinned={PINNED_CONTROL_PLANE_MANIFEST_SHA256}"
        )
    return digest


def _list_shadow_runner_pids() -> list[str]:
    """PIDs matching ``shadow_runner`` (module or ``.py`` cmdline)."""
    try:
        proc = subprocess.run(
            ["pgrep", "-f", _RUNNER_PGREP_PATTERN],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except FileNotFoundError as exc:
        raise QuiescenceError(
            f"pgrep unavailable — cannot attest quiescence: {exc}"
        ) from exc
    except subprocess.SubprocessError as exc:
        raise QuiescenceError(f"pgrep failed: {exc}") from exc
    if proc.returncode not in (0, 1):
        raise QuiescenceError(
            f"pgrep exit {proc.returncode}: {(proc.stderr or '').strip()}"
        )
    if proc.returncode == 1 or not (proc.stdout or "").strip():
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def assert_quiescent(
    *,
    list_pids: Callable[[], list[str]] = _list_shadow_runner_pids,
) -> None:
    pids = list_pids()
    if pids:
        raise QuiescenceError(
            "shadow_runner still running — refuse snapshot; "
            f"pids={','.join(pids)}"
        )


def assert_db_writer_quiescent(db_path: Path, *, busy_ms: int = 50) -> None:
    """Refuse snapshot if source DB cannot be locked (BEGIN IMMEDIATE)."""
    abs_path = Path(db_path).resolve()
    if not abs_path.is_file():
        raise SnapshotError(f"db not found: {abs_path}")
    conn = sqlite3.connect(str(abs_path), timeout=busy_ms / 1000.0)
    try:
        conn.execute(f"PRAGMA busy_timeout = {int(busy_ms)}")
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            raise QuiescenceError(
                f"db source locked — refuse snapshot: {exc}"
            ) from exc
        conn.execute("ROLLBACK")
    finally:
        conn.close()


def assert_disk_headroom(
    path: Path, *, refuse_ratio: float = _DISK_USAGE_REFUSE_RATIO
) -> dict[str, float]:
    """Refuse new persistent artefacts when volume usage ≥ refuse_ratio."""
    usage = shutil.disk_usage(str(Path(path)))
    used_ratio = (usage.total - usage.free) / float(usage.total)
    if used_ratio >= refuse_ratio:
        raise SnapshotError(
            f"disk usage {used_ratio:.1%} >= {refuse_ratio:.0%} at {path} "
            "— refuse new snapshot artefact (need Off-Host backup before delete)"
        )
    return {
        "total": float(usage.total),
        "free": float(usage.free),
        "used_ratio": float(used_ratio),
    }


def assert_skip_disk_check_allowed(
    *paths: Path, allow_live: bool = False
) -> None:
    """``--skip-disk-check`` is Scratch-only unless ``allow_live`` Freigabe.

    Fail-closed: any path under LIVE ``Application Support/agentx`` refuses
    the skip without explicit ``--allow-live-skip-disk-check``.
    """
    if allow_live:
        return
    from order_execution_engine.control_plane_lease import LivePathRefused

    for raw in paths:
        if raw is None:
            continue
        lowered = str(Path(raw).resolve()).lower()
        if "application support/agentx" in lowered:
            raise LivePathRefused(
                f"refuse --skip-disk-check on LIVE path without "
                f"--allow-live-skip-disk-check: {Path(raw).resolve()}"
            )


def _backup_db_quiescent(src: Path, dest: Path, *, busy_ms: int = 50) -> None:
    """K4 artefact via ``VACUUM INTO`` on a read-only source connection.

    Writer quiescence is probed separately with ``BEGIN IMMEDIATE`` on a
    short-lived RW connection (documented Live-DB side effect; not a lasting
    write). The copy itself uses ``mode=ro`` so the artefact path is the only
    write target.
    """
    assert_db_writer_quiescent(Path(src), busy_ms=busy_ms)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    abs_src = Path(src).resolve()
    abs_dest = dest.resolve()
    if "'" in abs_dest.as_posix():
        raise SnapshotError(f"snapshot path must not contain quotes: {abs_dest}")
    uri = f"file:{abs_src.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=max(1.0, busy_ms / 1000.0))
    try:
        conn.execute(f"PRAGMA busy_timeout = {int(busy_ms)}")
        try:
            conn.execute(f"VACUUM INTO '{abs_dest.as_posix()}'")
        except sqlite3.OperationalError as exc:
            raise QuiescenceError(
                f"VACUUM INTO refused (source busy?): {exc}"
            ) from exc
    finally:
        conn.close()


def _open_db_readonly(db_path: Path) -> sqlite3.Connection:
    abs_path = Path(db_path).resolve()
    if not abs_path.is_file():
        raise SnapshotError(f"db not found: {abs_path}")
    uri = f"file:{abs_path.as_posix()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=10.0)
    except sqlite3.Error as exc:
        raise SnapshotError(f"readonly open failed: {exc}") from exc
    conn.row_factory = sqlite3.Row
    return conn


def _schema_version(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
    except sqlite3.Error:
        return 0
    if row is None:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return 0


def _max_run_id(conn: sqlite3.Connection) -> int:
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "telemetry_runs" not in tables and "runs" not in tables:
        return 0
    table = "telemetry_runs" if "telemetry_runs" in tables else "runs"
    row = conn.execute(
        f"SELECT COALESCE(MAX(run_id), 0) FROM {table}"
    ).fetchone()
    return int(row[0])


def _quote_ident(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise SnapshotError(f"refusing unsafe SQL identifier: {name!r}")
    return name


def _logical_digest_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master"
        " WHERE type = 'table'"
        " ORDER BY name"
    ).fetchall()
    out: list[str] = []
    for (name,) in rows:
        if name.startswith("sqlite_"):
            continue
        if name in _LOGICAL_DIGEST_EXCLUDE_TABLES:
            continue
        out.append(name)
    return out


def _order_by_primary_key(conn: sqlite3.Connection, table: str) -> str:
    info = list(conn.execute(f"PRAGMA table_info({_quote_ident(table)})"))
    pk_cols = [row[1] for row in sorted(info, key=lambda r: r[5]) if row[5] > 0]
    if pk_cols:
        return ", ".join(_quote_ident(c) for c in pk_cols)
    return "rowid"


def _jsonable_cell(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"__bytes_hex__": value.hex()}
    if isinstance(value, memoryview):
        return {"__bytes_hex__": value.tobytes().hex()}
    return value


def compute_logical_digest_sha256(conn: sqlite3.Connection) -> str:
    """Full logical digest: every table except ``run_lease``, all columns (I1).

    Rows are ordered by primary key (or ``rowid``). ``sqlite_*`` internals and
    ``run_lease`` are omitted so lease fencing does not enter the data digest.
    """
    payload: dict[str, Any] = {"tables": {}}
    for table in _logical_digest_tables(conn):
        info = list(conn.execute(f"PRAGMA table_info({_quote_ident(table)})"))
        col_names = [row[1] for row in info]
        order_by = _order_by_primary_key(conn, table)
        select_list = ", ".join(_quote_ident(c) for c in col_names)
        sql = f"SELECT {select_list} FROM {_quote_ident(table)} ORDER BY {order_by}"
        rows = [
            [_jsonable_cell(v) for v in row]
            for row in conn.execute(sql).fetchall()
        ]
        payload["tables"][table] = {
            "columns": col_names,
            "rows": rows,
        }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def build_snapshot_manifest(
    db_path: Path,
    runner_path: Path,
    lock_path: Path,
    repo_root: Path,
    *,
    check_quiescent: bool = True,
    list_pids: Callable[[], list[str]] = _list_shadow_runner_pids,
    snapshot_dir: Optional[Path] = None,
    require_manifest_match: bool = True,
    persist_artefact: bool = True,
    check_disk_headroom: bool = True,
) -> dict[str, Any]:
    """Quiescent backup → artefact SHA + logical digest (no live-file hash).

    ``persist_artefact=True`` (verify-snapshot / post-run-check): write under
    ``snapshot_dir`` after disk-headroom check (≥85% refuse).
    ``persist_artefact=False`` (status / issue-token): temp copy, deleted after.
    ``check_disk_headroom=False`` is for Scratch tests on full volumes only.
    """
    if check_quiescent:
        assert_quiescent(list_pids=list_pids)
        assert_db_writer_quiescent(Path(db_path))

    for label, path in (
        ("db_path", db_path),
        ("runner_path", runner_path),
        ("lock_path", lock_path),
    ):
        if not Path(path).is_file():
            raise SnapshotError(f"{label} missing: {path}")

    tmp_dir: Optional[Path] = None
    disk_info: Optional[dict[str, float]] = None
    if persist_artefact:
        snap_root = (
            Path(snapshot_dir)
            if snapshot_dir
            else Path(db_path).resolve().parent / "snapshots"
        )
        snap_root.mkdir(parents=True, exist_ok=True)
        if check_disk_headroom:
            disk_info = assert_disk_headroom(snap_root)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        artefact = snap_root / f"shadow_backup_{ts}.sqlite3"
    else:
        tmp_dir = Path(tempfile.mkdtemp(prefix="cp_snap_tmp_"))
        artefact = tmp_dir / "shadow_backup.sqlite3"

    try:
        _backup_db_quiescent(Path(db_path), artefact)
        artefact_sha256 = _sha256_file(artefact)

        conn = _open_db_readonly(artefact)
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()
            ok = integrity[0] if integrity else None
            if ok != "ok":
                raise SnapshotError(f"PRAGMA integrity_check failed: {ok!r}")
            max_run_id = _max_run_id(conn)
            schema_version = _schema_version(conn)
            trigger_manifest_sha256 = compute_control_plane_manifest_sha256(conn)
            logical_digest_sha256 = compute_logical_digest_sha256(conn)
            expected = expected_control_plane_manifest_sha256()
            manifest_match = trigger_manifest_sha256 == expected
            if require_manifest_match and not manifest_match:
                raise ManifestMismatchError(
                    "control-plane DDL manifest mismatch: "
                    f"observed={trigger_manifest_sha256} expected={expected}"
                )
        finally:
            conn.close()

        body: dict[str, Any] = {
            "artefact_persisted": bool(persist_artefact),
            "artefact_sha256": artefact_sha256,
            "db_path": str(Path(db_path).resolve()),
            "expected_trigger_manifest_sha256": expected,
            "git_head": _git_head(Path(repo_root)),
            "integrity_check": "ok",
            "lock_path": str(Path(lock_path).resolve()),
            "lock_sha256": _sha256_file(Path(lock_path)),
            "logical_digest_sha256": logical_digest_sha256,
            "manifest_match": manifest_match,
            "max_run_id": max_run_id,
            "runner_path": str(Path(runner_path).resolve()),
            "runner_sha256": _sha256_file(Path(runner_path)),
            "schema_version": schema_version,
            "trigger_manifest_sha256": trigger_manifest_sha256,
        }
        if persist_artefact:
            body["artefact_path"] = str(artefact.resolve())
            if disk_info is not None:
                body["disk_used_ratio"] = disk_info["used_ratio"]
        else:
            body["artefact_path"] = None
        manifest_sha256 = hashlib.sha256(
            _canonical_json(body).encode("utf-8")
        ).hexdigest()
        out = dict(body)
        out["manifest_sha256"] = manifest_sha256
        return out
    finally:
        if tmp_dir is not None:
            try:
                if artefact.exists():
                    artefact.unlink()
            except OSError:
                pass
            shutil.rmtree(tmp_dir, ignore_errors=True)


class AppendOnlyAuditChain:
    """Hash-chained JSONL audit journal (flock + fsync)."""

    def __init__(self, journal_path: Path) -> None:
        self.journal_path = Path(journal_path)
        self.lock_path = Path(str(self.journal_path) + ".lock")

    def _lock_fd(self) -> int:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.lock_path), os.O_RDWR | os.O_CREAT, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd

    def _read_entries_unlocked(self) -> list[dict[str, Any]]:
        if not self.journal_path.is_file():
            return []
        entries: list[dict[str, Any]] = []
        with self.journal_path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise AuditChainError(
                        f"corrupt JSON at line {line_no}: {exc}"
                    ) from exc
                if not isinstance(obj, dict):
                    raise AuditChainError(
                        f"non-object entry at line {line_no}"
                    )
                entries.append(obj)
        return entries

    def _last_link_unlocked(self) -> tuple[int, str]:
        entries = self._read_entries_unlocked()
        if not entries:
            return 0, GENESIS_HASH
        last = entries[-1]
        try:
            return int(last["seq"]), str(last["entry_hash"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AuditChainError(
                f"last entry missing seq/entry_hash: {exc}"
            ) from exc

    @staticmethod
    def _entry_hash(record: dict[str, Any]) -> str:
        body = {k: v for k, v in record.items() if k != "entry_hash"}
        return hashlib.sha256(
            _canonical_json(body).encode("utf-8")
        ).hexdigest()

    def append(
        self,
        action: str,
        manifest_sha256: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if not action or not isinstance(action, str):
            raise AuditChainError("action required")
        if not re.fullmatch(r"[0-9a-f]{64}", manifest_sha256 or ""):
            raise AuditChainError("manifest_sha256 must be 64 hex chars")

        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        fd = self._lock_fd()
        try:
            prev_seq, prev_hash = self._last_link_unlocked()
            record: dict[str, Any] = {
                "seq": prev_seq + 1,
                "ts_utc": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "action": action,
                "manifest_sha256": manifest_sha256,
                "payload": payload if payload is not None else {},
                "prev_hash": prev_hash,
            }
            record["entry_hash"] = self._entry_hash(record)
            line = _canonical_json(record) + "\n"
            jfd = os.open(
                str(self.journal_path),
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                0o644,
            )
            try:
                os.write(jfd, line.encode("utf-8"))
                os.fsync(jfd)
            except OSError as exc:
                os.close(jfd)
                raise AuditChainError(f"journal write failed: {exc}") from exc
            else:
                os.close(jfd)
            try:
                dir_fd = os.open(str(self.journal_path.parent), os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
            return record
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def verify(self) -> int:
        fd = self._lock_fd()
        try:
            entries = self._read_entries_unlocked()
            prev_hash = GENESIS_HASH
            expected_seq = 1
            for idx, entry in enumerate(entries):
                try:
                    seq = int(entry["seq"])
                    entry_hash = str(entry["entry_hash"])
                    link = str(entry["prev_hash"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise AuditChainError(
                        f"entry {idx} missing required fields: {exc}"
                    ) from exc
                if seq != expected_seq:
                    raise AuditChainError(
                        f"sequence gap: expected {expected_seq}, got {seq}"
                    )
                if link != prev_hash:
                    raise AuditChainError(
                        f"prev_hash break at seq={seq}"
                    )
                if self._entry_hash(entry) != entry_hash:
                    raise AuditChainError(
                        f"entry_hash mismatch at seq={seq}"
                    )
                prev_hash = entry_hash
                expected_seq += 1
            return len(entries)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def read_entries(self) -> list[dict[str, Any]]:
        fd = self._lock_fd()
        try:
            return self._read_entries_unlocked()
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


# Off-host audit mirror. H4: existence+checksum preflight (Drive ignores
# --immutable). Incr-bundle folder must NOT be the audit-object target (M-gap).
# Override audit objects via env AUDIT_OBJECTS_FOLDER_ID before E-1.
DEFAULT_AUDIT_MIRROR_FOLDER_ID = "1VxqOIvk1a2qTBuQlpJ4PE3Z3p6Co7Tzz"
DEFAULT_AUDIT_MIRROR_REMOTE_PREFIX = "gdrive:audit_chain"
DEFAULT_AUDIT_OBJECTS_FOLDER_ID = os.environ.get(
    "AUDIT_OBJECTS_FOLDER_ID", DEFAULT_AUDIT_MIRROR_FOLDER_ID
)


def audit_mirror_rclone_flags(
    *, folder_id: str = DEFAULT_AUDIT_MIRROR_FOLDER_ID
) -> list[str]:
    """Flags that pin every mirror call to the verified Drive folder."""
    if not folder_id or not re.fullmatch(r"[A-Za-z0-9_-]+", folder_id):
        raise AuditChainError(f"invalid drive folder id: {folder_id!r}")
    return ["--drive-root-folder-id", folder_id]


def _run_rclone_cmd(
    cmd: list[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> subprocess.CompletedProcess[str]:
    try:
        return runner(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise AuditChainError(f"rclone not found: {exc}") from exc
    except subprocess.SubprocessError as exc:
        raise AuditChainError(f"rclone failed: {exc}") from exc


def mirror_audit_entry(
    entry: dict[str, Any],
    remote_prefix: str,
    *,
    run_rclone: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    folder_id: str = DEFAULT_AUDIT_MIRROR_FOLDER_ID,
) -> str:
    """Upload one off-host object ``{seq}_{entry_hash}.json`` (H4 fail-closed).

    Preflight: if the remote object already exists, compare SHA-256 of remote
    bytes to the local payload. Same hash → idempotent skip. Different hash →
    refuse (truncated local journal must not overwrite the off-host anchor).
    Measured: rclone ``--immutable`` alone is insufficient on Google Drive.
    """
    if not remote_prefix or not isinstance(remote_prefix, str):
        raise AuditChainError("remote_prefix required")
    try:
        seq = int(entry["seq"])
        entry_hash = str(entry["entry_hash"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AuditChainError(f"entry missing seq/entry_hash: {exc}") from exc
    if not re.fullmatch(r"[0-9a-f]{64}", entry_hash):
        raise AuditChainError("entry_hash must be 64 hex chars")

    name = f"{seq:08d}_{entry_hash}.json"
    remote = remote_prefix.rstrip("/") + "/" + name
    payload = _canonical_json(entry) + "\n"
    local_sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    tmp_dir = Path(tempfile.mkdtemp(prefix="audit_mirror_"))
    tmp = tmp_dir / name
    tmp.write_text(payload, encoding="utf-8")
    drive_flags = audit_mirror_rclone_flags(folder_id=folder_id)
    runner = run_rclone or subprocess.run

    # Existence probe (lsjson on the object path).
    ls = _run_rclone_cmd(
        ["rclone", "lsjson", remote, *drive_flags],
        runner=runner,
    )
    ls_out = ls.stdout if isinstance(ls.stdout, str) else ""
    if ls.returncode == 0 and ls_out.strip() not in ("", "[]"):
        cat = _run_rclone_cmd(
            ["rclone", "cat", remote, *drive_flags],
            runner=runner,
        )
        if cat.returncode != 0:
            err = cat.stderr if isinstance(cat.stderr, str) else ""
            out = cat.stdout if isinstance(cat.stdout, str) else ""
            raise AuditChainError(
                f"remote object exists but cat failed: {remote}: "
                f"{(err or out).strip()}"
            )
        cat_out = cat.stdout if isinstance(cat.stdout, str) else ""
        remote_sha = hashlib.sha256(cat_out.encode("utf-8")).hexdigest()
        if remote_sha != local_sha:
            raise AuditChainError(
                f"refuse overwrite of immutable audit object {remote}: "
                f"local_sha={local_sha} remote_sha={remote_sha}"
            )
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return remote

    cmd = [
        "rclone",
        "copyto",
        str(tmp),
        remote,
        "--immutable",
        "--checksum",
        *drive_flags,
    ]
    proc = _run_rclone_cmd(cmd, runner=runner)
    shutil.rmtree(tmp_dir, ignore_errors=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise AuditChainError(
            f"rclone copyto --immutable exit {proc.returncode}: {err}"
        )
    return remote


def mirror_audit_journal(
    journal_path: Path,
    remote_prefix: str,
    *,
    run_rclone: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    folder_id: str = DEFAULT_AUDIT_MIRROR_FOLDER_ID,
) -> list[str]:
    """Mirror each journal entry as its own immutable remote object (H4)."""
    chain = AppendOnlyAuditChain(Path(journal_path))
    remotes: list[str] = []
    for entry in chain.read_entries():
        remotes.append(
            mirror_audit_entry(
                entry,
                remote_prefix,
                run_rclone=run_rclone,
                folder_id=folder_id,
            )
        )
    return remotes


def verify_audit_mirror(
    journal_path: Path,
    remote_prefix: str,
    *,
    run_rclone: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    folder_id: str = DEFAULT_AUDIT_MIRROR_FOLDER_ID,
) -> dict[str, Any]:
    """Fail-closed: every journal entry must exist off-host with matching SHA.

    Compares local canonical payload SHA-256 to ``rclone cat`` of
    ``{seq}_{entry_hash}.json`` under ``remote_prefix`` (pinned folder id).
    """
    if not remote_prefix or not isinstance(remote_prefix, str):
        raise AuditChainError("remote_prefix required")
    chain = AppendOnlyAuditChain(Path(journal_path))
    n = chain.verify()
    entries = chain.read_entries()
    drive_flags = audit_mirror_rclone_flags(folder_id=folder_id)
    runner = run_rclone or subprocess.run
    checked: list[dict[str, Any]] = []
    for entry in entries:
        try:
            seq = int(entry["seq"])
            entry_hash = str(entry["entry_hash"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AuditChainError(
                f"entry missing seq/entry_hash: {exc}"
            ) from exc
        name = f"{seq:08d}_{entry_hash}.json"
        remote = remote_prefix.rstrip("/") + "/" + name
        local_payload = _canonical_json(entry) + "\n"
        local_sha = hashlib.sha256(local_payload.encode("utf-8")).hexdigest()
        cat = _run_rclone_cmd(
            ["rclone", "cat", remote, *drive_flags],
            runner=runner,
        )
        if cat.returncode != 0:
            err = cat.stderr if isinstance(cat.stderr, str) else ""
            out = cat.stdout if isinstance(cat.stdout, str) else ""
            raise AuditChainError(
                f"verify-mirror missing/unreachable {remote}: "
                f"{(err or out).strip()}"
            )
        cat_out = cat.stdout if isinstance(cat.stdout, str) else ""
        remote_sha = hashlib.sha256(cat_out.encode("utf-8")).hexdigest()
        if remote_sha != local_sha:
            raise AuditChainError(
                f"verify-mirror SHA mismatch {remote}: "
                f"local_sha={local_sha} remote_sha={remote_sha}"
            )
        checked.append(
            {
                "seq": seq,
                "remote": remote,
                "sha256": local_sha,
            }
        )
    return {
        "ok": True,
        "entries": n,
        "checked": checked,
        "remote_prefix": remote_prefix,
        "folder_id": folder_id,
    }


def token_sha256(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
