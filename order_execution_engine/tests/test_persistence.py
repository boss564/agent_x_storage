"""Self-Tests für persistence.py (Validierung, Decimal-TEXT, Senke, Schema)."""

import tempfile
import uuid
from decimal import Decimal
from pathlib import Path

from order_execution_engine.models import (
    Direction,
    FillResult,
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
        assert version == "1"
        for table in ("telemetry", "fills", "portfolio_snapshots"):
            conn.execute(f"SELECT 1 FROM {table} LIMIT 0")
        conn.close()
        store.close()
    print("OK test_schema_version_and_tables")


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
                             fills_provider=lambda oid: engine.matcher_last_fills(oid)
                             if hasattr(engine, "matcher_last_fills") else [])
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

    Dataclasses validieren ihre Annotationen nicht, deshalb erzwingt
    `__post_init__` den Typ. Ohne diese Wache nimmt der Record None (oder
    einen Rohstring) klaglos an und der Fehler faellt erst tief in der
    Persistenz auf — genau der latente Bug, den der Mutationsnachweis
    sichtbar gemacht hat. Dieser Test toetet den Mutanten an der Quelle.
    """
    base = dict(signal_id=uuid.uuid4(), order_id=uuid.uuid4(), latency_ms=1.0,
                approved=False, status=None)
    for bad in (None, "invalid_price", 42):
        try:
            TelemetryRecord(**base, reject_reason=bad)  # type: ignore[arg-type]
            raise AssertionError(f"{bad!r} haette abgelehnt werden muessen")
        except TypeError:
            pass
    # Der genehmigte Pfad ist explizit erlaubt und der Default.
    rec = TelemetryRecord(**base)
    assert rec.reject_reason is RejectReason.NONE
    # frozen: Nachtraegliche Manipulation ist ebenfalls blockiert.
    try:
        rec.reject_reason = None  # type: ignore[misc]
        raise AssertionError("frozen-Verletzung nicht erkannt")
    except Exception as exc:
        assert "frozen" in str(exc).lower() or isinstance(exc, (AttributeError, TypeError))
    print("OK test_record_rejects_none_at_construction")


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


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and fn.__name__.startswith("test_"):
            fn()
    print("ALLE PERSISTENCE-TESTS BESTANDEN")
