#!/usr/bin/env python3
"""Forensic Drill 2 — lease timeline during graceful scale-down (kind shadow cluster).

Determines whether failover used release (holder empty, renew_age < lease_duration)
or expiry (renew_age >= lease_duration) — never non-expired steal.
"""
from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = _ROOT / "logs" / "infra_guardian"
LOG_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = LOG_DIR / "lease_failover_forensic_latest.json"

NS = "regime-swarm-shadow"
LEASE = "regime-swarm-leader"
LEASE_DURATION_S = 15


def _kubectl_json(*args: str) -> Any:
    cmd = ["kubectl", "-n", NS, *args, "-o", "json"]
    out = subprocess.check_output(cmd, text=True)
    return json.loads(out)


def _lease_snapshot() -> Dict[str, Any]:
    data = _kubectl_json("get", "lease", LEASE)
    spec = data.get("spec") or {}
    renew = spec.get("renewTime") or ""
    holder = str(spec.get("holderIdentity") or "")
    renew_age_s: Optional[float] = None
    if renew:
        rt = datetime.fromisoformat(renew.replace("Z", "+00:00"))
        renew_age_s = (datetime.now(timezone.utc) - rt).total_seconds()
    return {
        "holder": holder,
        "renew_time": renew,
        "renew_age_s": round(renew_age_s, 3) if renew_age_s is not None else None,
        "acquire_time": spec.get("acquireTime"),
    }


def _metrics_leader(pod: str) -> int:
    try:
        out = subprocess.check_output(
            [
                "kubectl",
                "exec",
                "-n",
                NS,
                pod,
                "--",
                "wget",
                "-qO-",
                "http://127.0.0.1:8080/metrics",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return -1
    for line in out.splitlines():
        if line.startswith("swarm_is_leader "):
            return int(float(line.split()[1]))
    return -1


def _find_leader_pod() -> str:
    for pod in ("regime-swarm-shadow-0", "regime-swarm-shadow-1"):
        if _metrics_leader(pod) == 1:
            return pod
    snap = _lease_snapshot()
    if snap["holder"]:
        return snap["holder"]
    raise RuntimeError("no leader pod found")


def _wait_for_leader(pod: str, timeout_s: float = 90) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if _find_leader_pod() == pod:
                return True
        except RuntimeError:
            pass
        time.sleep(1)
    return False


def _force_leader(pod: str) -> None:
    """Clear lease so daemons race; wait until `pod` holds the lease."""
    subprocess.run(
        [
            "kubectl",
            "patch",
            "lease",
            LEASE,
            "-n",
            NS,
            "--type=merge",
            "-p",
            '{"spec":{"holderIdentity":"","renewTime":null,"acquireTime":null}}',
        ],
        check=True,
    )
    if not _wait_for_leader(pod):
        raise RuntimeError(f"could not elect {pod} as leader within timeout")


def _scale_replicas(n: int) -> None:
    subprocess.run(
        ["kubectl", "scale", "statefulset", "regime-swarm-shadow", "-n", NS, f"--replicas={n}"],
        check=True,
    )
    subprocess.run(
        [
            "kubectl",
            "rollout",
            "status",
            "statefulset/regime-swarm-shadow",
            "-n",
            NS,
            "--timeout=5m",
        ],
        check=True,
    )


def main() -> int:
    _scale_replicas(2)
    time.sleep(8)
    _force_leader("regime-swarm-shadow-1")
    leader_before = "regime-swarm-shadow-1"
    snap_before = _lease_snapshot()
    t0 = time.time()
    _scale_replicas(1)

    timeline: List[Dict[str, Any]] = []
    takeover: Optional[Dict[str, Any]] = None
    for _ in range(60):
        snap = _lease_snapshot()
        row = {"t_s": round(time.time() - t0, 2), **snap}
        timeline.append(row)
        if snap["holder"] == "regime-swarm-shadow-0" and takeover is None:
            takeover = row
        time.sleep(0.5)

    renew_at_takeover = takeover.get("renew_age_s") if takeover else None
    holder_empty_seen = any(not row["holder"] for row in timeline[:20])

    if holder_empty_seen and takeover and (renew_at_takeover or 0) < LEASE_DURATION_S:
        verdict = "RELEASE_OR_EMPTY_TAKEOVER"
    elif takeover and (renew_at_takeover or 0) >= LEASE_DURATION_S:
        verdict = "EXPIRED_TAKEOVER"
    elif takeover and (renew_at_takeover or 0) < LEASE_DURATION_S:
        verdict = "STEAL_NON_EXPIRED_SUSPECT"
    else:
        verdict = "INCONCLUSIVE"

    report = {
        "schema": "lease_failover_forensic_v1",
        "ts": datetime.now(timezone.utc).isoformat(),
        "leader_before": leader_before,
        "snap_before_scale": snap_before,
        "takeover": takeover,
        "holder_empty_seen_early": holder_empty_seen,
        "verdict": verdict,
        "timeline": timeline,
    }
    OUT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": verdict, "takeover": takeover, "out": str(OUT_PATH)}))
    return 0 if verdict in ("RELEASE_OR_EMPTY_TAKEOVER", "EXPIRED_TAKEOVER") else 1


if __name__ == "__main__":
    raise SystemExit(main())
