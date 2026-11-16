"""Phase-1 scratch Control-Plane: run_lease + migrate (not in __init__).

Zwischen-Enforcement until run_lease is live on production (K2/K3).
Scratch only — every public entry refuses LIVE Application Support paths
via ``PRAGMA database_list`` (F3).

``issued_at`` / ``expires_at`` are unix-second INTEGER (not datetime text);
TTL checks use integer deltas equivalent to the julianday formulæ.
Table name is ``telemetry_runs`` (this codebase; prompt ``runs`` maps here).

L3 WAL crash-window semantics (binding; control-plane writers only):
- Default durability: ``journal_mode=WAL`` + ``synchronous=FULL`` in
  ``_open_sqlite``. Deviations (e.g. NORMAL) require explicit operator
  Freigabe and a documented larger crash window.
- Recovery order on writer open: apply WAL recovery (SQLite open), then
  optional ``integrity_check`` / ``foreign_key_check`` via
  ``startup_integrity_checks`` before lease mutations.
- Crash after WAL write but before COMMIT of a lease/abort txn: the abort
  is **not** applied; no automatic replay. Audit intents that never
  confirmed are treated as rolled-back / open-intent fail-closed at status.
- Crash after COMMIT before checkpoint: durable in WAL; next open recovers.
- Token↔DB: issue-token writes O_EXCL 0600 file then DB lease row (gatectl);
  claim consumes token. Orphan file (no claim) → refuse reuse of stale open
  lease via fencing; orphan RUNNING row → explicit ``abort_run`` / watchdog
  (no silent TTL abort of RUNNING).
- ``persistence.py`` (frozen pin) does not set journal_mode; control-plane
  opens own the WAL/FULL contract for lease writers. L3 does **not** thaw
  persistence.
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
SCHEMA_V13 = 13  # STOPPED terminal (ordered SIGTERM; not ABORTED/COMMITTED)
SCHEMA_CONTROL = SCHEMA_V13

TTL_MAX_S = 900
# L3-d: bound WAL growth (pages). Same module as TTL_MAX_S (watchdog T_max
# binds to TTL_MAX_S — keep durability knobs co-located).
WAL_AUTOCHECKPOINT_PAGES = 1000
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
             AND NEW.status IN ('ABORTED', 'COMMITTED', 'STOPPED') THEN NULL
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


def db_file_from_conn(conn: sqlite3.Connection) -> Path:
    """Resolve main DB file path (no LIVE policy)."""
    for row in conn.execute("PRAGMA database_list"):
        if row[1] == "main":
            file_path = row[2]
            if not file_path:
                raise LivePathRefused("refuse: main database has empty file path")
            return Path(file_path).resolve()
    raise LivePathRefused("refuse: no main database in PRAGMA database_list")


def db_path_from_conn(
    conn: sqlite3.Connection, *, allow_live: bool = False
) -> Path:
    """Resolve main DB file; refuse LIVE unless ``allow_live`` (M4)."""
    path = db_file_from_conn(conn)
    if allow_live:
        return path
    return assert_scratch_db_path(path)


def _guard_live_conn(
    conn: sqlite3.Connection, *, allow_live: bool = False
) -> Path:
    return db_path_from_conn(conn, allow_live=allow_live)


def _refuse_live_conn(conn: sqlite3.Connection) -> Path:
    """Scratch default: always refuse LIVE markers."""
    return _guard_live_conn(conn, allow_live=False)


def _open_sqlite(path: Path) -> sqlite3.Connection:
    """RW open with WAL/FULL — writers only (migrate / issue / abort / claim).

    L3-a/d: WAL + synchronous=FULL + wal_autocheckpoint bound. Never silently
    downgrade to NORMAL/OFF.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = FULL")
    conn.execute(f"PRAGMA wal_autocheckpoint = {int(WAL_AUTOCHECKPOINT_PAGES)}")
    return conn


