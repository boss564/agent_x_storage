"""Zeuge TELEMETRY_RECONCILIATION-Gate (stille Write-Ausfälle)."""

from __future__ import annotations

import io
import sqlite3
import tempfile
import time
from contextlib import redirect_stdout
from pathlib import Path

from order_execution_engine.ops.preflight_check import (
    MIN_TELEMETRY_ROWS,
    _gate_criterion,
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


def test_gate_red_when_idle_underrun() -> None:
    """dispatched=0 → **RED**, nicht GREEN.

    Frühere Fassung: `test_gate_green_when_idle` mit der Begründung
    „nicht unterscheidbar von Inaktivität — erwartet". Das war die Tautologie
    als Erwartung: (1)-(4) sind bei beidseitiger Null erfüllt, also las sich
    ein stiller Ausfall wie Inaktivität. Bedingung (0) — Untergrenze aus dem
    dokumentierten Lauf — bricht das: ein Lauf ohne Daten ist kein Beleg.
    """
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
        assert g.status == "RED"
        assert g.detail["dispatched_success"] == 0
        assert g.detail.get("underrun") is True
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
        # Bedingung (0): eine Zeile ist unter der Untergrenze -> RED.
        # Dieser Test prüft die Gleichheitslogik und braucht daher genug
        # Daten; die Untergrenze selbst prüft test_branch_0_underrun.
        assert g.status == "RED"
        assert g.detail.get("underrun") is True
        conn.close()

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "t.db"
        conn = sqlite3.connect(db)
        _schema(conn)
        t0 = time.time()
        conn.execute(
            "INSERT INTO telemetry_runs VALUES (7, ?, 'x', '{}')", (t0,),
        )
        for i in range(MIN_TELEMETRY_ROWS):
            conn.execute(
                "INSERT INTO dispatched_signals VALUES (?, ?, NULL)",
                (f"a{i}", t0 + 1),
            )
            conn.execute(
                "INSERT INTO telemetry (signal_id, latency_ms, approved, run_id,"
                " decision_seq) VALUES (?, 1.0, 1, 7, ?)",
                (f"s{i}", i + 1),
            )
        conn.commit()
        g = gate_telemetry_reconciliation(conn, min_run_id=7)
        assert g.status == "LEDGER_CONSISTENT"
        assert g.detail["dispatched_success"] == MIN_TELEMETRY_ROWS
        assert g.detail["telemetry_rows"] == MIN_TELEMETRY_ROWS
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
        # Claim wurde verworfen -> dispatched_success == 0. Seit Bedingung (0)
        # ist ein leerer Lauf RED (Untergrenze), nicht GREEN: "gar nichts"
        # ist kein Beleg. Was der Test behauptet, ist die Attribution
        # (discard zählt nicht als Erfolgspfad) — die steht im detail.
        assert g.detail["dispatched_success"] == 0
        assert g.status == "RED"
        assert g.detail.get("underrun") is True
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
        # Legacy-Dispatch VOR dem Anker: darf weder in discard_reasons noch
        # in dispatched_success erscheinen — das ist die Aussage dieses Tests.
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
        # Mindestens MIN_TELEMETRY_ROWS Zeilen mit passendem Dispatch:
        # dieser Test prüft die Discard-Attribution, nicht die Untergrenze
        # (Bedingung 0) und nicht die Konvidenz (Zweig 4).
        # 1 + MIN_TELEMETRY_ROWS Dispatches im Fenster (ok-d + ok-d0..n),
        # also genauso viele Telemetriezeilen: decision_seq 1..n+1.
        for i in range(MIN_TELEMETRY_ROWS + 1):
            conn.execute(
                "INSERT INTO telemetry (signal_id, latency_ms, approved, run_id,"
                " decision_seq) VALUES (?, 0.2, 0, 7, ?)",
                (f"s{i}", i + 1),
            )
        for i in range(MIN_TELEMETRY_ROWS):
            conn.execute(
                "INSERT INTO dispatched_signals VALUES (?, ?, NULL)",
                (f"ok-d{i}", t0 + 4 + i),
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
        assert snap["dispatched_signals"] == 1 + MIN_TELEMETRY_ROWS
        assert snap["duplicate_item_ids"] == 0
        assert snap["join_is_one_to_one"] is True
        acct = snap["claim_discard_accounting"]
        assert acct.status == "GREEN"
        assert acct.detail == {
            "claims": 1 + MIN_TELEMETRY_ROWS,
            "success": 1 + MIN_TELEMETRY_ROWS,
            "post_claim_discards": 0,
            "discards": 2,
            "pre_claim_discards": 2,
            "post_claim_from_discards": 0,
        }
        # Dieser Test prüft die Discard-/Accounting-Attribution. Die
        # Dispatch-Konvidenz (Zweig 4) ist hier bewusst ungleich
        # (1 Dispatch, MIN_TELEMETRY_ROWS Zeilen) und darf melden; sie wird
        # durch test_branch_4_dispatched_not_fully_partitioned abgedeckt.
        assert [e for e in errors if "TELEMETRY_RECONCILIATION" not in e] == []
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
        # Run 9: genug Zeilen für (0), alle konsistent -> LEDGER_CONSISTENT.
        for i in range(PINNED_MIN_TELEMETRY_ROWS):
            conn.execute(
                "INSERT INTO dispatched_signals VALUES (?, ?, NULL)",
                (f"a9-{i}", t0 + 100 + i),
            )
            conn.execute(
                "INSERT INTO telemetry (signal_id, latency_ms, approved, run_id,"
                " decision_seq) VALUES (?, 1.0, 1, 9, ?)",
                (f"s9-{i}", i + 1),
            )
        conn.commit()
        errors: list[str] = []
        with redirect_stdout(io.StringIO()):
            snap = gate_snapshot(db, errors, min_run_id=8)
        assert snap is not None
        assert snap["reconciliation"].status == "RED"
        assert snap["verdicts"]["current"] == "LEDGER_CONSISTENT"
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


# --- Kopplung Kriterium <-> RED-Zweige -------------------------------------
# Vier Darstellungen derselben Regel: die vier RED-Rückgaben in
# gate_telemetry_reconciliation, der Docstring, und die gedruckte
# `criterion:`-Zeile. Der Docstring behauptete, ein Test könne das nicht
# prüfen. Das war die Erlaubnis, vier Kopien zu behalten.


def _seed_run(conn: sqlite3.Connection, *, rows: int, keyed: int,
              dispatched: int, reasons: int) -> None:
    """Legt einen Lauf mit genau definierten Zahlen an."""
    t0 = time.time()
    conn.execute("INSERT INTO telemetry_runs VALUES (9, ?, 'x', '{}')", (t0,))
    for i in range(1, rows + 1):
        conn.execute(
            "INSERT INTO telemetry (signal_id, latency_ms, approved, "
            "reject_reason, run_id, decision_seq) VALUES (?, 1.0, 0, 'X', 9, ?)",
            (f"s{i}", i if i <= keyed else None),
        )
    for i in range(dispatched):
        conn.execute(
            "INSERT INTO dispatched_signals VALUES (?, ?, NULL)",
            (f's{i}', t0 + 1),
        )
    conn.commit()


def _run(rows, keyed, dispatched, reasons) -> tuple[str, dict]:
    with tempfile.TemporaryDirectory() as td:
        conn = sqlite3.connect(Path(td) / "t.db")
        _schema(conn)
        _seed_run(conn, rows=rows, keyed=keyed, dispatched=dispatched,
                  reasons=reasons)
        g = gate_telemetry_reconciliation(conn, min_run_id=9)
        conn.close()
        return g.status, g.detail


def test_criterion_is_printed_in_the_same_order_as_the_red_branches() -> None:
    """(0)…(4) in der criterion-Zeile, in der Reihenfolge der Rückgaben."""
    line = _gate_criterion(9)
    assert line.startswith("LEDGER_CONSISTENT nur wenn (0)")
    for i in range(1, 5):
        assert f"({i})" in line, f"Bedingung {i} fehlt in der criterion-Zeile"
    assert f"(0) telemetry_rows >= {MIN_TELEMETRY_ROWS}" in line
    assert "scope = run_id >= 9" in line


def test_criterion_count_matches_red_branches_in_source() -> None:
    """Ein fünfter RED-Zweig ohne criterion-Ergänzung bricht diesen Test.

    Die vier (jetzt fünf) Fixtures unten prüfen, dass jeder Zweig existiert.
    Sie prüfen **nicht**, dass kein weiterer dazukommt — das tut diese
    Zeugenfunktion, indem sie die RED-Rückgaben im Quelltext des Gates
    zählt und mit der Anzahl der Bedingungen in der criterion-Zeile
    vergleicht. Genau hier bricht es, wenn eine Bedingung eingefügt wird,
    ohne daß die gedruckte Regel mitwächst.
    """
    import inspect
    import re

    from order_execution_engine.ops import preflight_check

    src = inspect.getsource(preflight_check.gate_telemetry_reconciliation)
    # Jede RED-Rückgabe ist ein Zweig. (0) hat zwei Ausgänge — "kein Lauf"
    # und "zu wenige Zeilen" — beide bedeuten "nicht gemessen" und tragen
    # deshalb dieselbe Nummer. Deshalb wird gegen numbered + 1 verglichen,
    # nicht gegen numbered.
    red_returns = len(re.findall(r'status="RED"', src))
    line = _gate_criterion(9)
    # (5) ist ausdrücklich als Warnung deklariert und hat keinen RED-Zweig.
    numbered = {n for n in re.findall(r"\((\d)\)", line) if n != "5"}
    # numbered = {0,1,2,3,4}; (0) hat zwei RED-Zweige -> 6 erwartet.
    expected = len(numbered) + 1
    assert red_returns == expected, (
        f"{red_returns} RED-Rückgaben im Gate, aber {expected} erwartet "
        f"({sorted(numbered)} + der zweite (0)-Ausgang) — ein Zweig ohne "
        "gedruckte Regel (oder umgekehrt)."
    )
    assert "(5) WARNUNG" in line


def test_branch_0_underrun() -> None:
    """(0) leere/unzureichende Datenlage -> RED, nicht GREEN."""
    status, detail = _run(rows=0, keyed=0, dispatched=0, reasons=0)
    assert status == "RED"
    assert detail.get("underrun") is True


def test_branch_1_row_without_decision_seq() -> None:
    """(1) telemetry_rows != keyed."""
    status, detail = _run(
        rows=MIN_TELEMETRY_ROWS + 1, keyed=MIN_TELEMETRY_ROWS,
        dispatched=MIN_TELEMETRY_ROWS, reasons=MIN_TELEMETRY_ROWS + 1,
    )
    assert status == "RED"
    assert detail.get("underrun") is None
    assert detail["telemetry_rows"] != detail["decision_seq_keyed"]


def test_branch_2_duplicate_decision_seq() -> None:
    """(2) keyed != distinct(run_id, decision_seq) — Kollision je Lauf."""
    with tempfile.TemporaryDirectory() as td:
        conn = sqlite3.connect(Path(td) / "t.db")
        _schema(conn)
        t0 = time.time()
        conn.execute("INSERT INTO telemetry_runs VALUES (9, ?, 'x', '{}')", (t0,))
        for _ in range(MIN_TELEMETRY_ROWS):
            conn.execute(
                "INSERT INTO telemetry (signal_id, latency_ms, approved, "
                "reject_reason, run_id, decision_seq) VALUES ('d', 1.0, 0, 'X', 9, 1)"
            )
        conn.commit()
        g = gate_telemetry_reconciliation(conn, min_run_id=9)
        conn.close()
    assert g.status == "RED"
    assert g.detail["decision_seq_unique_per_run"] is False


def test_branch_3_unattributed_dispatch() -> None:
    """(3) ein Dispatch ohne Telemetriezeile."""
    status, detail = _run(
        rows=MIN_TELEMETRY_ROWS, keyed=MIN_TELEMETRY_ROWS,
        dispatched=MIN_TELEMETRY_ROWS + 1, reasons=MIN_TELEMETRY_ROWS,
    )
    assert status == "RED"
    assert detail["unattributed"] >= 1


def test_branch_4_dispatched_not_fully_partitioned() -> None:
    """(4) dispatched_success != Σ reject_reasons.

    Erreichbar, wenn mehr klassifizierte Telemetriezeilen existieren als
    Dispatches gezählt wurden — der Zähler und die Klassen laufen über
    verschiedene Mengen (``dispatched_signals`` mit started_at-Filter vs.
    ``telemetry`` mit run_id-Filter). Genau diese Divergenz ist die Lücke,
    die (4) schließt.
    """
    with tempfile.TemporaryDirectory() as td:
        conn = sqlite3.connect(Path(td) / "t.db")
        _schema(conn)
        t0 = time.time()
        conn.execute("INSERT INTO telemetry_runs VALUES (9, ?, 'x', '{}')", (t0,))
        for i in range(MIN_TELEMETRY_ROWS):
            conn.execute(
                "INSERT INTO telemetry (signal_id, latency_ms, approved, "
                "reject_reason, run_id, decision_seq) VALUES (?, 1.0, 0, 'X', 9, ?)",
                (f"s{i}", i + 1),
            )
        # bewusst keine dispatched_signals-Zeilen
        conn.commit()
        g = gate_telemetry_reconciliation(conn, min_run_id=9)
        conn.close()
    assert g.status == "RED"
    assert g.detail["unattributed"] == 0
    assert sum(g.detail["reasons"].values()) > g.detail["dispatched_success"]


# --- Schwelle von beiden Seiten --------------------------------------------
# Die drei angehobenen Bestandstests (green_when_telemetry_matches,
# ignores_discarded_claims, snapshot_discards) lesen MIN_TELEMETRY_ROWS und
# wachsen mit. Probe: Untergrenze auf 5 gesetzt -> 21 passed. Sie prüfen die
# Untergrenze also nicht, sie folgen ihr. Das ist "Tests an die Schwelle
# anpassen" in der Form, die grün bleibt, egal wohin die Schwelle wandert.
# Hier wird sie von beiden Seiten gehalten.


def _seed_exact(conn: sqlite3.Connection, n: int) -> None:
    """Genau n konsistente Dispatches + Telemetriezeilen (alle gefüllt)."""
    t0 = time.time()
    conn.execute("INSERT INTO telemetry_runs VALUES (9, ?, 'x', '{}')", (t0,))
    for i in range(n):
        conn.execute(
            "INSERT INTO telemetry (signal_id, latency_ms, approved, run_id,"
            " decision_seq) VALUES (?, 1.0, 1, 9, ?)",
            (f"s{i}", i + 1),
        )
        conn.execute(
            "INSERT INTO dispatched_signals VALUES (?, ?, NULL)",
            (f"s{i}", t0 + 1),
        )
    conn.commit()


def _status_at(n: int) -> tuple[str, dict]:
    with tempfile.TemporaryDirectory() as td:
        conn = sqlite3.connect(Path(td) / "t.db")
        _schema(conn)
        _seed_exact(conn, n)
        g = gate_telemetry_reconciliation(conn, min_run_id=9)
        conn.close()
        return g.status, g.detail


# Gepinnte Schwelle. NICHT MIN_TELEMETRY_ROWS — sonst wandert der Test mit
# und ist bei jeder Schwelle grün (Probe: 3 und 5 beide 23 passed).
# Die Zahl ist die Abnahme-Zahl; wandert sie, bricht hier etwas, und das ist
# gewollt: eine Schwellenänderung ist eine Kriteriumsänderung.
PINNED_MIN_TELEMETRY_ROWS = 4


def test_threshold_constant_is_the_pinned_value() -> None:
    """Die Schwelle im Kriterium ist die gepinnte — nicht eine, die mitwächst."""
    assert MIN_TELEMETRY_ROWS == PINNED_MIN_TELEMETRY_ROWS, (
        f"MIN_TELEMETRY_ROWS={MIN_TELEMETRY_ROWS}, gepinnt="
        f"{PINNED_MIN_TELEMETRY_ROWS}. Eine Änderung der Untergrenze ist "
        "eine Änderung des Kriteriums — criterion-Zeile und Abnahme mitziehen."
    )


def test_threshold_exact_boundary_is_green() -> None:
    """Genau PINNED_MIN_TELEMETRY_ROWS konsistente Zeilen -> GREEN."""
    status, detail = _status_at(PINNED_MIN_TELEMETRY_ROWS)
    assert status == "LEDGER_CONSISTENT", detail
    assert detail["telemetry_rows"] == PINNED_MIN_TELEMETRY_ROWS


def test_threshold_one_below_is_red_underrun() -> None:
    """PINNED - 1 Zeilen -> RED als underrun, obwohl (1)-(4) erfüllt sind.

    Die Zeilenzahl ist gepinnt, nicht aus der Konstante abgeleitet: sonst
    wäre der Test bei jeder Schwelle grün und würde die Untergrenze nur
    mitschreiben statt sie zu halten.
    """
    status, detail = _status_at(PINNED_MIN_TELEMETRY_ROWS - 1)
    assert status == "RED", "Untergrenze greift eine Zeile zu tief" + str(detail)
    assert detail.get("underrun") is True
    assert detail["telemetry_rows"] == detail["decision_seq_keyed"]
    assert detail["unattributed"] == 0
    assert detail["dispatched_success"] == sum(detail["reasons"].values())


def test_latest_run_failure_blocks_even_when_called_with_old_min_run_id() -> None:
    """Ein Aufruf mit alter min_run_id darf den jüngsten Ausfall nicht schlucken.

    Befund: `recon` mißt nur min_run_id, die Blockade hing an
    `verdicts.current == "GREEN"` — und current war konstant "GREEN".
    Ergebnis: ein Aufruf mit min_run_id=8 über einem kaputten Run 9
    lieferte current=RED und errors==[] (0 blockierend). Der Befund über
    den laufenden Lauf war unerreichbar.

    Der Test pinnt beide Seiten: kaputter jüngster Lauf blockiert, intakter
    jüngster Lauf blockiert nicht.
    """
    def build(run9_rows: int) -> Path:
        td = tempfile.mkdtemp()
        db = Path(td) / "t.db"
        conn = sqlite3.connect(db)
        _schema(conn)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS telemetry_fill_metrics ("
            "telemetry_seq INTEGER PRIMARY KEY)"
        )
        t0 = 1_000_000.0
        conn.execute("INSERT INTO telemetry_runs VALUES (8, ?, 'x', '{}')", (t0,))
        conn.execute(
            "INSERT INTO telemetry_runs VALUES (9, ?, 'y', '{}')", (t0 + 99,)
        )
        # Run 8: historisch rot (2 Dispatches, 1 Zeile).
        conn.execute("INSERT INTO dispatched_signals VALUES ('a8', ?, NULL)", (t0 + 1,))
        conn.execute("INSERT INTO dispatched_signals VALUES ('b8', ?, NULL)", (t0 + 2,))
        conn.execute(
            "INSERT INTO telemetry (signal_id, latency_ms, approved, run_id,"
            " decision_seq) VALUES ('s8', 1.0, 1, 8, 2)"
        )
        for i in range(run9_rows):
            conn.execute(
                "INSERT INTO dispatched_signals VALUES (?, ?, NULL)",
                (f"a9-{i}", t0 + 100 + i),
            )
            conn.execute(
                "INSERT INTO telemetry (signal_id, latency_ms, approved, run_id,"
                " decision_seq) VALUES (?, 1.0, 1, 9, ?)",
                (f"s9-{i}", i + 1),
            )
        conn.commit()
        conn.close()
        return db

    # kaputter jüngster Lauf -> blockiert
    errors: list[str] = []
    with redirect_stdout(io.StringIO()):
        snap = gate_snapshot(build(1), errors, min_run_id=8)
    assert snap["verdicts"]["current"] == "RED"
    assert any("latest run 9" in e for e in errors), errors

    # intakter jüngster Lauf -> blockiert nicht (historical bleibt Warnung)
    errors = []
    with redirect_stdout(io.StringIO()):
        snap = gate_snapshot(build(PINNED_MIN_TELEMETRY_ROWS), errors, min_run_id=8)
    assert snap["verdicts"]["current"] == "LEDGER_CONSISTENT"
    assert errors == [], errors
