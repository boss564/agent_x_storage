"""Self-Tests für market_data_feed (SnapshotCache + PolySentinelBookHandler)."""

import sys
import threading
import time
from decimal import Decimal

sys.path.insert(0, "/mnt/agents/output")

from order_execution_engine.market_data_feed import (
    PolySentinelBookHandler,
    SnapshotCache,
)


def test_cache_update_and_get() -> None:
    cache = SnapshotCache(max_age_seconds=60)
    h = PolySentinelBookHandler(cache)
    snap = h.on_book_update(
        "0xtokenA",
        bids=[(Decimal("0.60"), Decimal("100")), (Decimal("0.59"), Decimal("50"))],
        asks=[(Decimal("0.61"), Decimal("200")), (Decimal("0.62"), Decimal("300"))],
    )
    got = cache.get("0xtokenA")
    assert got is not None
    assert got.best_bid() == Decimal("0.60")
    assert got.best_ask() == Decimal("0.61")
    assert list(got.bids[0].__dict__.values()) == [Decimal("0.60"), Decimal("100")]
    print("OK test_cache_update_and_get")


def test_cache_sorting_normalization() -> None:
    cache = SnapshotCache()
    h = PolySentinelBookHandler(cache)
    snap = h.on_book_update(
        "0xtokenA",
        bids=[(Decimal("0.58"), Decimal("1")), (Decimal("0.60"), Decimal("2"))],  # unsortiert
        asks=[(Decimal("0.62"), Decimal("1")), (Decimal("0.61"), Decimal("2"))],  # unsortiert
    )
    assert snap.bids[0].price == Decimal("0.60")  # absteigend
    assert snap.asks[0].price == Decimal("0.61")  # aufsteigend
    print("OK test_cache_sorting_normalization")


def test_cache_staleness() -> None:
    cache = SnapshotCache(max_age_seconds=0.1)
    h = PolySentinelBookHandler(cache)
    h.on_book_update("0xtokenA", bids=[(Decimal("0.6"), Decimal("10"))],
                     asks=[(Decimal("0.61"), Decimal("10"))])
    assert cache.get("0xtokenA") is not None
    time.sleep(0.15)
    assert cache.get("0xtokenA") is None
    print("OK test_cache_staleness")


def test_cache_snapshot_for_wait() -> None:
    cache = SnapshotCache(max_age_seconds=60)
    # ohne Daten: gibt nach Wartezeit None zurück
    t0 = time.time()
    assert cache.snapshot_for("0xUNKNOWN", wait_seconds=0.2) is None
    assert time.time() - t0 >= 0.15
    print("OK test_cache_snapshot_for_wait")


def test_cache_purge_and_tokens() -> None:
    cache = SnapshotCache(max_age_seconds=0.05)
    h = PolySentinelBookHandler(cache)
    h.on_book_update("t1", bids=[(Decimal("0.5"), Decimal("1"))], asks=[(Decimal("0.6"), Decimal("1"))])
    h.on_book_update("t2", bids=[(Decimal("0.5"), Decimal("1"))], asks=[(Decimal("0.6"), Decimal("1"))])
    assert sorted(cache.known_tokens()) == ["t1", "t2"]
    time.sleep(0.08)
    removed = cache.purge_stale()
    assert removed == 2
    assert cache.known_tokens() == []
    print("OK test_cache_purge_and_tokens")


def test_handler_ticker_fallback() -> None:
    cache = SnapshotCache()
    h = PolySentinelBookHandler(cache)
    snap = h.on_ticker("0xtokenA", best_bid=Decimal("0.59"), best_ask=Decimal("0.61"), size=Decimal("75"))
    assert snap.best_bid() == Decimal("0.59")
    assert snap.best_ask() == Decimal("0.61")
    assert snap.asks[0].size == Decimal("75")
    print("OK test_handler_ticker_fallback")


def test_feed_engine_integration() -> None:
    """End-to-End: PolySentinel-Event -> Cache -> Engine -> Fill."""
    from order_execution_engine.models import Direction, RiskConfig, SignalPayload
    from order_execution_engine.shadow_execution_engine import ShadowExecutionEngine

    cache = SnapshotCache(max_age_seconds=60)
    handler = PolySentinelBookHandler(cache)
    engine = ShadowExecutionEngine(risk_config=RiskConfig(max_order_size_shares=Decimal("150")))

    # Simuliertes PolySentinel-Buch-Event
    handler.on_book_update(
        "0xtokenA",
        bids=[(Decimal("0.59"), Decimal("500"))],
        asks=[(Decimal("0.61"), Decimal("500")), (Decimal("0.62"), Decimal("500"))],
    )
    snap = cache.snapshot_for("0xtokenA", wait_seconds=0.5)
    assert snap is not None

    sig = SignalPayload(target_token_id="0xtokenA", market_id="mkt-1",
                        direction=Direction.UP, confidence=Decimal("80"))
    rec = engine.on_signal(sig, snap)
    assert rec.approved and rec.status is not None
    assert engine.portfolio.positions["0xtokenA"].size == Decimal("150")
    print("OK test_feed_engine_integration")