def apply_writer_durability(conn: sqlite3.Connection) -> dict[str, Any]:
    """L3-a: bind WAL+FULL+autocheckpoint on **this** connection.

    ``journal_mode=WAL`` is file-persistent; ``synchronous`` and
    ``wal_autocheckpoint`` are per-connection. Runner re-opens via frozen
    persistence after preflight — claim/abort/issue must re-bind on the
    write connection (not rely on SQLite defaults).
    """
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = FULL")
    conn.execute(f"PRAGMA wal_autocheckpoint = {int(WAL_AUTOCHECKPOINT_PAGES)}")
    return startup_integrity_checks(conn)


def detect_restart_kind(db_path: Path) -> str:
    """L3-b: distinguish clean start vs leftover WAL/SHM (crash/open window).

    Not the E-1 production first-start path — only DB-file sidecar presence.
    """
    base = Path(db_path)
    wal = Path(str(base) + "-wal")
    shm = Path(str(base) + "-shm")
    if wal.is_file() and wal.stat().st_size > 0:
        return "crash_or_open_wal"
    if shm.is_file() and shm.stat().st_size > 0:
        return "crash_or_open_shm"
    return "clean_start"


def startup_integrity_checks(conn: sqlite3.Connection) -> dict[str, Any]:
    """L3-b: integrity + FK check after open / before lease mutations."""
    ic = conn.execute("PRAGMA integrity_check").fetchone()
    if not ic or str(ic[0]).lower() != "ok":
        raise ControlPlaneError(f"integrity_check failed: {ic!r}")
    fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
    if fk_rows:
        raise ControlPlaneError(
            f"foreign_key_check failed: {len(fk_rows)} violation(s)"
        )
    journal = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
    sync = conn.execute("PRAGMA synchronous").fetchone()[0]
    # FULL == 2 in SQLite; accept string 'full' on some builds.
    sync_ok = sync in (2, "2", "full", "FULL")
    if journal != "wal" or not sync_ok:
        raise ControlPlaneError(
            f"durability refuse: journal_mode={journal!r} synchronous={sync!r} "
            "(require WAL + FULL)"
        )
    ac = int(conn.execute("PRAGMA wal_autocheckpoint").fetchone()[0])
    return {
        "integrity_check": "ok",
        "foreign_key_check": "ok",
        "journal_mode": journal,
        "synchronous": sync,
        "wal_autocheckpoint": ac,
    }


def _open_sqlite_ro(path: Path) -> sqlite3.Connection:
    """Read-only URI open — no journal_mode / synchronous pragmas (E-0 safe)."""
    abs_path = Path(path).resolve()
    if not abs_path.is_file():
        raise LivePathRefused(f"db not found for RO open: {abs_path}")
    uri = f"file:{abs_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only = ON")
    except sqlite3.Error:
        pass
    return conn


def connect_scratch(db_path: Path) -> sqlite3.Connection:
    """Open scratch DB with WAL/FK/busy_timeout. Refuses LIVE paths."""
    path = assert_scratch_db_path(db_path)
    conn = _open_sqlite(path)
    _refuse_live_conn(conn)
    return conn


def is_live_agentx_path(path: Path) -> bool:
    """True if path sits under Application Support/agentx (LIVE marker)."""
    lowered = str(path.resolve()).lower()
    return any(m.lower() in lowered for m in _LIVE_PATH_MARKERS)


def connect_control_plane(
    db_path: Path, *, allow_live: bool = False
) -> sqlite3.Connection:
    """RW open for gatectl writers. LIVE requires ``allow_live=True`` (M4)."""
    path = Path(db_path).resolve()
    if is_live_agentx_path(path):
        if not allow_live:
            raise LivePathRefused(
                f"refuse LIVE path without --allow-live-db: {path}"
            )
        return _open_sqlite(path)
    return connect_scratch(path)


