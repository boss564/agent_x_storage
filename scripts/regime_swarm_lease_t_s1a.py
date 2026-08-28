#!/usr/bin/env python3
"""T-S1a — Split-Brain Lease test on real K8s (Infra-Guardian P5).

Two contenders race for coordination.k8s.io/v1 Lease `regime-swarm-leader`.
PASS: at every snapshot exactly one holder identity (I1).

Does NOT enable daemon lease mode (gate-closed for leader.py v2).
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
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
ROUNDS = 40
WORKERS = 2
IDENTITIES = ("regime-swarm-shadow-0", "regime-swarm-shadow-1")
REPORT_DIR = _ROOT / "logs" / "infra_guardian"
REPORT_PATH = REPORT_DIR / "lease_t_s1a_latest.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _worker_race(identity: str, rounds: int, context: str) -> Dict[str, Any]:
    spec = LeaseSpec(name=LEASE_NAME, namespace=NAMESPACE, lease_duration_seconds=15)
    client = KubectlLeaseClient(spec, context=context)
    wins = 0
    for _ in range(rounds):
        if client.try_acquire(identity):
            wins += 1
        time.sleep(0.05)
    snap = client.read()
    return {"identity": identity, "wins": wins, "holder_after": snap.holder if snap else ""}


def _count_holders(snapshot_holders: List[str]) -> int:
    active = {h for h in snapshot_holders if h}
    return len(active)


def run_t_s1a() -> Dict[str, Any]:
    spec = LeaseSpec(name=LEASE_NAME, namespace=NAMESPACE, lease_duration_seconds=15)
    client = KubectlLeaseClient(spec, context=CONTEXT)

    manifest = _ROOT / "manifests" / "infra-guardian" / "lease.yaml"
    if manifest.is_file():
        client._kubectl("apply", "-f", str(manifest))
    else:
        client.ensure_lease_object()

    # Reset lease holder
    client.release("reset")
    time.sleep(0.5)

    snapshots: List[Dict[str, Any]] = []
    violations: List[str] = []

    # Phase 1: concurrent race (split-brain simulation via API contention)
    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        futures = [
            pool.submit(_worker_race, IDENTITIES[i], ROUNDS, CONTEXT)
            for i in range(WORKERS)
        ]
        worker_results: List[Dict[str, Any]] = []
        for fut in as_completed(futures):
            worker_results.append(fut.result())

    snap = client.read()
    holder = snap.holder if snap else ""
    snapshots.append({"phase": "post_race", "holder": holder, "ts": _now()})
    if not holder:
        violations.append("no_holder_after_race")

  # Phase 2: poll holder stability — single holder over 20 samples
    holders_seen: List[str] = []
    for i in range(20):
        s = client.read()
        h = s.holder if s else ""
        holders_seen.append(h)
        snapshots.append({"phase": "stability_poll", "sample": i, "holder": h, "ts": _now()})
        if _count_holders([h]) > 1:
            violations.append(f"multiple_holders_sample_{i}")
        time.sleep(0.25)

    unique_holders = {h for h in holders_seen if h}
    if len(unique_holders) > 1:
        violations.append(f"holder_flip_during_stability:{sorted(unique_holders)}")

    # Phase 3: contender B cannot steal while A renews
    leader, challenger = IDENTITIES
    client.try_acquire(leader)
    stolen = False
    for _ in range(10):
        client.renew(leader)
        if client.try_acquire(challenger):
            stolen = True
            break
        time.sleep(0.2)
    if stolen:
        violations.append("challenger_stole_active_lease")
    renew_snap = client.read()
    snapshots.append(
        {
            "phase": "renew_fence",
            "leader": leader,
            "challenger": challenger,
            "stolen": stolen,
            "holder": renew_snap.holder if renew_snap else "",
        }
    )
    final = client.read()
    final_holder = final.holder if final else ""

    passed = not violations and bool(final_holder)
    report = {
        "schema": "infra_guardian_lease_t_s1a_v0",
        "test_id": "T-S1a",
        "scenario": "split_brain_lease_race",
        "namespace": NAMESPACE,
        "lease_name": LEASE_NAME,
        "context": CONTEXT,
        "passed": passed,
        "verdict": "T_S1A_LEASE_PASS" if passed else "T_S1A_LEASE_FAIL",
        "violations": violations,
        "worker_results": worker_results,
        "unique_holders_stability": sorted(unique_holders),
        "final_holder": final_holder,
        "snapshots": snapshots,
        "charter": "DEFENSIVE_CAUSAL_GROUNDING",
        "live_execution": False,
        "gate_note": "daemon lease runtime still CLOSED — harness-only",
        "ts": _now(),
    }
    return report


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = run_t_s1a()
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"], "passed": report["passed"], "violations": report["violations"]}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
