#!/usr/bin/env python3
"""Smoke tests for Option B hold-horizon calibration."""
from __future__ import annotations

import json
import math
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.position_sizing.hold_calibration import (  # noqa: E402
    SQRT_2_OVER_PI,
    TARGET_ABS_RETURN,
    TARGET_SIGMA_K,
    calibrate_hold_from_worm,
    hold_seconds_from_sigma,
    is_tick_signal,
    resample_last_price_bars,
    time_normalized_returns,
    TickPoint,
)


def _fail(msg: str) -> None:
    print(f"FAIL {msg}")
    raise SystemExit(1)


def _write_worm(path: Path, rows: list) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_filter_excludes_aggregate() -> None:
    if is_tick_signal({"action": "SIGNAL", "aggregate": True, "mark_price": "1"}):
        _fail("aggregate=True must be excluded")
    if is_tick_signal({"action": "SIGNAL", "signal_id": "aggregate", "mark_price": "1"}):
        _fail("signal_id=aggregate must be excluded")
    if not is_tick_signal({"action": "SIGNAL", "signal_id": "sig-1", "mark_price": "1"}):
        _fail("tick SIGNAL must pass")
    if is_tick_signal({"action": "SIM_FILL", "mark_price": "1"}):
        _fail("SIM_FILL must not count as tick signal")


def test_e_abs_vs_sigma_constant() -> None:
    # E[|r|] = σ√(2/π) ⇒ for target E[|r|]=0.6%, σ_k ≈ 0.7516%
    expected = TARGET_ABS_RETURN / SQRT_2_OVER_PI
    if abs(TARGET_SIGMA_K - expected) > 1e-12:
        _fail(f"TARGET_SIGMA_K {TARGET_SIGMA_K} != {expected}")
    if abs(TARGET_SIGMA_K - 0.007516) > 1e-5:
        _fail(f"TARGET_SIGMA_K unexpected {TARGET_SIGMA_K}")


def test_gap_excluded_from_returns() -> None:
    t0 = datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc)
    ticks = [
        TickPoint(t0, 100.0, 1),
        TickPoint(t0 + timedelta(seconds=1), 100.1, 2),
        TickPoint(t0 + timedelta(seconds=301), 101.0, 3),  # 300s gap
        TickPoint(t0 + timedelta(seconds=302), 101.1, 4),
    ]
    norms, dts, n_gap = time_normalized_returns(ticks, gap_dt_s=30.0)
    if n_gap != 1:
        _fail(f"expected 1 gap excluded, got {n_gap}")
    if len(norms) != 2:
        _fail(f"expected 2 returns, got {len(norms)}")
    if max(dts) < 300:
        _fail("dt series must still include gap for diagnostics")


def test_hold_from_sigma_uses_e_abs_not_sigma_equality() -> None:
    # σ_√s such that naive (0.006/σ)^2 would understate k vs (0.007516/σ)^2
    sigma = 0.0001
    k_correct = hold_seconds_from_sigma(sigma, TARGET_SIGMA_K)
    k_naive = (TARGET_ABS_RETURN / sigma) ** 2
    if k_correct is None:
        _fail("k_correct None")
    # correct k is larger by (σ_target/E[|r|])^2 ≈ (1/0.8)^2 ≈ 1.57
    ratio = k_correct / k_naive
    expected_ratio = (1.0 / SQRT_2_OVER_PI) ** 2
    if abs(ratio - expected_ratio) > 1e-9:
        _fail(f"ratio {ratio} != {expected_ratio}")


