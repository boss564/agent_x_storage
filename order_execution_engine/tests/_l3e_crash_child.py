"""L3-e crash-injection child — kill -9 target (never LIVE).

Invoked as: python _l3e_crash_child.py <mode> <db_path>
Modes: before_commit | after_commit | mid_wal
Prints READY then sleeps until parent SIGKILL.
"""

from __future__ import annotations

import secrets
import sys
import time
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: _l3e_crash_child.py <mode> <db_path>")
    mode, db_s = sys.argv[1], sys.argv[2]
    db = Path(db_s)

    from order_execution_engine.control_plane_lease import (
        _open_sqlite,
        claim_run,
        issue_token,
        next_run_id,
    )

    conn = _open_sqlite(db)
    now = int(time.time())
    rid = next_run_id(conn)

    if mode == "before_commit":
        tok = secrets.token_hex(20)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO run_lease"
            " (token, run_id, issued_at, expires_at, consumed_at, revoked_at)"
            " VALUES (?, ?, ?, ?, NULL, NULL)",
            (tok, rid, now, now + 120),
        )
        print("READY", flush=True)
        time.sleep(3600)
    elif mode == "after_commit":
        tok = issue_token(conn, run_id=rid, ttl_s=120, now=now)
        claim_run(
            conn, git_commit="l3e", config_json="{}", token=tok, now=now
        )
        print("READY", flush=True)
        time.sleep(3600)
    elif mode == "mid_wal":
        # Uncommitted writes into a scratch table (no lease triggers) + one
        # uncommitted lease INSERT — kill before COMMIT rolls both back.
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS l3e_wal_pad (k INTEGER PRIMARY KEY, v BLOB)"
        )
        pad = secrets.token_bytes(4096)
        for i in range(80):
            conn.execute(
                "INSERT OR REPLACE INTO l3e_wal_pad (k, v) VALUES (?, ?)",
                (i, pad),
            )
        tok = secrets.token_hex(20)
        conn.execute(
            "INSERT INTO run_lease"
            " (token, run_id, issued_at, expires_at, consumed_at, revoked_at)"
            " VALUES (?, ?, ?, ?, NULL, NULL)",
            (tok, rid, now, now + 120),
        )
        print("READY", flush=True)
        time.sleep(3600)
    else:
        raise SystemExit(f"unknown mode {mode!r}")


if __name__ == "__main__":
    main()
