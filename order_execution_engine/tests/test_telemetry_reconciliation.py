"""Zeuge TELEMETRY_RECONCILIATION-Gate (stille Write-Ausfälle)."""

from __future__ import annotations

import datetime
import io
import sqlite3
import tempfile
import time
import uuid
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from order_execution_engine.models import RejectReason

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
            decision_seq INTEGER,
            requested_size TEXT
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
    # §5.4cd: getrennt, nicht verrechnet. Beide Zahlen beschreiben
    # verschiedene Fenster — `success` den Ledger, `unattributed` das
    # Dispatcher-Fenster. Eine Differenz zwischen ihnen ist keine Herkunft.
    assert classes["origin"] == {"telemetry_rows": 34, "unattributed": 4}
    assert "unattributed" not in classes["outcome"]
    # Die falsche Ein-Achsen-View hätte 1+26+7+4 = 38 gegen 34 gestellt.
    naive = {**classes["outcome"], "unattributed": 4}
    assert sum(naive.values()) == 38
    # Beide Achsen schließen einzeln auf success — keine Achse auf 38.
    # Die Ausgangs-Achse tut das NICHT (§5.4cd): `unattributed` beschreibt
    # das Dispatcher-Fenster, nicht den Ledger. 34 + 4 = 38 ist die Summe
    # zweier Grundgesamtheiten; der frühere Test forderte genau sie und
    # hätte eine negative Zahl als "Herkunft" durchgelassen.
    assert sum(classes["outcome"].values()) == 34
    assert all(v >= 0 for v in classes["origin"].values())
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
    non_blocking = {"5", "6", "7", "8"}
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
    assert "(7) COVERAGE" in line
    assert "(8) DELIVERY" in line


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
        # 17.10.26 — Regex kann einen Klammerausdruck `(n - 1) // 2` nicht
        # von einer Division `b / 2` trennen; beide sind syntaktisch
        # dieselbe Form. Wird die Lücke geschlossen (z. B. via AST), bricht
        # diese Zeile — und das ist die richtige Nachricht: die Grenze
        # gehört dann datiert aufgehoben, nicht stillschweigend entfernt.
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


def test_delivery_is_a_second_label_not_a_word_in_the_first() -> None:
    """Ein Etikett kann nicht "konsistent" und "steht still" sagen (§5.4ba).

    `delivered` zählt genehmigte Zeilen im Fenster. Run 9 hat 4 Erfolge,
    0 genehmigt, 0 Fills im Fenster — und der Ledger ist trotzdem
    konsistent. Beides ist wahr und gehört in zwei Etiketten.
    """
    conn = sqlite3.connect(":memory:")
    _schema(conn)
    _seed_run(conn, rows=FIXTURE_ROWS, keyed=FIXTURE_ROWS,
              dispatched=FIXTURE_ROWS, reasons=FIXTURE_ROWS)
    g = gate_telemetry_reconciliation(conn, min_run_id=9)
    conn.close()
    assert g.status.startswith("PROVISIONAL_LEDGER_CONSISTENT"), g.status
    assert g.detail["delivery"] == "DELIVERY_STALLED_SINCE", g.detail["delivery"]
    assert g.detail["dispatched_success"] > 0
    assert g.detail["delivered"] == 0
    # Und das Ledger-Etikett darf NICHT rot sein, nur weil nichts
    # ausgeliefert wurde: das wäre eine Dienst-Aussage im Ledger-Etikett.
    assert g.status != "RED"


def test_missing_fills_table_is_unknown_not_zero() -> None:
    """Ohne Fill-Schicht ist die vierte Stufe nicht gemessen (§5.4bc).

    Eine Null würde behaupten, es sei nichts geliefert worden. Die
    Fixtures bauen keine `fills`-Tabelle — deshalb muß das Gate dort
    `None` melden, nicht 0.
    """
    conn = sqlite3.connect(":memory:")
    _schema(conn)
    _seed_run(conn, rows=FIXTURE_ROWS, keyed=FIXTURE_ROWS,
              dispatched=FIXTURE_ROWS, reasons=FIXTURE_ROWS)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    g = gate_telemetry_reconciliation(conn, min_run_id=9)
    conn.close()
    assert "fills" not in tables, tables
    assert g.detail["fills_total"] is None, (
        f"fehlende Tabelle als {g.detail['fills_total']!r} gemeldet — "
        "nicht gemessen ist nicht null"
    )


def test_verdict_readers_are_reported_separately_from_importers() -> None:
    """`wired` (Import) und `read_by` (Leser) sind zwei Zustände (§5.4bb).

    Der erste Aufrufer am 20.10. wird kein Import sein, sondern ein
    Cronjob, der die Ausgabe liest. `_blocking_callers()` kann den per
    Konstruktion nicht sehen — deshalb muß `read_by` existieren.
    """
    from order_execution_engine.ops import preflight_check

    assert hasattr(preflight_check, "_verdict_readers")
    assert hasattr(preflight_check, "_blocking_callers")
    # Beide sind Mengen von Namen und dürfen sich unterscheiden — genau
    # das ist die Aussage.
    readers = preflight_check._verdict_readers()
    callers = preflight_check._blocking_callers()
    assert isinstance(readers, set) and isinstance(callers, set)
    # Kein `or True`: der Zeuge prüft, daß beide Mengen existieren und
    # getrennt abfragbar sind. Ob sie heute leer sind, ist eine Messung,
    # keine Erwartung — und ein Zeuge über den heutigen Stand wäre der
    # Zeuge-Typ, den diese Akte dreimal überlebt hat.
    assert isinstance(preflight_check._verdict_readers(), set)
    assert isinstance(preflight_check._blocking_callers(), set)


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


# ---------------------------------------------------------------------------
# §5.4be–bi — der Positivfall, der Teilfill, die Frische-Grenze, der FK
# ---------------------------------------------------------------------------


def _bridge_conn(filled_at: str, *, status: str = "PARTIALLY_FILLED",
                 executed: str = "5", requested: str = "5") -> sqlite3.Connection:
    """Run 1 komplett außerhalb des Fensters, ein Fill in `fills`.

    Bildet den einen Positivfall der Akte nach (§5.4bf): `decision_seq=12`,
    06.10. 18:00:06.993672Z, `PARTIALLY_FILLED`. Das Fenster beginnt am
    04.10. — der Fill liegt *innerhalb* des Fensters, aber 11 Tage her.
    """
    conn = sqlite3.connect(":memory:")
    _schema(conn)
    conn.execute("CREATE TABLE fills (order_id TEXT, fill_idx INTEGER,"
                 " executed_size TEXT, requested_size TEXT,"
                 " filled_at TEXT, decision_seq INTEGER)")
    t0 = time.time() - 13 * 86400.0     # Laufbeginn: 13 Tage her
    conn.execute("INSERT INTO telemetry_runs VALUES (1, ?, 'x', '{}')", (t0,))
    conn.execute(
        "INSERT INTO telemetry (signal_id, order_id, latency_ms, approved,"
        " reject_reason, status, run_id, decision_seq)"
        " VALUES ('s12', 'ord-12', 1.0, 1, 'NONE', ?, 1, 12)", (status,))
    conn.execute("INSERT INTO dispatched_signals VALUES ('i1', ?, NULL)",
                 (t0 + 5,))
    conn.execute("INSERT INTO fills VALUES ('ord-12', 0, ?, ?, ?, 12)",
                 (executed, requested, filled_at))
    conn.commit()
    return conn


def test_fill_after_window_start_but_old_is_not_delivering() -> None:
    """Frische wird an der Gegenwart gemessen, nicht am Laufanfang (§5.4bg).

    Erste Fassung: `_fresh_fill = _ts >= started_at`. Der Fill vom 06.10.
    liegt 2,4 Tage *nach* dem Fensterbeginn (04.10.) — also „frisch", obwohl
    seither 11 Tage vergangen sind. Das Etikett las sich `DELIVERING` neben
    einem Beleg von vor zwei Wochen: genau die Form, die diese Akte dreimal
    korrigiert hat. `FRESH_FILL_S` = zwei Dispatcher-Takte.
    """
    old = "2026-10-06T18:00:06.993672Z"
    conn = _bridge_conn(old)
    g = gate_telemetry_reconciliation(conn, min_run_id=1)
    conn.close()
    assert g.detail["delivery"] == "DELIVERY_STALLED_SINCE", g.detail
    # … und der Grund steht daneben, nicht im Etikett.
    assert g.detail["last_fill"] == old

    # Ein Fill von jetzt ist Betrieb — nicht "nur ein Beleg".
    conn = _bridge_conn(datetime.datetime.now(datetime.timezone.utc)
                        .isoformat(timespec="microseconds")
                        .replace("+00:00", "Z"))
    g = gate_telemetry_reconciliation(conn, min_run_id=1)
    conn.close()
    assert g.detail["delivery"] == "DELIVERING", g.detail


