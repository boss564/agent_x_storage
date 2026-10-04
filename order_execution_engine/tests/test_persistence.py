"""Self-Tests für persistence.py (Validierung, Decimal-TEXT, Senke, Schema)."""

import tempfile
import uuid
from decimal import Decimal
from pathlib import Path

from order_execution_engine.models import (
    Direction,
    FillResult,
    OrderSide,
    RejectReason,
    RiskConfig,
    SignalPayload,
    VirtualPortfolio,
)
from order_execution_engine.persistence import (
    InvalidUserIdError,
    SQLiteShadowStorage,
    TelemetrySink,
    shadow_data_dir,
    validate_user_id,
)
from order_execution_engine.shadow_execution_engine import (
    MarketSnapshot,
    OrderBookLevel,
    ShadowExecutionEngine,
    TelemetryLogger,
    TelemetryRecord,
)


def test_user_id_validation() -> None:
    assert validate_user_id("oliver_1") == "oliver_1"
    for bad in ["", "../etc", "a/b", "..", "x y", "x\\y", "." * 3]:
        try:
            validate_user_id(bad)
            raise AssertionError(f"'{bad}' hätte abgelehnt werden müssen")
        except InvalidUserIdError:
            pass
    # Pfad-Bleibt-unter-Root-Garantie
    with tempfile.TemporaryDirectory() as tmp:
        p = shadow_data_dir(Path(tmp), "user-42")
        assert p == Path(tmp).resolve() / "user-42" / "shadow"
    print("OK test_user_id_validation")


def test_storage_roundtrip_decimal_text() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        fill = FillResult(
            order_id=__import__("uuid").uuid4(),
            execution_price=Decimal("0.615"),
            executed_size=Decimal("0.1"),
            slippage=Decimal("0.0000000000000001"),
            fee=Decimal("0"),
        )
        store.write_fill(fill)
        rows = store.read_fills(str(fill.order_id))
        assert len(rows) == 1
        price_text = rows[0][0]
        assert price_text == "0.615"  # TEXT, kein REAL
        assert Decimal(price_text) == Decimal("0.615")
        store.close()
    print("OK test_storage_roundtrip_decimal_text")


def test_schema_version_and_tables() -> None:
    import sqlite3
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        conn = sqlite3.connect(str(Path(tmp) / "u1" / "shadow" / "shadow.db"))
        version = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0]
        assert version == "5"  # v5: telemetry_fill_metrics
        for table in (
            "telemetry", "fills", "portfolio_snapshots",
            "peak_events", "telemetry_fill_metrics",
        ):
            conn.execute(f"SELECT 1 FROM {table} LIMIT 0")
        # Die neuen Spalten sind da
        tcols = {r[1] for r in conn.execute("PRAGMA table_info(telemetry)")}
        fcols = {r[1] for r in conn.execute("PRAGMA table_info(fills)")}
        assert {"requested_size", "decision_seq"} <= tcols
        assert "requested_size" in fcols
        assert {"side", "token_id", "market_id", "decision_seq"} <= fcols
        pcols = {r[1] for r in conn.execute("PRAGMA table_info(peak_events)")}
        assert {"seq", "raised_at", "journal_pos", "peak_equity", "marks_json"} <= pcols
        mcols = {r[1] for r in conn.execute("PRAGMA table_info(telemetry_fill_metrics)")}
        assert {"telemetry_seq", "fill_ratio", "payload_json", "capped"} <= mcols
        conn.close()
        store.close()
    print("OK test_schema_version_and_tables")


def test_schema_migrates_v3_to_v4_peak_events() -> None:
    """Befund 4: bestehende v3-DB wird auf v4 angehoben (peak_events).

    Simuliert eine Kanon-v3-Datei ohne peak_events-Tabelle; nach Öffnen
    muss SCHEMA_VERSION=4 und die Tabelle existieren. Anschließend
    append-only Write + identischer Re-Drain.
    """
    import sqlite3
    from order_execution_engine.models import PeakEvent
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "u1" / "shadow" / "shadow.db"
        db.parent.mkdir(parents=True)
        conn = sqlite3.connect(str(db))
        conn.executescript(
            """
            CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE telemetry (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id TEXT NOT NULL,
                order_id TEXT,
                latency_ms REAL NOT NULL,
                approved INTEGER NOT NULL,
                reject_reason TEXT,
                status TEXT,
                requested_size TEXT,
                decision_seq INTEGER
            );
            CREATE TABLE fills (
                order_id TEXT NOT NULL,
                fill_idx INTEGER NOT NULL,
                execution_price TEXT NOT NULL,
                executed_size TEXT NOT NULL,
                slippage TEXT NOT NULL,
                fee TEXT NOT NULL,
                filled_at TEXT NOT NULL,
                latency_ms REAL,
                requested_size TEXT,
                side TEXT,
                token_id TEXT,
                market_id TEXT,
                decision_seq INTEGER,
                PRIMARY KEY (order_id, fill_idx)
            );
            CREATE TABLE portfolio_snapshots (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                taken_at TEXT NOT NULL,
                cash TEXT NOT NULL,
                start_balance TEXT NOT NULL,
                realized_pnl TEXT NOT NULL,
                peak_equity TEXT NOT NULL,
                positions_json TEXT NOT NULL
            );
            INSERT INTO schema_meta (key, value) VALUES ('schema_version', '3');
            """
        )
        conn.commit()
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "peak_events" not in tables
        assert conn.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0] == "3"
        conn.close()

        store = SQLiteShadowStorage(db)
        conn2 = sqlite3.connect(str(db))
        # Kette: v3 → v4 (peak_events) → v5 (fill_metrics)
        assert conn2.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0] == "5"
        conn2.execute("SELECT 1 FROM peak_events LIMIT 0")
        conn2.execute("SELECT 1 FROM telemetry_fill_metrics LIMIT 0")
        conn2.close()

        ev = PeakEvent(
            seq=0, marks={"t": Decimal("0.5")}, journal_pos=0,
            peak_equity=Decimal("10001"),
        )
        store.write_peak_event(ev)
        store.write_peak_event(ev)  # Re-Drain
        assert store.read_peak_events() == [ev]
        store.close()
    print("OK test_schema_migrates_v3_to_v4_peak_events")


