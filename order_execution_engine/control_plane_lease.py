"""Phase-1 scratch Control-Plane: run_lease + migrate (not in __init__).

Zwischen-Enforcement until run_lease is live on production (K2/K3).
Scratch only — every public entry refuses LIVE Application Support paths
via ``PRAGMA database_list`` (F3).

``issued_at`` / ``expires_at`` are unix-second INTEGER (not datetime text);
TTL checks use integer deltas equivalent to the julianday formulæ.
Table name is ``telemetry_runs`` (this codebase; prompt ``runs`` maps here).
"""

from __future__ import annotations

import hashlib
import re
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Optional

SCHEMA_V10 = 10  # first control-plane stamp (historical)
SCHEMA_V11 = 11  # hardened lease BI + run_id floor (pre-G1)
SCHEMA_V12 = 12  # G1: issued_at wall-clock skew; G2: expanded manifest
SCHEMA_CONTROL = SCHEMA_V12

TTL_MAX_S = 900
# Max seconds issued_at may lie ahead of DB now (clock skew only).
ISSUED_AT_FUTURE_SKEW_S = 5
# Production freeze: LIVE max_run_id=15 → next claimable id is at least 16.
# Scratch uses the same floor (Grabstein also after restore onto older dumps).
RUN_ID_FLOOR = 15

_LIVE_PATH_MARKERS = (
    "Application Support/agentx",
)

_CREATE_RUN_LEASE = """
CREATE TABLE IF NOT EXISTS run_lease (
    token        TEXT PRIMARY KEY,
    run_id       INTEGER NOT NULL,
    issued_at    INTEGER NOT NULL,
    expires_at   INTEGER NOT NULL,
    consumed_at  INTEGER,
    revoked_at   INTEGER
)
"""

_CREATE_UX_OPEN = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_run_lease_open_run
  ON run_lease(run_id)
  WHERE consumed_at IS NULL AND revoked_at IS NULL
"""


def _next_run_id_sql() -> str:
    """SQL expr: MAX(floor, COALESCE(MAX(telemetry_runs.run_id),0)) + 1."""
    return (
        f"(MAX({RUN_ID_FLOOR}, COALESCE("
        f"(SELECT MAX(run_id) FROM telemetry_runs), 0)) + 1)"
    )


def _trigger_telemetry_runs_bi_lease() -> str:
    nxt = _next_run_id_sql()
    return f"""
CREATE TRIGGER IF NOT EXISTS trg_telemetry_runs_bi_lease
BEFORE INSERT ON telemetry_runs
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.run_id IS NULL THEN
            RAISE(ABORT, 'telemetry_runs.run_id required')
        WHEN NEW.run_id != {nxt} THEN
            RAISE(ABORT, 'telemetry_runs.run_id not MAX+1')
        WHEN NOT EXISTS (
            SELECT 1 FROM run_lease
            WHERE run_id = NEW.run_id
              AND consumed_at IS NULL
              AND revoked_at IS NULL
              AND expires_at > CAST(strftime('%s', 'now') AS INTEGER)
        ) THEN
            RAISE(ABORT, 'no valid open run_lease for run_id')
    END;
END
"""


TRIGGER_AFTER_INSERT = """
CREATE TRIGGER IF NOT EXISTS trg_telemetry_runs_ai_consume
AFTER INSERT ON telemetry_runs
FOR EACH ROW
BEGIN
    UPDATE run_lease
       SET consumed_at = CAST(strftime('%s', 'now') AS INTEGER)
     WHERE run_id = NEW.run_id
       AND consumed_at IS NULL
       AND revoked_at IS NULL;