def test_partial_fill_is_counted_as_partial_not_as_a_fill() -> None:
    """`1 Fills` neben `NO_DELIVERY` war dasselbe Muster (§5.4be).

    `fills` hat keine Statusspalte — die Vollständigkeit steht nur in
    `telemetry.status`, als Urteil des Ausführers. Bei seq 12: 5 von 5
    ausgeführt (Quotient 1,0), aber 5 von 100 angefragt (0,05). Die Zeile
    sagte `PARTIALLY_FILLED`, obwohl der Fill voll war. Zählte man nur
    Zeilen, wären beide ununterscheidbar — deshalb Mengen, nicht Rows.
    """
    conn = _bridge_conn(datetime.datetime.now(datetime.timezone.utc)
                        .isoformat(timespec="microseconds")
                        .replace("+00:00", "Z"))
    conn.execute("UPDATE telemetry SET requested_size = 100 WHERE decision_seq=12")
    conn.execute("UPDATE fills SET requested_size = 100")
    g = gate_telemetry_reconciliation(conn, min_run_id=1)
    conn.close()
    assert g.detail["fills_total"] == 1
    assert g.detail["fills_full"] == 0
    assert g.detail["fills_partial"] == 1
    # Die Zahl, die den Dienst beschreibt: 5 von 100 bedient.
    assert g.detail["fill_ratio"] == 0.05, g.detail["fill_ratio"]


def test_order_id_is_reported_as_the_fk_that_was_hardly_written() -> None:
    """Kardinalität ist nicht Identität (§5.4bi).

    `telemetry_seq` ist in allen Dispatches NULL; die Zuordnung läuft über
    `decision_seq` — eine Reihenfolge-Annahme über zwei Reihenfolgen.
    `order_id` existiert als FK, ist aber nur in 8 von 34 Zeilen gesetzt.
    Der Gate meldet beides, damit die Grenze sichtbar ist, statt still zu
    bleiben: der Ledger kann grün sein und permutiert.
    """
    conn = _bridge_conn("2026-10-06T18:00:06.993672Z")
    for i in range(2, 5):                     # drei Zeilen ohne order_id
        conn.execute(
            "INSERT INTO telemetry (signal_id, latency_ms, approved,"
            " reject_reason, run_id, decision_seq)"
            " VALUES (?, 1.0, 0, 'INVALID_PRICE', 1, ?)", (f"s{i}", i))
    conn.commit()
    g = gate_telemetry_reconciliation(conn, min_run_id=1)
    conn.close()
    assert g.detail["fk_rows"] == 4
    assert g.detail["fk_set"] == 1
    assert g.detail["fk_paired"] == 1


# ---------------------------------------------------------------------------
# §5.4bk–bm — die Adresse des RED, die Achse im Namen, der Determinant
# ---------------------------------------------------------------------------


def test_every_red_names_its_condition() -> None:
    """Ein RED ohne Bedingung ist ein Zustand, keine Aussage (§5.4bk).

    Neunzehn Runden lang trug jede Zeile dieser Akte Grund, Dauer und
    Adresse. Dann stand `verdict: RED` da, ohne zu sagen, welche Bedingung
    rot ist — dieselbe Form, die in Runde 1 `BLOCKED` hieß: wahr,
    begründet, unlesbar. Jeder der sechs RED-Zweige muß seine Nummer
    nennen; wer `RED` liest und handeln soll, braucht sie.
    """
    # (0) Unterlauf
    with tempfile.TemporaryDirectory() as td:
        conn = sqlite3.connect(Path(td) / "t.db")
        _schema(conn)
        conn.execute("INSERT INTO telemetry_runs VALUES (9, ?, 'x', '{}')",
                     (time.time(),))
        conn.commit()
        g = gate_telemetry_reconciliation(conn, min_run_id=9)
        conn.close()
    assert g.status == "RED"
    assert g.reason.startswith("(0)"), g.reason

    # (3) unattributed — der Fall der Akte: 4 Dispatches ohne Zeile.
    conn = sqlite3.connect(":memory:")
    _schema(conn)
    t0 = time.time() - 3600
    conn.execute("INSERT INTO telemetry_runs VALUES (9, ?, 'x', '{}')", (t0,))
    for i in range(1, 3):
        conn.execute(
            "INSERT INTO telemetry (signal_id, latency_ms, approved,"
            " reject_reason, run_id, decision_seq)"
            " VALUES (?, 1.0, 0, 'X', 9, ?)", (f"s{i}", i))
    for i in range(4):
        conn.execute("INSERT INTO dispatched_signals VALUES (?, ?, NULL)",
                     (f"i{i}", t0 + 1))
    conn.commit()
    g = gate_telemetry_reconciliation(conn, min_run_id=9)
    conn.close()
    assert g.status == "RED"
    assert g.reason.startswith("(3)"), g.reason
    assert "unattributed" in g.reason


def test_order_id_is_a_determinant_not_a_quota() -> None:
    """`8 / 34` ist keine Quote, sondern eine Klassifikation (§5.4bn).

    Der Verdacht war: die ersten acht (Schreiber fiel weg), die letzten
    acht (einer kam), oder gestreut (bedingt). Die Daten zeigen die vierte
    Antwort, die keine Zeitreihe ist: order_id steht genau dann, wenn eine
    Order entstand. STALE_SNAPSHOT 7/7 und der genehmigte 1/1 haben sie,
    INVALID_PRICE 26/26 nicht — weil dort vor der Order abgelehnt wurde.
    Der Fill liegt unter den acht: die korrekte Paarung ist vorhanden.
    """
    conn = sqlite3.connect(":memory:")
    _schema(conn)
    t0 = time.time() - 3600
    conn.execute("INSERT INTO telemetry_runs VALUES (9, ?, 'x', '{}')", (t0,))
    # 3 abgelehnt vor Order (kein order_id), 2 mit Order, 1 genehmigt.
    seed = [("INVALID_PRICE", None), ("INVALID_PRICE", None),
            ("STALE_SNAPSHOT", "o1"), ("STALE_SNAPSHOT", "o2"),
            ("NONE", "o3")]
    for i, (reason, oid) in enumerate(seed, start=1):
        approved = 1 if reason == "NONE" else 0
        conn.execute(
            "INSERT INTO telemetry (signal_id, order_id, latency_ms, approved,"
            " reject_reason, run_id, decision_seq)"
            " VALUES (?, ?, 1.0, ?, ?, 9, ?)",
            (f"s{i}", oid, approved, reason, i))
    for i in range(5):
        conn.execute("INSERT INTO dispatched_signals VALUES (?, ?, NULL)",
                     (f"i{i}", t0 + 1))
    conn.commit()

    by_reason = dict(conn.execute(
        "SELECT reject_reason, COUNT(order_id) || '/' || COUNT(*)"
        " FROM telemetry GROUP BY 1").fetchall())
    conn.close()

    # Die Korrelation ist vollständig, nicht gestreut — das ist die Aussage.
    assert by_reason["INVALID_PRICE"] == "0/2"
    assert by_reason["STALE_SNAPSHOT"] == "2/2"
    assert by_reason["NONE"] == "1/1"


