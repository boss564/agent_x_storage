"""M-l (SP-1928): dedicated tests for is_market_expired / parse_market_end_date.

Four cases (C1 fail-closed dispatch guard):
  NULL/unparseable → True
  past end_date    → True
  future end_date  → False
  naive input      → interpreted as UTC (documented; no local fallback)

Vacuity against baseline d2889bdb (function absent → ImportError) is measured
separately via scripts/vacuity_m_l_is_market_expired.sh — not a green placebo.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from order_execution_engine.allowlist_freeze import (
    is_market_expired,
    parse_market_end_date,
)


def test_m_l_null_unparseable_fail_closed_true() -> None:
    now = datetime(2026, 11, 11, 12, 0, 0, tzinfo=timezone.utc)
    for raw in (None, "", "null", "None", "not-a-date", "2026-13-99"):
        assert is_market_expired(raw, now=now) is True, raw
        assert parse_market_end_date(raw) is None, raw
    print("OK test_m_l_null_unparseable_fail_closed_true")


def test_m_l_past_end_date_true() -> None:
    now = datetime(2026, 11, 11, 12, 0, 0, tzinfo=timezone.utc)
    past = (now - timedelta(hours=1)).isoformat()
    assert is_market_expired(past, now=now) is True
    # end == now → expired (end <= now)
    assert is_market_expired(now.isoformat(), now=now) is True
    print("OK test_m_l_past_end_date_true")


def test_m_l_future_end_date_false() -> None:
    now = datetime(2026, 11, 11, 12, 0, 0, tzinfo=timezone.utc)
    future = (now + timedelta(days=1)).isoformat()
    assert is_market_expired(future, now=now) is False
    print("OK test_m_l_future_end_date_false")


def test_m_l_naive_interpreted_as_utc() -> None:
    """Naive end_date → UTC (documented); never local-tz fallback."""
    now = datetime(2026, 11, 11, 12, 0, 0, tzinfo=timezone.utc)
    # Naive "2026-11-11T11:00:00" as UTC is before now → expired.
    assert is_market_expired("2026-11-11T11:00:00", now=now) is True
    parsed = parse_market_end_date("2026-11-11T11:00:00")
    assert parsed is not None
    assert parsed.tzinfo is not None
    assert parsed == datetime(2026, 11, 11, 11, 0, 0, tzinfo=timezone.utc)
    # Naive future-as-UTC stays live.
    assert is_market_expired("2026-11-11T13:00:00", now=now) is False
    # Z / offset forms still work.
    assert is_market_expired("2026-11-11T13:00:00Z", now=now) is False
    print("OK test_m_l_naive_interpreted_as_utc")


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and fn.__name__.startswith("test_"):
            fn()
    print("M-l is_market_expired NACHWEIS grün")
