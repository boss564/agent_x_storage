"""Tag-7 Variante C: Fill-Pfad gegen den echten Handler, Datenquelle ersetzt.

Zwei Fälle aus demselben Korpus, damit C unterscheiden kann:

* Positiv: konstruiertes Book mit Bid/Ask -> Fill, fill_ratio > 0, VWAP
  innerhalb des Spreads.
* Negativ: konstruiertes Book ohne Bid/Ask -> ``INVALID_PRICE``, kein Fill.

Ersetzt wird ausschliesslich die Datenquelle (der Snapshot). Die
Entscheidungslogik der Engine (``ShadowExecutionEngine.on_signal``) und der
Fill-Handler (``PaperMatchEngine`` -> ``FillSimulator.cross``) laufen
unveraendert. Kein Mock der Entscheidung.

Isolation: eigener ``user_id`` -> eigene ``shadow.db`` unter ``tmp_path``.
Die Messlaeufe (``run_id`` 8/9) werden nicht beruehrt; der Test assertiert
das per Zeilenvergleich vor/nach, falls die Mess-DB vorhanden ist.
"""

from __future__ import annotations

import sqlite3
import uuid
from decimal import Decimal
from pathlib import Path

from order_execution_engine.fill_simulator import FillSimConfig
from order_execution_engine.models import (
    Direction,
    RejectReason,
    SignalPayload,
)
from order_execution_engine.persistence import SQLiteShadowStorage, TelemetrySink
from order_execution_engine.shadow_execution_engine import (
    MarketSnapshot,
    OrderBookLevel,
    RiskConfig,
    ShadowExecutionEngine,
    TelemetryLogger,
)

REPLAY_USER = "replay_sentinel"
MEASURE_DB = (
    Path.home() / "Library" / "Application Support" / "agentx"
    / "shadow_live" / "shadow" / "shadow" / "shadow.db"
)


def _level(price: str, size: str) -> OrderBookLevel:
    return OrderBookLevel(Decimal(price), Decimal(size))


def _engine(tmp_path: Path) -> tuple[ShadowExecutionEngine, SQLiteShadowStorage, TelemetrySink]:
    """Echte Engine an einer isolierten DB (eigener user_id)."""
    store = SQLiteShadowStorage.for_user(tmp_path, REPLAY_USER)
    store.open_run(git_commit="replay", config_json={"replay": True})
    telemetry = TelemetryLogger(
        initial_decision_seq=store.latest_decision_seq(),
    )
    engine = ShadowExecutionEngine(
        risk_config=RiskConfig(max_order_size_shares=Decimal("100")),
        telemetry=telemetry,
        fill_sim_config=FillSimConfig(max_book_age_ms=60_000),
    )
    # Produktiver Persistenzpfad, nur das Ziel ist ein anderes Verzeichnis.
    sink = TelemetrySink(
        store, telemetry,
        fills_provider=lambda oid: engine._fills_by_order.get(oid, ()),
    )
    return engine, store, sink


def _signal(token: str) -> SignalPayload:
    return SignalPayload(
        signal_id=uuid.UUID(int=7),
        target_token_id=token,
        market_id="replay-market",
        direction=Direction.UP,
        confidence=Decimal("80"),
        suggested_price=Decimal("0.50"),
    )


def _measure_counts() -> dict[str, int] | None:
    """Zeilen der Messlaeufe 8/9 - Beweis, dass der Replay nichts veraendert."""
    if not MEASURE_DB.exists():
        return None
    con = sqlite3.connect(f"file:{MEASURE_DB}?mode=ro", uri=True)
    try:
        return {
            table: int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("telemetry", "dispatched_signals", "bridge_discards",
                          "telemetry_fill_metrics")
        }
    finally:
        con.close()


def test_c1_positive_fill_inside_spread(tmp_path: Path) -> None:
    """(a) Book mit Bid/Ask -> Fill, fill_ratio > 0, VWAP im Spread."""
    engine, store, sink = _engine(tmp_path)
    book = MarketSnapshot(
        token_id="tok-positive",
        bids=(_level("0.48", "200"),),
        asks=(_level("0.50", "40"), _level("0.55", "80")),
    )
    report = engine.on_signal(_signal("tok-positive"), book)

    assert report.approved, report.reject_reason
    assert report.reject_reason is RejectReason.NONE
    assert report.fills, "Positivfall muss fuellen"
    record = engine.telemetry._records[-1]
    metrics = record.fill_metrics
    assert metrics is not None
    assert metrics.fill_ratio > 0
    # VWAP innerhalb des konstruierten Spreads.
    assert book.best_bid() < metrics.vwap
    assert metrics.vwap <= max(Decimal("0.55"), book.best_ask())
    assert metrics.levels_consumed >= 1
    sink.drain()
    persisted = store._conn.execute(
        "SELECT reject_reason FROM telemetry"
    ).fetchall()
    assert [r[0] for r in persisted] == ["NONE"]
    fill_rows = store._conn.execute(
        "SELECT COUNT(*) FROM telemetry_fill_metrics"
    ).fetchone()[0]
    assert fill_rows == 1
    print("OK test_c1_positive_fill_inside_spread")
    store.close()


def test_c2_negative_no_book_rejects_invalid_price(tmp_path: Path) -> None:
    """(b) Book ohne Bid/Ask -> INVALID_PRICE, kein Fill."""
    engine, store, sink = _engine(tmp_path)
    empty = MarketSnapshot(token_id="tok-negative")
    before_fills = len(engine.telemetry._records)

    report = engine.on_signal(_signal("tok-negative"), empty)

    assert not report.approved
    assert report.reject_reason is RejectReason.INVALID_PRICE
    assert report.fills == ()
    records = engine.telemetry._records[before_fills:]
    assert len(records) == 1
    assert records[0].reject_reason is RejectReason.INVALID_PRICE
    assert records[0].fill_metrics is None
    sink.drain()
    assert store._conn.execute(
        "SELECT COUNT(*) FROM telemetry WHERE reject_reason='INVALID_PRICE'"
    ).fetchone()[0] == 1
    assert store._conn.execute(
        "SELECT COUNT(*) FROM telemetry_fill_metrics"
    ).fetchone()[0] == 0
    print("OK test_c2_negative_no_book_rejects_invalid_price")
    store.close()


def test_c3_replay_does_not_touch_measurement_db(tmp_path: Path) -> None:
    """(c) Replay schreibt in eigene DB; Messlaeufe bleiben zeilengleich."""
    before = _measure_counts()
    engine, store, sink = _engine(tmp_path)
    engine.on_signal(
        _signal("tok-a"),
        MarketSnapshot(
            token_id="tok-a",
            bids=(_level("0.48", "100"),),
            asks=(_level("0.50", "100"),),
        ),
    )
    engine.on_signal(_signal("tok-b"), MarketSnapshot(token_id="tok-b"))
    sink.drain()
    after = _measure_counts()

    assert before == after, (before, after)
    rows = store._conn.execute(
        "SELECT reject_reason, COUNT(*) FROM telemetry GROUP BY 1"
    ).fetchall()
    assert dict(rows) == {"NONE": 1, "INVALID_PRICE": 1}
    print("OK test_c3_replay_does_not_touch_measurement_db")
    store.close()