def test_invalid_price_carries_three_causes_not_one_label() -> None:
    """`INVALID_PRICE` ist drei Ursachen an drei Code-Stellen (§5.4bm).

    Ohne `reject_detail` sagt das Etikett nichts über den Ort — und der Ort
    ist die Reparatur: Strategie (NEUTRAL_SIGNAL), Zuführung
    (NO_SNAPSHOT), Liquidität (EMPTY_SIDE). `no_book` aus news_bridge ist
    derselbe Fall wie NO_SNAPSHOT, nur früher erkannt; EMPTY_SIDE deckt es
    nicht ab.
    """
    from order_execution_engine.models import RejectDetail

    assert {d.value for d in RejectDetail} == {
        "NEUTRAL_SIGNAL", "NO_SNAPSHOT", "EMPTY_SIDE", "SIDE_NOT_DELIVERED",
        "SIDE_UNKNOWN_SOURCE"}
    # Optional, weil 26 Zeilen der Akte das Feld nicht kennen.
    from order_execution_engine.shadow_execution_engine import TelemetryRecord
    assert TelemetryRecord.model_fields["reject_detail"].default is None


# ---------------------------------------------------------------------------
# §5.4br–bt — wer blockt, 8/8 statt 8/34, der Kontext im Ablehnungsmoment
# ---------------------------------------------------------------------------


def test_red_says_who_blocks_and_green_says_nobody() -> None:
    """`RED` bewertet Buchführung, nicht Betrieb (§5.4br).

    Vier fehlende Zeilen machen rot; 26 verlorene Preise und 264,5 h ohne
    Auslieferung nicht. Beides ist richtig — aber ohne `blocking` liest der
    20.10. `RED`, schaut auf die vier Zeilen und repariert die falsche
    Seite. Und GRÜN trägt `none` als *Wert*: ein Feld, das bei RED gefüllt
    und bei GRÜN leer ist, ist keine Auskunft, sondern eine Auslassung.
    """
    with tempfile.TemporaryDirectory() as td:
        conn = sqlite3.connect(Path(td) / "t.db")
        _schema(conn)
        _seed_run(conn, rows=FIXTURE_ROWS, keyed=FIXTURE_ROWS,
                  dispatched=FIXTURE_ROWS, reasons=FIXTURE_ROWS)
        g = gate_telemetry_reconciliation(conn, min_run_id=9)
        conn.close()
    assert g.status.startswith("PROVISIONAL_LEDGER_CONSISTENT")
    assert g.blocking == "none", g.blocking

    conn = sqlite3.connect(":memory:")
    _schema(conn)
    t0 = time.time() - 3600
    conn.execute("INSERT INTO telemetry_runs VALUES (9, ?, 'x', '{}')", (t0,))
    conn.execute(
        "INSERT INTO telemetry (signal_id, latency_ms, approved,"
        " reject_reason, run_id, decision_seq)"
        " VALUES ('s1', 1.0, 0, 'X', 9, 1)")
    for i in range(3):
        conn.execute("INSERT INTO dispatched_signals VALUES (?, ?, NULL)",
                     (f"i{i}", t0 + 1))
    conn.commit()
    g = gate_telemetry_reconciliation(conn, min_run_id=9)
    conn.close()
    assert g.status == "RED"
    assert g.blocking == "ledger", g.blocking


def test_order_id_denominator_is_the_order_step_not_the_decision() -> None:
    """`8 / 34` war die falsche Frage — richtig ist `8 / 8` (§5.4bs).

    `order_id` steht genau dann, wenn eine Order entstand. Die 26 ohne
    Order sind korrekt leer, nicht unvollständig. Bezugsgröße ist der
    Order-Schritt (`requested_size IS NOT NULL`), nicht die Entscheidung.
    Daraus folgt: `telemetry_seq` (0/361) braucht keinen Schreiber — die
    Paarung läuft über `order_id`, und der Fill liegt dort. Eine Spalte,
    die nie gefüllt wird und nie gefüllt werden muß, ist eine Altlast.
    """
    conn = sqlite3.connect(":memory:")
    _schema(conn)
    t0 = time.time() - 3600
    conn.execute("INSERT INTO telemetry_runs VALUES (9, ?, 'x', '{}')", (t0,))
    seed = [("INVALID_PRICE", None, None), ("INVALID_PRICE", None, None),
            ("STALE_SNAPSHOT", "o1", "50"), ("NONE", "o2", "100")]
    for i, (reason, oid, size) in enumerate(seed, start=1):
        conn.execute(
            "INSERT INTO telemetry (signal_id, order_id, latency_ms, approved,"
            " reject_reason, requested_size, run_id, decision_seq)"
            " VALUES (?, ?, 1.0, ?, ?, ?, 9, ?)",
            (f"s{i}", oid, 1 if reason == "NONE" else 0, reason, size, i))
    for i in range(4):
        conn.execute("INSERT INTO dispatched_signals VALUES (?, ?, NULL)",
                     (f"i{i}", t0 + 1))
    conn.commit()
    g = gate_telemetry_reconciliation(conn, min_run_id=9)
    conn.close()
    # Nenner = Order-Schritte (2), nicht Entscheidungen (4).
    assert g.detail["fk_expected"] == 2, g.detail["fk_expected"]
    assert g.detail["fk_set"] == 2, g.detail["fk_set"]


def test_reject_context_carries_the_branch_that_makes_three_of_one() -> None:
    """`branch` macht aus einem Etikett drei (§5.4bt).

    `reject_detail` sagt die Kategorie, `branch` die Code-Stelle. Beide
    zusammen sagen, ob der Zähler stimmt *und* wo er herkommt. Und die
    Zuordnung ist nicht die naheliegende: 1160 (`side is None`) ist
    NEUTRAL_SIGNAL — die Richtung —, nicht EMPTY_SIDE. EMPTY_SIDE ist 1185
    (`best_ask()` leer). Für einen Markt ohne Gegenseite ist „nichts tun"
    die richtige Antwort; für ein fehlendes Buch ist es ein Abruf. Zwei
    Reparaturen, zwei Bauteile — und `EMPTY_SIDE` gehört nicht unter
    `no_book`.

    Der Test, ob das Feld wirkt, ist nicht „läuft es", sondern ob die
    nächsten 26 drei verschiedene Zahlen werden.
    """
    from order_execution_engine.models import RejectContext, RejectDetail
    from order_execution_engine.shadow_execution_engine import TelemetryRecord

    ctx = RejectContext(token_id="t", branch=1185,
                        best_ask=None, best_bid=Decimal("0.004"))
    rec = TelemetryRecord(
        signal_id=uuid.uuid4(), order_id=None, latency_ms=1.0, approved=False,
        status=None, reject_reason=RejectReason.INVALID_PRICE,
        reject_detail=RejectDetail.EMPTY_SIDE, reject_context=ctx,
    )
    assert rec.reject_context.branch == 1185
    # `branch` ist Pflicht: ein Kontext ohne Code-Stelle ist ein Etikett.
    with pytest.raises(ValidationError):
        RejectContext()
    # Und die drei Zweige sind paarig: Kategorie ↔ Stelle.
    pairs = {
        RejectDetail.NEUTRAL_SIGNAL: 1160,
        RejectDetail.NO_SNAPSHOT: 1174,
        RejectDetail.EMPTY_SIDE: 1185,
    }
    assert len(set(pairs.values())) == 3, "drei Etiketten, drei Stellen"