def test_schema_migrates_v4_to_v5_fill_metrics() -> None:
    """C4: v4-DB ohne telemetry_fill_metrics → v5 idempotent."""
    import sqlite3

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "u1" / "shadow" / "shadow.db"
        db.parent.mkdir(parents=True)
        conn = sqlite3.connect(str(db))
        conn.executescript(
            """
            CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE telemetry (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id TEXT NOT NULL,
                order_id TEXT,
                latency_ms REAL NOT NULL,
                approved INTEGER NOT NULL,
                reject_reason TEXT,
                status TEXT,
                requested_size TEXT,
                decision_seq INTEGER
            );
            CREATE TABLE fills (
                order_id TEXT NOT NULL,
                fill_idx INTEGER NOT NULL,
                execution_price TEXT NOT NULL,
                executed_size TEXT NOT NULL,
                slippage TEXT NOT NULL,
                fee TEXT NOT NULL,
                filled_at TEXT NOT NULL,
                latency_ms REAL,
                requested_size TEXT,
                side TEXT,
                token_id TEXT,
                market_id TEXT,
                decision_seq INTEGER,
                PRIMARY KEY (order_id, fill_idx)
            );
            CREATE TABLE portfolio_snapshots (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                taken_at TEXT NOT NULL,
                cash TEXT NOT NULL,
                start_balance TEXT NOT NULL,
                realized_pnl TEXT NOT NULL,
                peak_equity TEXT NOT NULL,
                positions_json TEXT NOT NULL
            );
            CREATE TABLE peak_events (
                seq INTEGER PRIMARY KEY,
                raised_at TEXT NOT NULL,
                journal_pos INTEGER NOT NULL,
                peak_equity TEXT NOT NULL,
                marks_json TEXT NOT NULL
            );
            INSERT INTO schema_meta (key, value) VALUES ('schema_version', '4');
            """
        )
        conn.commit()
        assert "telemetry_fill_metrics" not in {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        conn.close()

        store = SQLiteShadowStorage(db)
        store2 = SQLiteShadowStorage(db)  # zweites Init — idempotent
        conn2 = sqlite3.connect(str(db))
        assert conn2.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0] == "5"
        conn2.execute("SELECT 1 FROM telemetry_fill_metrics LIMIT 0")
        n = conn2.execute(
            "SELECT COUNT(*) FROM telemetry_fill_metrics"
        ).fetchone()[0]
        assert n == 0
        conn2.close()
        store.close()
        store2.close()
    print("OK test_schema_migrates_v4_to_v5_fill_metrics")


def test_w_persist_1_fill_metrics_roundtrip() -> None:
    """W-PERSIST-1: Record mit fill_metrics → Neben-Zeile, typed + JSON identisch."""
    from order_execution_engine.fill_simulator import (
        FillMetrics, SlippageReport,
    )

    metrics = FillMetrics(
        requested_size=Decimal("100"),
        filled_size=Decimal("40"),
        fill_ratio=Decimal("0.4"),
        levels_consumed=1,
        vwap=Decimal("0.55"),
        slippage=SlippageReport(
            vs_touch_ref_bps=Decimal("100"),
            vs_signal_bps=Decimal("200"),
            capped=False,
        ),
    )
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        rec = TelemetryRecord(
            signal_id=uuid.uuid4(),
            order_id=uuid.uuid4(),
            latency_ms=2.0,
            approved=True,
            status=None,
            reject_reason=RejectReason.NONE,
            decision_seq=1,
            fill_metrics=metrics,
        )
        store.write_telemetry(rec)
        assert store.count_fill_metrics_rows() == 1
        restored = store.read_fill_metrics(1)
        assert restored is not None
        assert restored == metrics
        assert FillMetrics.model_validate_json(
            restored.model_dump_json()
        ) == metrics
        store.close()
    print("OK test_w_persist_1_fill_metrics_roundtrip")