END
"""

TRIGGER_BEFORE_DELETE = """
CREATE TRIGGER IF NOT EXISTS trg_telemetry_runs_bd_forbid
BEFORE DELETE ON telemetry_runs
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'telemetry_runs DELETE forbidden');
END
"""

TRIGGER_BEFORE_UPDATE_RUN_ID = """
CREATE TRIGGER IF NOT EXISTS trg_telemetry_runs_bu_run_id_forbid
BEFORE UPDATE OF run_id ON telemetry_runs
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'telemetry_runs.run_id UPDATE forbidden');
END
"""

TRIGGER_BEFORE_UPDATE_STATUS = """
CREATE TRIGGER IF NOT EXISTS trg_telemetry_runs_bu_status
BEFORE UPDATE OF status ON telemetry_runs
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN OLD.status IS NEW.status THEN NULL
        WHEN OLD.status = 'RUNNING'
             AND NEW.status IN ('ABORTED', 'COMMITTED') THEN NULL
        ELSE RAISE(ABORT, 'telemetry_runs status transition forbidden')
    END;
END
"""


def _trigger_run_lease_before_insert() -> str:
    """BEFORE INSERT ON run_lease — next-id, wall-clock skew, TTL (G1)."""
    nxt = _next_run_id_sql()
    skew = int(ISSUED_AT_FUTURE_SKEW_S)
    ttl = int(TTL_MAX_S)
    return f"""
CREATE TRIGGER IF NOT EXISTS trg_run_lease_before_insert
BEFORE INSERT ON run_lease
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.run_id != {nxt} THEN
            RAISE(ABORT, 'run_lease.run_id not next')
        WHEN NEW.issued_at IS NULL OR NEW.expires_at IS NULL THEN
            RAISE(ABORT, 'run_lease timestamps required')
        WHEN NEW.issued_at >
             CAST(strftime('%s', 'now') AS INTEGER) + {skew} THEN
            RAISE(ABORT, 'run_lease issued_at too far in future')
        WHEN NEW.expires_at <= NEW.issued_at THEN
            RAISE(ABORT, 'run_lease expires_at must be after issued_at')
        WHEN (NEW.expires_at - NEW.issued_at) > {ttl} THEN
            RAISE(ABORT, 'run_lease TTL out of range')
        WHEN (NEW.expires_at - NEW.issued_at) < 1 THEN
            RAISE(ABORT, 'run_lease TTL out of range')
    END;
END
"""


TRIGGER_LEASE_NO_DELETE = """
CREATE TRIGGER IF NOT EXISTS trg_run_lease_bd_forbid
BEFORE DELETE ON run_lease
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'run_lease DELETE forbidden');
END
"""

TRIGGER_LEASE_UPDATE_GUARD = """
CREATE TRIGGER IF NOT EXISTS trg_run_lease_bu_guard
BEFORE UPDATE ON run_lease
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.token IS NOT OLD.token
          OR NEW.run_id IS NOT OLD.run_id
          OR NEW.issued_at IS NOT OLD.issued_at
          OR NEW.expires_at IS NOT OLD.expires_at THEN
            RAISE(ABORT, 'run_lease immutable columns')
        WHEN OLD.consumed_at IS NOT NULL
             AND (NEW.consumed_at IS NULL
                  OR NEW.consumed_at IS NOT OLD.consumed_at) THEN
            RAISE(ABORT, 'run_lease consumed_at immutable once set')
        WHEN OLD.revoked_at IS NOT NULL
             AND (NEW.revoked_at IS NULL
                  OR NEW.revoked_at IS NOT OLD.revoked_at) THEN
            RAISE(ABORT, 'run_lease revoked_at immutable once set')
        WHEN OLD.consumed_at IS NULL AND NEW.consumed_at IS NULL
             AND OLD.revoked_at IS NULL AND NEW.revoked_at IS NULL THEN
            RAISE(ABORT, 'run_lease UPDATE without consume/revoke')
    END;