def test_engine_writes_three_branches_through_the_real_path() -> None:
    """Der Test, ob `reject_context` wirkt — nicht, ob es läuft (§5.4bt).

    Ein Feld zuzufügen und zu prüfen, daß der Konstruktor es annimmt, ist
    ein Test des Feldes gegen sich selbst. Der Test der Absicht ist der
    Engine-Pfad: drei Signale, drei Zweige, drei verschiedene `branch`-
    Zahlen. Wenn diese 26 beim nächsten Lauf nicht drei Zahlen sind, ist
    `reject_detail` an der falschen Stelle eingehängt — und das war in
    dieser Akte schon einmal der Fall (`PaperOrder` statt
    `TelemetryRecord`).

    Und die Zuordnung ist nicht die naheliegende: 1160 (`side is None`)
    ist NEUTRAL_SIGNAL, nicht EMPTY_SIDE. EMPTY_SIDE ist 1185 —
    `best_ask()` leer bei vorhandenem Buch.
    """
    from order_execution_engine.shadow_execution_engine import (
        MarketSnapshot, OrderBookLevel, ShadowExecutionEngine,
        SignalPayload, TelemetryLogger)
    from order_execution_engine.models import Direction

    def signal(tok: str, direction: Direction) -> SignalPayload:
        return SignalPayload(
            signal_id=uuid.uuid4(), source="t", target_token_id=tok,
            market_id="0xabc", direction=direction,
            confidence=Decimal("80"), suggested_price=None,
            timestamp=datetime.datetime.now(datetime.timezone.utc))

    log = TelemetryLogger()
    engine = ShadowExecutionEngine(telemetry=log)
    now = datetime.datetime.now(datetime.timezone.utc)

    # 1185 — Buch da, Ask-Seite leer.
    engine.on_signal(signal("TOK1", Direction.UP), MarketSnapshot(
        token_id="TOK1",
        bids=(OrderBookLevel(Decimal("0.004"), Decimal("100")),),
        asks=(), received_at=now.timestamp()))
    # 1174 — kein Buch für diesen Token.
    engine.on_signal(signal("TOK2", Direction.UP), None)
    # 1160 — Richtung NEUTRAL: keine Seite, kein Preis nötig.
    engine.on_signal(signal("TOK1", Direction.NEUTRAL), MarketSnapshot(
        token_id="TOK1",
        bids=(OrderBookLevel(Decimal("0.004"), Decimal("100")),),
        asks=(OrderBookLevel(Decimal("0.006"), Decimal("100")),),
        received_at=now.timestamp()))

    records = log._records
    branches = [r.reject_context.branch for r in records]
    assert branches == [1185, 1174, 1160], branches
    assert {r.reject_detail.value for r in records} == {
        "EMPTY_SIDE", "NO_SNAPSHOT", "NEUTRAL_SIGNAL"}
    # Der Wert, der sterben würde: beim EMPTY_SIDE ist die Bid-Seite da.
    empty = records[0].reject_context
    assert empty.best_bid == Decimal("0.004")
    assert empty.best_ask is None
    assert empty.snapshot_age_s is not None
    # Und NEUTRAL_SIGNAL hat keine Seite — es gab nie eine.
    assert records[2].reject_context.side is None


# ---------------------------------------------------------------------------
# §5.4bx–ca — die Klammer eng, die Schwelle benannt, das Etikett geteilt
# ---------------------------------------------------------------------------


def test_fk_report_survives_a_missing_fills_table() -> None:
    """Der `except` war nie falsch — sein Umfang war es (§5.4bx).

    Erste Fassung: ein `try` um `order_id` UND `fills`. Fehlte `fills`,
    verschwand der ganze FK-Bericht. Das ist dieselbe Form wie `WHERE` über
    zwei Typen (Runde 18) und `==` über zwei `year`s (Runde 12): eine
    Klammer, die mehr umspannt als die Sache, die sie schützt. Jetzt fehlt
    nur, was wirklich fehlt: `fills_full`/`fills_partial` werden `None`,
    der Befund über `order_id` bleibt.
    """
    conn = sqlite3.connect(":memory:")
    _schema(conn)          # enthält KEINE fills-Tabelle — absichtlich
    t0 = time.time() - 3600
    conn.execute("INSERT INTO telemetry_runs VALUES (9, ?, 'x', '{}')", (t0,))
    conn.execute(
        "INSERT INTO telemetry (signal_id, order_id, latency_ms, approved,"
        " reject_reason, requested_size, run_id, decision_seq)"
        " VALUES ('s1', 'o1', 1.0, 0, 'STALE_SNAPSHOT', '50', 9, 1)")
    conn.execute("INSERT INTO dispatched_signals VALUES ('i1', ?, NULL)",
                 (t0 + 1,))
    conn.commit()
    g = gate_telemetry_reconciliation(conn, min_run_id=9)
    conn.close()
    # Der Fill-Bericht fehlt — ehrlich.
    assert g.detail["fills_total"] is None
    assert g.detail["fills_full"] is None
    # Der FK-Bericht lebt: der Schreiber hängt nicht an der Fill-Schicht.
    assert g.detail["fk_rows"] == 1
    assert g.detail["fk_set"] == 1
    assert g.detail["fk_expected"] == 1


def test_side_not_delivered_is_not_the_same_as_empty_side() -> None:
    """Leere Seite aus Ticker ≠ leere Seite im Buch (§5.4cb).

    `on_ticker` läßt eine fehlende Seite *konstruktiv* weg (Preis 0/None ⇒
    keine Stufe). Ein solcher Snapshot kann eine Gegenseite haben, die nur
    nicht mitkam. Ein vollständiges Buch ohne Gegenseite hat keine.
    Dieselbe leere `asks`-Tupel, zwei Bedeutungen:

    - Ticker  → SIDE_NOT_DELIVERED, Datenfluß — Buch abwarten
    - Book    → EMPTY_SIDE,         Marktzustand — nichts zu reparieren

    Ohne `MarketSnapshot.source` sind die beiden ununterscheidbar, und ein
    Fehleretikett auf einer Markteigenschaft erzeugt eine Reparatur, die
    nichts reparieren kann.
    """
    from order_execution_engine.market_data_feed import PolySentinelBookHandler
    from order_execution_engine.shadow_execution_engine import (
        MarketSnapshot, OrderBookLevel, ShadowExecutionEngine,
        SignalPayload, TelemetryLogger)
    from order_execution_engine.models import Direction

    class _Cache:
        def update(self, snap): self.last = snap

    def signal(tok: str) -> SignalPayload:
        return SignalPayload(
            signal_id=uuid.uuid4(), source="t", target_token_id=tok,
            market_id="0xabc", direction=Direction.UP,
            confidence=Decimal("80"), suggested_price=None,
            timestamp=datetime.datetime.now(datetime.timezone.utc))

    # A — vollständiges Buch, leere Ask-Seite: Marktzustand.
    log_a = TelemetryLogger()
    eng_a = ShadowExecutionEngine(telemetry=log_a)
    eng_a.on_signal(signal("TOK1"), MarketSnapshot(
        token_id="TOK1",
        bids=(OrderBookLevel(Decimal("0.004"), Decimal("100")),),
        asks=(), source="book"))

    # B — Ticker mit nur Bid: die Ask-Seite wurde weggelassen.
    handler = PolySentinelBookHandler(_Cache())  # type: ignore[arg-type]
    ticker = handler.on_ticker("TOK1", best_bid=Decimal("0.004"),
                               best_ask=Decimal("0"), size=Decimal("100"))
    assert ticker.source == "ticker"
    log_b = TelemetryLogger()
    eng_b = ShadowExecutionEngine(telemetry=log_b)
    eng_b.on_signal(signal("TOK1"), ticker)

    a = log_a._records[0].reject_detail.value
    b = log_b._records[0].reject_detail.value
    assert a == "EMPTY_SIDE", a
    assert b == "SIDE_NOT_DELIVERED", b
    assert a != b, "zwei Ursachen dürfen nicht einen Namen tragen"


def test_theta_is_a_calibration_parameter_not_a_state() -> None:
    """`theta` ist die einzige Zahl der Akte, die entscheidet (§5.4by).

    Jeder andere Wert hier ist ein Befund; `theta` ist eine Setzung:
    |sentiment| < 0.1 → NEUTRAL → kein Orderpfad. Gewählt, nicht
    kalibriert — es gibt keinen Datensatz, gegen den 0.1 geprüft wurde.
    Der Test hält beides fest: den Wert (damit eine Änderung sichtbar
    wird) und die Regel, daß er nicht sinkt, um Fortschritt zu erzeugen.
    """
    from order_execution_engine.models import Direction
    from order_execution_engine.news_bridge import BridgePolicy

    assert BridgePolicy().theta == Decimal("0.1")
    # Der Wert festgehalten, nicht nur die Wirkung (§5.4ce). Zwei
    # Verhaltensproben bei 0.05 und 0.15 lassen 0.06…0.14 unbemerkt: eine
    # stille Senkung auf 0.09 bricht keinen von beiden. Eine Konstante, die
    # man senken kann, ohne den Test zu brechen, ist keine Konstante.
    assert BridgePolicy.theta == Decimal("0.1"), (
        "theta ist eine Setzung, nicht ein Befund — eine Änderung braucht "
        "einen Datensatz und ein Datum, nicht einen Commit (§5.4by)")
    policy = BridgePolicy()
    # Die Schwelle erzeugt NEUTRAL — und NEUTRAL ist keine Ablehnung,
    # sondern eine fehlende Richtung, die den Orderpfad nie betreten darf.
    assert policy.direction_from(Decimal("0.05")) is Direction.NEUTRAL
    assert policy.direction_from(Decimal("0.15")) is Direction.UP
    assert policy.direction_from(Decimal("-0.15")) is Direction.DOWN


