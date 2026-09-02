#!/usr/bin/env python3
"""G1 n_min — interval-scaled gate floor (NEWS_24H_SCHEDULER_GATE A1+A3)."""
from __future__ import annotations

from services.news_agent.gate_g1 import g1_n_min


def test_g1_anchor_hourly_no_downtime() -> None:
    assert g1_n_min(0.0, interval_min=60) == 20


def test_g1_anchor_hourly_night_sleep() -> None:
    assert g1_n_min(7.5, interval_min=60) == 14


def test_g1_polling_epoch_5min_no_downtime() -> None:
    assert g1_n_min(0.0, interval_min=5) == 244


def test_g1_polling_epoch_5min_with_downtime() -> None:
    assert g1_n_min(7.5, interval_min=5) == 168
