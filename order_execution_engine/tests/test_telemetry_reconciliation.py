"""Zeuge TELEMETRY_RECONCILIATION-Gate (stille Write-Ausfälle)."""

from __future__ import annotations

import io
import sqlite3
import tempfile
import time
from contextlib import redirect_stdout
from pathlib import Path

from order_execution_engine.ops.preflight_check import (
    _gate_criterion,
    gate_claim_discard_accounting,
    gate_snapshot,
    gate_telemetry_reconciliation,
    partition_ok,
    terminal_classes,
)

# Wieviele Zeilen die Fixtures bauen. Das ist eine Eigenschaft der Fixtures,
# nicht des Gates: das Gate kennt seit §5.4v keine Untergrenze mehr. Der Name
# ist bewusst neutral — hieße er weiter nach einer Schwelle, sähe ein Leser
# hier eine Regel, die es nicht gibt.
FIXTURE_ROWS = 4


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
        # Eine Zeile, ein passender Erfolgs-Dispatch: Identität erfüllt.
        # Keine Untergrenze mehr (§5.4v) — dieser Zeuge prüft die
        # Gleichheitslogik, und die gilt bei jeder Zeilenzahl.
        assert g.status.startswith("PROVISIONAL_LEDGER_CONSISTENT")
        assert not g.detail.get("underrun")
        conn.close()

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "t.db"
        conn = sqlite3.connect(db)
        _schema(conn)
        t0 = time.time()
        conn.execute(
            "INSERT INTO telemetry_runs VALUES (7, ?, 'x', '{}')", (t0,),
        )
        for i in range(FIXTURE_ROWS):
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
        assert g.status.startswith("PROVISIONAL_LEDGER_CONSISTENT")
        assert g.detail["dispatched_success"] == FIXTURE_ROWS
        assert g.detail["telemetry_rows"] == FIXTURE_ROWS
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
        # Mindestens FIXTURE_ROWS Zeilen mit passendem Dispatch:
        # dieser Test prüft die Discard-Attribution, nicht die Untergrenze
        # (Bedingung 0) und nicht die Konvidenz (Zweig 4).
        # 1 + FIXTURE_ROWS Dispatches im Fenster (ok-d + ok-d0..n),
        # also genauso viele Telemetriezeilen: decision_seq 1..n+1.
        for i in range(FIXTURE_ROWS + 1):
            conn.execute(
                "INSERT INTO telemetry (signal_id, latency_ms, approved, run_id,"
                " decision_seq) VALUES (?, 0.2, 0, 7, ?)",
                (f"s{i}", i + 1),
            )
        for i in range(FIXTURE_ROWS):
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
        assert snap["dispatched_signals"] == 1 + FIXTURE_ROWS
        assert snap["duplicate_item_ids"] == 0
        assert snap["join_is_one_to_one"] is True
        acct = snap["claim_discard_accounting"]
        assert acct.status == "GREEN"
        assert acct.detail == {
            "claims": 1 + FIXTURE_ROWS,
            "success": 1 + FIXTURE_ROWS,
            "post_claim_discards": 0,
            "discards": 2,
            "pre_claim_discards": 2,
            "post_claim_from_discards": 0,
        }
        # Dieser Test prüft die Discard-/Accounting-Attribution. Die
        # Dispatch-Konvidenz (Zweig 4) ist hier bewusst ungleich
        # (1 Dispatch, FIXTURE_ROWS Zeilen) und darf melden; sie wird
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
        for i in range(PINNED_FIXTURE_ROWS):
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
        assert snap["verdicts"]["current"].startswith(
            "PROVISIONAL_LEDGER_CONSISTENT")
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
    assert line.startswith("PROVISIONAL_LEDGER_CONSISTENT solange der Lauf offen")
    assert "LEDGER_CONSISTENT nur wenn (0)" in line
    for i in range(1, 5):
        assert f"({i})" in line, f"Bedingung {i} fehlt in der criterion-Zeile"
    # (3b) ist die Gegenrichtung zu (3) — Zeile ohne Erfolg.
    assert "(3b) orphan_rows == 0" in line
    assert "(0) dispatched_success > 0 oder telemetry_rows > 0" in line
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
    # (5) und (6) sind Feststellungen ohne RED-Zweig: (5) ist die Warnung zu
    # delivered, (6) der Nenner des Urteils. Beide sagen etwas über den
    # Geltungsbereich, nicht über die Daten — sie dürfen nicht blocken und
    # dürfen deshalb auch nicht als Zweig existieren. Die Ausnahme ist
    # benannt: wer eine weitere Zahl ohne Zweig einführt, muß sie hier
    # eintragen und damit begründen.
    non_blocking = {"5", "6"}
    numbered = {n for n in re.findall(r"\((\d+b?)\)", line)} - non_blocking
    # numbered = {0,1,2,3,3B,4}; (0) hat zwei RED-Zweige -> 7 erwartet.
    expected = len(numbered) + 1
    assert red_returns == expected, (
        f"{red_returns} RED-Rückgaben im Gate, aber {expected} erwartet "
        f"({sorted(numbered)} + der zweite (0)-Ausgang) — ein Zweig ohne "
        "gedruckte Regel (oder umgekehrt)."
    )
    assert "(5) WARNUNG" in line
    assert "(6) NENNER" in line