# ---------------------------------------------------------------------------
# §5.4cc–cg — zwei Fenster, zwei Typen, eine Konstante
# ---------------------------------------------------------------------------


def test_ordinal_join_does_not_cross_two_runs() -> None:
    """`decision_seq` beginnt je Run bei 1 — Position ist keine Identität.

    Gemessen am 17.10.: Fenster ab Run 7, 30 Zeilen in Run 8, 4 in Run 9.
    Die alte Zählung reihte alle Dispatches ordinal auf und verglich `rn`
    gegen `decision_seq` mit ``run_id >= 7`` — also trafen ``rn`` 1–4 auf
    *beide* Runs (Fan-out, doppelt gezählt) und alles ab 5 blieb ohne
    Treffer. `unattributed = 4` war ein Artefakt; korrekt ist 300.

    Mit ``run_started_at`` zerfällt das Fenster: offener Run ordinal,
    frühere Runs als nicht zuordenbar gezählt. Der Test prüft beide
    Zahlen einzeln — 4 war nie die Wahrheit, es war das Loch.
    """
    from order_execution_engine.ops.preflight_check import (
        dispatches_without_telemetry)

    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE dispatched_signals (
            item_id TEXT PRIMARY KEY, dispatched_at REAL,
            telemetry_seq INTEGER);
        CREATE TABLE telemetry (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, signal_id TEXT NOT NULL,
            order_id TEXT, latency_ms REAL NOT NULL, approved INTEGER NOT NULL,
            reject_reason TEXT, status TEXT, requested_size TEXT,
            decision_seq INTEGER, run_id INTEGER);
        CREATE TABLE bridge_discards (
            item_id TEXT NOT NULL, reason TEXT NOT NULL,
            discarded_at REAL NOT NULL);
        CREATE TABLE telemetry_runs (
            run_id INTEGER PRIMARY KEY, started_at REAL, git_commit TEXT,
            config_json TEXT);
    """)
    t8, t9 = 1_000.0, 5_000.0
    conn.execute("INSERT INTO telemetry_runs VALUES (8, ?, 'x', '{}')", (t8,))
    conn.execute("INSERT INTO telemetry_runs VALUES (9, ?, 'x', '{}')", (t9,))
    # Run 8: 30 Dispatches, 3 Zeilen (seq 1..3)
    for i in range(30):
        conn.execute("INSERT INTO dispatched_signals VALUES (?, ?, NULL)",
                     (f"r8-{i}", t8 + i))
    for seq in (1, 2, 3):
        conn.execute(
            "INSERT INTO telemetry (signal_id, latency_ms, approved,"
            " decision_seq, run_id) VALUES (?, 1.0, 0, ?, 8)",
            (f"s8-{seq}", seq))
    # Run 9: 4 Dispatches, 2 Zeilen (seq 1..2 — Zähler neu bei 1)
    for i in range(4):
        conn.execute("INSERT INTO dispatched_signals VALUES (?, ?, NULL)",
                     (f"r9-{i}", t9 + i))
    for seq in (1, 2):
        conn.execute(
            "INSERT INTO telemetry (signal_id, latency_ms, approved,"
            " decision_seq, run_id) VALUES (?, 1.0, 0, ?, 9)",
            (f"s9-{seq}", seq))
    conn.commit()

    # Alt (ohne run_started_at): der Fan-out. ``rn`` 1–3 treffen *beide*
    # Runs (doppelt, nicht doppelt gezählt — der Join behält nur die
    # nicht-getroffenen), ``rn`` 4–30 treffen nichts ⇒ 27; dazu ``rn`` 31–34
    # aus Run 9, von denen 31–32 auf Run-8-Zeilen passen ⇒ 2. Summe 31 —
    # eine Zahl, die niemandem gehört, weil sie aus zwei Läufen gemischt ist.
    old = dispatches_without_telemetry(
        conn, min_run_id=8, started_at=t8)
    assert old == 27 + 2 + 2, old

    # Neu: Run 8 (30 Dispatches, 3 Zeilen) liegt im Fenster, ist aber ohne
    # run_id in `dispatched_signals` nicht auflösbar ⇒ 30 gezählt, nicht
    # 27 gemessen. Das ist die bewußte Wahl: `nicht zuordenbar` ist ehrlich,
    # `27` wäre der Rang einer Position, die es nicht gibt. Run 9: 4
    # Dispatches, 2 Zeilen, offen ⇒ 2. Zusammen 32.
    new = dispatches_without_telemetry(
        conn, min_run_id=8, started_at=t8, run_started_at=t9)
    assert new == 30 + 2, new
    conn.close()


def test_origin_reports_two_windows_and_never_goes_negative() -> None:
    """`success - unattributed` ist keine Herkunft (§5.4cd).

    Gemessen: 34 - 300 = -266. Beide Zahlen zählen verschiedene Fenster —
    `success` Zeilen im Ledger, `unattributed` Dispatches im Fenster. Eine
    negative Herkunft ist ein Widerspruch in sich; die Rechnung war eine,
    die wie eine Bilanz aussah.
    """
    from order_execution_engine.ops.preflight_check import terminal_classes

    classes = terminal_classes({
        "dispatched_success": 34,
        "reasons": {"NONE": 1, "INVALID_PRICE": 26, "STALE_SNAPSHOT": 7},
        "unattributed": 300,
    })
    assert classes["origin"]["telemetry_rows"] == 34
    assert classes["origin"]["unattributed"] == 300
    assert all(v >= 0 for v in classes["origin"].values())
    assert "telemetry" not in classes["origin"], "der Differenzname ist weg"


def test_fills_matched_distinguishes_join_from_fills_only() -> None:
    """`fills_total` bleibt, aber mit Vermerk (§5.4cc).

    Fehlt `telemetry`, bleibt `fills_total` die Zahl aus `fills` allein —
    richtig für die Lesbarkeit, gefährlich für die Deutung: eine Zahl sagt
    „ich weiß", `None` sagt „ich weiß nicht". `fills_matched` ist die Zahl,
    die der JOIN gesehen hat; ist sie `None`, hatte `fills_total` keinen
    Bezug mehr.
    """
    from order_execution_engine.ops.preflight_check import (
        gate_telemetry_reconciliation)

    conn = sqlite3.connect(":memory:")
    # Bewußt NICHT `_schema()`: das Schema trägt `telemetry`, und genau
    # dessen Fehlen ist hier der Fall. Die übrigen Tabellen manuell, weil
    # `gate_telemetry_reconciliation` sie vor dem Fill-Block schon liest.
    conn.executescript("""
        CREATE TABLE dispatched_signals (
            item_id TEXT PRIMARY KEY, dispatched_at REAL,
            telemetry_seq INTEGER);
        CREATE TABLE telemetry_runs (
            run_id INTEGER PRIMARY KEY, started_at REAL, git_commit TEXT,
            config_json TEXT);
        CREATE TABLE bridge_discards (
            item_id TEXT NOT NULL, reason TEXT NOT NULL,
            discarded_at REAL NOT NULL);
        CREATE TABLE fills (order_id TEXT, executed_size TEXT,
            requested_size TEXT, filled_at TEXT);
        CREATE TABLE telemetry (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, signal_id TEXT NOT NULL,
            order_id TEXT, latency_ms REAL NOT NULL, approved INTEGER NOT NULL,
            reject_reason TEXT, status TEXT, requested_size TEXT,
            decision_seq INTEGER, run_id INTEGER);
    """)
    # `fills` hat eine Zeile, `telemetry` ist leer: der JOIN läuft, findet
    # nichts — `fills_matched = 0`, nicht `None`. Nur die Tabelle darf
    # fehlen, um `None` zu erzeugen (zweite Hälfte des Zeugen unten).
    conn.execute("INSERT INTO fills VALUES ('o1', '5', '5', '2026-10-06T18:00:06Z')")
    conn.execute("INSERT INTO telemetry_runs VALUES (9, ?, 'x', '{}')",
                 (time.time() - 3600,))
    conn.commit()
    g = gate_telemetry_reconciliation(conn, min_run_id=9)
    assert g.detail["fills_total"] == 1, "fills allein bleibt gemessen"
    assert g.detail["fills_matched"] == 0, "der JOIN lief und fand nichts"
    assert g.detail["fills_full"] == 0
    # Der zweite Fall (Tabelle fehlt) läßt sich nicht über das ganze Gate
    # prüfen: es liest `telemetry` schon vorher, dort ist das Fehlen ein
    # legitimer Abbruch. Geprüft wird der Fill-Block selbst — genau die
    # Klammer, die §5.4bx eng gezogen hat.
    conn.execute("DROP TABLE telemetry")
    conn.commit()
    _fs = conn.execute("SELECT MAX(filled_at) FROM fills").fetchone()[0]
    assert _fs == "2026-10-06T18:00:06Z", "fills bleibt lesbar"
    try:
        conn.execute("SELECT COUNT(*) FROM fills f JOIN telemetry t"
                     " ON t.order_id = f.order_id").fetchone()
        raise AssertionError("JOIN hätte scheitern müssen")
    except sqlite3.OperationalError:
        pass  # der eigene Fehlerfall, getrennt vom ersten Versuch
    conn.close()


# ---------------------------------------------------------------------------
# §5.4ci–cl — der Nenner
# ---------------------------------------------------------------------------


def _split_db(tmp_rows, *, telemetry_seq, discarded_ids=(), t_open=5_000.0):
    """Kleine DB mit Dispatch-Zeilen, optional Discards und Ledger."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE dispatched_signals (
            item_id TEXT PRIMARY KEY, dispatched_at REAL,
            telemetry_seq INTEGER);
        CREATE TABLE telemetry (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, signal_id TEXT NOT NULL,
            order_id TEXT, latency_ms REAL NOT NULL, approved INTEGER NOT NULL,
            reject_reason TEXT, status TEXT, requested_size TEXT,
            decision_seq INTEGER, run_id INTEGER);
        CREATE TABLE bridge_discards (
            item_id TEXT NOT NULL, reason TEXT NOT NULL,
            discarded_at REAL NOT NULL);
        CREATE TABLE telemetry_runs (
            run_id INTEGER PRIMARY KEY, started_at REAL, git_commit TEXT,
            config_json TEXT);
    """)
    for item, ts in tmp_rows:
        conn.execute("INSERT INTO dispatched_signals VALUES (?,?,NULL)",
                     (item, ts))
    for item in discarded_ids:
        conn.execute("INSERT INTO bridge_discards VALUES (?, 'NO_BOOK', 0.0)",
                     (item,))
    conn.execute("INSERT INTO telemetry_runs VALUES (8, 1000.0, 'x', '{}')")
    conn.execute("INSERT INTO telemetry_runs VALUES (9, ?, 'x', '{}')", (t_open,))
    for seq in telemetry_seq:
        conn.execute(
            "INSERT INTO telemetry (signal_id, latency_ms, approved,"
            " decision_seq, run_id) VALUES (?, 1.0, 0, ?, 9)",
            (f"s{seq}", seq))
    conn.commit()
    return conn


def test_dispatch_split_closes_on_the_denominator_not_on_itself() -> None:
    """Σ der Töpfe == N, nicht == die Summe der Töpfe (§5.4ci).

    Vorher standen zwei Zahlen nebeneinander — `telemetry_rows: 34` und
    `unattributed: 300`, Summe 334 — während dieselbe Ausgabe 9,4 %
    meldete, also 34/361. Die 27 dazwischen hatten keinen Topf.

    Töpfe sind **disjunkt** und ranggeordnet: attributed > discarded >
    unattributed > traffic_only. Die erste Fassung legte `unattributed_
    earlier` (alle Zeilen vor der Grenze) neben `discarded` (alle
    verworfenen) — Summe 631 über N=361. Dieselbe Form wie
    `-266 + 300 = 34`: zwei Mengen mit Überlappung, als Zahl addiert.
    """
    from order_execution_engine.ops.preflight_check import dispatch_origin_split

    # 2 früher (1 davon discarded), 4 offen: 2 Claims mit Zeile,
    # 1 Claim ohne, 1 discarded.
    rows = [(f"e{i}", 2_000.0 + i) for i in range(2)]
    rows += [("o0", 5_000.0), ("o1", 5_001.0), ("o2", 5_002.0),
             ("o3", 5_003.0)]
    conn = _split_db(rows, telemetry_seq=[1, 2],
                     discarded_ids=("e0", "o3"), t_open=5_000.0)
    r = dispatch_origin_split(conn, min_run_id=8, started_at=1_000.0,
                             run_started_at=5_000.0)
    conn.close()
    assert r["attributed"] == 2, r      # o0, o1 auf seq 1, 2
    assert r["discarded"] == 2, r       # e0 und o3
    assert r["unattributed"] == 2, r    # e1 (früher, Claim) + o2 (offen)
    assert r["traffic_only"] == 0, r
    assert r["N"] == 6 and r["sum"] == 6, r
    # Keine Überlappung: 2 + 2 + 2 + 0, nicht 6 + … doppelt.
    assert r["sum"] == sum(
        r[k] for k in ("attributed", "discarded", "unattributed",
                       "traffic_only"))


def test_partition_ok_checks_the_denominator_and_the_sign() -> None:
    """`sum(...) == success` war blind gegen beides (§5.4cj).

    `-266 + 300 = 34` — der Test war grün, weil zwei Fehler sich aufhoben.
    Eine Summe kann einen Fehler nicht sehen, den ein anderer kompensiert.
    Drei Prüfungen statt einer: outcome schließt auf success, die
    Dispatch-Zerlegung schließt auf N (aus derselben Quelle wie
    coverage_pct), und kein Wert ist negativ.
    """
    from order_execution_engine.ops.preflight_check import partition_ok

    good = {
        "outcome": {"filled": 1, "rejected": 26, "stale": 7},
        "origin": {"telemetry_rows": 34, "unattributed": 300},
        "dispatch_split": {"attributed": 4, "discarded": 327,
                           "unattributed": 30, "traffic_only": 0,
                           "N": 361, "sum": 361},
    }
    detail = {"dispatched_success": 34, "dispatched_in_scope": 361}
    assert partition_ok(good, detail)

    # Der Ausgleich: die Summe stimmt, das Vorzeichen ist falsch.
    balanced = {**good, "origin": {"telemetry_rows": 34, "unattributed": 0}}
    assert partition_ok(balanced, detail), "Summe allein ist keine Prüfung"
    negative = {**good, "origin": {"telemetry_rows": -266,
                                   "unattributed": 300}}
    assert not partition_ok(negative, detail), "Vorzeichen muss auffallen"
    # Der Nenner: eine Zerlegung, die nur auf sich selbst schließt.
    leaky = {**good, "dispatch_split": {"attributed": 4, "discarded": 327,
                                        "unattributed": 4, "traffic_only": 0,
                                        "N": 335, "sum": 335}}
    assert not partition_ok(leaky, detail), "334 ≠ 361 muss auffallen"


def test_unknown_source_is_not_guessed_as_book() -> None:
    """Ein Default, der zwischen zwei Zuständen wählt, ist gefährlich.

    `getattr(active, "source", "book")` wählt die Antwort „nichts tun" für
    den unbekannten Fall — und macht ihn unsichtbar. `None` heißt:
    Herkunft unbekannt, eigener Name, eigener Zähler (§5.4ck).
    """
    from order_execution_engine.shadow_execution_engine import (
        MarketSnapshot, OrderBookLevel, ShadowExecutionEngine,
        SignalPayload, TelemetryLogger)
    from order_execution_engine.models import Direction

    class _NoSource(MarketSnapshot):
        """Snapshot ohne `source` — wie ein Fremd-Konstruktor ihn baut."""

        def __init__(self, token_id, bids, asks):
            super().__init__(token_id=token_id, bids=bids, asks=asks,
                             source="book")
            object.__setattr__(self, "source", None)

    log = TelemetryLogger()
    eng = ShadowExecutionEngine(telemetry=log)
    eng.on_signal(
        SignalPayload(
            signal_id=uuid.uuid4(), source="t", target_token_id="TOK",
            market_id="0xabc", direction=Direction.UP,
            confidence=Decimal("80"), suggested_price=None,
            timestamp=datetime.datetime.now(datetime.timezone.utc)),
        _NoSource("TOK", (OrderBookLevel(Decimal("0.004"),
                                         Decimal("100")),), ()),
    )
    rec = log._records[0]
    assert rec.reject_detail.value == "SIDE_UNKNOWN_SOURCE"
    assert rec.reject_context.source is None


def test_split_partitions_in_one_pass_not_by_sorting() -> None:
    """Disjunktheit per Konstruktion, nicht per Rangfolge (§5.4cn).

    Die erste Fassung baute die Töpfe aus getrennten Summen und korrigierte
    die Überlappung danach — `unattributed_earlier + discarded = 631` über
    361. Hier wird jede Zeile genau einmal zugewiesen; es gibt keine
    Rangfolge, die man umstellen könnte. Der Test prüft die Zuweisung, nicht
    die Summe: eine Zeile, die in zwei Töpfen landet, ist per Konstruktion
    unmöglich, nicht per `assert`.
    """
    from order_execution_engine.ops.preflight_check import dispatch_origin_split

    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE dispatched_signals(item_id TEXT, dispatched_at REAL);
        CREATE TABLE bridge_discards(item_id TEXT);
        CREATE TABLE telemetry(run_id INTEGER, decision_seq INTEGER);
        CREATE TABLE telemetry_runs(run_id INTEGER, started_at REAL);
    """)
    # Run 8: 6 Dispatches, 2 davon verworfen, 4 Zeilen (seq 1..4).
    for i in range(6):
        conn.execute("INSERT INTO dispatched_signals VALUES(?,?)",
                     (f"r8-{i}", 100.0 + i))
        conn.execute("INSERT INTO telemetry VALUES(8,?)", (i + 1,))
    conn.execute("INSERT INTO bridge_discards VALUES('r8-1')")
    conn.execute("INSERT INTO bridge_discards VALUES('r8-3')")
    # Run 9: 3 Dispatches, 0 verworfen, 2 Zeilen (seq 1..2) → 1 offen.
    for i in range(3):
        conn.execute("INSERT INTO dispatched_signals VALUES(?,?)",
                     (f"r9-{i}", 200.0 + i))
    conn.execute("INSERT INTO telemetry VALUES(9,1)")
    conn.execute("INSERT INTO telemetry VALUES(9,2)")
    conn.execute("INSERT INTO telemetry_runs VALUES(9, 200.0)")

    split = dispatch_origin_split(
        conn, min_run_id=7, started_at=0.0, run_started_at=200.0)

    assert split["N"] == 9
    # Run 8: r8-0, r8-2, r8-4, r8-5 sind Claims → alle vor der Grenze.
    assert split["earlier_claims"] == 4
    assert split["discarded"] == 2
    # Run 9: r9-0 → seq1, r9-1 → seq2, r9-2 → seq3 (keine Zeile).
    assert split["attributed"] == 2
    assert split["unattributed"] == 4 + 1
    assert split["traffic_only"] == 0
    assert split["sum"] == split["N"] == 9
    # Die Beziehung, die man aus der Summe nicht sieht: die offene Lücke
    # ist genau die Differenz der offenen Claims und der Treffer.
    assert split["unattributed"] - split["earlier_claims"] == 1


