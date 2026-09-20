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


def test_telemetry_sink_approved_record_has_null_reject_reason() -> None:
    """Regression: genehmigte Records haben reject_reason=None.

    Das ist der Normalfall jeder gefuellten Order, nicht ein Randfall.
    `write_telemetry` rief vorher `record.reject_reason.value` auf und
    stuerzte mit AttributeError ab, sobald ein APPROVED-Record persistiert
    wurde — also bei jedem erfolgreichen Fill.
    """
    from order_execution_engine.models import OrderStatus
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        logger = TelemetryLogger()
        sink = TelemetrySink(store, logger)

        logger.log(TelemetryRecord(signal_id=uuid.uuid4(), order_id=uuid.uuid4(),
                                   latency_ms=1.5, approved=True, reject_reason=None,
                                   status=OrderStatus.FILLED))
        assert sink.drain() == 1

        logger.log(TelemetryRecord(signal_id=uuid.uuid4(), order_id=uuid.uuid4(),
                                   latency_ms=2.5, approved=False,
                                   reject_reason=RejectReason.MAX_POSITION_SIZE,
                                   status=OrderStatus.PENDING))
        assert sink.drain() == 1

        assert sink.drain() == 0  # idempotent, kein Doppel-Append
        store.close()
    print("OK test_telemetry_sink_approved_record_has_null_reject_reason")


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
