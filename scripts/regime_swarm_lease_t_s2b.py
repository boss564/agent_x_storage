#!/usr/bin/env python3
"""T-S2b — Silent Hang / Lease-Renewal-Timeout on real K8s (Infra-Guardian P4).

Leader stops renewing; standby must acquire after lease expiry.
PASS per iteration: acquire_delay = failover − lease_duration ≤ 1.0 s,
no zombie re-acquire, I1 holds. Report median/max over n_iterations runs.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.regime_swarm.lease_harness import (  # noqa: E402
    KubectlLeaseClient,
    LeaseSpec,
)

NAMESPACE = "regime-swarm-shadow"
LEASE_NAME = "regime-swarm-leader"
CONTEXT = "kind-regime-shadow"
LEASE_DURATION_S = 15
N_ITERATIONS = 5
I3_MAX_ACQUIRE_DELAY_S = 1.0  # post-expiry takeover only (not total failover)
POLL_INTERVAL_S = 0.25
HANG_TIMEOUT_S = 30.0
LEADER = "regime-swarm-shadow-0"
STANDBY = "regime-swarm-shadow-1"
REPORT_DIR = _ROOT / "logs" / "infra_guardian"
REPORT_PATH = REPORT_DIR / "lease_t_s2b_latest.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _reset_lease(client: KubectlLeaseClient) -> None:
    snap = client.read()
    if snap and snap.holder:
        client.release(snap.holder)
    time.sleep(0.2)


def run_single_iteration(
    client: KubectlLeaseClient,
    *,
    iteration: int,
    leader: str = LEADER,
    standby: str = STANDBY,
    lease_duration_s: int = LEASE_DURATION_S,
) -> Dict[str, Any]:
    violations: List[str] = []
    _reset_lease(client)

    if not client.try_acquire(leader):
        violations.append("leader_initial_acquire_failed")
    if not client.renew(leader):
        violations.append("leader_initial_renew_failed")

    leader_snap = client.read()
    if leader_snap is None or leader_snap.holder != leader:
        violations.append("leader_not_holder_after_renew")
    last_renew = leader_snap.renew_time if leader_snap else None

    takeover_ok = False
    holders_during_failover: List[str] = []
    hang_start = time.monotonic()

    while time.monotonic() - hang_start < HANG_TIMEOUT_S:
        snap = client.read()
        holder = snap.holder if snap else ""
        holders_during_failover.append(holder)

        if snap and snap.is_expired and snap.holder == leader:
            if client.try_acquire(standby):
                takeover_ok = True
                break
        if snap and snap.holder == standby:
            takeover_ok = True
            break
        time.sleep(POLL_INTERVAL_S)

    takeover_at = datetime.now(timezone.utc)
    failover_s: float | None = None
    acquire_delay_s: float | None = None
    if last_renew:
        failover_s = (takeover_at - last_renew).total_seconds()
        acquire_delay_s = failover_s - float(lease_duration_s)

    if not takeover_ok:
        violations.append("standby_never_acquired_after_hang")
    if acquire_delay_s is None:
        violations.append("acquire_delay_unmeasured")
    elif acquire_delay_s > I3_MAX_ACQUIRE_DELAY_S:
        violations.append(f"i3_acquire_delay_too_slow:{acquire_delay_s:.3f}s")

    unique_holders = {h for h in holders_during_failover if h}
    if len(unique_holders) > 2:
        violations.append(f"too_many_identities_seen:{sorted(unique_holders)}")

    final_snap = client.read()
    final_holder = final_snap.holder if final_snap else ""
    if final_holder != standby:
        violations.append(f"final_holder_not_standby:{final_holder}")

    zombie_renew = client.renew(leader)
    zombie_acquire = client.try_acquire(leader)
    if zombie_renew:
        violations.append("zombie_leader_renew_succeeded")
    if zombie_acquire:
        violations.append("zombie_leader_acquire_succeeded")

    return {
        "iteration": iteration,
        "passed": not violations,
        "violations": violations,
        "leader": leader,
        "standby": standby,
        "last_leader_renew": last_renew.isoformat() if last_renew else None,
        "failover_seconds": round(failover_s, 3) if failover_s is not None else None,
        "acquire_delay_seconds": round(acquire_delay_s, 3) if acquire_delay_s is not None else None,
        "lease_duration_seconds": lease_duration_s,
        "final_holder": final_holder,
        "zombie_renew": zombie_renew,
        "zombie_acquire": zombie_acquire,
        "unique_holders": sorted(unique_holders),
    }


def run_t_s2b() -> Dict[str, Any]:
    spec = LeaseSpec(
        name=LEASE_NAME,
        namespace=NAMESPACE,
        lease_duration_seconds=LEASE_DURATION_S,
        renew_interval_seconds=5,
    )
    client = KubectlLeaseClient(spec, context=CONTEXT)

    manifest = _ROOT / "manifests" / "infra-guardian" / "lease.yaml"
    if manifest.is_file():
        client._kubectl("apply", "-f", str(manifest))
    else:
        client.ensure_lease_object()

    runs: List[Dict[str, Any]] = []
    for i in range(N_ITERATIONS):
        runs.append(run_single_iteration(client, iteration=i + 1))

    acquire_delays = [r["acquire_delay_seconds"] for r in runs if r["acquire_delay_seconds"] is not None]
    failovers = [r["failover_seconds"] for r in runs if r["failover_seconds"] is not None]
    violations: List[str] = []
    for r in runs:
        violations.extend(f"iter{r['iteration']}:{v}" for v in r["violations"])

    median_acquire = statistics.median(acquire_delays) if acquire_delays else None
    max_acquire = max(acquire_delays) if acquire_delays else None
    median_failover = statistics.median(failovers) if failovers else None
    max_failover = max(failovers) if failovers else None

    passed = all(r["passed"] for r in runs) and bool(acquire_delays)
    if max_acquire is not None and max_acquire > I3_MAX_ACQUIRE_DELAY_S:
        passed = False

    report: Dict[str, Any] = {
        "schema": "infra_guardian_lease_t_s2b_v1",
        "test_id": "T-S2b",
        "scenario": "silent_hang_lease_expiry",
        "namespace": NAMESPACE,
        "lease_name": LEASE_NAME,
        "context": CONTEXT,
        "n_iterations": N_ITERATIONS,
        "lease_duration_seconds": LEASE_DURATION_S,
        "i3_max_acquire_delay_seconds": I3_MAX_ACQUIRE_DELAY_S,
        "poll_interval_seconds": POLL_INTERVAL_S,
        "metric_note": (
            "acquire_delay = failover_seconds - lease_duration_seconds; "
            "measures post-expiry takeover only (lease-bound floor excluded)"
        ),
        "passed": passed,
        "verdict": "T_S2B_LEASE_PASS" if passed else "T_S2B_LEASE_FAIL",
        "violations": violations,
        "runs": runs,
        "acquire_delay_seconds": {
            "median": round(median_acquire, 3) if median_acquire is not None else None,
            "max": round(max_acquire, 3) if max_acquire is not None else None,
            "values": acquire_delays,
        },
        "failover_seconds": {
            "median": round(median_failover, 3) if median_failover is not None else None,
            "max": round(max_failover, 3) if max_failover is not None else None,
            "values": failovers,
        },
        "charter": "DEFENSIVE_CAUSAL_GROUNDING",
        "live_execution": False,
        "caveat": (
            "Total failover is structurally >= lease_duration; threshold tests acquire_delay only. "
            f"{N_ITERATIONS} runs on kind-regime-shadow; slower API may widen acquire_delay."
        ),
        "section_6_gate": "OPEN" if passed else "CLOSED",
        "ts": _now(),
    }
    return report


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = run_t_s2b()
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "verdict": report["verdict"],
                "passed": report["passed"],
                "n_iterations": report["n_iterations"],
                "acquire_delay_max": report["acquire_delay_seconds"]["max"],
                "acquire_delay_median": report["acquire_delay_seconds"]["median"],
                "section_6_gate": report.get("section_6_gate"),
                "violations": report["violations"],
            }
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