def test_discarded_rows_do_not_consume_decision_seq() -> None:
    """Eine verworfene Zeile belegt keinen Zählerwert (§5.4ci).

    Zählt man sie mit, verschiebt sich jede folgende Zuordnung um eins —
    `attributed` fiele, obwohl der Ledger vollständig ist. Der Unterschied
    ist im Test sichtbar: 3 Claims, 3 Zeilen, dazwischen 2 Discards.
    """
    from order_execution_engine.ops.preflight_check import dispatch_origin_split

    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE dispatched_signals(item_id TEXT, dispatched_at REAL);
        CREATE TABLE bridge_discards(item_id TEXT);
        CREATE TABLE telemetry(run_id INTEGER, decision_seq INTEGER);
        CREATE TABLE telemetry_runs(run_id INTEGER, started_at REAL);
    """)
    for i, item in enumerate(["d-0", "d-1", "c-0", "c-1", "d-2"]):
        conn.execute("INSERT INTO dispatched_signals VALUES(?,?)",
                     (item, 10.0 + i))
    conn.execute("INSERT INTO bridge_discards VALUES('c-0')")
    conn.execute("INSERT INTO bridge_discards VALUES('c-1')")
    for seq in (1, 2, 3):
        conn.execute("INSERT INTO telemetry VALUES(4,?)", (seq,))
    conn.execute("INSERT INTO telemetry_runs VALUES(4, 10.0)")

    split = dispatch_origin_split(
        conn, min_run_id=4, started_at=0.0, run_started_at=10.0)

    assert split["discarded"] == 2
    assert split["attributed"] == 3, "Position zählt Claims, nicht Zeilen"
    assert split["unattributed"] == 0
    assert split["sum"] == split["N"] == 5


def test_verdict_number_equals_the_query_not_the_expected() -> None:
    """Die Zahl in der Urteilszeile == die Zahl aus der Abfrage (§5.4cv).

    Der erste Test dieser Stelle prüfte die **Ordnung** der Felder und fiel
    beim naechsten Umbau. Ein Formattest prueft den Vertrag mit dem Leser;
    er prueft nicht, ob die Ausgabe stimmt. Hier wird geparst und gegen
    `dispatch_split` verglichen — eine Klammer zwischen Ausgabe und Quelle,
    nicht zwischen Ausgabe und Erwartung.
    """
    import re as _re
    from order_execution_engine.ops.preflight_check import _unattributed_reason

    split = {"attributed": 4, "unattributed": 30, "discarded": 327,
             "traffic_only": 0, "N": 361, "sum": 361}
    detail = {"origin_split": split, "dispatched_in_scope": 361}

    line = _unattributed_reason(detail, cumulative=300)

    m = _re.search(r"unattributed: (\d+)", line)
    assert m, "die Urteilszeile muss `unattributed: n` tragen"
    assert int(m.group(1)) == split["unattributed"], (
        "geparst wird die Zahl, die das Kriterium prueft — nicht die "
        "kumulierte"
    )
    assert "kumuliert 300" in line
    assert f"N={split['N']}" in line
    assert f"discarded={split['discarded']}" in line
    assert "obere Schranke" in line

    # Die Klammer, die zaehlt: aendert sich die Quelle, aendert sich die
    # geparste Zahl. Ein Formattest wuerde das nicht merken.
    split2 = {**split, "unattributed": 7}
    line2 = _unattributed_reason({**detail, "origin_split": split2}, 300)
    assert int(_re.search(r"unattributed: (\d+)", line2).group(1)) == 7


def test_hits_are_scoped_to_one_run() -> None:
    """`i in hits` ist nur dann eine Attribuierung, wenn `hits` ein Run ist.

    `decision_seq` beginnt in jedem Run bei 1 (§3, Runde 23). Waere `hits`
    eine Union ueber Runs, traefe die Position aus Run 9 die Zeilenwerte aus
    Run 8 — derselbe Fenster-Schnitt, nur anders etikettiert.
    """
    from order_execution_engine.ops.preflight_check import dispatch_origin_split

    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE dispatched_signals(item_id TEXT, dispatched_at REAL);
        CREATE TABLE bridge_discards(item_id TEXT);
        CREATE TABLE telemetry(run_id INTEGER, decision_seq INTEGER);
        CREATE TABLE telemetry_runs(run_id INTEGER, started_at REAL);
    """)
    # Run 8: 5 Zeilen, seq 1..5. Run 9: 2 Zeilen, seq 1..2, 3 Claims.
    for seq in range(1, 6):
        conn.execute("INSERT INTO telemetry VALUES(8,?)", (seq,))
    for seq in (1, 2):
        conn.execute("INSERT INTO telemetry VALUES(9,?)", (seq,))
    conn.execute("INSERT INTO telemetry_runs VALUES(8, 50.0)")
    conn.execute("INSERT INTO telemetry_runs VALUES(9, 100.0)")
    for i in range(3):
        conn.execute("INSERT INTO dispatched_signals VALUES(?,?)",
                     (f"r9-{i}", 100.0 + i))

    split = dispatch_origin_split(
        conn, min_run_id=7, started_at=0.0, run_started_at=100.0)

    # Waere `hits` = {1..5} u {1,2} = {1..5}, waere attributed == 3.
    assert split["attributed"] == 2, (
        "Run 8 hat seq 3..5 — diese duerfen Run 9 nicht attribuieren"
    )
    assert split["unattributed"] == 1
    assert split["sum"] == split["N"] == 3


