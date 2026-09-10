"""M2 shadow backtest — lag buckets + decision engine (no OHLCV network)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts.backtest_h1_news_m2_shadow_lag import (
    ALPHA_EFF,
    MDE_REFERENCE_STD_BPS,
    MIN_TRADES_PER_BUCKET,
    BucketResult,
    _bonferroni_significant,
    assign_lag_bucket,
    bucket_statistics,
    data_threshold_status,
    decision_engine,
    min_detectable_effect_bps,
)


def _bucket(
    name: str,
    *,
    n: int = 50,
    mean: float = 0.0,
    p: float = 1.0,
    bonferroni: bool = False,
    adjudication: str = "adjudicated",
    mde_bps_realized: float | None = 51.0,
    mde_bps_prereg: float | None = 32.0,
    sigma_bps_realized: float | None = 75.0,
) -> BucketResult:
    ranges = {
        "LT_15M": (0.0, 900.0),
        "M15_60": (900.0, 3600.0),
        "GT_60": (3600.0, float("inf")),
    }
    lo, hi = ranges[name]
    return BucketResult(
        bucket_name=name,
        lag_range_sec=(lo, hi),
        n_trades=n,
        mean_pnl_bps=mean,
        std_pnl_bps=sigma_bps_realized or 0.0,
        t_stat=3.0 if bonferroni else 0.0,
        p_value=p,
        adjudication=adjudication,  # type: ignore[arg-type]
        bonferroni_significant=bonferroni,
        mde_bps_prereg=mde_bps_prereg,
        mde_bps_realized=mde_bps_realized,
        sigma_bps_realized=sigma_bps_realized,
    )


def _event(n: int, *, lag_min: float) -> object:
    """Minimal event stub for threshold tests."""

    class _E:
        def __init__(self) -> None:
            base = datetime(2026, 1, 1, tzinfo=timezone.utc)
            self.t_ingest = base + timedelta(days=n)
            self.t_published = self.t_ingest - timedelta(minutes=lag_min)

        @property
        def detection_lag_seconds(self) -> float:
            return lag_min * 60.0

    return _E()


def test_assign_lag_bucket_spec_ranges() -> None:
    assert assign_lag_bucket(0) == "LT_15M"
    assert assign_lag_bucket(899.9) == "LT_15M"
    assert assign_lag_bucket(900) == "M15_60"
    assert assign_lag_bucket(3599.9) == "M15_60"
    assert assign_lag_bucket(3600) == "GT_60"
    assert assign_lag_bucket(7200) == "GT_60"


def test_min_detectable_effect_bps() -> None:
    mde_n5 = min_detectable_effect_bps(5, 75.0)
    assert mde_n5 is not None
    assert 95.0 < mde_n5 < 105.0

    mde_n50 = min_detectable_effect_bps(50, 75.0)
    assert mde_n50 is not None
    assert 28.0 < mde_n50 < 34.0

    assert min_detectable_effect_bps(1, 75.0) is None


def test_mde_prereg_vs_realized_in_bucket() -> None:
    pnls = [-120.0] * 24 + [120.0] * 24
    res = bucket_statistics("M15_60", pnls)
    assert res.n_trades == 48
    assert res.mde_bps_prereg is not None
    assert 31.0 < res.mde_bps_prereg < 33.5
    assert res.mde_bps_realized is not None
    assert 50.0 < res.mde_bps_realized < 52.5
    assert res.sigma_bps_realized is not None
    assert abs(res.sigma_bps_realized - 120.0) < 2.0


def test_bonferroni_alpha_and_bucket_min_n() -> None:
    assert ALPHA_EFF == 0.05 / 3
    assert MIN_TRADES_PER_BUCKET == 40
    assert MDE_REFERENCE_STD_BPS == 75.0

    low_n = bucket_statistics("M15_60", [float(i) for i in range(1, 40)])
    assert low_n.adjudication == "insufficient"
    assert low_n.bonferroni_significant is False
    assert low_n.mde_bps_prereg is not None
    assert low_n.mde_bps_realized is not None

    sig = bucket_statistics("M15_60", [float(i) for i in range(1, 51)])
    assert sig.adjudication == "adjudicated"
    assert sig.bonferroni_significant is True
    assert sig.mde_bps_prereg is not None
    assert sig.mde_bps_realized is not None

    assert not _bonferroni_significant(mean=1.0, p_value=0.02, adjudicated=True)
    assert _bonferroni_significant(mean=1.0, p_value=0.01, adjudicated=True)
    assert not _bonferroni_significant(mean=1.0, p_value=0.01, adjudicated=False)


def test_decision_pass_m15_60() -> None:
    results = {
        "LT_15M": _bucket("LT_15M", bonferroni=False),
        "M15_60": _bucket("M15_60", mean=5.0, p=0.001, bonferroni=True),
        "GT_60": _bucket("GT_60", n=2, adjudication="insufficient", mde_bps_realized=None, mde_bps_prereg=None, sigma_bps_realized=None),
    }
    decision, reason = decision_engine(results)
    assert decision == "PASS"
    assert "M15_60" in reason
    assert "GT_60" in reason


def test_decision_fail_arms_race() -> None:
    results = {
        "LT_15M": _bucket("LT_15M", mean=8.0, p=0.0001, bonferroni=True),
        "M15_60": _bucket("M15_60", bonferroni=False),
        "GT_60": _bucket("GT_60", n=1, adjudication="insufficient", mde_bps_realized=None, mde_bps_prereg=None, sigma_bps_realized=None),
    }
    decision, reason = decision_engine(results)
    assert decision == "FAIL (Latency Arms Race)"
    assert "GT_60" in reason


def test_decision_fail_no_alpha_gt60_excluded() -> None:
    results = {
        "LT_15M": _bucket("LT_15M", mean=-2.0, p=0.99, bonferroni=False, mde_bps_realized=35.0),
        "M15_60": _bucket("M15_60", mean=-1.0, p=0.9, bonferroni=False, mde_bps_realized=20.0),
        "GT_60": _bucket("GT_60", n=3, adjudication="insufficient", mde_bps_realized=None, mde_bps_prereg=None, sigma_bps_realized=None),
    }
    decision, reason = decision_engine(results)
    assert decision == "FAIL (No News Alpha)"
    assert "GT_60" in reason
    assert "80 %" in reason
    assert "nicht nachweisbar" in reason
    assert "MDE≈20bps" in reason
    assert "MDE≈35bps" in reason
    assert "Nachweisgrenze" not in reason


def test_decision_inconclusive_when_primary_insufficient() -> None:
    results = {
        "LT_15M": _bucket("LT_15M", n=20, adjudication="insufficient"),
        "M15_60": _bucket("M15_60", n=20, adjudication="insufficient"),
        "GT_60": _bucket("GT_60", n=1, adjudication="insufficient", mde_bps_realized=None, mde_bps_prereg=None, sigma_bps_realized=None),
    }
    decision, reason = decision_engine(results)
    assert decision == "INCONCLUSIVE"
    assert "M15_60" in reason


def test_data_threshold_blocked() -> None:
    events = [_event(i, lag_min=30) for i in range(10)]
    status, reason = data_threshold_status(events)
    assert status == "BLOCKED"
    assert "200" in reason

    many = [_event(i, lag_min=30) for i in range(250)]
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i, ev in enumerate(many):
        ev.t_ingest = base + timedelta(hours=i)
    status2, reason2 = data_threshold_status(many)
    assert status2 == "BLOCKED"
    assert "90" in reason2

    span_ok = [_event(i, lag_min=30) for i in range(250)]
    span_ok[0].t_ingest = datetime(2026, 1, 1, tzinfo=timezone.utc)
    span_ok[-1].t_ingest = datetime(2026, 6, 1, tzinfo=timezone.utc)
    status3, reason3 = data_threshold_status(span_ok)
    assert status3 == "OK"
    assert reason3 == ""


def test_decision_blocked_when_threshold_not_met() -> None:
    results = {
        "LT_15M": _bucket("LT_15M", mean=8.0, p=0.0001, bonferroni=True),
        "M15_60": _bucket("M15_60", mean=5.0, p=0.001, bonferroni=True),
        "GT_60": _bucket("GT_60"),
    }
    decision, reason = decision_engine(results, "BLOCKED", "span too short")
    assert decision == "BLOCKED"
    assert "span" in reason