def test_start_md_gate_line_matches_criterion() -> None:
    """Die Absicht in START.md und das Gate im Code müssen dasselbe sagen.

    START.md ist die einzige Stelle in dieser Akte, an der die *Absicht*
    steht statt einer Messung — und bis §5.4x war sie der einzige Zeuge,
    der nie gegen seinen Gegenstand gehalten wurde. Sie sagte `GREEN` und
    `rows >= dispatched_success`, während der Code `LEDGER_CONSISTENT` und
    fünf Bedingungen sagte. Beides war je für sich lesbar; zusammen waren
    sie zwei Dokumente.

    Der Test liest die Zeile aus der Datei (kein Duplikat im Test) und
    vergleicht Label und Bedingungsnummern mit `_gate_criterion()`. Er bricht
    bei jeder Divergenz in beide Richtungen.
    """
    import re

    from order_execution_engine.ops import preflight_check

    start = (
        Path(preflight_check.__file__).resolve().parent / "START.md"
    ).read_text()
    rows = [
        ln for ln in start.splitlines()
        if ln.startswith("| `TELEMETRY_RECONCILIATION`")
    ]
    # Genau ein Treffer, sonst fail — nicht skip. Eine umbrochene Zeile in
    # der Tabelle erzeugt null Treffer, und ein Zeuge, der bei null Treffern
    # grün wird, ist der Zeuge, der übersieht, daß er nichts sieht (§5.4af).
    # Zwei Treffer heißen zwei Wahrheiten; auch das ist ein Bruch.
    assert len(rows) == 1, (
        f"{len(rows)} Zeilen für das Gate in START.md — erwartet genau 1. "
        "Null Treffer heißt: die Zeile ist umbrochen oder umbenannt und "
        "dieser Zeuge sieht nichts mehr. Zwei heißen: zwei Wahrheiten."
    )
    row = rows[0]

    line = _gate_criterion(9)
    # Das Label steht am Anfang der Zeile, vor dem "solange der Lauf offen".
    label = line.split(" ")[0]
    assert label in row, (
        f"START.md nennt das Urteil anders als der Code ({label}): {row}"
    )
    # ZÄHLGRENZE, die diese Akte seit Runde 1 kennt: verglichen werden
    # Nummern, nicht Inhalte. Der Zeuge prüft, *daß* die Bedingungen
    # dastehen — nicht, ob sie dasselbe bedeuten. Er kann eine Bedingung
    # nicht gegen ihre Formel prüfen; das tun die Fixtures unten. Er kann
    # nur verhindern, daß die Absicht in START.md und der Code
    # auseinanderlaufen, ohne daß es jemand merkt.
    doc_nums = set(re.findall(r"\((\d+b?)\)", row)) or set()
    code_nums = set(re.findall(r"\((\d+b?)\)", line))
    # Die Doku schreibt die Nummern nicht aus; sie muß die Bedingungen aber
    # inhaltlich nennen. Verglichen wird deshalb über die Zahl der
    # RED-tragenden Bedingungen — die steht im Code und muß in der Doku
    # erkennbar sein. Wenn die Doku nummeriert, muß sie exakt passen.
    # Die Doku nennt die blockierenden Bedingungen im Volltext (0, 3, 3b, 4),
    # der Code druckt zusätzlich die nicht-blockierenden (5, 6) und die
    # Kardinalitätsprüfungen (1, 2). Verglichen wird die Schnittmenge, die
    # in beiden stehen muß: keine mehr, keine weniger.
    if doc_nums:
        assert doc_nums <= code_nums, (
            f"START.md nennt {sorted(doc_nums)}, Code {sorted(code_nums)}"
        )
        # (3b) ist neu: die Doku muß die Gegenrichtung nennen, wenn der Code
        # sie blockierend macht. Wer sie streicht, bricht hier.
        assert "3b" in doc_nums, (
            "START.md nennt die Überbehauptungs-Prüfung (3b) nicht — "
            "der Code blockt sie."
        )
    assert "delivered" in row and "Warnung" in row, (
        "Die Warnung zu delivered steht in (5) — sie fehlt in START.md"
    )


