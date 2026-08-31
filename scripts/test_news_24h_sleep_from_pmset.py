#!/usr/bin/env python3
"""Smoke tests for pmset sleep derivation (NEWS 24h gate G4)."""
from __future__ import annotations

from datetime import datetime, timezone

from scripts.news_24h_sleep_from_pmset import (
    g1_n_min,
    pmset_covers_gate_window,
    sleep_intervals_from_pmset_log,
    total_sleep_seconds,
)


def test_g1_anchor_no_sleep() -> None:
    assert g1_n_min(0.0) == 20


def test_g1_night_sleep_example() -> None:
    assert g1_n_min(7.5) == 14


def test_pmset_log_parses_sleep_block() -> None:
    log = """
2026-08-31 22:00:00 +0000 Sleep                Entering Sleep state due to 'Clamshell Sleep':
2026-09-01 05:30:00 +0000 Wake                 Wake from Deep Idle
"""
    window_start = datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc)
    window_end = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
    intervals = sleep_intervals_from_pmset_log(
        log, window_start=window_start, window_end=window_end
    )
    assert len(intervals) == 1
    sleep_s = total_sleep_seconds(intervals)
    assert 7.0 <= sleep_s / 3600.0 <= 7.6


def test_pmset_log_rotation_incomplete() -> None:
    window_start = datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc)
    window_end = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
    # Log only covers last 12h of window — sleep at window start would be missing.
    log = """
2026-08-31 21:00:00 +0000 Assertions           Summary- 0x0
2026-09-01 08:00:00 +0000 Wake                 Wake from Deep Idle
"""
    ok, reason = pmset_covers_gate_window(
        log, window_start=window_start, window_end=window_end
    )
    assert not ok
    assert "log_starts_after_epoch" in reason


def test_pmset_log_covers_full_window() -> None:
    window_start = datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc)
    window_end = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
    log = """
2026-08-31 08:59:00 +0000 Assertions           Summary- 0x0
2026-09-01 09:00:00 +0000 Wake                 Wake from Deep Idle
"""
    ok, reason = pmset_covers_gate_window(
        log, window_start=window_start, window_end=window_end
    )
    assert ok, reason


def run() -> None:
    test_g1_anchor_no_sleep()
    test_g1_night_sleep_example()
    test_pmset_log_parses_sleep_block()
    test_pmset_log_rotation_incomplete()
    test_pmset_log_covers_full_window()
    print("news_24h_sleep_from_pmset: 5/5 passed")


if __name__ == "__main__":
    run()