def test_w_persist_2_reject_has_no_fill_metrics_row() -> None:
    """W-PERSIST-2: Reject (z. B. STALE) → keine Neben-Zeile."""
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        rec = TelemetryRecord(
            signal_id=uuid.uuid4(),
            order_id=uuid.uuid4(),
            latency_ms=0.5,
            approved=False,
            status=None,
            reject_reason=RejectReason.STALE_SNAPSHOT,
            decision_seq=1,
            fill_metrics=None,
        )
        store.write_telemetry(rec)
        assert store.count_fill_metrics_rows() == 0
        assert store.read_fill_metrics(1) is None
        store.close()
    print("OK test_w_persist_2_reject_has_no_fill_metrics_row")


def test_telemetry_sink_end_to_end() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        engine = ShadowExecutionEngine(risk_config=RiskConfig(max_order_size_shares=Decimal("100")))
        snap = MarketSnapshot(
            token_id="0xtokenA",
            bids=(OrderBookLevel(Decimal("0.59"), Decimal("500")),),
            asks=(OrderBookLevel(Decimal("0.61"), Decimal("500")),),
        )
        sig = SignalPayload(target_token_id="0xtokenA", market_id="mkt-1",
                            direction=Direction.UP, confidence=Decimal("80"))
        rec = engine.on_signal(sig, snap)
        assert rec.approved

        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        sink = TelemetrySink(store, engine.telemetry,
                             fills_provider=engine.fills_for)
        written = sink.drain()
        assert written == 1
        assert sink.drain() == 0  # idempotent
        store.close()
    print("OK test_telemetry_sink_end_to_end")


def test_telemetry_all_production_paths() -> None:
    """Regression: alle vier on_signal-Pfade laufen fehlerfrei durch die Senke.

    Deckt die Luecke ab, die den Bug durchgelassen hat: `write_telemetry`
    rief unbedingt `record.reject_reason.value` auf. Der genehmigte Pfad
    (approved=True) setzt laut Vertrag `RejectReason.NONE` — die Engine
    liefert also auf jedem Pfad ein Enum, niemals None. Geprueft wird, dass
    alle vier Pfade persistieren und der genehmigte mit "NONE" in der DB
    steht (nicht NULL).

    Hinweis zu Pfad 3: `on_signal` leitet die Ordergroesse aus
    `max_order_size_shares` ab, die Order ist also immer exakt das Limit —
    `MAX_POSITION_SIZE` ist dort strukturell unerreichbar. Ein echter
    Risiko-Reject wird ueber `max_event_exposure_usdc` ausgeloest.
    """
    import sqlite3
    with tempfile.TemporaryDirectory() as tmp:
        engine = ShadowExecutionEngine(risk_config=RiskConfig(max_order_size_shares=Decimal("100")))
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        sink = TelemetrySink(store, engine.telemetry, fills_provider=lambda oid: [])
        book = MarketSnapshot(
            token_id="0xtokenA",
            bids=(OrderBookLevel(Decimal("0.59"), Decimal("500")),),
            asks=(OrderBookLevel(Decimal("0.61"), Decimal("500")),),
        )
        # Pfad 1: NEUTRAL -> Pre-Order-Ablehnung, keine Order erzeugt
        neutral = SignalPayload(target_token_id="0xtokenA", market_id="mkt-1",
                                direction=Direction.NEUTRAL, confidence=Decimal("80"))
        # Pfad 2: BUY ohne Ask-Liquiditaet -> Pre-Order-Ablehnung
        no_liquidity = MarketSnapshot(
            token_id="0xtokenA",
            bids=(OrderBookLevel(Decimal("0.59"), Decimal("500")),),
            asks=(),
        )
        up = SignalPayload(target_token_id="0xtokenA", market_id="mkt-1",
                           direction=Direction.UP, confidence=Decimal("80"))
        # Pfad 3: echter Risiko-Reject ueber das Event-Exposure-Limit.
        # Order ist exakt max_order_size_shares (100 Shares * ~0.615 = 61,50);
        # ein Limit darunter -> MAX_EVENT_EXPOSURE. Alle vier Pfade laufen
        # ueber dieselbe Engine-Instanz, weil die Senke genau eine Quelle
        # beobachtet (sonst waere ihr Drain-Zaehler mehrdeutig).
        # RiskConfig ist frozen, also ueber model_copy ersetzen.
        engine.risk.config = engine.risk.config.model_copy(
            update={"max_event_exposure_usdc": Decimal("10")})

        r1 = engine.on_signal(neutral, book)
        r2 = engine.on_signal(up, no_liquidity)
        r3 = engine.on_signal(up, book)
        # Pfad 4: genehmigter Fill — hier stuerzte die Persistenz vorher ab.
        engine.risk.config = engine.risk.config.model_copy(
            update={"max_event_exposure_usdc": Decimal("1000")})
        r4 = engine.on_signal(up, book)

        assert not r1.approved and not r2.approved and not r3.approved, \
            (r1.reject_reason, r2.reject_reason, r3.reject_reason)
        assert r4.approved

        assert sink.drain() == 4
        assert sink.drain() == 0  # Idempotenz

        conn = sqlite3.connect(str(Path(tmp) / "u1" / "shadow" / "shadow.db"))
        rows = conn.execute("SELECT approved, reject_reason FROM telemetry ORDER BY seq").fetchall()
        conn.close()
        assert [r[0] for r in rows] == [0, 0, 0, 1]
        # Jeder Pfad liefert einen Enum-Wert — nie NULL, auch nicht approved.
        assert all(r[1] for r in rows), rows
        assert rows[3][1] == "NONE", rows[3][1]
        store.close()
    print("OK test_telemetry_all_production_paths")


