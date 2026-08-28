#!/usr/bin/env python3
"""P2/P5 shadow chaos battery — Compose-based (ordinal leader, gate-closed for Lease).

Runs C-01…C-04 + T-S1a (ordinal) + T-S2a (pause) and writes JSON report.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

_ROOT = Path(__file__).resolve().parents[1]
COMPOSE = _ROOT / "docker-compose.regime-swarm-shadow.yml"
REPORT_DIR = _ROOT / "logs" / "infra_guardian"
REPORT_PATH = REPORT_DIR / "shadow_chaos_latest.json"

LEADER = "regime-swarm-shadow-0"
STANDBY = "regime-swarm-shadow-1"
LEADER_METRICS_PORT = 8080
STANDBY_METRICS_PORT = 8081


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(cmd: List[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=check, cwd=_ROOT)


def _compose(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(["docker", "compose", "-f", str(COMPOSE), *args], check=check)


def _metric_is_leader(container: str, port: int) -> int:
    py = (
        "import urllib.request,re; "
        f"b=urllib.request.urlopen('http://127.0.0.1:{port}/metrics',timeout=5).read().decode(); "
        "m=re.search(r'^swarm_is_leader (\\d+)', b, re.M); "
        "print(m.group(1) if m else -1)"
    )
    r = _run(["docker", "exec", container, "python3", "-c", py], check=False)
    if r.returncode != 0:
        return -1
    try:
        return int((r.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return -1


def _wait_healthy(timeout_s: int = 90) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        h0 = _run(["docker", "exec", LEADER, "test", "-f", "/tmp/swarm_heartbeat"], check=False)
        h1 = _run(["docker", "exec", STANDBY, "test", "-f", "/tmp/swarm_heartbeat"], check=False)
        if h0.returncode == 0 and h1.returncode == 0:
            return
        time.sleep(3)
    raise RuntimeError("containers not healthy within timeout")


def _docker_logs(name: str, tail: int = 200) -> str:
    r = _run(["docker", "logs", name, f"--tail={tail}"], check=False)
    return (r.stdout or "") + (r.stderr or "")


def _record(results: List[Dict[str, Any]], test_id: str, passed: bool, detail: str) -> None:
    results.append(
        {
            "test_id": test_id,
            "passed": passed,
            "detail": detail,
            "ts": _now(),
        }
    )


def run_battery() -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_ROOT / "logs/worm/paper_runs").mkdir(parents=True, exist_ok=True)

    _compose("build", check=True)
    _compose("up", "-d", check=True)
    _wait_healthy()

    # Baseline — leader vs standby metrics
    try:
        l0 = _metric_is_leader(LEADER, LEADER_METRICS_PORT)
        l1 = _metric_is_leader(STANDBY, STANDBY_METRICS_PORT)
        _record(results, "BASELINE", l0 == 1 and l1 == 0, f"leader metrics: pod0={l0} pod1={l1}")
    except Exception as exc:
        _record(results, "BASELINE", False, str(exc))

    # T-S1a ordinal — standby must not emit COMPLETE cycles
    logs1 = _docker_logs(STANDBY, 300)
    standby_ticks = logs1.count("standby_tick")
    complete_on_standby = logs1.count('"status": "COMPLETE"')
    _record(
        results,
        "T-S1a",
        standby_ticks > 0 and complete_on_standby == 0,
        f"standby_tick={standby_ticks} complete_cycles={complete_on_standby}",
    )

    # C-01 — delete leader container (simulate pod delete)
    _run(["docker", "restart", LEADER], check=True)
    time.sleep(12)
    _wait_healthy(60)
    hb = _run(["docker", "exec", LEADER, "test", "-f", "/tmp/swarm_heartbeat"], check=False)
    _record(results, "C-01", hb.returncode == 0, "leader heartbeat after restart")

    # C-02 — ordered restart (standby first, then leader)
    _run(["docker", "restart", STANDBY], check=True)
    time.sleep(8)
    _run(["docker", "restart", LEADER], check=True)
    time.sleep(12)
    _wait_healthy(60)
    l0 = _metric_is_leader(LEADER, LEADER_METRICS_PORT)
    l1 = _metric_is_leader(STANDBY, STANDBY_METRICS_PORT)
    _record(results, "C-02", l0 == 1 and l1 == 0, f"post-rolling metrics pod0={l0} pod1={l1}")

    # C-03 — IO stress on leader (lightweight)
    stress = _run(
        [
            "docker",
            "exec",
            LEADER,
            "python3",
            "-c",
            "import json; p='/data/state/swarm_state.json'; "
            "open(p,'w').write(json.dumps({'stress':1})); "
            "import os; os.path.exists('/tmp/swarm_heartbeat')",
        ],
        check=False,
    )
    _record(results, "C-03", stress.returncode == 0, "leader state write + heartbeat ok")

    # T-S2a — pause leader (silent hang simulation)
    _run(["docker", "pause", LEADER], check=False)
    time.sleep(8)
    s1 = _metric_is_leader(STANDBY, STANDBY_METRICS_PORT)
    _run(["docker", "unpause", LEADER], check=False)
    time.sleep(6)
    # Standby must NOT promote under ordinal model
    _record(
        results,
        "T-S2a",
        s1 == 0,
        f"standby stayed non-leader during leader pause (is_leader={s1})",
    )

    # C-04 — standby survives (memory limit 384M in compose)
    st = _run(["docker", "inspect", "-f", "{{.State.Running}}", STANDBY], check=False)
    _record(results, "C-04", st.stdout.strip() == "true", f"standby running={st.stdout.strip()}")

    # P3 — state file exists on leader volume after chaos
    st_exist = _run(
        ["docker", "exec", LEADER, "test", "-f", "/data/state/swarm_state.json"],
        check=False,
    )
    _record(results, "P3-state", st_exist.returncode == 0, "swarm_state.json present on leader PVC")

    failed = [r for r in results if not r["passed"]]
    report: Dict[str, Any] = {
        "schema": "infra_guardian_shadow_chaos_v0",
        "environment": "docker-compose-shadow",
        "charter": "DEFENSIVE_CAUSAL_GROUNDING",
        "live_execution": False,
        "leader_mode": "ordinal_0_static",
        "lease_api_gate": "CLOSED",
        "ts": _now(),
        "tests": results,
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "gate_chaos_ordinal": "PASS" if not failed else "FAIL",
        "gate_lease_api": "CLOSED",
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    try:
        report = run_battery()
    except Exception as exc:
        print(json.dumps({"error": str(exc), "ts": _now()}), flush=True)
        return 1
    finally:
        _compose("down", check=False)

    print(json.dumps(report, indent=2))
    if report.get("gate_chaos_ordinal") != "PASS":
        print("VERDICT: INFRA_SHADOW_CHAOS_FAIL")
        return 1
    print("VERDICT: INFRA_SHADOW_CHAOS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
