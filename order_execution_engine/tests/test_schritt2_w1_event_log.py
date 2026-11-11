"""S2-W1: Event-Log + Runner-Hook + dual producer (GP-S2-1/2/7).

W1-Startpflicht — Tap-Anker verifiziert am Live-Tree 2026-11-10:
  SnapshotCache.update                 market_data_feed.py:63
  on_book_update → cache.update        market_data_feed.py:181
"""

from __future__ import annotations

import inspect
import os
import tempfile
import time
from decimal import Decimal
from pathlib import Path

from order_execution_engine.event_log import (
    TAP_ANCHOR_ON_BOOK_UPDATE_CALL,
    TAP_ANCHOR_UPDATE,
    JsonlEventLog,
    count_events,
    emit_tick_samples,
    install_cache_tap,
    iter_events,
    last_event_age_s,
)
from order_execution_engine.market_data_feed import (
    PolySentinelBookHandler,
    SnapshotCache,
)
from order_execution_engine.shadow_execution_engine import MarketSnapshot, OrderBookLevel


def _snap(token_id: str = "tok-a", *, bid: str = "0.4", ask: str = "0.6") -> MarketSnapshot:
    return MarketSnapshot(
        token_id=token_id,
        bids=(OrderBookLevel(price=Decimal(bid), size=Decimal("10")),),
        asks=(OrderBookLevel(price=Decimal(ask), size=Decimal("10")),),
        received_at=time.time(),
        source="book",
    )


def test_w1_tap_anchors_match_live_source() -> None:
    """W1-Startpflicht: Anker zitieren echte Zeilen, kein stiller Fix."""
    import order_execution_engine.market_data_feed as mdf

    src = Path(inspect.getsourcefile(mdf.SnapshotCache)).read_text(encoding="utf-8")
    lines = src.splitlines()
    # 1-indexed — pinned after G8 SP-1926 M-a (peek-Insert 2195610f Anker-Drift)
    assert "def update(" in lines[56], f"expected update at L57, got: {lines[56]!r}"
    assert TAP_ANCHOR_UPDATE.endswith(":57")
    # on_book_update body calls self._cache.update(snapshot)
    assert "self._cache.update(snapshot)" in src
    on_book_line = next(
        i for i, ln in enumerate(lines, 1) if "self._cache.update(snapshot)" in ln
    )
    assert on_book_line == 175, (
        f"on_book_update→update expected L175, found L{on_book_line} "
        f"(Fund, kein stiller Fix — Anker melden)"
    )
    assert TAP_ANCHOR_ON_BOOK_UPDATE_CALL.endswith(":175")
    print(
        f"OK test_w1_tap_anchors_match_live_source "
        f"update={TAP_ANCHOR_UPDATE} on_book_update_call=L{on_book_line}"
    )


def test_w1_a_a1_three_updates_three_events() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        log = JsonlEventLog(path, producer="runner")
        cache = SnapshotCache(max_age_seconds=30)
        install_cache_tap(cache, log)
        for i in range(3):
            cache.update(_snap(bid=f"0.{4 + i}"))
            time.sleep(0.01)
        n = count_events(path, event_type="book_update", token_id="tok-a")
        assert n >= 3, n
        rows = [e for e in iter_events(path) if e["event_type"] == "book_update"]
        assert all("ts_mono" in e and "wall_ts" in e for e in rows)
        print("OK test_w1_a_a1_three_updates_three_events")


def test_w1_a_a2_vacuity_no_invented_book_update() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        log = JsonlEventLog(path, producer="runner")
        cache = SnapshotCache(max_age_seconds=30)
        install_cache_tap(cache, log)
        # Wait without updates — only tick/probe samples allowed.
        emit_tick_samples(cache, log, ["tok-a", "tok-b"], max_age_s=30)
        assert count_events(path, event_type="book_update") == 0
        assert count_events(path, event_type="tick_sample") == 2
        print("OK test_w1_a_a2_vacuity_no_invented_book_update")


def test_w1_a_a5_runner_hook_fires_on_fake_snapshot() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        log = JsonlEventLog(path, producer="runner")
        cache = SnapshotCache(max_age_seconds=30)
        install_cache_tap(cache, log)
        handler = PolySentinelBookHandler(cache)
        before = count_events(path, event_type="book_update")
        handler.on_book_update(
            "tok-a",
            bids=[(Decimal("0.4"), Decimal("1"))],
            asks=[(Decimal("0.6"), Decimal("1"))],
        )
        after = count_events(path, event_type="book_update")
        assert after >= before + 1
        print("OK test_w1_a_a5_runner_hook_fires_on_fake_snapshot")


def test_w1_a_a6_deaf_venue_tick_without_book() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        log = JsonlEventLog(path, producer="runner")
        cache = SnapshotCache(max_age_seconds=30)
        install_cache_tap(cache, log)
        emit_tick_samples(cache, log, ["deaf-token"], max_age_s=30)
        assert count_events(path, event_type="tick_sample", token_id="deaf-token") == 1
        assert count_events(path, event_type="book_update") == 0
        row = iter_events(path)[0]
        assert row["cache_state"] == "MISS"
        print("OK test_w1_a_a6_deaf_venue_tick_without_book")


def test_w1_a_a3_two_producers_separate_ages() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        runner = JsonlEventLog(path, producer="runner")
        probe = JsonlEventLog(path, producer="probe")
        cache_r = SnapshotCache(max_age_seconds=30)
        install_cache_tap(cache_r, runner)
        cache_r.update(_snap("tok-a"))
        time.sleep(0.05)
        probe.emit_book_update(_snap("tok-a"))
        now = time.time()
        eng_age = last_event_age_s(
            path, "tok-a", producer="runner", event_type="book_update", now=now,
        )
        probe_age = last_event_age_s(
            path, "tok-a", producer="probe", event_type="book_update", now=now,
        )
        assert eng_age is not None and probe_age is not None
        assert eng_age >= probe_age  # runner wrote earlier
        print("OK test_w1_a_a3_two_producers_separate_ages")


def test_w1_a_a4_max_book_age_default_untouched() -> None:
    from order_execution_engine.fill_simulator import FillSimConfig

    assert FillSimConfig().max_book_age_ms == 2000
    print("OK test_w1_a_a4_max_book_age_default_untouched")


def test_w1_never_opens_shadow_db(tmp_path: Path | None = None) -> None:
    """GP-S2-7: event log path is JSONL; no sqlite connect to shadow.db."""
    src = Path(__file__).resolve().parents[1] / "event_log.py"
    text = src.read_text(encoding="utf-8")
    assert "shadow.db" not in text or "never" in text.lower()
    assert "sqlite" not in text.lower()
    print("OK test_w1_never_opens_shadow_db")


if __name__ == "__main__":
    # Isolate from developer env so resolve_* side effects stay out.
    os.environ.setdefault("SHADOW_EVENT_LOG", "off")
    for fn in list(globals().values()):
        if callable(fn) and fn.__name__.startswith("test_"):
            fn()
    print("S2-W1 NACHWEIS grün")