def test_record_rejects_none_at_construction() -> None:
    """Vertrag: `TelemetryRecord.reject_reason` ist immer ein RejectReason-Enum.

    F2b/B1: ADR-13 wird durch die Pydantic-Felddeklaration durchgesetzt
    (nicht mehr per Dataclass-``__post_init__``). Das ist Verschärfung:
    greift auf jedem Konstruktionspfad. Dieser Test toetet den Mutanten
    an der Quelle (None / Rohstring / int).
    """
    from pydantic import ValidationError

    base = dict(signal_id=uuid.uuid4(), order_id=uuid.uuid4(), latency_ms=1.0,
                approved=False, status=None)
    for bad in (None, "invalid_price", 42):
        try:
            TelemetryRecord(**base, reject_reason=bad)  # type: ignore[arg-type]
            raise AssertionError(f"{bad!r} haette abgelehnt werden muessen")
        except (TypeError, ValidationError):
            pass
    # Der genehmigte Pfad ist explizit erlaubt und der Default.
    rec = TelemetryRecord(**base)
    assert rec.reject_reason is RejectReason.NONE
    # frozen: Nachtraegliche Manipulation ist ebenfalls blockiert.
    try:
        rec.reject_reason = None  # type: ignore[misc]
        raise AssertionError("frozen-Verletzung nicht erkannt")
    except Exception as exc:
        assert "frozen" in str(exc).lower() or isinstance(exc, (AttributeError, TypeError, ValidationError))
    print("OK test_record_rejects_none_at_construction")


def test_telemetry_record_json_roundtrip() -> None:
    """F2b/B1: Schema-Zeuge — Ablehnungspfad ueber JSON (Persistenz-TEXT-Felder)."""
    rec = TelemetryRecord(
        signal_id=uuid.uuid4(),
        order_id=uuid.uuid4(),
        latency_ms=1.83,
        approved=False,
        status=None,
        reject_reason=RejectReason.MAX_POSITION_SIZE,
        requested_size=Decimal("31"),
        decision_seq=3,
    )
    restored = TelemetryRecord.model_validate_json(rec.model_dump_json())
    assert restored == rec
    assert restored.reject_reason is RejectReason.MAX_POSITION_SIZE
    assert restored.requested_size == Decimal("31")
    assert restored.status is None
    print("OK test_telemetry_record_json_roundtrip")


def test_write_telemetry_db_roundtrip() -> None:
    """Persistenz-Sync: Spaltengrenze, nicht nur Transport-Dict.

    Liest aus der DB zurück. Decimal bleibt TEXT (kein float/REAL);
    ``Decimal(str(stored))`` ist der dokumentierte TEXT-Pfad.
    """
    import sqlite3

    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        rec = TelemetryRecord(
            signal_id=uuid.uuid4(),
            order_id=uuid.uuid4(),
            latency_ms=1.83,
            approved=False,
            status=None,
            reject_reason=RejectReason.MAX_POSITION_SIZE,
            requested_size=Decimal("31"),
            decision_seq=3,
        )
        store.write_telemetry(rec)
        conn = sqlite3.connect(str(Path(tmp) / "u1" / "shadow" / "shadow.db"))
        conn.row_factory = sqlite3.Row
        stored = conn.execute(
            "SELECT signal_id, order_id, status, reject_reason, requested_size, "
            "decision_seq, approved FROM telemetry WHERE signal_id = ?",
            (str(rec.signal_id),),
        ).fetchone()
        conn.close()
        store.close()

        expected = rec.model_dump(mode="json")
        assert stored is not None
        assert stored["signal_id"] == expected["signal_id"]
        assert stored["order_id"] == expected["order_id"]
        assert stored["status"] == expected["status"]
        assert stored["reject_reason"] == expected["reject_reason"]
        assert Decimal(str(stored["requested_size"])) == rec.requested_size
        assert stored["requested_size"] == "31"  # TEXT-Kanon, nicht REAL/float
        assert stored["decision_seq"] == 3
        assert stored["approved"] == 0
    print("OK test_write_telemetry_db_roundtrip")