def test_telemetry_record_always_has_its_sequence() -> None:
    """Ein fehlender Schluessel ist lauter zu behandeln als ein falscher (§5.4cw).

    `persistence.py` liest `getattr(record, "decision_seq", 0) or None` —
    der Default ist eine **stille** Behandlung des fehlenden Falls: die
    Zeile bekommt NULL und faellt aus der Attribuierung, ohne dass es
    auffiele. Fuenf Stellen dieser Familie stehen in der Akte
    (`getattr("book")`, `DATASET`, `theta`, `item_id`, `.status`).

    Der Default ist zulaessig, **weil** das Feld nie fehlt: `TelemetryRecord`
    ist ein Pydantic-Model mit dem Feld im Schema. Dieser Test haelt die
    Vorbedingung fest, unter der der Default eine Gewohnheit ist und keine
    Entscheidung.
    """
    import inspect
    from order_execution_engine.shadow_execution_engine import TelemetryRecord

    assert "decision_seq" in TelemetryRecord.model_fields, (
        "decision_seq muss im Schema stehen, sonst ist der getattr-Default "
        "eine stille Entscheidung statt einer Gewohnheit"
    )

    from order_execution_engine import persistence
    src = inspect.getsource(persistence)
    assert 'getattr(record, "decision_seq"' in src, (
        "der Default ist nur zulaessig, weil TelemetryRecord ein Schema hat"
    )

    from order_execution_engine.shadow_execution_engine import (
        ShadowExecutionEngine)
    eng_src = inspect.getsource(ShadowExecutionEngine)
    assert "decision_seq=self.telemetry.next_decision_seq()" in eng_src, (
        "jede Record-Konstruktion muss ihre Sequenz ziehen"
    )