def connect_control_plane_ro(
    db_path: Path, *, allow_live: bool = False
) -> sqlite3.Connection:
    """RO open for status / retire prechecks / post-run reads — never sets WAL.

    LIVE still requires ``allow_live=True`` so RO is not a silent LIVE channel.
    """
    path = Path(db_path).resolve()
    if is_live_agentx_path(path):
        if not allow_live:
            raise LivePathRefused(
                f"refuse LIVE path without --allow-live-db: {path}"
            )
        return _open_sqlite_ro(path)
    # Scratch RO: still refuse LIVE markers via resolve path check
    assert_scratch_db_path(path)
    return _open_sqlite_ro(path)


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
    allow_live: bool = False,
    _abort_after: Optional[str] = None,
) -> None:
    """Apply control-plane schema up to SCHEMA_CONTROL (atomic; no executescript).

    Not called from SQLiteShadowStorage.__init__. Only tests / gatectl migrate.
    ``allow_live`` must match gatectl ``--allow-live-db`` (M4).
    """
    _guard_live_conn(conn, allow_live=allow_live)
    if db_path is not None:
        if allow_live:
            Path(db_path).resolve()
        else:
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

    if ver < SCHEMA_V13 and ver >= SCHEMA_V10:
        # → v13: allow STOPPED terminal transition (refresh status trigger).
        def _drop_status_trg() -> None:
            conn.execute("DROP TRIGGER IF EXISTS trg_telemetry_runs_bu_status")

        steps.append(("drop_status_trg", _drop_status_trg))
        _add("trg_bu_status", TRIGGER_BEFORE_UPDATE_STATUS)

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
    allow_live: bool = False,
) -> str:
    """Issue a lease token for exactly next_run_id; revoke expired opens first."""
    _guard_live_conn(conn, allow_live=allow_live)
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
    conn: sqlite3.Connection,
    token: str,
    *,
    now: Optional[int] = None,
    allow_live: bool = False,
) -> None:
    """Revoke an unconsumed token and allow re-issue for its run_id."""
    _guard_live_conn(conn, allow_live=allow_live)
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
    token: str,
    started_at: Optional[float] = None,
    now: Optional[int] = None,
) -> int:
    """BEGIN IMMEDIATE fenced claim: bind INSERT to a specific open lease token (D1).

    Gate #6 / E-1: production ``open_run`` path. Does **not** refuse LIVE paths
    (unlike ``connect_scratch`` / ``issue_token`` / ``migrate_control_plane``).

    Fencing: the caller must present the exact token issued for ``next_run_id``.
    An expired holder whose token was revoked/replaced cannot INSERT — even if
    another process later issued a fresh lease for the same run_id.
    """
    if not token or not isinstance(token, str):
        raise LeaseError("claim_run requires lease token (D1 fencing)")
    # L3-a: re-bind per-connection durability on the runner write conn
    # (persistence re-open after preflight close — see shadow_runner main).
    apply_writer_durability(conn)
    started = float(started_at if started_at is not None else time.time())
    ts = int(now if now is not None else time.time())
    conn.execute("BEGIN IMMEDIATE")
    try:
        run_id = next_run_id(conn)
        row = conn.execute(
            "SELECT token, run_id, expires_at, consumed_at, revoked_at"
            " FROM run_lease WHERE token = ?",
            (token,),
        ).fetchone()
        if row is None:
            conn.execute("ROLLBACK")
            raise LeaseError("claim refused: unknown lease token")
        # Tuple or sqlite3.Row — never assume row_factory.
        _tok, lease_rid, expires_at, consumed_at, revoked_at = (
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
        )
        if int(lease_rid) != int(run_id):
            conn.execute("ROLLBACK")
            raise LeaseError(
                f"claim refused: token run_id={lease_rid} != next={run_id}"
            )
        if consumed_at is not None or revoked_at is not None:
            conn.execute("ROLLBACK")
            raise LeaseError("claim refused: lease token already closed")
        if int(expires_at) <= ts:
            conn.execute("ROLLBACK")
            raise LeaseError("claim refused: lease token expired")
        conn.execute(
            "INSERT INTO telemetry_runs"
            " (run_id, started_at, git_commit, config_json, status, closed_at)"
            " VALUES (?, ?, ?, ?, 'RUNNING', NULL)",
            (run_id, started, git_commit, config_json),
        )
        # AI trigger consumes the open lease for run_id. Fence: THIS token
        # must be the one now consumed (stale holder after re-issue fails).
        after = conn.execute(
            "SELECT consumed_at, revoked_at FROM run_lease WHERE token = ?",
            (token,),
        ).fetchone()
        if after is None or after[0] is None or after[1] is not None:
            conn.execute("ROLLBACK")
            raise LeaseError("claim refused: token consume failed (fence)")
        conn.execute("COMMIT")
        return run_id
    except LeaseError:
        raise
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


