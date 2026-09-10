"""Tests for services/m2_shadow/risk_alpha.py (diagnostic overlays)."""
from __future__ import annotations

import math

import pytest

from services.m2_shadow.risk_alpha import (
    AlphaDecayDiagnostic,
    AssetLiquidityGate,
    LagTradeObservation,
    build_decay_curve_bps,
    expected_gross_decay_bps,
    fit_lambda_per_second,
)


def test_v1_core_assets_only() -> None:
    gate = AssetLiquidityGate()
    ok, reason = gate.is_eligible("BTC")
    assert ok is True
    assert reason == "tier_1_core"
    ok2, reason2 = gate.is_eligible("SOL")
    assert ok2 is False
    assert "outside M2 v1 core" in reason2


def test_expected_gross_decay_monotone() -> None:
    r0 = 50.0
    lam = 0.002
    assert expected_gross_decay_bps(0, r0, lambda_per_s=lam) == pytest.approx(r0)
    assert expected_gross_decay_bps(600, r0, lambda_per_s=lam) < r0


def test_fit_lambda_from_synthetic_decay() -> None:
    lam_true = 0.0015
    r0 = 80.0
    obs = []
    for lag in (60, 300, 600, 1200, 2400):
        gross = r0 * math.exp(-lam_true * lag)
        obs.append(
            LagTradeObservation(
                asset="BTC",
                lag_sec=float(lag),
                gross_pnl_bps=gross,
                net_pnl_bps=gross - 19.0,
                lag_bucket="M15_60",
            )
        )
    lam_fit, status = fit_lambda_per_second(obs, r0_bps=r0, min_obs=5)
    assert status == "ok"
    assert lam_fit is not None
    assert lam_fit == pytest.approx(lam_true, rel=0.15)


def test_alpha_decay_diagnostic_to_dict() -> None:
    diag = AlphaDecayDiagnostic()
    for lag in (600, 1200, 1800, 2400):
        diag.add(
            LagTradeObservation(
                asset="ETH",
                lag_sec=float(lag),
                gross_pnl_bps=25.0 - lag / 200.0,
                net_pnl_bps=6.0,
                lag_bucket="M15_60",
            )
        )
    diag.fit()
    payload = diag.to_dict()
    assert payload["n_observations"] == 4
    assert payload["diagnostic_only"] is True
    assert payload["r0_source"] == "max_observed_ohlcv_gross_bps"
    lag_obs = payload["lag_observed_sec"]
    assert lag_obs["min"] == 600.0
    assert lag_obs["max"] == 2400.0
    curve = payload["decay_curve_bps"]
    assert isinstance(curve, list)
    assert not any(p.get("lag_label") == "0s" for p in curve)
    ref_5m = next(p for p in curve if p["lag_label"] == "ref_5m")
    assert ref_5m["extrapolated"] is True  # 300s < observed_min 600s
    obs_min = next(p for p in curve if p["lag_label"] == "observed_min")
    assert obs_min["extrapolated"] is False


def test_decay_curve_marks_in_range_refs_not_extrapolated() -> None:
    obs = [
        LagTradeObservation("BTC", 200.0, 40.0, 21.0),
        LagTradeObservation("BTC", 800.0, 30.0, 11.0),
        LagTradeObservation("BTC", 1500.0, 20.0, 1.0),
    ]
    curve = build_decay_curve_bps(obs, r0_bps=40.0, lambda_per_s=0.001)
    ref_15m = next(p for p in curve if p["lag_label"] == "ref_15m")
    assert ref_15m["lag_sec"] == 900.0
    assert ref_15m["extrapolated"] is False
