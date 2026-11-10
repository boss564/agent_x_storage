"""Phase B — Migration v8 + Stage-Funnel + telemetry_seq-Bindung."""

from __future__ import annotations

import sqlite3
import tempfile
import uuid
from decimal import Decimal
from pathlib import Path

from order_execution_engine.models import Direction, RejectReason, SignalPayload
from order_execution_engine.news_bridge import SIGNAL_NAMESPACE
from order_execution_engine.persistence import (
    LEGACY_BARE_CANONICAL,
    LEGACY_BARE_UNRESOLVED,
    SCHEMA_VERSION,
    SIGNAL_NAMESPACE as PERSIST_NS,
    SQLiteShadowStorage,
    TelemetrySink,
)
from order_execution_engine.shadow_execution_engine import (
    MarketSnapshot,
    OrderBookLevel,
    ShadowExecutionEngine,
    TelemetryRecord,
)


def _book() -> MarketSnapshot:
    return MarketSnapshot(
        token_id="0xtokenA",
        asks=(OrderBookLevel(Decimal("0.61"), Decimal("200")),),
        bids=(OrderBookLevel(Decimal("0.59"), Decimal("150")),),
    )


def test_schema_version_is_9() -> None:
    """Schritt 1 / W1: SCHEMA_VERSION=9 (v8-Spalten bleiben, + telemetry_class)."""
    assert SCHEMA_VERSION == 9
    assert PERSIST_NS == SIGNAL_NAMESPACE
    assert LEGACY_BARE_UNRESOLVED == "unresolved_asset"
    assert LEGACY_BARE_CANONICAL == "unresolved_asset:empty_list"
    print("OK test_schema_version_is_9")


