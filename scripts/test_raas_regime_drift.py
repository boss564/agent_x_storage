#!/usr/bin/env python3
"""Smoke tests for Baustein 2 regime drift monitor + 9-agent swarm."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.regime_drift import (  # noqa: E402
    assess_price_series,
    kolmogorov_smirnov_stat,
    permutation_ks_pvalue,
    wasserstein_1d,
)
from prototypes.raas_paper_trading.regime_swarm import RegimeSwarmOrchestrator  # noqa: E402
from prototypes.raas_paper_trading.regime_swarm.adaptive import (  # noqa: E402
    AdaptiveCoolingOffManager,
    DynamicWindowManager,
    SoftStrategyState,
    StuckUnreliableTracker,
)
from prototypes.raas_paper_trading.regime_swarm.leader import is_leader_pod, pod_ordinal  # noqa: E402
from prototypes.raas_paper_trading.regime_swarm.state_store import SwarmStateStore  # noqa: E402
from prototypes.raas_paper_trading.regime_swarm.agents import (  # noqa: E402
    DriftClassifierAgent,
    StrategyAdapterAgent,
    build_r2_cubed_series,
    calculate_iid_violation_flag,
)
from prototypes.raas_paper_trading.regime_swarm.types import (  # noqa: E402
    FeatureMatrix,
    KSFeatureResult,
    WassersteinResult,
)


def _write_worm(path: Path, prices: list[float]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for i, p in enumerate(prices):
            f.write(
                json.dumps(
                    {
                        "action": "SIGNAL",
                        "mark_price": p,
                        "seq": i,
                    }
                )
                + "\n"
            )


def main() -> int:
    failed = 0

    base = [float(i) for i in range(80)]
    d_same, p_same = permutation_ks_pvalue(base, list(base), n_perm=200, seed=1)
    shifted = [float(i) + 50.0 for i in range(80)]
    d_shift, p_shift = permutation_ks_pvalue(base, shifted, n_perm=200, seed=1)
    if p_same < 0.5:
        print(f"  FAIL  KS p should be high for identical samples (p={p_same})")
        failed += 1
    else:
        print("  PASS  KS identical samples")
    if p_shift > 0.01:
        print(f"  FAIL  KS p should be low for shifted samples (p={p_shift})")
        failed += 1
    else:
        print("  PASS  KS shifted samples")

    w0 = wasserstein_1d([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    w1 = wasserstein_1d([1.0, 2.0, 3.0], [10.0, 11.0, 12.0])
    if w0 != 0.0 or w1 <= 0.0:
        print("  FAIL  wasserstein_1d")
        failed += 1
    else:
        print("  PASS  wasserstein_1d")

    stable = [100.0 + (i % 3) * 0.01 for i in range(200)]
    report_stable = assess_price_series(stable, symbol="TEST")
    if report_stable.get("regime_drift"):
        print("  FAIL  stable series should not drift")
        failed += 1
    else:
        print("  PASS  stable series no drift")

    crash = stable[:100] + [stable[99] * (0.99 ** (i + 1)) for i in range(100)]
    report_crash = assess_price_series(crash, symbol="TEST")
    if not report_crash.get("regime_drift"):
        print("  FAIL  crash series should flag drift")
        failed += 1
    else:
        print("  PASS  crash series drift detected")

    if kolmogorov_smirnov_stat([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) > 1e-12:
        print("  FAIL  ks stat identical")
        failed += 1
    else:
        print("  PASS  ks stat identical")

    with tempfile.TemporaryDirectory() as tmp:
        worm_stable = Path(tmp) / "stable.jsonl"
        worm_crash = Path(tmp) / "crash.jsonl"
        audit = Path(tmp) / "audit.jsonl"
        _write_worm(worm_stable, stable)
        _write_worm(worm_crash, crash)
        orch = RegimeSwarmOrchestrator(
            audit_path=audit,
            cooling_path=Path(tmp) / "cooling.jsonl",
            seed=42,
        )

        r_stable = orch.run_cycle(worm_path=worm_stable, symbol="TEST", write_audit=False)
        if r_stable.get("status") != "COMPLETE":
            print(f"  FAIL  swarm stable status={r_stable.get('status')}")
            failed += 1
        elif (r_stable.get("drift_summary") or {}).get("regime_flag", 99) > 1:
            print("  FAIL  swarm stable should not be critical")
            failed += 1
        else:
            print("  PASS  swarm stable cycle")

        r_crash = orch.run_cycle(worm_path=worm_crash, symbol="TEST", write_audit=True)
        ds = r_crash.get("drift_summary") or {}
        if r_crash.get("status") != "COMPLETE":
            print(f"  FAIL  swarm crash status={r_crash.get('status')}")
            failed += 1
        elif ds.get("regime_flag", 0) < 1:
            print(f"  FAIL  swarm crash should warn (flag={ds.get('regime_flag')})")
            failed += 1
        else:
            print("  PASS  swarm crash drift flagged")
        if not audit.is_file() and r_crash.get("alert_level") != "OK":
            print("  FAIL  swarm crash should write audit when alert")
            failed += 1
        elif r_crash.get("alert_level") != "OK":
            print("  PASS  swarm audit append")
        adv = r_crash.get("adaptive_action") or {}
        if not adv.get("advisory_only"):
            print("  FAIL  A8 must be advisory_only")
            failed += 1
        else:
            print("  PASS  A8 advisory_only")

    # --- A4 i.i.d. monitor + A7 override + A8 interlock (unit) ---
    ar_returns = [0.2]
    for _ in range(80):
        ar_returns.append(0.92 * ar_returns[-1])
    r2_series = build_r2_cubed_series(ar_returns)
    iid = calculate_iid_violation_flag(r2_series)
    if not iid.is_iid_violation or iid.rho <= 0.3:
        print(f"  FAIL  AR(1) r2_cubed should trigger iid violation (rho={iid.rho})")
        failed += 1
    else:
        print("  PASS  A4 iid violation on autocorrelated r2_cubed")

    matrix = FeatureMatrix(
        names=["log_return_pct"],
        baseline={"log_return_pct": [0.01 + (i % 3) * 0.001 for i in range(40)]},
        current={"log_return_pct": ar_returns[-40:]},
    )
    ks_hit = [
        KSFeatureResult(feature="log_return_pct", d_stat=0.5, p_value=0.001, drift_detected=True)
    ]
    w_res = WassersteinResult(mean_w1=0.5, max_w1=0.5, per_feature={"log_return_pct": 0.5})
    clf = DriftClassifierAgent()
    classification, _meta, intervention = clf.run(
        ks_hit, w_res, matrix, iid_status=iid
    )
    if not classification.iid_unreliable or classification.allow_amendment:
        print("  FAIL  A7 should block amendment when iid unreliable")
        failed += 1
    elif classification.regime_flag < 1:
        print("  FAIL  A7 must preserve regime_flag on iid unreliable path")
        failed += 1
    else:
        print("  PASS  A7 iid-unreliable override (flag preserved)")
    if classification.classified_regime != "DRIFT_IID_UNRELIABLE":
        print(f"  FAIL  A7 regime label (got {classification.classified_regime})")
        failed += 1
    else:
        print("  PASS  A7 DRIFT_IID_UNRELIABLE label")
    if intervention is None or not intervention.triggered:
        print("  FAIL  A7 pre_reg intervention missing")
        failed += 1
    else:
        print("  PASS  A7 pre_reg intervention")

    adv, a8_meta = StrategyAdapterAgent().run(
        classification,
        symbol="TEST",
        cooling_decision={"action": "WARN_ONLY", "confirmed": True},
    )
    if not a8_meta.get("amendment_skipped") or a8_meta.get("final_action") != "PARAMETER_UNCHANGED":
        print("  FAIL  A8 interlock should NOP when amendment blocked")
        failed += 1
    else:
        print("  PASS  A8 interlock NOP")

    # --- Scenario 15: Bonferroni + high rho → IID unreliable, window stretch ---
    walk = [0.0]
    for _ in range(99):
        walk.append(walk[-1] + 0.15)
    dwm = DynamicWindowManager()
    wmeta = dwm.adapt_window("S15", walk)
    iid15 = calculate_iid_violation_flag(build_r2_cubed_series(ar_returns))
    ks15 = [
        KSFeatureResult("log_return_pct", 0.4, 0.001, True),
        KSFeatureResult("abs_return_pct", 0.2, 0.1, False),
        KSFeatureResult("down_move_pct", 0.2, 0.1, False),
        KSFeatureResult("rolling_vol_pct", 0.2, 0.1, False),
    ]
    m15 = FeatureMatrix(
        names=["log_return_pct", "abs_return_pct", "down_move_pct", "rolling_vol_pct"],
        baseline={"log_return_pct": [0.01] * 40, "abs_return_pct": [0.01] * 40,
                  "down_move_pct": [0.0] * 40, "rolling_vol_pct": [0.01] * 40},
        current={"log_return_pct": ar_returns[-40:], "abs_return_pct": [0.05] * 40,
                 "down_move_pct": [0.02] * 40, "rolling_vol_pct": [0.03] * 40},
    )
    c15, _, _ = DriftClassifierAgent().run(
        ks15, WassersteinResult(0.5, 0.5, {}), m15, iid_status=iid15
    )
    if (
        c15.regime_flag != 1
        or c15.classified_regime != "DRIFT_IID_UNRELIABLE"
        or not wmeta.get("was_stretched")
        or c15.allow_amendment
    ):
        print("  FAIL  scenario 15 bonferroni+iid+window stretch")
        failed += 1
    else:
        print("  PASS  scenario 15 bonferroni+iid+window stretch")

    # --- Scenario 16: 5 real-drift cycles → ADAPT ---
    with tempfile.TemporaryDirectory() as tmp16:
        cool_path = Path(tmp16) / "cool.jsonl"
        mgr = AdaptiveCoolingOffManager(path=cool_path)
        last = {}
        for _ in range(5):
            last = mgr.update("S16", regime_flag=2, classified_regime="HIGH_VOL_TREND")
        if last.get("action") != "ADAPT" or not last.get("confirmed"):
            print(f"  FAIL  scenario 16 adaptive cooling (got {last})")
            failed += 1
        else:
            print("  PASS  scenario 16 adaptive cooling ADAPT at cycle 5")

    # --- Scenario 17: stuck unreliable >4h → REVIEW_REQUIRED ---
    t0 = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)
    tracker = StuckUnreliableTracker()
    tracker.now_fn = lambda: t0  # type: ignore[method-assign]
    tracker.evaluate("S17", "DRIFT_IID_UNRELIABLE")
    tracker.now_fn = lambda: t0 + timedelta(hours=5)  # type: ignore[method-assign]
    comp = tracker.evaluate("S17", "DRIFT_IID_UNRELIABLE")
    if comp.get("compliance_alert") != "REVIEW_REQUIRED":
        print("  FAIL  scenario 17 stuck unreliable telemetry")
        failed += 1
    else:
        print("  PASS  scenario 17 stuck unreliable REVIEW_REQUIRED")

    # --- Scenario 18: state store round-trip (container cold start) ---
    with tempfile.TemporaryDirectory() as tmp18:
        state_path = Path(tmp18) / "swarm_state.json"
        soft = SoftStrategyState()
        soft._current["BTCUSDC"] = 1.15
        tracker18 = StuckUnreliableTracker()
        tracker18._start["BTCUSDC"] = t0
        store = SwarmStateStore(state_path)
        store.capture_soft_state(soft)
        store.capture_stuck_state(tracker18)
        store.save()
        soft2 = SoftStrategyState()
        tracker2 = StuckUnreliableTracker()
        store2 = SwarmStateStore(state_path)
        store2.load()
        store2.apply_soft_state(soft2)
        store2.apply_stuck_state(tracker2)
        if soft2.current("BTCUSDC") != 1.15 or tracker2._start.get("BTCUSDC") != t0:
            print("  FAIL  scenario 18 state store round-trip")
            failed += 1
        else:
            print("  PASS  scenario 18 state store round-trip")

    # --- Scenario 19: StatefulSet leader election (ordinal 0 = active) ---
    if pod_ordinal("regime-swarm-0") != 0 or pod_ordinal("regime-swarm-1") != 1:
        print("  FAIL  scenario 19 pod ordinal parse")
        failed += 1
    elif not is_leader_pod("regime-swarm-0", election_enabled=True):
        print("  FAIL  scenario 19 leader ordinal 0")
        failed += 1
    elif is_leader_pod("regime-swarm-1", election_enabled=True):
        print("  FAIL  scenario 19 standby ordinal 1")
        failed += 1
    elif not is_leader_pod("regime-swarm-1", election_enabled=False):
        print("  FAIL  scenario 19 election disabled")
        failed += 1
    else:
        print("  PASS  scenario 19 leader election ordinals")

    print("=" * 60)
    if failed:
        print(f"VERDICT: RAAS_REGIME_DRIFT_FAIL ({failed})")
        return 1
    print("VERDICT: RAAS_REGIME_DRIFT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