def test_calibrate_end_to_end_synthetic() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        worm = Path(tmp) / "paper_trades.worm.jsonl"
        t0 = datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc)
        rows = []
        price = 2500.0
        for i in range(200):
            # ~1s ticks, small geometric noise
            price *= math.exp(0.0002 if i % 2 == 0 else -0.00015)
            rows.append(
                {
                    "action": "SIGNAL",
                    "signal_id": f"sig-{i}",
                    "mark_price": f"{price:.4f}",
                    "ts": (t0 + timedelta(seconds=i)).isoformat(),
                }
            )
        rows.append(
            {
                "action": "SIGNAL",
                "signal_id": "aggregate",
                "aggregate": True,
                "mark_price": f"{price:.4f}",
                "ts": (t0 + timedelta(seconds=200)).isoformat(),
            }
        )
        # Feed gap: 5 min silence then resume
        rows.append(
            {
                "action": "SIGNAL",
                "signal_id": "sig-gap",
                "mark_price": f"{price * 1.02:.4f}",
                "ts": (t0 + timedelta(seconds=200 + 300)).isoformat(),
            }
        )
        _write_worm(worm, rows)
        result = calibrate_hold_from_worm(worm, gap_dt_s=30.0, n_subwindows=4)
        if result.n_aggregate_skipped < 1:
            _fail("aggregate row not counted")
        if result.n_gap_excluded < 1:
            _fail("gap not excluded")
        if result.worm_sha256 is None or len(result.worm_sha256) != 64:
            _fail("sha256 missing")
        if result.recommended_hold_seconds is None or result.recommended_hold_seconds <= 0:
            _fail(f"bad hold {result.recommended_hold_seconds}")
        if not result.sigma_subwindows:
            _fail("expected subwindow sigmas")
        if "HARKing" not in result.anti_harking_note:
            _fail("anti-harking note missing")


def test_1s_bar_resampling_collapses_microstructure() -> None:
    t0 = datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc)
    # 10 trade prints inside one second + next second
    ticks = [
        TickPoint(t0 + timedelta(milliseconds=i * 50), 100.0 + i * 0.01, i)
        for i in range(10)
    ]
    ticks.append(TickPoint(t0 + timedelta(seconds=1, milliseconds=10), 101.0, 99))
    bars = resample_last_price_bars(ticks, bar_seconds=1.0)
    if len(bars) != 2:
        _fail(f"expected 2 bars, got {len(bars)}")
    if abs(bars[0].price - 100.09) > 1e-9:
        _fail(f"first bar last price {bars[0].price}")
    if abs(bars[1].price - 101.0) > 1e-9:
        _fail(f"second bar last price {bars[1].price}")


def test_calibrate_1s_basis_flag() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        worm = Path(tmp) / "paper_trades.worm.jsonl"
        t0 = datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc)
        rows = []
        price = 2500.0
        for i in range(120):
            price *= math.exp(0.0001 if i % 2 == 0 else -0.00008)
            # two prints per second
            for j in range(2):
                rows.append(
                    {
                        "action": "SIGNAL",
                        "signal_id": f"sig-{i}-{j}",
                        "mark_price": f"{price:.4f}",
                        "ts": (t0 + timedelta(seconds=i, milliseconds=j * 10)).isoformat(),
                    }
                )
        _write_worm(worm, rows)
        r = calibrate_hold_from_worm(worm, bar_seconds=1.0, gap_dt_s=30.0, n_subwindows=3)
        if r.price_basis != "last_price_bar":
            _fail(f"basis {r.price_basis}")
        if r.bar_seconds != 1.0:
            _fail(f"bar_seconds {r.bar_seconds}")
        if r.n_price_points is None or r.n_price_points > r.n_tick_signals:
            _fail(f"bars {r.n_price_points} vs ticks {r.n_tick_signals}")
        if r.sigma_1d is None:
            _fail("sigma_1d missing")


def main() -> int:
    test_filter_excludes_aggregate()
    test_e_abs_vs_sigma_constant()
    test_gap_excluded_from_returns()
    test_hold_from_sigma_uses_e_abs_not_sigma_equality()
    test_calibrate_end_to_end_synthetic()
    test_1s_bar_resampling_collapses_microstructure()
    test_calibrate_1s_basis_flag()
    print("PAPER_HOLD_CALIBRATION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
