#!/usr/bin/env python3
"""Smoke tests for Baustein 2 regime drift monitor + 9-agent swarm."""
from __future__ import annotations

import json
import sys
import tempfile
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
        orch = RegimeSwarmOrchestrator(audit_path=audit, seed=42)

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

    print("=" * 60)
    if failed:
        print(f"VERDICT: RAAS_REGIME_DRIFT_FAIL ({failed})")
        return 1
    print("VERDICT: RAAS_REGIME_DRIFT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
