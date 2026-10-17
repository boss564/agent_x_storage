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
    partition_ok,
    terminal_classes,
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
            run_id INTEGER,
            decision_seq INTEGER
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
            "INSERT INTO telemetry (signal_id, latency_ms, approved, run_id,"
            " decision_seq) VALUES ('s1', 1.0, 1, 7, 1)",
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
            "INSERT INTO telemetry (signal_id, latency_ms, approved, run_id,"
            " decision_seq) VALUES ('s1', 1.0, 1, 7, 1)",
        )
        conn.commit()
        g = gate_telemetry_reconciliation(conn, min_run_id=7)
        assert g.status == "RED"
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
            "INSERT INTO telemetry (signal_id, latency_ms, approved, run_id,"
            " decision_seq) VALUES ('s1', 0.2, 0, 7, 1)",
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
        assert snap["join_is_one_to_one"] is True
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


def test_terminal_view_is_two_axes_not_one_sum() -> None:
    """Run-8-Form: eine Achse summiert 38 gegen 34 — zwei Achsen summieren 34.

    Der Defekt, den dieser Zeuge fängt: ``unattributed`` in die Ausgangs-Achse
    gelegt ergibt filled 1 + rejected 22 + stale 7 + unattributed 4 = 34,
    aber mit ``telemetry_rows`` als rejected-Basis 26 + 4 = doppelt.
    """
    detail = {
        "dispatched_success": 34,
        "telemetry_rows": 34,
        "reasons": {"NONE": 1, "INVALID_PRICE": 26, "STALE_SNAPSHOT": 7},
        "classifiable": 34,
        "unattributed": 4,
    }
    classes = terminal_classes(detail)
    assert classes["outcome"] == {"filled": 1, "rejected": 26, "stale": 7}
    assert classes["origin"] == {"telemetry": 30, "unattributed": 4}
    assert "unattributed" not in classes["outcome"]
    # Die falsche Ein-Achsen-View hätte 1+26+7+4 = 38 gegen 34 gestellt.
    naive = {**classes["outcome"], "unattributed": 4}
    assert sum(naive.values()) == 38
    # Beide Achsen schließen einzeln auf success — keine Achse auf 38.
    assert sum(classes["outcome"].values()) == 34
    assert sum(classes["origin"].values()) == 34
    print("OK test_terminal_view_is_two_axes_not_one_sum")


def test_gate_red_when_decision_seq_collides() -> None:
    """Join-Schlüssel ``decision_seq`` doppelt -> RED (item_id wäre unauffällig)."""
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
        # Zwei Zeilen, zwei verschiedene signal_ids, aber derselbe
        # Entscheidungs-Key. Die Vollständigkeitsprüfung muss dabei grün
        # bleiben (beide Dispatches haben eine Zeile) — rot kommen darf nur
        # die Kardinalität.
        conn.execute(
            "INSERT INTO telemetry (signal_id, latency_ms, approved, run_id,"
            " decision_seq) VALUES ('s1', 1.0, 1, 7, 1)",
        )
        conn.execute(
            "INSERT INTO telemetry (signal_id, latency_ms, approved, run_id,"
            " decision_seq) VALUES ('s2', 1.0, 1, 7, 1)",
        )
        conn.commit()
        g = gate_telemetry_reconciliation(conn, min_run_id=7)
        assert g.status == "RED"
        assert g.detail["decision_seq_keyed"] == 2
        assert g.detail["decision_seq_distinct_pair"] == 1
        assert g.detail["decision_seq_unique_per_run"] is False
        conn.close()
    print("OK test_gate_red_when_decision_seq_collides")


def test_gate_red_when_telemetry_row_has_no_decision_seq() -> None:
    """Zeile ohne Entscheidungs-Key ist nicht joinbar -> RED, nicht still."""
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
        assert g.status == "RED"
        assert g.detail["telemetry_rows"] == 1
        assert g.detail["decision_seq_keyed"] == 0
        conn.close()
    print("OK test_gate_red_when_telemetry_row_has_no_decision_seq")


def test_decision_seq_restarts_per_run_and_is_not_a_collision() -> None:
    """Run 9 beginnt bei decision_seq=1: das Paar ist eindeutig, die Spalte nicht."""
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "t.db"
        conn = sqlite3.connect(db)
        _schema(conn)
        t0 = time.time()
        conn.execute("INSERT INTO telemetry_runs VALUES (8, ?, 'x', '{}')", (t0,))
        conn.execute("INSERT INTO telemetry_runs VALUES (9, ?, 'y', '{}')", (t0 + 10,))
        for rid in (8, 9):
            conn.execute(
                "INSERT INTO dispatched_signals VALUES (?, ?, NULL)",
                (f"d{rid}", t0 + rid,),
            )
            conn.execute(
                "INSERT INTO telemetry (signal_id, latency_ms, approved, run_id,"
                " decision_seq) VALUES (?, 1.0, 1, ?, ?)",
                (f"s{rid}", rid, rid - 7),
            )
        conn.commit()
        g = gate_telemetry_reconciliation(conn, min_run_id=8)
        assert g.detail["decision_seq_keyed"] == 2
        assert g.detail["decision_seq_distinct_pair"] == 2
        assert g.detail["decision_seq_unique_per_run"] is True
        # decision_seq beginnt je Run neu (Run 9 bei 1) und ist dennoch eindeutig
        # als Paar — das ist der Normalfall. Die Vollständigkeit ist hier rot,
        # weil ohne `started_at` die Reihenfolge nicht bestimmbar ist; das ist
        # Aufgabe eines eigenen Zeugen, nicht dieses.
        assert g.detail["decision_seq_distinct_pair"] == 2
        conn.close()
    print("OK test_decision_seq_restarts_per_run_and_is_not_a_collision")


