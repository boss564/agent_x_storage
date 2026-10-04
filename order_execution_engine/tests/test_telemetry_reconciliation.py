"""Zeuge TELEMETRY_RECONCILIATION-Gate (stille Write-Ausfälle)."""

from __future__ import annotations

import sqlite3
import tempfile
import time
from pathlib import Path

from order_execution_engine.ops.preflight_check import gate_telemetry_reconciliation


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
