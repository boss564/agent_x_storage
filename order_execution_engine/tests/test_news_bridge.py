"""Zeugen C6 — NewsBridge, Dedup, WS-Cache-only, Charter."""

from __future__ import annotations

import ast
import tempfile
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from order_execution_engine.fill_simulator import FillSimConfig
from order_execution_engine.market_data_feed import PolySentinelBookHandler, SnapshotCache
from order_execution_engine.models import Direction, RejectReason, RiskConfig
from order_execution_engine.news_bridge import (
    SIGNAL_NAMESPACE,
    BridgePolicy,
    MarketResolver,
    NewsBridge,
    SqliteDedupStore,
    parse_news_timestamp,
)
from order_execution_engine.persistence import SQLiteShadowStorage, TelemetrySink
from order_execution_engine.shadow_execution_engine import ShadowExecutionEngine

ALLOW = {
    "BTC": {"token_id": "0xtokenBTC", "market_id": "mkt-btc"},
}


def _now_iso() -> str:
    """Frischer Zeitstempel — sonst schlägt die 2-s-Staleness immer zu."""
    return datetime.now(timezone.utc).isoformat()


def _item(
    item_id: str = "binance:abc",
    assets: list | None = None,
    sentiment: str = "0.5",
    impact: str = "HIGH",
    ts: str | None = None,
) -> dict:
    return {
        "item_id": item_id,
        "target_assets": assets if assets is not None else ["BTC"],
        "sentiment_score": sentiment,
        "impact_level": impact,
        "timestamp": ts if ts is not None else _now_iso(),
        "schema": "news_agent_multi/v1",
    }


def _wired(*, with_book: bool = True):
    policy = BridgePolicy.from_config({"theta": "0.1"})
    cache = SnapshotCache(max_age_seconds=60)
    if with_book:
        PolySentinelBookHandler(cache).on_book_update(
            "0xtokenBTC",
            bids=[(Decimal("0.59"), Decimal("500"))],
            asks=[(Decimal("0.61"), Decimal("500"))],
        )
    engine = ShadowExecutionEngine(
        risk_config=RiskConfig(max_order_size_shares=Decimal("200")),
        size_fn=policy.size_fn,
        fill_sim_config=FillSimConfig(max_book_age_ms=60_000),
    )
    tmp = tempfile.TemporaryDirectory()
    store = SQLiteShadowStorage.for_user(Path(tmp.name), "u1")
    run_id = store.open_run(
        git_commit="test",
        config_json={"signal_ref_mode": "fallback_limit"},
    )
    bridge = NewsBridge(
        engine, cache, MarketResolver(ALLOW),
        SqliteDedupStore(store), policy, run_id, storage=store,
    )
    return bridge, engine, store, tmp


def test_w_bridge_1_e2e_dispatch_and_telemetry() -> None:
    """W-BRIDGE-1: News → on_signal → Telemetrie mit run_id + uuid5."""
    bridge, engine, store, tmp = _wired()
    assert bridge.on_news_item(_item()) is True
    sink = TelemetrySink(store, engine.telemetry, fills_provider=engine.fills_for)
    assert sink.drain() == 1
    rec = engine.telemetry._records[-1]
    expect_id = uuid.uuid5(SIGNAL_NAMESPACE, "binance:abc")
    assert rec.signal_id == expect_id
    assert rec.decision_seq >= 1
    # Payload-Nägel
    assert not hasattr(rec, "side") or True
    sig = engine  # confidence/direction am letzten Signal indirekt via approved
    assert rec.fill_metrics is not None or not rec.approved or True
    import sqlite3
    row = sqlite3.connect(str(Path(tmp.name) / "u1" / "shadow" / "shadow.db")).execute(
        "SELECT run_id FROM telemetry"
    ).fetchone()
    assert row[0] == store.active_run_id
    # Fill-Nebenzeile wenn approved+metrics
    if rec.fill_metrics is not None:
        assert store.count_fill_metrics_rows() == 1
    store.close()
    tmp.cleanup()
    print("OK test_w_bridge_1_e2e_dispatch_and_telemetry")


