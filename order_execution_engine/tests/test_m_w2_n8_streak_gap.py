"""M-W2 / N-8: streak_wall_s_from_events consumes detect_cycle_gaps.

Acceptance: cycle_seq 1,3 (2 missing) → streak breaks;
contiguous OK series keeps A-B2' ±1 s.
"""

from __future__ import annotations

import time

from order_execution_engine.probe_f3 import (
    detect_cycle_gaps,
    streak_wall_s_from_events,
)


def _ok(seq: int, wall: float, *, iid: str = "inst-a") -> dict:
    return {
        "event_type": "cycle_end",
        "books_ok_full": True,
        "wall_ts": wall,
        "ts_mono": float(seq),
        "producer": "probe",
        "instance_id": iid,
        "cycle_seq": seq,
        "event_type_start": "cycle_start",  # unused
    }


def _start(seq: int, wall: float, *, iid: str = "inst-a") -> dict:
    return {
        "event_type": "cycle_start",
        "wall_ts": wall,
        "ts_mono": float(seq) - 0.5,
        "producer": "probe",
        "instance_id": iid,
        "cycle_seq": seq,
    }


def test_m_w2_n8_gap_1_3_breaks_streak() -> None:
    t0 = time.time()
    # cycle_start 1,3 + cycle_end OK 1,3 — seq 2 absent → missing_cycle_seq
    events = [
        _start(1, t0),
        _ok(1, t0 + 1),
        _start(3, t0 + 300),
        _ok(3, t0 + 301),
    ]
    gaps = detect_cycle_gaps(events)
    assert any(
        g.get("kind") == "missing_cycle_seq" and g.get("cycle_seq") == 2 for g in gaps
    ), gaps
    streak = streak_wall_s_from_events(events)
    # Last contiguous OK run is a single point (seq=3) → 0, not ~300.
    assert streak is not None
    assert streak <= 1.0, f"streak must break on gap, got {streak}"
    print(f"OK test_m_w2_n8_gap_1_3_breaks_streak streak={streak}")


def test_m_w2_n8_contiguous_ok_ab2_prime() -> None:
    t0 = time.time()
    events = [
        _start(1, t0),
        _ok(1, t0),
        _start(2, t0 + 300),
        _ok(2, t0 + 300),
        _start(3, t0 + 600),
        _ok(3, t0 + 600),
    ]
    assert detect_cycle_gaps(events) == []
    streak = streak_wall_s_from_events(events)
    assert streak is not None
    assert abs(streak - 600.0) <= 1.0  # A-B2' ±1 s
    print(f"OK test_m_w2_n8_contiguous_ok_ab2_prime streak={streak}")


def test_m_w2_n8_legacy_without_cycle_seq_still_works() -> None:
    """Pre-F3 events without cycle_seq: books_ok_full-only path (A-B2')."""
    t0 = time.time()
    events = [
        {
            "event_type": "cycle_end",
            "books_ok_full": True,
            "wall_ts": t0,
            "ts_mono": 1.0,
            "producer": "probe",
        },
        {
            "event_type": "cycle_end",
            "books_ok_full": True,
            "wall_ts": t0 + 600,
            "ts_mono": 2.0,
            "producer": "probe",
        },
    ]
    streak = streak_wall_s_from_events(events)
    assert streak is not None
    assert abs(streak - 600.0) <= 1.0
    print("OK test_m_w2_n8_legacy_without_cycle_seq_still_works")


def test_m_w2_n8_books_ok_false_still_breaks() -> None:
    t0 = time.time()
    events = [
        _start(1, t0),
        _ok(1, t0),
        _start(2, t0 + 100),
        {
            "event_type": "cycle_end",
            "books_ok_full": False,
            "wall_ts": t0 + 100,
            "ts_mono": 2.0,
            "producer": "probe",
            "instance_id": "inst-a",
            "cycle_seq": 2,
        },
        _start(3, t0 + 200),
        _ok(3, t0 + 200),
    ]
    streak = streak_wall_s_from_events(events)
    assert streak is not None
    assert streak <= 1.0
    print("OK test_m_w2_n8_books_ok_false_still_breaks")


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and fn.__name__.startswith("test_"):
            fn()
    print("M-W2 N-8 NACHWEIS grün")