def test_write_fill_db_roundtrip() -> None:
    """Persistenz-Sync analog fuer FillResult — Spaltengrenze + TEXT-Decimal."""
    import sqlite3

    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        fill = FillResult(
            order_id=uuid.uuid4(),
            execution_price=Decimal("0.419"),
            executed_size=Decimal("31"),
            slippage=Decimal("-1.18"),
            fee=Decimal("0"),
            latency_ms=0.29,
        )
        store.write_fill(fill, fill_idx=0, requested_size=Decimal("50"))
        conn = sqlite3.connect(str(Path(tmp) / "u1" / "shadow" / "shadow.db"))
        conn.row_factory = sqlite3.Row
        stored = conn.execute(
            "SELECT order_id, execution_price, executed_size, slippage, fee, "
            "requested_size, latency_ms FROM fills WHERE order_id = ?",
            (str(fill.order_id),),
        ).fetchone()
        conn.close()
        store.close()

        assert stored is not None
        assert stored["order_id"] == str(fill.order_id)
        assert Decimal(stored["execution_price"]) == Decimal("0.419")
        assert stored["execution_price"] == "0.419"  # kanonisches TEXT, nicht 1E-…
        assert Decimal(stored["executed_size"]) == Decimal("31")
        assert Decimal(stored["slippage"]) == Decimal("-1.18")
        assert Decimal(stored["requested_size"]) == Decimal("50")
        assert stored["latency_ms"] == 0.29
    print("OK test_write_fill_db_roundtrip")


def test_resting_status_db_roundtrip() -> None:
    """RESTING ueber Persistenz hinweg — Schema hat kein CHECK, Status als TEXT."""
    import sqlite3

    from order_execution_engine.models import OrderStatus

    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        rec = TelemetryRecord(
            signal_id=uuid.uuid4(),
            order_id=uuid.uuid4(),
            latency_ms=0.0,
            approved=True,
            status=OrderStatus.RESTING,
            reject_reason=RejectReason.NONE,
            requested_size=Decimal("200"),
            decision_seq=7,
        )
        store.write_telemetry(rec)
        conn = sqlite3.connect(str(Path(tmp) / "u1" / "shadow" / "shadow.db"))
        row = conn.execute(
            "SELECT status, reject_reason FROM telemetry WHERE signal_id = ?",
            (str(rec.signal_id),),
        ).fetchone()
        conn.close()
        store.close()
        assert row is not None
        assert row[0] == "RESTING"
        assert row[1] == "NONE"
    print("OK test_resting_status_db_roundtrip")


def test_expired_status_db_roundtrip() -> None:
    """EXPIRED ueber Persistenz — Schema ohne CHECK, Status als TEXT (wie RESTING)."""
    import sqlite3

    from order_execution_engine.models import OrderStatus

    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        rec = TelemetryRecord(
            signal_id=uuid.uuid4(),
            order_id=uuid.uuid4(),
            latency_ms=0.0,
            approved=True,
            status=OrderStatus.EXPIRED,
            reject_reason=RejectReason.NONE,
            requested_size=Decimal("200"),
            decision_seq=9,
        )
        store.write_telemetry(rec)
        conn = sqlite3.connect(str(Path(tmp) / "u1" / "shadow" / "shadow.db"))
        row = conn.execute(
            "SELECT status, reject_reason FROM telemetry WHERE signal_id = ?",
            (str(rec.signal_id),),
        ).fetchone()
        conn.close()
        store.close()
        assert row is not None
        assert row[0] == "EXPIRED"
        assert row[1] == "NONE"
    print("OK test_expired_status_db_roundtrip")


def test_storage_normalizes_none_at_boundary_defensively() -> None:
    """Defensive Schicht — NICHT der produktive Vertrag.

    Produktiver Vertrag: `TelemetryRecord` lehnt None an der Konstruktion ab
    (siehe `test_record_rejects_none_at_construction`). Diese Senke deckt den
    Fall ab, dass ein typ-ignorierender Aufrufer den Record per Stub/Duck-Typ
    nachbaut. Charter `diagnostic_only=true`: Telemetrie darf den Engine-Loop
    nie crashen. Normalisierung auf `RejectReason.NONE` (die Spalte ist
    NOT NULL per Vertrag), mit Warnung — stilles Normalisieren wuerde genau
    die Bugs maskieren, die es ueberleben laesst.
    """
    import logging
    import sqlite3
    from types import SimpleNamespace

    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        # Typ-ignorierender Aufrufer: alles valid ausser reject_reason.
        stub = SimpleNamespace(
            signal_id=uuid.uuid4(), order_id=None, latency_ms=1.0,
            approved=False, reject_reason=None, status=None,
            requested_size=None, decision_seq=0,
        )
        with __import__("unittest").TestCase().assertLogs(
                "order_execution_engine.persistence", level="WARNING") as captured:
            store.write_telemetry(stub)  # type: ignore[arg-type]
        assert any("kein RejectReason" in m for m in captured.output), captured.output

        conn = sqlite3.connect(str(Path(tmp) / "u1" / "shadow" / "shadow.db"))
        row = conn.execute("SELECT reject_reason FROM telemetry").fetchone()
        conn.close()
        assert row is not None and row[0] == "NONE", row
        store.close()
    print("OK test_storage_normalizes_none_at_boundary_defensively")


