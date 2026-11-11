"""M-W2 / N-5: Gate-C freshness from raw fields only (never cache_state).

Acceptance: Report/Gate-C reads only raw ages; changing named threshold flips
freshness without rewriting cache_state semantics on the event.
"""

from __future__ import annotations

import inspect
import os
import tempfile
import time
from decimal import Decimal
from pathlib import Path

import order_execution_engine.gate_c as gate_c
from order_execution_engine.event_log import JsonlEventLog
from order_execution_engine.fill_simulator import FillSimConfig
from order_execution_engine.gate_c import (
    ENGINE_FRESH_S,
    PROBE_FRESH_S,
    assert_no_cache_state_dependency,
    engine_fresh_s_default,
    freshness_ok,
    last_book_update_age_s,
)
from order_execution_engine.market_data_feed import SnapshotCache
from order_execution_engine.shadow_execution_engine import MarketSnapshot, OrderBookLevel


def test_m_w2_n5_engine_threshold_reads_fillsim_default() -> None:
    assert FillSimConfig().max_book_age_ms == 2000  # Charter — unangetastet
    assert engine_fresh_s_default() == 2.0
    assert ENGINE_FRESH_S == 2.0
    assert PROBE_FRESH_S == 30.0
    print("OK test_m_w2_n5_engine_threshold_reads_fillsim_default")


def test_m_w2_n5_gate_c_ignores_cache_state() -> None:
    now = time.time()
    events = [
        {
            "event_type": "book_update",
            "producer": "runner",
            "token_id": "tok-a",
            "received_at": now - 1.0,
            "wall_ts": now - 0.5,
            "cache_state": "STALE",  # baked lie — must be ignored
        },
        {
            "event_type": "tick_sample",
            "producer": "runner",
            "token_id": "tok-a",
            "received_at": now - 100.0,
            "wall_ts": now,
            "cache_state": "OK",
            "age_s": 100.0,
        },
    ]
    age = last_book_update_age_s(events, "tok-a", now=now)
    assert age is not None
    assert abs(age - 1.0) <= 0.05
    # threshold 2.0 → fresh despite cache_state=STALE on the book_update
    assert freshness_ok(age, threshold_s=2.0) is True
    # tighter threshold → not fresh, without rewriting the event
    assert freshness_ok(age, threshold_s=0.1) is False
    print("OK test_m_w2_n5_gate_c_ignores_cache_state")


def test_m_w2_n5_source_forbids_cache_state_reads() -> None:
    src = inspect.getsource(gate_c)
    assert_no_cache_state_dependency(src)
    print("OK test_m_w2_n5_source_forbids_cache_state_reads")


def test_m_w2_n5_tick_sample_emits_threshold() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "e.jsonl"
        log = JsonlEventLog(path, producer="runner")
        cache = SnapshotCache(max_age_seconds=30)
        snap = MarketSnapshot(
            token_id="tok-a",
            bids=(OrderBookLevel(price=Decimal("0.4"), size=Decimal("1")),),
            asks=(OrderBookLevel(price=Decimal("0.6"), size=Decimal("1")),),
            received_at=time.time(),
            source="book",
        )
        cache.update(snap)
        row = log.emit_tick_sample("tok-a", cache.peek("tok-a"), max_age_s=30.0)
        assert row is not None
        assert row.get("threshold_s") == 30.0
        assert row.get("max_age_s") == 30.0
        assert "cache_state" in row  # still present, but Gate-C must ignore
        print("OK test_m_w2_n5_tick_sample_emits_threshold")


if __name__ == "__main__":
    os.environ.setdefault("SHADOW_EVENT_LOG", "off")
    for fn in list(globals().values()):
        if callable(fn) and fn.__name__.startswith("test_"):
            fn()
    print("M-W2 N-5 NACHWEIS grün")