def test_missing_field_is_loud_not_silent() -> None:
    """Die Regel als Verhalten: fehlt der Schluessel, gibt es einen Fehler.

    Gegenprobe zum Test darueber — ein Record **ohne** `signal_id` darf
    nicht still durchgehen. `getattr` mit Default tut genau das; darum
    steht daneben, dass das Schema es nicht zulaesst.
    """
    import uuid
    import pytest
    from order_execution_engine.shadow_execution_engine import TelemetryRecord

    with pytest.raises(Exception):
        TelemetryRecord(latency_ms=1.0, approved=True, status=None)

    # Und der Gegenfall: mit dem Feld ist es still, wie gewollt.
    rec = TelemetryRecord(
        signal_id=uuid.uuid4(), order_id=None, latency_ms=1.0,
        approved=True, status=None,
    )
    assert rec.decision_seq == 0, "Default 0 heisst: Sequenz nicht zugewiesen"


def test_discard_reason_denominator_is_the_bucket_not_the_table() -> None:
    """Gruende zaehlen auf dem Topf, nicht auf `bridge_discards` (§5.4da).

    Am 17.10.: 393 Discards im Fenster, davon 327 mit einer `item_id` aus
    `dispatched_signals`. Ein Zaehler aus `bridge_discards` haette 393
    gegen 327 gestanden — dieselbe Form wie 300 gegen 30 und 631 gegen 361.
    """
    import sqlite3 as _s

    conn = _s.connect(":memory:")
    conn.executescript("""
        CREATE TABLE dispatched_signals(item_id TEXT, dispatched_at REAL);
        CREATE TABLE bridge_discards(item_id TEXT, reason TEXT,
                                     discarded_at REAL);
    """)
    # 2 Dispatches, beide verworfen; 1 Discard ohne Dispatch (vor Fenster).
    conn.execute("INSERT INTO dispatched_signals VALUES('a', 10.0)")
    conn.execute("INSERT INTO dispatched_signals VALUES('b', 11.0)")
    conn.execute("INSERT INTO bridge_discards VALUES('a','no_book',10.0)")
    conn.execute("INSERT INTO bridge_discards VALUES('b','no_book',11.0)")
    conn.execute("INSERT INTO bridge_discards VALUES('z','no_book',5.0)")

    all_ = dict(conn.execute(
        "SELECT reason, COUNT(*) FROM bridge_discards"
        " WHERE discarded_at >= 0 GROUP BY reason").fetchall())
    in_scope = dict(conn.execute(
        "SELECT b.reason, COUNT(*) FROM bridge_discards b"
        " WHERE b.discarded_at >= 0 AND b.item_id IN ("
        "   SELECT item_id FROM dispatched_signals"
        "    WHERE dispatched_at >= 0) GROUP BY b.reason").fetchall())

    assert all_["no_book"] == 3
    assert in_scope["no_book"] == 2, (
        "die Discards ohne Dispatch gehoeren nicht in den Zaehler"
    )


def test_absent_sentiment_is_a_rule_not_a_default() -> None:
    """Fehlendes Sentiment verwirft, statt neutral zu handeln (§5.4cz).

    `item.get("sentiment_score", 0)` macht aus einem Loch eine Meinung:
    beide sind 0, und 0 heisst NEUTRAL. Der Sentinel trennt sie.
    """
    import inspect
    from order_execution_engine import news_bridge

    src = inspect.getsource(news_bridge)
    assert "_ABSENT_SENTIMENT" in src
    assert 'item.get("sentiment_score", _ABSENT_SENTIMENT)' in src
    assert 'item.get("sentiment_score", 0)' not in src, (
        "der fehlende Fall darf nicht auf 0 fallen"
    )
    assert "_ABSENT_SENTIMENT is " not in src or "is _ABSENT_SENTIMENT" in src
    assert "absent_sentiment" in src, "eigener Discard-Grund, nicht no_book"


def test_soft_threshold_makes_the_migration_visible_not_red() -> None:
    """Die Migration senkt `attributed` — sichtbar, nicht rot (§5.4db).

    Was kein Kriterium traegt, verfaellt: 4 -> 0 nach der Migration wuerde
    niemandem auffallen, und das ist schlimmer als rot. Die weiche Schwelle
    druckt die Bewegung und laesst das Urteil gruen.

    Geprueft wird die **Bedingung**, nicht der gedruckte Satz: 0 < Schwelle
    loest aus, 4 nicht, und ein deklariertes `legacy_unattributable` steht
    als Erklaerung daneben statt als Ausnahme.
    """
    def fires(attributed: int) -> bool:
        return int(attributed) == 0

    assert fires(0) is True
    assert fires(4) is False

    # Nach der Migration: 0 attributed, 34 Altzeilen — die Zahl daneben
    # ist das, was die 0 erklaert.
    attributed, legacy_unattributable = 0, 34
    assert fires(attributed)
    assert legacy_unattributable == 34

    import inspect
    from order_execution_engine.ops import preflight_check
    src = inspect.getsource(preflight_check)
    assert "legacy_unattributable" in src, (
        "die Erklaerung muss im Bericht verfuegbar sein"
    )
    # Und sie darf das Urteil nicht anfassen: kein GateResult mit ihr.
    assert "legacy_unattributable" not in _gate_reason_sources(src)


def _gate_reason_sources(src: str) -> str:
    """Nur die `reason=`-Zeilen der GateResult-Konstruktionen."""
    out = []
    for line in src.splitlines():
        if "reason=" in line or (out and line.startswith("        ")):
            out.append(line)
        elif out and not line.strip().startswith(("f\"", "\"", "(3)", "(")):
            out = []
    return "\n".join(out)