def test_unattributed_join_uses_decision_seq_not_item_id() -> None:
    """item_id (MD5) ist nie die signal_id (UUID-sub5) — der Join läuft über den Key."""
    import hashlib

    from order_execution_engine.news_bridge import SIGNAL_NAMESPACE
    import uuid

    item_id = "e3b0c44298fc1c149afbf4c8996fb924"
    signal_id = str(uuid.uuid5(SIGNAL_NAMESPACE, item_id))
    assert item_id != signal_id
    assert len(item_id) == 32 and len(signal_id) == 36
    assert hashlib.md5(item_id.encode()).hexdigest() == hashlib.md5(
        item_id.encode()).hexdigest()

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "t.db"
        conn = sqlite3.connect(db)
        _schema(conn)
        t0 = time.time()
        conn.execute("INSERT INTO telemetry_runs VALUES (8, ?, 'x', '{}')", (t0,))
        # Erster Dispatch hat KEINE Zeile, der zweite hat eine.
        conn.execute(
            "INSERT INTO dispatched_signals VALUES (?, ?, NULL)", (item_id, t0 + 1))
        conn.execute(
            "INSERT INTO dispatched_signals VALUES (?, ?, NULL)",
            ("other", t0 + 2))
        conn.execute(
            "INSERT INTO telemetry (signal_id, latency_ms, approved, run_id,"
            " decision_seq) VALUES (?, 1.0, 0, 8, 2)", (signal_id,))
        conn.commit()
        g = gate_telemetry_reconciliation(conn, min_run_id=8)
        # Genau 1 unklassifiziert — der erste Dispatch. Ein Join über signal_id
        # (UUID) gegen item_id (MD5) fände hier gar nichts und meldete 2.
        assert g.detail["unattributed"] == 1
        conn.close()
    print("OK test_unattributed_join_uses_decision_seq_not_item_id")


def test_historical_red_does_not_block_current_green() -> None:
    """Abgeschlossener roter Lauf: current GREEN, historical RED, keine Blocker."""
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "t.db"
        conn = sqlite3.connect(db)
        _schema(conn)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS telemetry_fill_metrics ("
            "telemetry_seq INTEGER PRIMARY KEY)"
        )
        t0 = 1_000_000.0
        conn.execute("INSERT INTO telemetry_runs VALUES (8, ?, 'x', '{}')", (t0,))
        conn.execute("INSERT INTO telemetry_runs VALUES (9, ?, 'y', '{}')", (t0 + 99,))
        # Run 8: 2 Dispatches, 1 Zeile -> 1 unattributed (historisch rot).
        conn.execute("INSERT INTO dispatched_signals VALUES ('a8', ?, NULL)", (t0 + 1,))
        conn.execute("INSERT INTO dispatched_signals VALUES ('b8', ?, NULL)", (t0 + 2,))
        conn.execute(
            "INSERT INTO telemetry (signal_id, latency_ms, approved, run_id,"
            " decision_seq) VALUES ('s8', 1.0, 1, 8, 2)")
        # Run 9: 1 Dispatch, 1 Zeile -> grün.
        conn.execute("INSERT INTO dispatched_signals VALUES ('a9', ?, NULL)", (t0 + 100,))
        conn.execute(
            "INSERT INTO telemetry (signal_id, latency_ms, approved, run_id,"
            " decision_seq) VALUES ('s9', 1.0, 1, 9, 1)")
        conn.commit()
        errors: list[str] = []
        with redirect_stdout(io.StringIO()):
            snap = gate_snapshot(db, errors, min_run_id=8)
        assert snap is not None
        assert snap["reconciliation"].status == "RED"
        assert snap["verdicts"]["current"] == "GREEN"
        assert "RED (run 8" in snap["verdicts"]["historical"]
        # Nicht blockierend: der historische Befund landet nicht in errors.
        assert errors == [], errors
        conn.close()
    print("OK test_historical_red_does_not_block_current_green")


def test_current_red_still_blocks() -> None:
    """Jüngster Lauf rot -> current RED -> blockierend. Die Trennung schluckt nichts."""
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "t.db"
        conn = sqlite3.connect(db)
        _schema(conn)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS telemetry_fill_metrics ("
            "telemetry_seq INTEGER PRIMARY KEY)"
        )
        t0 = 1_000_000.0
        conn.execute("INSERT INTO telemetry_runs VALUES (9, ?, 'y', '{}')", (t0,))
        conn.execute("INSERT INTO dispatched_signals VALUES ('a9', ?, NULL)", (t0 + 1,))
        conn.execute("INSERT INTO dispatched_signals VALUES ('b9', ?, NULL)", (t0 + 2,))
        conn.execute(
            "INSERT INTO telemetry (signal_id, latency_ms, approved, run_id,"
            " decision_seq) VALUES ('s9', 1.0, 1, 9, 2)")
        conn.commit()
        errors: list[str] = []
        with redirect_stdout(io.StringIO()):
            snap = gate_snapshot(db, errors, min_run_id=9)
        assert snap is not None
        assert snap["verdicts"]["current"] == "RED"
        assert snap["verdicts"]["historical"] == "n/a"
        assert any("TELEMETRY_RECONCILIATION" in e for e in errors), errors
        conn.close()
    print("OK test_current_red_still_blocks")