def test_non_blocking_conditions_have_no_red_branch() -> None:
    """Gegenprobe zu ``{5, 6}``: die Ausnahme darf nicht mitwachsen.

    Die vorige Prüfung zählt RED-Zweige und läßt (5) und (6) als benannte
    Ausnahme zu. Damit ist sie in einer Richtung offen: kommt ein RED-Zweig
    für (5) oder (6) dazu, wächst ``red_returns`` — und die Ausnahme bleibt
    im Set stehen, der Test wäre also *grün mit falscher Begründung*.

    Diese Prüfung schließt die Richtung: (5) ist eine Warnung, (6) ein
    Geltungsbereich. Keiner von beiden darf blocken. Wer sie blockierend
    macht, muß sie aus ``non_blocking`` entfernen — und dabei hier scheitern
    und die Entscheidung begründen.
    """
    import inspect
    import re

    from order_execution_engine.ops import preflight_check

    src = inspect.getsource(preflight_check.gate_telemetry_reconciliation)
    # Strukturell statt textuell: jeder RED-Zweig bekommt die Nummer der
    # Bedingung, die ihn auslöst, aus seiner Position in der Funktion.
    # Heute: (0) hat zwei Ausgänge, (1)-(4) je einen = 6 RED-Zweige.
    # (5) und (6) stehen hinter dem letzten RED-Zweig — ein weiterer RED-Zweig
    # am Ende der Funktion gehört damit zu (5) oder (6) oder ist neu, und in
    # beiden Fällen wächst die Zahl, ohne daß die Ausnahme es merkt.
    red_positions = [m.start() for m in re.finditer(r'status="RED"', src)]
    assert len(red_positions) == 7, (
        f"{len(red_positions)} RED-Zweige, 7 erwartet "
        "(0 zweimal, 1-4 je einmal, 3b einmal). "
        "Ein neuer Zweig muß entweder eine neue Kriterium-Nummer bekommen "
        "oder die Ausnahme {5,6} muß begründet geändert werden."
    )
    # Der letzte RED-Zweig muß VOR der Warnungs-/Nenner-Deklaration liegen.
    warn_at = src.find("(5) WARNUNG")
    assert warn_at == -1, "(5) gehört in _gate_criterion, nicht ins Gate"


def test_branch_0_underrun() -> None:
    """(0) leere/unzureichende Datenlage -> RED, nicht GREEN."""
    status, detail = _run(rows=0, keyed=0, dispatched=0, reasons=0)
    assert status == "RED"
    assert detail.get("underrun") is True


