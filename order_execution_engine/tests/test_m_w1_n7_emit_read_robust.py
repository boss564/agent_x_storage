"""M-W1 / N-7: Emit/Read robustness (Bauplan v1.2 §7).

Acceptance:
  - Fake IO error on emit → cache.update still applied; emit_drop_total > 0
  - Torn JSON line → remaining file readable; corrupt_line_total > 0; no raise
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import order_execution_engine.event_log as event_log
from order_execution_engine.event_log import (
    JsonlEventLog,
    install_cache_tap,
    iter_events,
    reset_corrupt_line_total,
)
from order_execution_engine.market_data_feed import SnapshotCache
from order_execution_engine.shadow_execution_engine import MarketSnapshot, OrderBookLevel


def _snap(token_id: str = "tok-a") -> MarketSnapshot:
    return MarketSnapshot(
        token_id=token_id,
        bids=(OrderBookLevel(price=Decimal("0.4"), size=Decimal("10")),),
        asks=(OrderBookLevel(price=Decimal("0.6"), size=Decimal("10")),),
        received_at=time.time(),
        source="book",
    )


def test_m_w1_n7_emit_io_error_cache_update_survives() -> None:
    """Fake disk error on emit: feed/cache continues; drop counter increments."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        log = JsonlEventLog(path, producer="runner")
        cache = SnapshotCache(max_age_seconds=30)
        install_cache_tap(cache, log)
        assert log.emit_drop_total == 0

        real_open = Path.open

        def boom_open(self, *args, **kwargs):  # noqa: ANN001
            # Only break appends to our event log path.
            if Path(self).resolve() == path.resolve():
                raise OSError("ENOSPC: fake disk full")
            return real_open(self, *args, **kwargs)

        with patch.object(Path, "open", boom_open):
            cache.update(_snap())  # must not raise

        peeked = cache.peek("tok-a") if hasattr(cache, "peek") else cache.get("tok-a")
        assert peeked is not None, "cache.update must survive emit IO failure"
        assert peeked.token_id == "tok-a"
        assert log.emit_drop_total >= 1
        # Nothing durable written under the boom.
        assert not path.exists() or path.read_text(encoding="utf-8") == ""
        print(
            f"OK test_m_w1_n7_emit_io_error_cache_update_survives "
            f"emit_drop_total={log.emit_drop_total}"
        )


def test_m_w1_n7_emit_direct_oserror_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        log = JsonlEventLog(path, producer="runner")
        real_open = Path.open

        def boom_open(self, *args, **kwargs):  # noqa: ANN001
            if Path(self).resolve() == path.resolve():
                raise OSError("EIO")
            return real_open(self, *args, **kwargs)

        with patch.object(Path, "open", boom_open):
            row = log.emit("tick_sample", token_id="x", cache_state="MISS")
        assert row is None
        assert log.emit_drop_total == 1
        print("OK test_m_w1_n7_emit_direct_oserror_returns_none")


def test_m_w1_n7_iter_events_skips_torn_line() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        good_a = {
            "rowid": 1,
            "ts_mono": 1.0,
            "wall_ts": 1.0,
            "event_type": "book_update",
            "producer": "runner",
            "token_id": "a",
        }
        good_b = {
            "rowid": 2,
            "ts_mono": 2.0,
            "wall_ts": 2.0,
            "event_type": "book_update",
            "producer": "runner",
            "token_id": "b",
        }
        path.write_text(
            json.dumps(good_a, separators=(",", ":"))
            + "\n"
            + '{"event_type":"torn", "incomplete"'
            + "\n"
            + json.dumps(good_b, separators=(",", ":"))
            + "\n",
            encoding="utf-8",
        )
        reset_corrupt_line_total()
        before = event_log.corrupt_line_total
        events = iter_events(path)  # must not raise
        assert [e["token_id"] for e in events] == ["a", "b"]
        assert event_log.corrupt_line_total == before + 1
        print(
            f"OK test_m_w1_n7_iter_events_skips_torn_line "
            f"corrupt_line_total={event_log.corrupt_line_total}"
        )


def test_m_w1_n7_counters_are_observation_not_gate() -> None:
    """Charter note: drop/corrupt counters exist as observations only."""
    src = Path(__file__).resolve().parents[1] / "event_log.py"
    text = src.read_text(encoding="utf-8")
    assert "emit_drop_total" in text
    assert "corrupt_line_total" in text
    assert "not a Gate" in text or "observation only" in text.lower()
    print("OK test_m_w1_n7_counters_are_observation_not_gate")


if __name__ == "__main__":
    os.environ.setdefault("SHADOW_EVENT_LOG", "off")
    for fn in list(globals().values()):
        if callable(fn) and fn.__name__.startswith("test_"):
            fn()
    print("M-W1 N-7 NACHWEIS grün")