END
"""


class LivePathRefused(RuntimeError):
    """Scratch helpers must not touch LIVE Application Support paths."""


class LeaseError(RuntimeError):
    """Token issue / claim refused."""


def assert_scratch_db_path(db_path: Path) -> Path:
    """Abort if path looks like LIVE under Application Support/agentx."""
    resolved = db_path.resolve()
    lowered = str(resolved).lower()
    for marker in _LIVE_PATH_MARKERS:
        if marker.lower() in lowered:
            raise LivePathRefused(
                f"refuse LIVE path for Phase-1 scratch: {resolved}"
            )
    return resolved


def db_path_from_conn(conn: sqlite3.Connection) -> Path:
    """Resolve main DB file from the connection (F3)."""
    for row in conn.execute("PRAGMA database_list"):
        if row[1] == "main":
            file_path = row[2]
            if not file_path:
                raise LivePathRefused("refuse: main database has empty file path")
            return assert_scratch_db_path(Path(file_path))
    raise LivePathRefused("refuse: no main database in PRAGMA database_list")


def _refuse_live_conn(conn: sqlite3.Connection) -> Path:
    return db_path_from_conn(conn)


def connect_scratch(db_path: Path) -> sqlite3.Connection:
    """Open scratch DB with WAL/FK/busy_timeout. Refuses LIVE paths."""
    path = assert_scratch_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = FULL")
    _refuse_live_conn(conn)
    return conn


def _schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT value FROM schema_meta WHERE key = 'schema_version'"
    ).fetchone()
    if row is None:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return 0


def next_run_id(conn: sqlite3.Connection) -> int:
    """Next claimable run_id: MAX(RUN_ID_FLOOR, COALESCE(MAX(run_id),0)) + 1."""
    row = conn.execute(
        "SELECT COALESCE(MAX(run_id), 0) FROM telemetry_runs"
    ).fetchone()
    return max(RUN_ID_FLOOR, int(row[0])) + 1


def _normalize_ddl_sql(sql: Optional[str]) -> str:
    if not sql:
        return ""
    return re.sub(r"\s+", " ", sql.strip())


def trigger_manifest_sha256(conn: sqlite3.Connection) -> str:
    """SHA-256 over control-plane DDL (G2 / Phase-2 DROP detection).

    Covers CREATE TABLE for run_lease + telemetry_runs, the open-lease
    unique index, and every trigger on either table.
    """
    _refuse_live_conn(conn)
    parts: list[str] = []
    for tbl in ("run_lease", "telemetry_runs"):
        row = conn.execute(
            "SELECT sql FROM sqlite_master"
            " WHERE type = 'table' AND name = ?",
            (tbl,),
        ).fetchone()
        parts.append(
            f"TABLE {tbl}\n{_normalize_ddl_sql(row[0] if row else None)}"
        )
    idx = conn.execute(
        "SELECT name, sql FROM sqlite_master"
        " WHERE type = 'index' AND name = 'ux_run_lease_open_run'"
        " ORDER BY name"
    ).fetchone()
    parts.append(
        "INDEX ux_run_lease_open_run\n"
        + _normalize_ddl_sql(idx[1] if idx else None)
    )
    for row in conn.execute(
        "SELECT name, sql FROM sqlite_master"
        " WHERE type = 'trigger'"
        "   AND tbl_name IN ('run_lease', 'telemetry_runs')"
        " ORDER BY name"
    ):
        parts.append(f"TRIGGER {row[0]}\n{_normalize_ddl_sql(row[1])}")
    blob = "\n--\n".join(parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def migrate_control_plane(
    conn: sqlite3.Connection,
    *,
    db_path: Optional[Path] = None,
    _abort_after: Optional[str] = None,
) -> None:
    """Apply control-plane schema up to SCHEMA_CONTROL (atomic; no executescript).

    Not called from SQLiteShadowStorage.__init__. Only tests / gatectl migrate.
    """
    _refuse_live_conn(conn)
    if db_path is not None:
        assert_scratch_db_path(db_path)

    ver = _schema_version(conn)
    if ver < 9:
        raise LeaseError(
            f"migrate_control_plane refuses schema_version={ver}"
            " (need >=9 baseline)"
        )
    if ver >= SCHEMA_CONTROL:
        return

    steps: list[tuple[str, Callable[[], None]]] = []

    def _add(name: str, sql: str) -> None:
        steps.append((name, lambda s=sql: conn.execute(s)))

    if ver < SCHEMA_V10:
        _add("create_run_lease", _CREATE_RUN_LEASE)
        _add("create_ux_open", _CREATE_UX_OPEN)

        def _add_closed_at() -> None:
            cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(telemetry_runs)")
            }
            if "closed_at" not in cols:
                conn.execute(
                    "ALTER TABLE telemetry_runs ADD COLUMN closed_at INTEGER"
                )

        def _add_status() -> None:
            cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(telemetry_runs)")
            }
            if "status" not in cols:
                conn.execute(
                    "ALTER TABLE telemetry_runs ADD COLUMN status TEXT"
                )

        def _backfill_terminal() -> None:
            conn.execute(
                "UPDATE telemetry_runs SET status = 'ABORTED',"
                " closed_at = CAST(strftime('%s', 'now') AS INTEGER)"
                " WHERE status IS NULL"
            )

        steps.append(("add_closed_at", _add_closed_at))
        steps.append(("add_status", _add_status))
        steps.append(("backfill_terminal", _backfill_terminal))
        _add("trg_bi_lease", _trigger_telemetry_runs_bi_lease())
        _add("trg_ai_consume", TRIGGER_AFTER_INSERT)
        _add("trg_bd_forbid", TRIGGER_BEFORE_DELETE)
        _add("trg_bu_run_id", TRIGGER_BEFORE_UPDATE_RUN_ID)
        _add("trg_bu_status", TRIGGER_BEFORE_UPDATE_STATUS)
        _add("trg_lease_bi", _trigger_run_lease_before_insert())
        _add("trg_lease_bd", TRIGGER_LEASE_NO_DELETE)
        _add("trg_lease_bu", TRIGGER_LEASE_UPDATE_GUARD)
    else:
        # v10/v11 → SCHEMA_CONTROL: replace BI triggers (floor / TTL / G1 skew).
        def _drop_old_lease_bi() -> None:
            conn.execute("DROP TRIGGER IF EXISTS trg_run_lease_bi_guard")
            conn.execute("DROP TRIGGER IF EXISTS trg_run_lease_before_insert")

        def _drop_old_runs_bi() -> None:
            conn.execute("DROP TRIGGER IF EXISTS trg_telemetry_runs_bi_lease")

        steps.append(("drop_old_lease_bi", _drop_old_lease_bi))
        steps.append(("drop_old_runs_bi", _drop_old_runs_bi))
        _add("trg_bi_lease", _trigger_telemetry_runs_bi_lease())
        _add("trg_lease_bi", _trigger_run_lease_before_insert())

    def _stamp_version() -> None:
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value)"
            " VALUES ('schema_version', ?)",
            (str(SCHEMA_CONTROL),),
        )
        conn.execute(f"PRAGMA user_version = {SCHEMA_CONTROL}")

    steps.append(("stamp_version", _stamp_version))

    conn.execute("BEGIN IMMEDIATE")
    try:
        for name, fn in steps:
            fn()
            if _abort_after is not None and name == _abort_after:
                raise RuntimeError(f"forced migrate abort after {name}")
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise


def migrate_v10(
    conn: sqlite3.Connection,
    *,
    db_path: Optional[Path] = None,
    _abort_after: Optional[str] = None,
) -> None:
    """Deprecated alias for ``migrate_control_plane``."""
    return migrate_control_plane(
        conn, db_path=db_path, _abort_after=_abort_after
    )


def issue_token(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    ttl_s: int = 300,
    now: Optional[int] = None,
) -> str:
    """Issue a lease token for exactly next_run_id; revoke expired opens first."""
    _refuse_live_conn(conn)
    if run_id < 1:
        raise LeaseError("run_id must be >= 1")
    if ttl_s < 1 or ttl_s > TTL_MAX_S:
        raise LeaseError(f"ttl_s must be in 1..{TTL_MAX_S}, got {ttl_s}")
    ts = int(now if now is not None else time.time())

    conn.execute("BEGIN IMMEDIATE")
    try:
        expect = next_run_id(conn)
        if run_id != expect:
            conn.execute("ROLLBACK")
            raise LeaseError(
                f"issue-token refuses run_id={run_id}, next is {expect}"
            )

        running = conn.execute(
            "SELECT 1 FROM telemetry_runs WHERE status = 'RUNNING' LIMIT 1"
        ).fetchone()
        if running is not None:
            conn.execute("ROLLBACK")
            raise LeaseError("issue-token refused: RUNNING run exists (L2)")

        conn.execute(
            "UPDATE run_lease SET revoked_at = ?"
            " WHERE consumed_at IS NULL AND revoked_at IS NULL"
            "   AND expires_at <= ?",
            (ts, ts),
        )

        open_same = conn.execute(
            "SELECT token FROM run_lease"
            " WHERE run_id = ? AND consumed_at IS NULL AND revoked_at IS NULL",
            (run_id,),
        ).fetchone()
        if open_same is not None:
            conn.execute("ROLLBACK")
            raise LeaseError(f"open lease already exists for run_id={run_id}")

        token = secrets.token_hex(16)
        conn.execute(
            "INSERT INTO run_lease"
            " (token, run_id, issued_at, expires_at, consumed_at, revoked_at)"
            " VALUES (?, ?, ?, ?, NULL, NULL)",
            (token, run_id, ts, ts + int(ttl_s)),
        )
        conn.execute("COMMIT")
        return token
    except LeaseError:
        raise
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise


def revoke_token(
    conn: sqlite3.Connection, token: str, *, now: Optional[int] = None
) -> None:
    """Revoke an unconsumed token and allow re-issue for its run_id."""
    _refuse_live_conn(conn)
    ts = int(now if now is not None else time.time())
    conn.execute("BEGIN IMMEDIATE")
    try:
        cur = conn.execute(
            "UPDATE run_lease SET revoked_at = ?"
            " WHERE token = ? AND consumed_at IS NULL AND revoked_at IS NULL",
            (ts, token),
        )
        if cur.rowcount != 1:
            conn.execute("ROLLBACK")
            raise LeaseError("revoke failed: token missing or already closed")
        conn.execute("COMMIT")
    except LeaseError:
        raise
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise


def claim_run(
    conn: sqlite3.Connection,
    *,
    git_commit: str,
    config_json: str,
    started_at: Optional[float] = None,
) -> int:
    """BEGIN IMMEDIATE claim: INSERT telemetry_runs with explicit next_run_id."""
    _refuse_live_conn(conn)
    started = float(started_at if started_at is not None else time.time())
    conn.execute("BEGIN IMMEDIATE")
    try:
        run_id = next_run_id(conn)
        conn.execute(
            "INSERT INTO telemetry_runs"
            " (run_id, started_at, git_commit, config_json, status, closed_at)"
            " VALUES (?, ?, ?, ?, 'RUNNING', NULL)",
            (run_id, started, git_commit, config_json),
        )
        conn.execute("COMMIT")
        return run_id
    except sqlite3.IntegrityError as exc:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise LeaseError(f"claim aborted: {exc}") from exc
    except sqlite3.DatabaseError as exc:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise LeaseError(f"claim aborted: {exc}") from exc
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise


def lease_snapshot(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Debug/test helper — all lease rows."""
    _refuse_live_conn(conn)
    rows = conn.execute(
        "SELECT token, run_id, issued_at, expires_at, consumed_at, revoked_at"
        " FROM run_lease ORDER BY issued_at, token"
    ).fetchall()
    return [dict(r) for r in rows]