def test_migrate_v8_idempotent_and_user_version() -> None:
    """B-Abnahme 1: Migration zweimal ohne Fehler; schema_meta/user_version aktuell."""
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        # second open = second migrate pass
        store.close()
        store2 = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        row = store2._conn.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
        assert row is not None and int(row[0]) == SCHEMA_VERSION
        uv = store2._conn.execute("PRAGMA user_version").fetchone()[0]
        assert int(uv) == SCHEMA_VERSION
        cols = {
            r[1] for r in store2._conn.execute("PRAGMA table_info(telemetry)")
        }
        assert "reject_detail" in cols
        assert "reject_context_json" in cols
        assert "telemetry_class" in cols  # v9
        disp = {
            r[1]
            for r in store2._conn.execute("PRAGMA table_info(dispatched_signals)")
        }
        assert "signal_id" in disp
        tables = {
            r[0]
            for r in store2._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "funnel_events" in tables
        store2.close()
    print("OK test_migrate_v8_idempotent_and_user_version")


def test_reject_detail_persisted_new_rows_only() -> None:
    """B-Abnahme 2: neue Reject-Zeilen tragen reject_detail; alte bleiben NULL."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "u1" / "shadow" / "shadow.db"
        db.parent.mkdir(parents=True)
        # Simulate pre-v8 row by raw insert after schema create.
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        store._conn.execute(
            "INSERT INTO telemetry (signal_id, latency_ms, approved, reject_reason)"
            " VALUES ('legacy-sig', 1.0, 0, 'INVALID_PRICE')"
        )
        store._conn.commit()
        eng = ShadowExecutionEngine()
        eng.on_signal(
            SignalPayload(
                target_token_id="0xtokenA", market_id="mkt-1",
                direction=Direction.NEUTRAL, confidence=Decimal("50"),
            ),
            _book(),
        )
        TelemetrySink(store, eng.telemetry).drain()
        rows = store._conn.execute(
            "SELECT signal_id, reject_reason, reject_detail FROM telemetry ORDER BY seq"
        ).fetchall()
        assert rows[0][2] is None, rows[0]  # legacy NULL
        assert rows[1][1] == "NEUTRAL_SIGNAL"
        assert rows[1][2] == "NEUTRAL_SIGNAL"
        store.close()
    print("OK test_reject_detail_persisted_new_rows_only")


def test_telemetry_seq_bound_on_claim() -> None:
    """B-Abnahme 3: telemetry_seq für Engine-Ingress-Rows belegt."""
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        item_id = "item-bind-1"
        assert store.claim_dispatch(item_id) is True
        signal_id = uuid.uuid5(SIGNAL_NAMESPACE, item_id)
        eng = ShadowExecutionEngine()
        eng.on_signal(
            SignalPayload(
                signal_id=signal_id,
                target_token_id="0xtokenA", market_id="mkt-1",
                direction=Direction.UP, confidence=Decimal("80"),
            ),
            _book(),
        )
        TelemetrySink(store, eng.telemetry).drain()
        row = store._conn.execute(
            "SELECT signal_id, telemetry_seq FROM dispatched_signals WHERE item_id=?",
            (item_id,),
        ).fetchone()
        assert row is not None
        assert row[0] == str(signal_id)
        assert row[1] is not None and int(row[1]) >= 1
        # Funnel stages present
        stages = {
            r[0]: r[1]
            for r in store._conn.execute(
                "SELECT stage, COUNT(*) FROM funnel_events GROUP BY stage"
            )
        }
        assert stages.get("out_claim", 0) >= 1
        assert stages.get("out_dispatch", 0) >= 1
        assert stages.get("approval", 0) >= 1
        store.close()
    print("OK test_telemetry_seq_bound_on_claim")


def test_funnel_claim_then_discard_includes_bare_taxonomy() -> None:
    """B-Abnahme 3 inkl. SP-1898 bare-Zeile als claim_then_discard."""
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        item_id = "9f568b38fd2b46b9d4d8d11943f4bd24"
        assert store.claim_dispatch(item_id) is True
        store.log_bridge_discard(item_id, LEGACY_BARE_UNRESOLVED)
        stages = list(
            store._conn.execute(
                "SELECT stage, reason FROM funnel_events ORDER BY seq"
            )
        )
        assert any(s[0] == "out_claim" for s in stages)
        ctd = [s for s in stages if s[0] == "claim_then_discard"]
        assert len(ctd) == 1
        assert ctd[0][1] == LEGACY_BARE_UNRESOLVED
        # Arithmetic pin: 1 claim = 1 claim_then_discard + 0 in_engine
        claims = store._conn.execute(
            "SELECT COUNT(*) FROM dispatched_signals"
        ).fetchone()[0]
        ctd_n = store._conn.execute(
            "SELECT COUNT(*) FROM funnel_events WHERE stage='claim_then_discard'"
        ).fetchone()[0]
        assert claims == ctd_n
        store.close()
    print("OK test_funnel_claim_then_discard_includes_bare_taxonomy")


def test_backfill_telemetry_seq_on_reopen() -> None:
    """v8 Backfill: bestehende Claims bekommen signal_id + seq-Bindung."""
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        item_id = "legacy-claim"
        signal_id = str(uuid.uuid5(SIGNAL_NAMESPACE, item_id))
        # Pretend pre-v8 claim (null signal_id) — force null after insert
        store.claim_dispatch(item_id)
        store._conn.execute(
            "UPDATE dispatched_signals SET signal_id=NULL, telemetry_seq=NULL"
            " WHERE item_id=?",
            (item_id,),
        )
        store._conn.execute(
            "INSERT INTO telemetry (signal_id, latency_ms, approved, reject_reason)"
            " VALUES (?, 1.0, 0, 'STALE_SNAPSHOT')",
            (signal_id,),
        )
        store._conn.commit()
        store.close()
        # Re-open triggers migrate_v8 backfill
        store2 = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        row = store2._conn.execute(
            "SELECT signal_id, telemetry_seq FROM dispatched_signals WHERE item_id=?",
            (item_id,),
        ).fetchone()
        assert row[0] == signal_id
        assert row[1] is not None
        store2.close()
    print("OK test_backfill_telemetry_seq_on_reopen")


def test_sp1925_reject_detail_chain_e2e_persisted() -> None:
    """SP-1925: WS/Cache/Engine-Reject → reject_detail gesetzt und persistiert.

    Deckt die Live-Lücke run_id=12 (STALE_SNAPSHOT ohne Detail) und die
    übrigen Reject-Pfade, die das harte 100-%-Gate berühren.
    """
    from order_execution_engine.fill_simulator import FillSimConfig
    from order_execution_engine.models import RiskConfig

    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")

        # 1) STALE_SNAPSHOT (Live-NULL-Fall)
        eng = ShadowExecutionEngine(
            risk_config=RiskConfig(max_order_size_shares=Decimal("100")),
            fill_sim_config=FillSimConfig(max_book_age_ms=500),
        )
        aged = MarketSnapshot(
            token_id="0xtokenA",
            asks=(OrderBookLevel(Decimal("0.61"), Decimal("200")),),
            bids=(OrderBookLevel(Decimal("0.59"), Decimal("150")),),
            received_at=1.0,
        )
        eng.on_signal(
            SignalPayload(
                target_token_id="0xtokenA", market_id="mkt-1",
                direction=Direction.UP, confidence=Decimal("80"),
            ),
            aged,
        )
        TelemetrySink(store, eng.telemetry).drain()

        # 2) NEUTRAL_SIGNAL
        eng2 = ShadowExecutionEngine()
        eng2.on_signal(
            SignalPayload(
                target_token_id="0xtokenA", market_id="mkt-1",
                direction=Direction.NEUTRAL, confidence=Decimal("50"),
            ),
            _book(),
        )
        TelemetrySink(store, eng2.telemetry).drain()

        # 3) NO_SNAPSHOT
        eng3 = ShadowExecutionEngine()
        eng3.on_signal(
            SignalPayload(
                target_token_id="0xtokenA", market_id="mkt-1",
                direction=Direction.UP, confidence=Decimal("80"),
            ),
            None,
        )
        TelemetrySink(store, eng3.telemetry).drain()

        # 4) EMPTY_SIDE (book, ask missing for BUY)
        eng4 = ShadowExecutionEngine()
        empty_ask = MarketSnapshot(
            token_id="0xtokenA",
            asks=(),
            bids=(OrderBookLevel(Decimal("0.59"), Decimal("150")),),
            source="book",
        )
        eng4.on_signal(
            SignalPayload(
                target_token_id="0xtokenA", market_id="mkt-1",
                direction=Direction.UP, confidence=Decimal("80"),
            ),
            empty_ask,
        )
        TelemetrySink(store, eng4.telemetry).drain()

        # 5) INVALID_PRICE (price outside 0..1)
        eng5 = ShadowExecutionEngine()
        bad = MarketSnapshot(
            token_id="0xtokenA",
            asks=(OrderBookLevel(Decimal("1.5"), Decimal("10")),),
            bids=(OrderBookLevel(Decimal("1.4"), Decimal("10")),),
        )
        eng5.on_signal(
            SignalPayload(
                target_token_id="0xtokenA", market_id="mkt-1",
                direction=Direction.UP, confidence=Decimal("80"),
            ),
            bad,
        )
        TelemetrySink(store, eng5.telemetry).drain()

        rows = store._conn.execute(
            "SELECT reject_reason, reject_detail, approved FROM telemetry"
            " WHERE approved = 0 ORDER BY seq"
        ).fetchall()
        assert len(rows) == 5, rows
        null_detail = [r for r in rows if r[1] is None]
        assert not null_detail, f"reject_detail NULL: {null_detail}"
        by_reason = {r[0]: r[1] for r in rows}
        assert by_reason["STALE_SNAPSHOT"] == "STALE_SNAPSHOT"
        assert by_reason["NEUTRAL_SIGNAL"] == "NEUTRAL_SIGNAL"
        assert by_reason["NO_SNAPSHOT"] == "NO_SNAPSHOT"
        assert by_reason["EMPTY_SIDE"] == "EMPTY_SIDE"
        assert by_reason["INVALID_PRICE"] == "INVALID_PRICE"
        store.close()
    print("OK test_sp1925_reject_detail_chain_e2e_persisted")


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and fn.__name__.startswith("test_"):
            fn()
    print("ALLE PHASE-B-MIGRATION-TESTS BESTANDEN")