class ControlPlaneError(RuntimeError):
    """Schema / trigger-manifest preflight refused (Gate #6)."""


def ensure_control_plane_ready(conn: sqlite3.Connection) -> dict[str, Any]:
    """Fail-closed: schema == SCHEMA_CONTROL and DDL manifest == Soll.

    L3-a/b: upgrade this connection to WAL+FULL (persistence.py is frozen and
    does not set journal_mode; preflight owns the durability contract), then
    ``startup_integrity_checks``.
    """
    from order_execution_engine.control_plane_audit import (
        compute_control_plane_manifest_sha256,
        expected_control_plane_manifest_sha256,
    )

    # Heal this connection (preflight). Write path re-binds in claim_run.
    durability = apply_writer_durability(conn)
    ver = _schema_version(conn)
    if ver < SCHEMA_CONTROL:
        raise ControlPlaneError(
            f"control-plane schema_version={ver} < {SCHEMA_CONTROL} — refuse start"
        )
    if ver > SCHEMA_CONTROL:
        raise ControlPlaneError(
            f"control-plane schema_version={ver} > {SCHEMA_CONTROL} — refuse start"
        )
    ist = compute_control_plane_manifest_sha256(conn)
    soll = expected_control_plane_manifest_sha256()
    if ist != soll:
        raise ControlPlaneError(
            f"trigger manifest mismatch: observed={ist} expected={soll}"
        )
    return {
        "schema_version": ver,
        "trigger_manifest_sha256": ist,
        "expected_trigger_manifest_sha256": soll,
        "next_run_id": next_run_id(conn),
        "durability": durability,
    }


def lease_snapshot(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Debug/test helper — all lease rows."""
    _refuse_live_conn(conn)
    rows = conn.execute(
        "SELECT token, run_id, issued_at, expires_at, consumed_at, revoked_at"
        " FROM run_lease ORDER BY issued_at, token"
    ).fetchall()
    return [dict(r) for r in rows]


def abort_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    reason: str = "",
    now: Optional[int] = None,
    allow_live: bool = False,
) -> dict[str, Any]:
    """Atomically mark RUNNING run ABORTED; revoke leftover open leases (L2).

    Caller must wrap with audit journal: on audit failure, ``ROLLBACK`` this
    transaction (gatectl holds BEGIN until audit succeeds).
    """
    _guard_live_conn(conn, allow_live=allow_live)
    # Heal only when not mid-transaction (gatectl may already BEGIN).
    if not conn.in_transaction:
        apply_writer_durability(conn)
    rid = int(run_id)
    ts = int(now if now is not None else time.time())
    cur = conn.execute(
        "UPDATE telemetry_runs SET status='ABORTED',"
        " closed_at=?"
        " WHERE run_id=? AND status='RUNNING'",
        (ts, rid),
    )
    if cur.rowcount != 1:
        raise LeaseError(f"abort-run refused: run_id={rid} not RUNNING")
    revoked = conn.execute(
        "UPDATE run_lease SET revoked_at=?"
        " WHERE run_id=? AND consumed_at IS NULL AND revoked_at IS NULL",
        (ts, rid),
    ).rowcount
    return {
        "run_id": rid,
        "reason": str(reason or ""),
        "closed_at": ts,
        "leases_revoked": int(revoked),
    }