def test_portfolio_snapshot_persistence() -> None:
    from order_execution_engine.models import OrderSide, Position
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        pf = VirtualPortfolio(cash=Decimal("9939.00"))
        pf.positions["t1"] = Position(token_id="t1", market_id="mA", side=OrderSide.BUY,
                                      avg_entry_price=Decimal("0.61"), size=Decimal("100"))
        store.write_portfolio(pf, user_id="u1")
        store.close()
        import sqlite3, json
        conn = sqlite3.connect(str(Path(tmp) / "u1" / "shadow" / "shadow.db"))
        row = conn.execute("SELECT cash, positions_json FROM portfolio_snapshots").fetchone()
        assert row[0] == "9939.00"
        positions = json.loads(row[1])
        assert positions["t1"]["avg_entry_price"] == "0.61"
        assert Decimal(row[0]) == Decimal("9939.00")
        conn.close()
    print("OK test_portfolio_snapshot_persistence")


def test_dispatch_rejects_negative_size() -> None:
    """Randfall-Prüfung der anderen Session: size=-5 verworfen."""
    from order_execution_engine.market_data_feed import PolymarketWsFeed, PolySentinelBookHandler
    from order_execution_engine.market_data_feed import SnapshotCache
    cache = SnapshotCache()
    feed = PolymarketWsFeed(PolySentinelBookHandler(cache))
    feed._dispatch({
        "event_type": "book", "market": "0xtokenA",
        "bids": [{"price": "0.60", "size": "100"}],
        "asks": [{"price": "0.62", "size": "150"}, {"price": "0.70", "size": "500"}],
    })
    feed._dispatch({
        "event_type": "price_change", "market": "0xtokenA",
        "changes": [
            {"side": "SELL", "price": "0.62", "size": "-5"},   # verworfen
            {"side": "SELL", "price": "0", "size": "50"},      # verworfen
        ],
    })
    snap = cache.get("0xtokenA")
    assert snap is not None
    assert [a.price for a in snap.asks] == [Decimal("0.62"), Decimal("0.70")]
    assert snap.asks[0].size == Decimal("150")  # unverändert, kein -5
    print("OK test_dispatch_rejects_negative_size")


def test_replay_matches_live_snapshot_decimal_identical() -> None:
    """Vertrag: Live-snapshot == Replay-snapshot (Decimal, DTO-Gleichheit)."""
    from order_execution_engine.shadow_replay import ShadowReplay

    with tempfile.TemporaryDirectory() as tmp:
        eng = ShadowExecutionEngine(
            risk_config=RiskConfig(max_order_size_shares=Decimal("100")),
        )
        book = MarketSnapshot(
            token_id="0xtokenA",
            bids=(OrderBookLevel(Decimal("0.59"), Decimal("500")),),
            asks=(OrderBookLevel(Decimal("0.61"), Decimal("500")),),
        )
        up = SignalPayload(
            target_token_id="0xtokenA", market_id="mkt-1",
            direction=Direction.UP, confidence=Decimal("80"),
        )
        # 1) FAK-Fill
        r1 = eng.on_signal(up, book)
        assert r1.approved and r1.status is not None
        # 2) Risk-Reject (Exposure-Limit)
        eng.risk.config = eng.risk.config.model_copy(
            update={"max_event_exposure_usdc": Decimal("1")},
        )
        r2 = eng.on_signal(up, book)
        assert not r2.approved
        # 3) Neutral-Reject (kein Fill)
        neutral = SignalPayload(
            target_token_id="0xtokenA", market_id="mkt-1",
            direction=Direction.NEUTRAL, confidence=Decimal("80"),
        )
        r3 = eng.on_signal(neutral, book)
        assert not r3.approved

        marks = {"0xtokenA": Decimal("0.61")}
        as_of = eng.telemetry._decision_seq
        live = eng.portfolio.snapshot(marks, as_of_seq=as_of)

        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        sink = TelemetrySink(store, eng.telemetry, fills_provider=eng.fills_for)
        assert sink.drain() >= 3

        replay = ShadowReplay(store, Decimal("10000.00")).reconstruct(
            mark_prices=marks, as_of_seq=as_of,
        )
        assert replay.gaps == ()
        assert replay.unfilled_rows == 0
        assert replay.fills_folded >= 1
        assert replay.snapshot == live
        assert replay.resting_orders == ()
        store.close()
    print("OK test_replay_matches_live_snapshot_decimal_identical")


