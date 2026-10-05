"""Zeuge TELEMETRY_RECONCILIATION-Gate (stille Write-Ausfälle)."""

from __future__ import annotations

import io
import sqlite3
import tempfile
import time
from contextlib import redirect_stdout
from pathlib import Path

from order_execution_engine.ops.preflight_check import (
    gate_claim_discard_accounting,
    gate_snapshot,
    gate_telemetry_reconciliation,
)


def _schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE telemetry_runs (
            run_id INTEGER PRIMARY KEY,
            started_at REAL,
            git_commit TEXT,
            config_json TEXT
        );
        CREATE TABLE telemetry (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id TEXT NOT NULL,
            order_id TEXT,
            latency_ms REAL NOT NULL,
            approved INTEGER NOT NULL,
            reject_reason TEXT,
            status TEXT,
            run_id INTEGER
        );
        CREATE TABLE dispatched_signals (
            item_id TEXT PRIMARY KEY,
            dispatched_at REAL,
            telemetry_seq INTEGER
        );
        CREATE TABLE bridge_discards (
            item_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            discarded_at REAL NOT NULL
        );
        """
    )


def test_gate_green_when_idle() -> None:
    """dispatched=0 → GREEN (nicht unterscheidbar von Inaktivität — erwartet)."""
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "t.db"
        conn = sqlite3.connect(db)
        _schema(conn)
        t0 = time.time()
        conn.execute(
            "INSERT INTO telemetry_runs VALUES (7, ?, 'x', '{}')", (t0,),
        )
        conn.commit()
        g = gate_telemetry_reconciliation(conn, min_run_id=7)
        assert g.status == "GREEN"
        assert g.detail["dispatched_success"] == 0
        conn.close()
    print("OK test_gate_green_when_idle")


def test_gate_green_when_telemetry_matches() -> None:
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "t.db"
        conn = sqlite3.connect(db)
        _schema(conn)
        t0 = time.time()
        conn.execute(
            "INSERT INTO telemetry_runs VALUES (7, ?, 'x', '{}')", (t0,),
        )
        conn.execute(
            "INSERT INTO dispatched_signals VALUES ('a', ?, NULL)", (t0 + 1,),
        )
        conn.execute(
            "INSERT INTO telemetry (signal_id, latency_ms, approved, run_id)"
            " VALUES ('s1', 1.0, 1, 7)",
        )
        conn.commit()
        g = gate_telemetry_reconciliation(conn, min_run_id=7)
        assert g.status == "GREEN"
        assert g.detail["dispatched_success"] == 1
        assert g.detail["telemetry_rows"] == 1
        conn.close()
    print("OK test_gate_green_when_telemetry_matches")


def test_gate_red_on_silent_write_gap() -> None:
    """Erfolgreicher Dispatch ohne Telemetrie-Zeile → RED."""
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "t.db"
        conn = sqlite3.connect(db)
        _schema(conn)
        t0 = time.time()
        conn.execute(
            "INSERT INTO telemetry_runs VALUES (7, ?, 'x', '{}')", (t0,),
        )
        conn.execute(
            "INSERT INTO dispatched_signals VALUES ('a', ?, NULL)", (t0 + 1,),
        )
        conn.execute(
            "INSERT INTO dispatched_signals VALUES ('b', ?, NULL)", (t0 + 2,),
        )
        conn.execute(
            "INSERT INTO telemetry (signal_id, latency_ms, approved, run_id)"
            " VALUES ('s1', 1.0, 1, 7)",
        )
        conn.commit()
        g = gate_telemetry_reconciliation(conn, min_run_id=7)
        assert g.status == "RED"
        assert g.detail["dispatched_success"] == 2
        assert g.detail["telemetry_rows"] == 1
        conn.close()
    print("OK test_gate_red_on_silent_write_gap")


def test_gate_ignores_discarded_claims() -> None:
    """Claim + bridge_discard (unresolved) zählt nicht als Erfolgspfad."""
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "t.db"
        conn = sqlite3.connect(db)
        _schema(conn)
        t0 = time.time()
        conn.execute(
            "INSERT INTO telemetry_runs VALUES (7, ?, 'x', '{}')", (t0,),
        )
        conn.execute(
            "INSERT INTO dispatched_signals VALUES ('miss', ?, NULL)", (t0 + 1,),
        )
        conn.execute(
            "INSERT INTO bridge_discards VALUES "
            "('miss', 'unresolved_asset:mapping_miss', ?)",
            (t0 + 1,),
        )
        conn.commit()
        g = gate_telemetry_reconciliation(conn, min_run_id=7)
        assert g.status == "GREEN"
        assert g.detail["dispatched_success"] == 0
        conn.close()
    print("OK test_gate_ignores_discarded_claims")


def test_gate_snapshot_discards_use_min_run_started_at() -> None:
    """Discards + Dispatches + Dups ab min_run_id.started_at (wie Reconciliation)."""
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "t.db"
        conn = sqlite3.connect(db)
        _schema(conn)
        conn.executescript(
            """
            CREATE TABLE telemetry_fill_metrics (
                telemetry_seq INTEGER PRIMARY KEY
            );
            """
        )
        t0 = 1_000_000.0
        conn.execute(
            "INSERT INTO telemetry_runs VALUES (7, ?, 'x', '{}')", (t0,),
        )
        # Vor Anker — darf nicht in discard_reasons / dispatched erscheinen
        conn.execute(
            "INSERT INTO bridge_discards VALUES "
            "('legacy', 'unresolved_asset', ?)",
            (t0 - 100,),
        )
        conn.execute(
            "INSERT INTO dispatched_signals VALUES ('legacy-d', ?, NULL)",
            (t0 - 50,),
        )
        conn.execute(
            "INSERT INTO bridge_discards VALUES "
            "('ok1', 'no_book', ?)",
            (t0 + 1,),
        )
        conn.execute(
            "INSERT INTO bridge_discards VALUES "
            "('ok2', 'unresolved_asset:mapping_miss', ?)",
            (t0 + 2,),
        )
        conn.execute(
            "INSERT INTO dispatched_signals VALUES ('ok-d', ?, NULL)",
            (t0 + 3,),
        )
        conn.execute(
            "INSERT INTO telemetry (signal_id, latency_ms, approved, run_id)"
            " VALUES ('s1', 0.2, 0, 7)",
        )
        conn.commit()
        conn.close()

        errors: list[str] = []
        with redirect_stdout(io.StringIO()):
            snap = gate_snapshot(db, errors, min_run_id=7)
        assert snap is not None
        assert snap["time_filter"] == "run_id=7.started_at"
        assert snap["discard_reasons"] == {
            "no_book": 1,
            "unresolved_asset:mapping_miss": 1,
        }
        assert "unresolved_asset" not in snap["discard_reasons"]
        assert snap["dispatched_signals"] == 1
        assert snap["duplicate_item_ids"] == 0
        acct = snap["claim_discard_accounting"]
        assert acct.status == "GREEN"
        assert acct.detail == {
            "claims": 1,
            "success": 1,
            "post_claim_discards": 0,
            "discards": 2,
            "pre_claim_discards": 2,
            "post_claim_from_discards": 0,
        }
        assert errors == []
    print("OK test_gate_snapshot_discards_use_min_run_started_at")


def test_gate_claim_discard_accounting_run8_shape() -> None:
    """Run-8-Form: claims=success+post; discards=post+pre (empty_list vor Claim)."""
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "t.db"
        conn = sqlite3.connect(db)
        _schema(conn)
        t0 = 2_000_000.0
        conn.execute(
            "INSERT INTO telemetry_runs VALUES (8, ?, 'x', '{}')", (t0,),
        )
        # pre-claim (empty_list): discard ohne Claim
        conn.execute(
            "INSERT INTO bridge_discards VALUES "
            "('pre1', 'unresolved_asset:empty_list', ?)",
            (t0 + 1,),
        )
        # post-claim: Claim dann Discard
        conn.execute(
            "INSERT INTO dispatched_signals VALUES ('post1', ?, NULL)",
            (t0 + 2,),
        )
        conn.execute(
            "INSERT INTO bridge_discards VALUES "
            "('post1', 'unresolved_asset:mapping_miss', ?)",
            (t0 + 2,),
        )
        # success: Claim ohne Discard
        conn.execute(
            "INSERT INTO dispatched_signals VALUES ('ok', ?, NULL)",
            (t0 + 3,),
        )
        conn.commit()
        g = gate_claim_discard_accounting(conn, started_at=t0)
        assert g.status == "GREEN"
        assert g.detail["claims"] == 2
        assert g.detail["success"] == 1
        assert g.detail["post_claim_discards"] == 1
        assert g.detail["discards"] == 2
        assert g.detail["pre_claim_discards"] == 1
        assert g.detail["claims"] == (
            g.detail["success"] + g.detail["post_claim_discards"]
        )
        assert g.detail["discards"] == (
            g.detail["post_claim_from_discards"] + g.detail["pre_claim_discards"]
        )
        conn.close()
    print("OK test_gate_claim_discard_accounting_run8_shape")


def test_gate_claim_discard_accounting_red_on_orphan_claim() -> None:
    """Claim im Fenster, Discard nur außerhalb → post-Views divergieren → RED."""
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "t.db"
        conn = sqlite3.connect(db)
        _schema(conn)
        t0 = 3_000_000.0
        conn.execute(
            "INSERT INTO telemetry_runs VALUES (8, ?, 'x', '{}')", (t0,),
        )
        conn.execute(
            "INSERT INTO dispatched_signals VALUES ('orphan', ?, NULL)",
            (t0 + 1,),
        )
        conn.execute(
            "INSERT INTO bridge_discards VALUES "
            "('orphan', 'no_book', ?)",
            (t0 - 10,),
        )
        conn.commit()
        g = gate_claim_discard_accounting(conn, started_at=t0)
        assert g.status == "RED"
        assert g.detail["post_claim_discards"] == 1
        assert g.detail["post_claim_from_discards"] == 0
        conn.close()
    print("OK test_gate_claim_discard_accounting_red_on_orphan_claim")
