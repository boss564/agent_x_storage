"""Sharpe calibration — trade-level mean/std, not bar-frequency annualization."""
from __future__ import annotations

import numpy as np

from scripts.backtest_metrics import trade_sharpe_stats


def test_sharpe_synthetic_known_mean_std():
    rng = np.random.default_rng(42)
    mu, sigma = 0.01, 0.05
    returns = rng.normal(mu, sigma, 2000)
    stats = trade_sharpe_stats(returns, years=1.0)
    expected_pt = mu / sigma
    assert abs(stats["mean"] - mu) < 0.004
    assert abs(stats["std"] - sigma) < 0.008
    assert abs(stats["sharpe_per_trade"] - expected_pt) < 0.12
    assert abs(stats["sharpe_annualized"] - expected_pt * np.sqrt(2000)) < 3.0


def test_sharpe_tp_sl_model_not_hundreds():
    """M2b-style: 24.2% hit 2σ, else −1σ, minus 19 bps — Sharpe must be O(1)."""
    sigma = 0.003
    friction = 0.0019
    win_rate = 0.242
    rng = np.random.default_rng(0)
    n = 8000
    wins = rng.random(n) < win_rate
    gross = np.where(wins, 2.0 * sigma, -1.0 * sigma)
    net = gross - friction
    stats = trade_sharpe_stats(net, years=1.0)

    expected_gross = win_rate * 2 * sigma + (1 - win_rate) * (-sigma)
    assert abs(float(np.mean(gross)) - expected_gross) < 0.00005
    assert abs(stats["sharpe_per_trade"]) < 2.0
    assert abs(stats["sharpe_annualized"]) < 70.0
    assert stats["mean"] < 0  # friction dominates this toy model


def test_bar_frequency_annualization_would_be_absurd():
    """Document the bug: sqrt(bars/year) on sparse trades inflates Sharpe ~100x."""
    rng = np.random.default_rng(1)
    net = rng.normal(-0.002, 0.003, 545)
    mu, std = float(np.mean(net)), float(np.std(net, ddof=1))
    wrong = mu / std * np.sqrt(365 * 24 * 4)
    correct = mu / std
    assert abs(wrong) > 50
    assert abs(correct) < 2.0


def test_mde_n5_reference():
    """Same spirit as MDE n=5 → ~100 bps: small n, known σ."""
    from scripts.backtest_h1_news_m2_shadow_lag import min_detectable_effect_bps

    mde = min_detectable_effect_bps(5, 75.0)
    assert mde is not None
    assert 95.0 < mde < 105.0
