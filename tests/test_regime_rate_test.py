"""Tests for regime Poisson rate verdict."""
from datetime import datetime, timezone

from scripts.regime_rate_test import RateWindow, poisson_rate_test, rate_ratio_test


def _win(label: str, y1: int, m1: int, d1: int, y2: int, m2: int, d2: int, n: int) -> RateWindow:
    return RateWindow(
        label,
        datetime(y1, m1, d1, tzinfo=timezone.utc),
        datetime(y2, m2, d2, tzinfo=timezone.utc),
        n,
    )


def test_funding_shift_confirmed_synthetic():
    pre = _win("pre", 2019, 9, 1, 2023, 11, 13, 102)
    post = _win("post", 2023, 11, 13, 2026, 9, 2, 1)
    r = poisson_rate_test(pre, post)
    assert r.verdict == "REGIME_SHIFT_CONFIRMED"
    assert r.shift_direction == "decrease"
    assert r.p_value_one_sided < 0.01
    assert r.expected_post_under_constant_rate > 50


def test_increase_shift_confirmed_synthetic():
    pre = _win("pre", 2019, 1, 1, 2021, 1, 1, 30)
    post = _win("post", 2021, 1, 1, 2023, 1, 1, 200)
    r = poisson_rate_test(pre, post)
    assert r.verdict == "REGIME_SHIFT_CONFIRMED"
    assert r.shift_direction == "increase"
    assert r.rate_ratio_post_pre > 4.0


def test_fluctuation_when_rates_similar():
    pre = _win("pre", 2020, 1, 1, 2022, 1, 1, 40)
    post = _win("post", 2022, 1, 1, 2024, 1, 1, 35)
    r = poisson_rate_test(pre, post)
    assert r.verdict == "FLUCTUATION"


def test_rate_ratio_test_decrease_example():
    r = rate_ratio_test(50, 100, 10, 100)
    assert r.decision == "decrease"
    assert r.ratio == 0.2
    assert r.p_lower < 0.01


def test_rate_ratio_test_increase_example():
    r = rate_ratio_test(10, 100, 50, 100)
    assert r.decision == "increase"
    assert r.ratio == 5.0
    assert r.p_upper < 0.01


def test_rate_ratio_test_no_change_example():
    r = rate_ratio_test(30, 100, 35, 100)
    assert r.decision == "no_change"