def test_replay_resting_orders_survive_then_clear_on_expired() -> None:
    """GTC ruht durch Replay (Rest korrekt); nach EXPIRED-Telemetrie Liste leer.

    Kein Schema-Neu: Status aus letztem Telemetrie-Record, remaining =
    requested_size − Σ fills. PARTIALLY_FILLED+Rest zaehlt als ruhend (GTC).
    """
    from order_execution_engine.models import OrderStatus
    from order_execution_engine.shadow_replay import ShadowReplay

    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        oid = uuid.uuid4()
        sid = uuid.uuid4()
        # Partial fill 200 von 400 → Rest 200 ruht
        store.write_telemetry(TelemetryRecord(
            signal_id=sid, order_id=oid, latency_ms=0.0, approved=True,
            status=OrderStatus.PARTIALLY_FILLED, reject_reason=RejectReason.NONE,
            requested_size=Decimal("400"), decision_seq=1,
        ))
        store.write_fill(
            FillResult(
                order_id=oid, execution_price=Decimal("0.61"),
                executed_size=Decimal("200"), side=OrderSide.BUY,
                token_id="0xtokenA", market_id="mkt-1",
            ),
            fill_idx=0, decision_seq=1,
        )

        mid = ShadowReplay(store, Decimal("10000.00")).reconstruct(as_of_seq=1)
        assert len(mid.resting_orders) == 1
        rest = mid.resting_orders[0]
        assert rest.order_id == oid
        assert rest.remaining == Decimal("200")
        assert rest.token_id == "0xtokenA"
        assert rest.market_id == "mkt-1"
        assert rest.resting_at_seq == 1

        store.write_telemetry(TelemetryRecord(
            signal_id=sid, order_id=oid, latency_ms=0.0, approved=True,
            status=OrderStatus.EXPIRED, reject_reason=RejectReason.NONE,
            requested_size=Decimal("400"), decision_seq=2,
        ))
        after = ShadowReplay(store, Decimal("10000.00")).reconstruct()
        assert after.resting_orders == ()
        store.close()
    print("OK test_replay_resting_orders_survive_then_clear_on_expired")


def test_replay_marks_gap_and_continues() -> None:
    """decision_seq-Luecke: markieren, nicht abbrechen."""
    import sqlite3

    from order_execution_engine.shadow_replay import ShadowReplay

    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        for seq in (1, 2, 3):
            store.write_telemetry(TelemetryRecord(
                signal_id=uuid.uuid4(),
                order_id=None,
                latency_ms=0.0,
                approved=False,
                status=None,
                reject_reason=RejectReason.INVALID_PRICE,
                decision_seq=seq,
            ))
        db = Path(tmp) / "u1" / "shadow" / "shadow.db"
        conn = sqlite3.connect(str(db))
        conn.execute("DELETE FROM telemetry WHERE decision_seq = 2")
        conn.commit()
        conn.close()

        replay = ShadowReplay(store, Decimal("10000.00")).reconstruct()
        assert replay.gaps == (2,)
        assert replay.snapshot.cash == Decimal("10000.00")
        store.close()
    print("OK test_replay_marks_gap_and_continues")


def test_replay_counts_unfilled_legacy_rows() -> None:
    """Edit-0-NULL: unfaltbare Legacy-Zeilen werden gezaehlt, nicht geraten."""
    from order_execution_engine.shadow_replay import ShadowReplay

    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        # Fold-komplett
        good = FillResult(
            order_id=uuid.uuid4(),
            execution_price=Decimal("0.61"),
            executed_size=Decimal("10"),
            side=OrderSide.BUY,
            token_id="0xtokenA",
            market_id="mkt-1",
        )
        store.write_fill(good, fill_idx=0, decision_seq=1)
        # Legacy ohne side/token/market
        legacy = FillResult(
            order_id=uuid.uuid4(),
            execution_price=Decimal("0.62"),
            executed_size=Decimal("5"),
        )
        store.write_fill(legacy, fill_idx=0, decision_seq=2)

        replay = ShadowReplay(store, Decimal("10000.00")).reconstruct(
            mark_prices={"0xtokenA": Decimal("0.61")},
        )
        assert replay.unfilled_rows == 1
        assert replay.fills_folded == 1
        assert replay.snapshot.positions["0xtokenA"] == Decimal("10")
        store.close()
    print("OK test_replay_counts_unfilled_legacy_rows")


def test_peak_event_roundtrip() -> None:
    """Befund 4: PeakEvents überleben Write/Load exakt (Decimal als TEXT)."""
    from order_execution_engine.models import PeakEvent
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        ev0 = PeakEvent(seq=0, marks={"0xtokenA": Decimal("0.795")}, journal_pos=1,
                        peak_equity=Decimal("10037.123456789012345678"))
        ev1 = PeakEvent(seq=1, marks={"0xtokenA": Decimal("0.855"),
                                      "0xtokenB": Decimal("0.0000000000000001")},
                        journal_pos=2, peak_equity=Decimal("10060.5"))
        store.write_peak_event(ev0)
        store.write_peak_event(ev1)
        assert store.read_peak_events() == [ev0, ev1]
        store.close()
    print("OK test_peak_event_roundtrip")