def test_feed_thread_safety() -> None:
    """Konkurrente Schreiber/Leser ohne Fehler (smoke)."""
    cache = SnapshotCache(max_age_seconds=60)
    h = PolySentinelBookHandler(cache)
    errors: list[Exception] = []

    def writer(tid: str) -> None:
        try:
            for _ in range(200):
                h.on_book_update(tid, bids=[(Decimal("0.6"), Decimal("10"))],
                                 asks=[(Decimal("0.61"), Decimal("10"))])
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(f"t{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    while any(t.is_alive() for t in threads):
        cache.purge_stale()
        cache.known_tokens()
    for t in threads:
        t.join()
    assert not errors
    print("OK test_feed_thread_safety")


def test_ticker_missing_side_emits_no_level() -> None:
    """Fix 1: Ticker mit fehlender Seite (Preis 0) -> keine 0-Stufe."""
    cache = SnapshotCache()
    h = PolySentinelBookHandler(cache)
    # Nur Bid-Seite bekannt
    snap = h.on_ticker("0xtokenA", best_bid=Decimal("0.60"), best_ask=Decimal("0"), size=Decimal("50"))
    assert snap.best_bid() == Decimal("0.60")
    assert snap.asks == ()
    assert snap.best_ask() is None
    # Nur Ask-Seite bekannt
    snap2 = h.on_ticker("0xtokenB", best_bid=Decimal("0"), best_ask=Decimal("0.62"), size=Decimal("70"))
    assert snap2.bids == ()
    assert snap2.best_ask() == Decimal("0.62")
    print("OK test_ticker_missing_side_emits_no_level")


def test_feed_book_and_price_change_aggregation() -> None:
    """Fix 2: book (Vollbuch) + price_change (Delta) -> verdichtete Snapshots."""
    from order_execution_engine.market_data_feed import PolymarketWsFeed

    cache = SnapshotCache()
    feed = PolymarketWsFeed(PolySentinelBookHandler(cache))

    # Vollbuch-Event
    feed._dispatch({
        "event_type": "book",
        "market": "0xtokenA",
        "bids": [{"price": "0.60", "size": "100"}, {"price": "0.59", "size": "50"}],
        "asks": [{"price": "0.61", "size": "200"}],
    })
    snap = cache.get("0xtokenA")
    assert snap is not None
    assert snap.best_bid() == Decimal("0.60")
    assert snap.best_ask() == Decimal("0.61")
    assert len(snap.bids) == 2

    # Delta: Bid-Größe ändern, neues Ask-Level, Level streichen (size=0)
    feed._dispatch({
        "event_type": "price_change",
        "market": "0xtokenA",
        "changes": [
            {"side": "BUY", "price": "0.60", "size": "80"},    # Update
            {"side": "SELL", "price": "0.62", "size": "300"},  # Neues Level
            {"side": "BUY", "price": "0.59", "size": "0"},     # Streichen
        ],
    })
    snap2 = cache.get("0xtokenA")
    assert snap2 is not None
    assert [b.price for b in snap2.bids] == [Decimal("0.60")]
    assert snap2.bids[0].size == Decimal("80")
    assert [a.price for a in snap2.asks] == [Decimal("0.61"), Decimal("0.62")]
    print("OK test_feed_book_and_price_change_aggregation")


def test_feed_delta_without_initial_book() -> None:
    """Delta vor Vollbuch: Level werden inkrementell aufgebaut."""
    from order_execution_engine.market_data_feed import PolymarketWsFeed

    cache = SnapshotCache()
    feed = PolymarketWsFeed(PolySentinelBookHandler(cache))
    feed._dispatch({
        "event_type": "price_change",
        "market": "0xtokenA",
        "changes": [{"side": "SELL", "price": "0.63", "size": "150"}],
    })
    snap = cache.get("0xtokenA")
    assert snap is not None
    assert snap.best_ask() == Decimal("0.63")
    assert snap.bids == ()
    print("OK test_feed_delta_without_initial_book")


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and fn.__name__.startswith("test_"):
            fn()
    print("ALLE FEED-TESTS BESTANDEN")