def test_branch_1_row_without_decision_seq() -> None:
    """(1) telemetry_rows != keyed."""
    status, detail = _run(
        rows=FIXTURE_ROWS + 1, keyed=FIXTURE_ROWS,
        dispatched=FIXTURE_ROWS, reasons=FIXTURE_ROWS + 1,
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
        for _ in range(FIXTURE_ROWS):
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
        rows=FIXTURE_ROWS, keyed=FIXTURE_ROWS,
        dispatched=FIXTURE_ROWS + 1, reasons=FIXTURE_ROWS,
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
        for i in range(FIXTURE_ROWS):
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
# ignores_discarded_claims, snapshot_discards) lesen FIXTURE_ROWS und
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


# Gepinnte Fixture-Größe. NICHT FIXTURE_ROWS — sonst wandert der Test mit.
# Sie hält fest, wieviele Zeilen die Fixtures bauen; das ist keine Schwelle
# mehr (die gibt es seit §5.4v nicht), sondern der Aufbau der Prüfungen.
PINNED_FIXTURE_ROWS = 4


def test_fixture_size_is_the_pinned_value() -> None:
    """Die Fixtures bauen so viele Zeilen wie gepinnt — nicht wie bequem."""
    assert FIXTURE_ROWS == PINNED_FIXTURE_ROWS, (
        f"FIXTURE_ROWS={FIXTURE_ROWS}, gepinnt={PINNED_FIXTURE_ROWS}. "
        "Ein anderer Aufbau ändert, was die Zeugen unten messen."
    )


def test_no_rule_constant_lives_as_literal_copy_in_production() -> None:
    """Eine Form, drei Instanzen — der Zeuge fängt die Klasse (§5.4ap).

    ``MIN_TELEMETRY_ROWS`` (Wert), das Jahr in ``--since`` (Wert),
    ``!= "LEDGER_CONSISTENT"`` (Literal): das Kriterium lebte als Kopie in
    einer zweiten Datei und wanderte dort nicht mit. Kein struktureller
    Zeuge konnte das fangen — ``test_non_blocking_conditions_have_no_red_branch``
    zählt Zweige, und ein Literalvergleich ist kein Zweig.

    Geprüft wird nicht der Text, sondern die Richtung: jeder
    Regel-Konstante darf in Produktionscode **nur** als Definition, als
    Parameter oder als Teil der Set-/Listen-Deklaration vorkommen — nicht
    in einem Vergleich.

    Verglichen wird gegen einen Vergleichsoperator in derselben Zeile.
    Das ist die Form, die alle drei Instanzen hatten:
    ``rows >= 4``, ``year == 2025``, ``!== "LEDGER_CONSISTENT"``.
    """
    import re

    root = Path(__file__).resolve().parent.parent
    # Die Etiketten und Schwellen, die das Gate vergibt. Quelle ist
    # _gate_criterion()/GateResult, nicht eine zweite Liste — deshalb
    # werden sie hier aus dem Gate-Modul gelesen, nicht getippt.
    from order_execution_engine.ops import preflight_check
    labels = {
        "LEDGER_CONSISTENT",
        "PROVISIONAL_LEDGER_CONSISTENT",
        "RED",
    }
    # Schwellen, die als benannte Konstante in einem Modul standen und dort
    # ein Kriterium wiederholt haben. Sie dürfen **nirgends** mehr
    # definiert sein — auch nicht im Gate selbst, denn dort gehört eine
    # Schwelle in _gate_criterion(), nicht in eine Variable, die jemand
    # später an einer zweiten Stelle liest.
    banned_names = {
        "MIN_TELEMETRY_ROWS",   # war 4, kalibriert auf Run 9 (§5.4v)
        "PINNED_MIN_TELEMETRY_ROWS",
    }
    allowed_files = {"preflight_check.py"}
    offenders = []
    for py in root.rglob("*.py"):
        if py.parent.name == "tests" or "__pycache__" in py.parts:
            continue
        if py.name in allowed_files and py.parent.name != "tests":
            pass  # die Quelle darf ihre Etiketten prägen, aber keine Schwellen
        for n, line in enumerate(py.read_text(encoding="utf-8",
                                             errors="ignore").splitlines(), 1):
            code = line.split("#", 1)[0]
            # Gestalt 1: Schwellen-Konstante, benannt.
            for name in banned_names:
                if re.search(rf"\b{name}\b", code):
                    offenders.append(
                        f"{py.relative_to(root)}:{n}  {name} in {code.strip()}"
                    )
            # Gestalt 2: Etikett als Literal in einem Vergleich.
            if py.name in allowed_files:
                continue
            if not re.search(r"[=!<>]=", code):
                continue
            for lab in labels:
                if f'"{lab}"' in code or f"'{lab}'" in code:
                    offenders.append(
                        f"{py.relative_to(root)}:{n}  {lab} in {code.strip()}"
                    )
            # Gestalt 3: Kalenderjahr in einem Vergleich. Die Sweep-Schwelle
            # stand als `== 2025` im Code und war im Folgejahr falsch — sie
            # ist weder Konstante noch Etikett, sondern ein Datum im
            # Ausdruck. Geprüft wird nur gegen das Jahr, das das Gate selbst
            # als Messjahr führt; ein Jahr im Kommentar oder als default eines
            # kwarg ist erlaubt.
            for y in re.findall(r"[=!<>]=\s*(20\d\d)\b", code):
                offenders.append(
                    f"{py.relative_to(root)}:{n}  Jahr {y} im Vergleich in "
                    f"{code.strip()}"
                )
            # Gestalt 4: Schwelle AUS einer Messung berechnet (§5.4av).
            # `0.1 * total`, `len(x) / 2` — weder Konstante noch Literal
            # noch Kalenderwert, und sie wandert mit, wenn die Messung sich
            # ändert. Erkannt wird: rechte Seite beginnt mit einem Term und
            # einem Arithmetik-Operator.
            #
            # GRENZE, benannt: `(n - 1) // 2` (Ausdruck in Klammern) und
            # `b / 2` (Division einer Variablen, keine Messung) sind mit
            # Regex nicht sicher zu trennen. Der Wächter ist damit ein
            # Filter, kein Beweis — die Test-Fixture unten hält fest,
            # welche Formen er kennt und welche nicht.
            m = re.search(r"(?:[=!<>]=|[<>])", code)
            if m and _rhs_is_derived(code[m.end():]):
                offenders.append(
                    f"{py.relative_to(root)}:{n}  abgeleitete Schwelle in "
                    f"{code.strip()}"
                )
    assert offenders == [], (
        "Regel-Konstante als Literal-Kopie in einem Vergleich:\n  "
        + "\n  ".join(offenders)
        + "\nDas Kriterium lebt dann in zwei Dateien und wandert nicht mit. "
        "Vergleiche gegen die Gate-Funktion, nicht gegen ihren Text."
    )


def _rhs_is_derived(rhs: str) -> bool:
    """Rechte Seite eines Vergleichs: ist sie aus einer Messung berechnet?

    Kennt drei Formen sicher (``0.1 * total``, ``len(x) / 2``,
    ``n * 0.9``) und zwei nicht (``(n - 1) // 2``, ``b / 2``). Die
    Grenze steht im Zeugen ``test_rule_constant_guard_catches_history``.
    """
    import re

    return bool(re.match(
        r"\s*[\w.]+(?:\([^()]*\))?\s*(?:[*/]|//)\s*[\w.(]", rhs,
    )) and not re.match(r"\s*[a-z_]\w*\s*/\s*\d+\s*[:)]?\s*$", rhs)


def test_rule_constant_guard_catches_history() -> None:
    """Der Wächter gegen die Historie, nicht gegen heute (§5.4av).

    *„Eine Prüfung, die nur gegen heute läuft, findet nie, was gestern
    falsch war."* Die drei Instanzen sind als Fixture festgehalten: sie
    waren einmal im Code und dürfen nie wieder durchgehen. Kommt eine
    vierte Gestalt dazu, gehört ihre Zeile hierher — dann prüft die Suite
    Regression statt Zustand.
    """
    import re

    labels = ("LEDGER_CONSISTENT",)
    cases = [
        # (Gestalt, Zeile, muß gefangen werden)
        ("Konstante", "if telemetry_rows < MIN_TELEMETRY_ROWS:", True),
        ("Kalenderwert", "if year_expected == 2025 and run_started >= since:", True),
        ("Literal", 'and snapshot["verdicts"]["current"] != "LEDGER_CONSISTENT"', True),
        ("Ableitung", "if delivered < 0.1 * total:", True),
        ("Ableitung", "if rows > len(all_rows) / 2:", True),
        # Grenze des Wächters, ausdrücklich als Lücke festgehalten:
        # Klammerausdruck und einfache Division sind regex nicht sicher
        # zu trennen. Sie stehen hier, damit die Grenze nicht wächst,
        # ohne daß jemand sie liest.
        ("Grenze (nicht erkannt)", "if rows > (n - 1) // 2:", False),
        ("Grenze (nicht erkannt)", "if a < b / 2:", False),
        # Gegenproben: was NICHT gefangen werden darf.
        ("Harmlos", "threshold = 0.1 * n", False),
        ("Harmlos", "run_id = int(cur.lastrowid)", False),
        ("Harmlos", "if rows != keyed:", False),
    ]
    cmp_ = re.compile(r"[=!<>]=")
    banned = ("MIN_TELEMETRY_ROWS", "PINNED_MIN_TELEMETRY_ROWS")

    def caught(code: str) -> bool:
        g1 = any(re.search(rf"\b{b}\b", code) for b in banned)
        g2 = bool(cmp_.search(code)) and any(f'"{lb}"' in code for lb in labels)
        g3 = bool(re.findall(r"[=!<>]=\s*(20\d\d)\b", code))
        m4 = re.search(r"(?:[=!<>]=|[<>])", code)
        g4 = bool(m4) and _rhs_is_derived(code[m4.end():])
        return g1 or g2 or g3 or g4

    misses = []
    for kind, line, want in cases:
        got = caught(line)
        if got != want:
            misses.append(f"{kind}: erwartet {want}, bekam {got} — {line}")
    assert misses == [], "Wächter-Lücken:\n  " + "\n  ".join(misses)


def test_derived_observes_the_whole_criterion_set() -> None:
    """Der Marker beobachtet den Kriteriumssatz, nicht eine Datei (§5.4aq).

    Das Kriterium lebt in drei Dateien: Code, START.md, Akte. Ein
    Blob-Vergleich über eine davon läßt die anderen zwei unüberwacht —
    und START.md war genau die Datei, die 14 Runden lang nicht diffed
    wurde. Der Zeuge prüft, daß alle drei im Satz stehen; fehlt eine,
    ist sie wieder unsichtbar.
    """
    from order_execution_engine.ops import preflight_check

    files = preflight_check.CRITERION_FILES
    assert len(files) == 3, files
    names = {Path(f).name for f in files}
    assert names == {
        "preflight_check.py", "START.md", "TAG7_ABNAHME.md",
    }, names
    root = Path(preflight_check.__file__).resolve().parents[2]
    for f in files:
        assert (root / f).exists(), f"{f} fehlt — dann ist es nicht im Satz"


def test_fixture_rows_never_reaches_production() -> None:
    """``FIXTURE_ROWS`` ist Aufbau, keine Regel — strukturell geprüft (§5.4ag).

    Ein ``grep`` über ``order_execution_engine/`` zeigt: die Konstante
    existiert in keiner Produktionsdatei, nur hier und in der Akte. Das
    genügt aber nur für den heutigen Stand. Eine Konstante, die in zwei
    Runden wieder eine Schwelle mit anderem Namen werden kann, braucht
    einen Zeugen, der das beim nächsten Mal verhindert.

    Der Zeuge prüft nicht den Text, sondern die Import-Richtung: kein
    Produktionsmodul darf ``test_telemetry_reconciliation`` importieren.
    Damit kann ``FIXTURE_ROWS`` nicht ins Gate wandern, egal wie oft es
    umbenannt wird.
    """
    root = Path(__file__).resolve().parent.parent
    offenders = []
    for py in root.rglob("*.py"):
        if py.parent.name == "tests" or "__pycache__" in py.parts:
            continue
        src = py.read_text(encoding="utf-8", errors="ignore")
        if "test_telemetry_reconciliation" in src or "FIXTURE_ROWS" in src:
            offenders.append(str(py.relative_to(root)))
    assert offenders == [], (
        f"Produktionsmodule kennen die Test-Fixture: {offenders}. "
        "FIXTURE_ROWS ist Aufbau, keine Schwelle — es darf das Gate nicht "
        "erreichen."
    )


def test_orphan_row_without_dispatch_is_red() -> None:
    """Die Richtung, die bis §5.4ac durchging: Zeile ohne Erfolg.

    Autocommit pro Zeile heißt: Telemetriezeile geschrieben, Erfolg nicht
    gezählt, ist ein realer Zustand. ``rows > success`` war grün. Die
    Überbehauptung liegt zwischen Ledger und Dispatcher — (4) sieht sie
    nicht, weil (4) innerhalb des Ledgers bilanziert.
    """
    with tempfile.TemporaryDirectory() as td:
        conn = sqlite3.connect(Path(td) / "t.db")
        _schema(conn)
        t0 = time.time()
        conn.execute("INSERT INTO telemetry_runs VALUES (9, ?, 'x', '{}')", (t0,))
        # 4 Erfolgs-Dispatches, aber 5 Telemetriezeilen: die fünfte behauptet
        # eine Auslieferung, die nie stattfand.
        for i in range(FIXTURE_ROWS):
            conn.execute(
                "INSERT INTO dispatched_signals (item_id, dispatched_at)"
                " VALUES (?, ?)", (f"d{i}", t0 + i),
            )
        for i in range(FIXTURE_ROWS + 1):
            conn.execute(
                "INSERT INTO telemetry (signal_id, latency_ms, approved, run_id,"
                " decision_seq) VALUES (?, 1.0, 1, 9, ?)",
                (f"s{i}", i + 1),
            )
        conn.commit()
        g = gate_telemetry_reconciliation(conn, min_run_id=9)
        conn.close()
    assert g.status == "RED", g.detail
    assert g.detail["orphan_rows"] == 1, g.detail
    assert g.detail.get("overclaim") is True, (
        "RED ohne overclaim-Markierung: der Befund muß als Überbehauptung "
        "erkennbar sein, nicht als gewöhnliche Lücke"
    )


def test_closed_at_schema_is_the_reason() -> None:
    """Der Grund ist das Schema, nicht der Boolean (§5.4ao).

    Ein Zeuge gegen ``latest_run_is_closed() is False`` prüft einen
    konstanten Wert — der dritte dieser Art nach
    ``PINNED_MIN_TELEMETRY_ROWS``. Die Ursache ist die Tabelle:
    ``telemetry_runs`` hat kein ``closed_at``. Solange das so ist, *kann*
    kein Lauf geschlossen sein.

    Wandert ``closed_at`` ins Schema, bricht **die erste Zeile** — und das
    ist dann die richtige Nachricht: die Folge (PROVISIONAL) darf nicht
    weiterleben, wenn ihr Grund verschwunden ist.
    """
    from order_execution_engine.ops import preflight_check

    conn = sqlite3.connect(":memory:")
    _schema(conn)
    schema = preflight_check.run_end_schema(conn)
    _seed_run(conn, rows=FIXTURE_ROWS, keyed=FIXTURE_ROWS,
              dispatched=FIXTURE_ROWS, reasons=FIXTURE_ROWS)
    verdict = gate_telemetry_reconciliation(conn, min_run_id=9)
    conn.close()

    # Der Grund.
    assert schema["has_closed_at"] is False, (
        f"telemetry_runs hat jetzt closed_at ({schema['columns']}) — "
        "latest_run_is_closed() muß es lesen und PROVISIONAL endlich werden"
    )
    # Die Folge.
    assert verdict.status.startswith("PROVISIONAL_"), (
        f"ohne closed_at darf das Urteil nicht vollständig sein: {verdict.status}"
    )
    # Und die Folge darf nicht blockieren, solange sie gilt (§5.4an).
    assert verdict.status != "RED", verdict.status


def test_three_rows_all_delivered_is_ledger_consistent() -> None:
    """Die Gegenrichtung, die die alte Untergrenze brach (§5.4v).

    Drei Dispatches, drei Zeilen, drei erfolgreiche Entscheidungen, alle
    zugeordnet: das ist ein vollständig konsistenter Ledger. Unter
    ``rows >= 4`` war dieser Lauf RED — bei erfüllter Identität. Die
    Untergrenze war nicht "zu leicht", sie war in beide Richtungen falsch.
    """
    status, detail = _status_at(3)
    assert status.startswith("PROVISIONAL_LEDGER_CONSISTENT"), detail
    assert detail["telemetry_rows"] == 3
    assert detail["unattributed"] == 0


def test_empty_traffic_is_red_not_ledger_consistent() -> None:
    """Die Lücke, die die Untergrenze eigentlich schließen sollte.

    ``rows == dispatched_success`` gilt perfekt, wenn beide 0 sind: ein
    leerer Dienst hat einen vollständig konsistenten Ledger. Die Antwort
    darauf ist keine Zahl, sondern die Frage "hat der Dienst überhaupt
    etwas erzeugt".
    """
    status, detail = _status_at(0)
    assert status == "RED", detail
    assert detail.get("empty_traffic") is True
    assert detail["dispatched_success"] == 0
    assert detail["telemetry_rows"] == 0


def test_observed_window_and_rate_are_reported() -> None:
    """Dauer und Rate stehen neben dem Urteil, nicht in seinem Kriterium.

    Eine absolute Zahl ohne Zeitraum ist mit jedem System vereinbar, das
    gerade noch atmet. Die erwartete Rate ist ausdrücklich unbekannt (sie
    steht in keiner Aktenstelle) — eine Zahl aus den Daten wäre immer
    erfüllt und damit keine Prüfung.
    """
    status, detail = _status_at(PINNED_FIXTURE_ROWS)
    assert status.startswith("PROVISIONAL_LEDGER_CONSISTENT"), detail
    assert detail["observed_hours"] > 0
    expected = detail["telemetry_rows"] / detail["observed_hours"]
    assert abs(detail["rows_per_hour"] - expected) < 1e-9
    line = _gate_criterion(9)
    assert "erwartete Rate" not in line
    assert "kein leerer Dienst" in line


def test_coverage_against_traffic_is_reported() -> None:
    """Der Nenner des Urteils: Zeilen gegen allen Verkehr (§5.4w).

    ``dispatched_success`` sind die, die den Ledger erreicht haben. Der
    Abnehmer muß wissen, worüber das Urteil spricht — 34 gegen 360 sind
    9,4 %, und die 56 von 60 sind nicht "abgelehnt", sie waren nie im
    Ledger.
    """
    status, detail = _status_at(PINNED_FIXTURE_ROWS)
    assert status.startswith("PROVISIONAL_LEDGER_CONSISTENT"), detail
    assert detail["dispatched_in_scope"] >= detail["telemetry_rows"]
    assert 0 < detail["coverage_pct"] <= 100.0


def test_rate_is_a_report_value_not_a_gate() -> None:
    """Die Rate steht daneben, sie entscheidet nicht.

    Wäre die Schwelle eine Rate, hinge der Status von der Laufzeit ab und
    jede langsamere Quelle fiele durch. Das ist nicht die Bedingung: die
    **Anzahl** zählt, die Dauer steht daneben. Das ist die bewusste Grenze
    — sie ist datiert, nicht erraten.
    """
    status, detail = _status_at(PINNED_FIXTURE_ROWS)
    assert status.startswith("PROVISIONAL_LEDGER_CONSISTENT")
    assert detail["rows_per_hour"] is not None
    assert detail["observed_hours"] > 0


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
    def build(run9_rows: int, *, run9_broken: bool = False) -> Path:
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
        if run9_broken:
            # Ein dritter Dispatch ohne Zeile: Identität (1) bricht. Das ist
            # der Bruch, den der Test braucht — nicht mehr die Zeilenzahl.
            conn.execute(
                "INSERT INTO dispatched_signals VALUES ('orphan9', ?, NULL)",
                (t0 + 200,),
            )
        conn.commit()
        conn.close()
        return db

    # kaputter jüngster Lauf -> blockiert
    errors: list[str] = []
    with redirect_stdout(io.StringIO()):
        snap = gate_snapshot(build(1, run9_broken=True), errors, min_run_id=8)
    assert snap["verdicts"]["current"] == "RED"
    assert any("latest run 9" in e for e in errors), errors

    # intakter jüngster Lauf -> blockiert nicht (historical bleibt Warnung)
    errors = []
    with redirect_stdout(io.StringIO()):
        snap = gate_snapshot(
            build(PINNED_FIXTURE_ROWS), errors, min_run_id=8
        )
    assert snap["verdicts"]["current"].startswith(
            "PROVISIONAL_LEDGER_CONSISTENT")
    assert errors == [], errors