def test_peak_event_rewrite_and_conflict() -> None:
    """Befund 4: Identischer Re-Drain ok, Inhaltwechsel unter seq ist Befund."""
    from order_execution_engine.models import PeakEvent
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        ev = PeakEvent(seq=0, marks={"t": Decimal("0.5")}, journal_pos=0,
                       peak_equity=Decimal("10001"))
        store.write_peak_event(ev)
        store.write_peak_event(ev)
        assert len(store.read_peak_events()) == 1
        forged = ev.model_copy(update={"peak_equity": Decimal("99999")})
        try:
            store.write_peak_event(forged)
            raise AssertionError("Append-only-Konflikt hätte ValueError werfen müssen")
        except ValueError:
            pass
        assert store.read_peak_events()[0].peak_equity == Decimal("10001")
        store.close()
    print("OK test_peak_event_rewrite_and_conflict")


def test_telemetry_sink_drains_peak_events() -> None:
    """Befund 4: Sink persistiert PeakEvent-Zeugen inkrementell."""
    with tempfile.TemporaryDirectory() as tmp:
        engine = ShadowExecutionEngine(risk_config=RiskConfig(max_order_size_shares=Decimal("100")))
        snap = MarketSnapshot(
            token_id="0xtokenA",
            bids=(OrderBookLevel(Decimal("0.59"), Decimal("500")),),
            asks=(OrderBookLevel(Decimal("0.61"), Decimal("500")),),
        )
        sig = SignalPayload(target_token_id="0xtokenA", market_id="mkt-1",
                            direction=Direction.UP, confidence=Decimal("80"))
        assert engine.on_signal(sig, snap).approved
        engine.on_book_update(MarketSnapshot(
            token_id="0xtokenA",
            bids=(OrderBookLevel(Decimal("0.79"), Decimal("500")),),
            asks=(OrderBookLevel(Decimal("0.80"), Decimal("500")),),
        ))
        assert len(engine.peak_events()) == 1

        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        sink = TelemetrySink(store, engine.telemetry,
                             fills_provider=engine.fills_for,
                             peak_events_provider=engine.peak_events)
        sink.drain()
        assert [e.seq for e in store.read_peak_events()] == [0]
        sink.drain()
        assert len(store.read_peak_events()) == 1
        engine.on_book_update(MarketSnapshot(
            token_id="0xtokenA",
            bids=(OrderBookLevel(Decimal("0.85"), Decimal("500")),),
            asks=(OrderBookLevel(Decimal("0.86"), Decimal("500")),),
        ))
        sink.drain()
        assert store.read_peak_events() == list(engine.peak_events())
        assert [e.seq for e in store.read_peak_events()] == [0, 1]
        store.close()
    print("OK test_telemetry_sink_drains_peak_events")


def test_peak_events_reload_clean_audit() -> None:
    """Befund 4 Pflicht: Reload aus DB erzeugt keine Ceiling-Befunde."""
    with tempfile.TemporaryDirectory() as tmp:
        eng = ShadowExecutionEngine(risk_config=RiskConfig(max_order_size_shares=Decimal("200")))
        sig = SignalPayload(target_token_id="0xtokenA", market_id="mkt-1",
                            direction=Direction.UP, confidence=Decimal("70"))
        eng.on_signal(sig, MarketSnapshot(
            token_id="0xtokenA",
            bids=(OrderBookLevel(Decimal("0.59"), Decimal("200")),),
            asks=(OrderBookLevel(Decimal("0.61"), Decimal("200")),),
        ))
        eng.on_book_update(MarketSnapshot(
            token_id="0xtokenA",
            bids=(OrderBookLevel(Decimal("0.79"), Decimal("200")),),
            asks=(OrderBookLevel(Decimal("0.80"), Decimal("200")),),
        ))
        assert len(eng.peak_events()) == 1

        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        for ev in eng.peak_events():
            store.write_peak_event(ev)
        loaded = store.read_peak_events()
        store.close()
        assert loaded == list(eng.peak_events())

        eng2 = ShadowExecutionEngine(risk_config=RiskConfig(max_order_size_shares=Decimal("200")))
        eng2._execution_journal.extend(eng.execution_journal())
        eng2._mark_prices.update(eng.current_marks())
        eng2.portfolio = eng.portfolio.model_copy(deep=True)
        assert eng2.restore_peak_events(loaded) == 1
        report = eng2.audit_shadow_state()
        assert report.ok, report.findings
        assert not any(f.path.startswith("peak_equity.ceiling") for f in report.findings)
    print("OK test_peak_events_reload_clean_audit")


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and fn.__name__.startswith("test_"):
            fn()
    print("ALLE PERSISTENCE-TESTS BESTANDEN")