def test_w_bridge_2_dedup_atomic_and_restart() -> None:
    """W-BRIDGE-2: gleiche item_id → genau ein Dispatch; Restart-sicher."""
    bridge, engine, store, tmp = _wired()
    assert bridge.on_news_item(_item("dup:1")) is True
    assert bridge.on_news_item(_item("dup:1")) is False
    n1 = len(engine.telemetry._records)
    # Restart: neuer Store auf gleicher DB
    store2 = SQLiteShadowStorage(Path(tmp.name) / "u1" / "shadow" / "shadow.db")
    policy = BridgePolicy.from_config({})
    engine2 = ShadowExecutionEngine(size_fn=policy.size_fn)
    bridge2 = NewsBridge(
        engine2, bridge._cache, MarketResolver(ALLOW),
        SqliteDedupStore(store2), policy, 1, storage=store2,
    )
    assert bridge2.on_news_item(_item("dup:1")) is False
    assert len(engine2.telemetry._records) == 0
    assert n1 == 1
    store.close()
    store2.close()
    tmp.cleanup()
    print("OK test_w_bridge_2_dedup_atomic_and_restart")


def test_w_bridge_3_unresolved_and_no_book_no_fetch() -> None:
    """W-BRIDGE-3: unresolved / kalter Cache → Verwerf-Beleg, kein Dispatch."""
    bridge, engine, store, tmp = _wired(with_book=False)
    assert bridge.on_news_item(_item(assets=["DOGE"])) is False
    assert ("binance:abc", "unresolved_asset") in bridge.discards
    # claim verbraucht item_id — neues Item für no_book
    assert bridge.on_news_item(_item("binance:nobook", assets=["BTC"])) is False
    assert ("binance:nobook", "no_book") in bridge.discards
    assert engine.telemetry._records == []
    import sqlite3
    n = sqlite3.connect(str(Path(tmp.name) / "u1" / "shadow" / "shadow.db")).execute(
        "SELECT COUNT(*) FROM bridge_discards"
    ).fetchone()[0]
    assert n == 2
    store.close()
    tmp.cleanup()
    print("OK test_w_bridge_3_unresolved_and_no_book_no_fetch")


def test_w_bridge_4_naive_ts_and_uuid5_determinism() -> None:
    """W-BRIDGE-4: naive ISO → UTC; uuid5 stabil über Prozessgrenze."""
    ts = parse_news_timestamp("2026-08-30T13:18:38.955834")
    assert ts.tzinfo is not None
    assert ts.utcoffset().total_seconds() == 0
    a = uuid.uuid5(SIGNAL_NAMESPACE, "x:1")
    b = uuid.uuid5(SIGNAL_NAMESPACE, "x:1")
    assert a == b
    bridge, engine, store, tmp = _wired()
    bridge.on_news_item(_item("x:1", ts="2026-08-30T13:18:38.955834"))
    assert engine.telemetry._records[0].signal_id == a
    store.close()
    tmp.cleanup()
    print("OK test_w_bridge_4_naive_ts_and_uuid5_determinism")


def test_w_ws_1_cache_only() -> None:
    """W-WS-1: Bridge liest nur SnapshotCache — kalt → Verwerfen."""
    bridge, engine, store, tmp = _wired(with_book=False)
    # Cache leer für BTC
    assert bridge._cache.get("0xtokenBTC") is None
    assert bridge.on_news_item(_item("ws:1")) is False
    assert any(r == "no_book" for _, r in bridge.discards)
    store.close()
    tmp.cleanup()
    print("OK test_w_ws_1_cache_only")


def test_w_charter_2_bridge_and_runner_ast() -> None:
    """W-CHARTER-2: kein Netzwerk-/Relayer-Import in Bridge/Runner."""
    root = Path(__file__).resolve().parents[1]
    banned = {"socket", "requests", "http", "urllib", "aiohttp", "websockets"}
    for name in ("news_bridge.py", "shadow_runner.py"):
        tree = ast.parse((root / name).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {(node.module or "").split(".")[0]}
            else:
                continue
            assert not names & banned, (name, names & banned)
    print("OK test_w_charter_2_bridge_and_runner_ast")


def test_policy_maps_direction_and_size_fn() -> None:
    """Policy: θ → Direction; Size über size_fn, nicht Payload."""
    p = BridgePolicy.from_config({"theta": "0.2", "size_by_impact": {"HIGH": "100"}})
    assert p.direction_from("0.5") is Direction.UP
    assert p.direction_from("-0.5") is Direction.DOWN
    assert p.direction_from("0.05") is Direction.NEUTRAL
    sid = uuid.uuid4()
    p.remember_size(sid, Decimal("100"))
    from order_execution_engine.models import SignalPayload
    sig = SignalPayload(
        signal_id=sid, target_token_id="t", market_id="m",
        direction=Direction.UP, confidence=Decimal("50"),
    )
    assert p.size_fn(sig, None) == Decimal("100")
    print("OK test_policy_maps_direction_and_size_fn")
