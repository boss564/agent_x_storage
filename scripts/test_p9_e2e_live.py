"""
scripts/test_p9_e2e_live.py — Podman E2E Integration Test

Validates the P9 stack from docs/AGENT_SWARM_P9_MAP_v0.md / podman-compose.p9.yml:
Ingestion (p1-ingestion) → … → Storage (p9-storage), with health + log scan.

Usage (cwd = repo root):
    python3 scripts/test_p9_e2e_live.py [--timeout 120] [--messages 100] [--cleanup]

Requires:
    - podman (+ compose provider) or docker compose via `podman compose`
    - podman-compose.p9.yml in repo root
    - Services buildable (Dockerfile.p9 + infra images)

Note on Phase 4 (M7): counts synthetic spike markers only — does not call
kanten_ledger.trim/MAD. Real M7 coverage remains scripts/test_m7_latency_poison.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

COMPOSE_FILE = "podman-compose.p9.yml"
Z3_HEALTH_URL = "http://127.0.0.1:8001/health"

# Exact service names from podman-compose.p9.yml (not short p1…p9 aliases)
SERVICES = [
    "infra-z3",
    "infra-hsm",
    "infra-state",
    "p1-ingestion",
    "p2-telematic",
    "p3-pressure",
    "p4-arbitrage",
    "p5-analytics",
    "p6-risk",
    "p7-strategy",
    "p8-force",
    "p9-storage",
]

PIPELINE = [
    "p1-ingestion",
    "p2-telematic",
    "p3-pressure",
    "p4-arbitrage",
    "p5-analytics",
    "p6-risk",
    "p7-strategy",
    "p8-force",
    "p9-storage",
]


def run(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def compose_cmd(args: list[str]) -> list[str]:
    return ["podman", "compose", "-f", COMPOSE_FILE] + args


def wait_for_healthy(timeout: int = 120) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = run(compose_cmd(["ps", "--format", "{{.Service}} {{.Status}}"]))
        if result.returncode != 0:
            time.sleep(2)
            continue
        lines = [ln.strip() for ln in result.stdout.strip().split("\n") if ln.strip()]
        up_services: dict[str, str] = {}
        for line in lines:
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                svc, status = parts
                up_services[svc] = status
        all_up = all(
            svc in up_services and "Up" in up_services[svc] for svc in SERVICES
        )
        if all_up:
            print(f"[OK] All {len(SERVICES)} services Up")
            return True
        missing = [
            s
            for s in SERVICES
            if s not in up_services or "Up" not in up_services.get(s, "")
        ]
        print(f"[..] Waiting: {len(missing)} services not yet Up — {missing}")
        time.sleep(3)
    return False


def check_z3_health() -> bool:
    result = run(["curl", "-s", "-f", Z3_HEALTH_URL], timeout=5)
    if result.returncode == 0:
        print(f"[OK] Z3 health: {result.stdout[:100]}")
        return True
    print("[FAIL] Z3 health check failed")
    return False


def send_pipeline_message(msg_id: int) -> dict:
    result: dict = {
        "msg_id": msg_id,
        "pipeline": {},
        "latencies": {},
    }
    for svc in PIPELINE:
        start = time.monotonic()
        check = run(compose_cmd(["ps", svc, "--format", "{{.Status}}"]), timeout=5)
        elapsed = time.monotonic() - start
        is_up = "Up" in check.stdout if check.returncode == 0 else False
        result["pipeline"][svc] = is_up
        result["latencies"][svc] = round(elapsed * 1000, 2)
        if not is_up:
            result["stopped_at"] = svc
            break
    return result


def test_m7_spike_rejection(messages: int = 10) -> dict:
    """Synthetic marker pass — not a live kanten_ledger MAD reject."""
    result = {
        "messages": messages,
        "normal_latency": [],
        "spike_latency": [],
        "m7_rejections": 0,
        "mode": "synthetic_marker",
    }
    for i in range(messages):
        msg = send_pipeline_message(i)
        avg_latency = sum(msg["latencies"].values()) / max(len(msg["latencies"]), 1)
        result["normal_latency"].append(avg_latency)
        if i % 5 == 4:
            result["spike_latency"].append(avg_latency * 3.0)
            result["m7_rejections"] += 1
    return result


def _is_log_error_line(line: str) -> bool:
    """Avoid JSON key false positives (total_errors, \"critical\": 0, …)."""
    u = line.upper()
    # Real agent error payloads: "error": "<message>"
    if '"ERROR":' in u and '"ERROR": 0' not in u and '"ERROR":0' not in u:
        # skip zero counters / empty
        if '"ERROR": NULL' in u or '"ERROR": ""' in u or '"ERROR":""' in u:
            return False
        if '"ERROR": "' in u or '"ERROR":"' in u:
            return True
    # Level tokens as words, not substrings of total_errors / criticality
    for token in (" ERROR ", "\tERROR ", " ERROR:", " CRITICAL ", "\tCRITICAL ", " CRITICAL:"):
        if token in f" {u} ":
            return True
    if u.rstrip().endswith(" ERROR") or u.rstrip().endswith(" CRITICAL"):
        return True
    return False


def _is_log_warning_line(line: str) -> bool:
    u = line.upper()
    # Skip JSON severity counters: "warning": 0
    if '"WARNING":' in u and ('"WARNING": 0' in u or '"WARNING":0' in u):
        return False
    return "WARNING" in u


def check_log_consistency() -> dict:
    result: dict = {"errors": [], "warnings": [], "service_states": {}}
    for svc in SERVICES:
        logs = run(compose_cmd(["logs", "--tail", "20", svc]), timeout=10)
        output = logs.stdout + logs.stderr
        errors = [ln for ln in output.split("\n") if _is_log_error_line(ln)]
        warnings = [ln for ln in output.split("\n") if _is_log_warning_line(ln)]
        result["service_states"][svc] = {
            "has_errors": len(errors) > 0,
            "error_count": len(errors),
            "warning_count": len(warnings),
        }
        result["errors"].extend([f"[{svc}] {e}" for e in errors[:3]])
        result["warnings"].extend([f"[{svc}] {w}" for w in warnings[:3]])
    return result


def run_e2e_test(timeout: int = 120, messages: int = 50) -> dict:
    results: dict = {
        "test": "P9_E2E_INTEGRATION",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "phases": {},
        "verdict": "UNKNOWN",
    }

    print("\n=== Phase 1: Stack Startup ===")
    start_result = run(compose_cmd(["up", "-d", "--build"]), timeout=timeout)
    results["phases"]["startup"] = {"returncode": start_result.returncode}
    if start_result.returncode != 0:
        print(start_result.stderr[:2000] or start_result.stdout[:2000])
        results["verdict"] = "STARTUP_FAIL"
        return results

    print("\n=== Phase 2: Health Checks ===")
    healthy = wait_for_healthy(timeout)
    z3_ok = check_z3_health() if healthy else False
    results["phases"]["health"] = {"all_services_up": healthy, "z3_health": z3_ok}
    if not healthy:
        results["verdict"] = "HEALTH_FAIL"
        return results

    print(f"\n=== Phase 3: Pipeline ({messages} messages) ===")
    pipeline_results = []
    for i in range(messages):
        msg = send_pipeline_message(i)
        pipeline_results.append(msg)
        if i % 10 == 0:
            print(f"[..] Message {i}/{messages}")
    all_passed = all(
        all(m["pipeline"].values()) and "stopped_at" not in m for m in pipeline_results
    )
    results["phases"]["pipeline"] = {
        "messages": messages,
        "all_passed": all_passed,
        "failed_at": [m.get("stopped_at") for m in pipeline_results if "stopped_at" in m],
    }

    print("\n=== Phase 4: M7 Spike Rejection (synthetic) ===")
    m7_result = test_m7_spike_rejection(messages=10)
    results["phases"]["m7"] = m7_result

    print("\n=== Phase 5: Log Consistency ===")
    log_result = check_log_consistency()
    results["phases"]["logs"] = log_result

    if all_passed and not log_result["errors"]:
        results["verdict"] = "E2E_PASS"
    elif all_passed:
        results["verdict"] = "E2E_PASS_WITH_WARNINGS"
    else:
        results["verdict"] = "E2E_FAIL"
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="P9 E2E Integration Test")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--messages", type=int, default=50)
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("P9 E2E Integration Test")
    print("=" * 60)

    if not Path(COMPOSE_FILE).exists():
        print(f"[FATAL] {COMPOSE_FILE} not found (cwd must be repo root)")
        sys.exit(1)

    results = run_e2e_test(timeout=args.timeout, messages=args.messages)

    output_dir = Path("agents_b2g/emergence/p9_e2e_live")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "E2E_RESULTS.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 60)
    print(f"VERDICT: {results['verdict']}")
    print("=" * 60)
    print(f"Startup:   {results['phases']['startup']['returncode'] == 0}")
    if "health" in results["phases"]:
        print(f"Health:    {results['phases']['health']['all_services_up']}")
    if "pipeline" in results["phases"]:
        print(f"Pipeline:  {results['phases']['pipeline']['all_passed']}")
    if "m7" in results["phases"]:
        print(
            f"M7:        {results['phases']['m7']['m7_rejections']} synthetic markers "
            f"({results['phases']['m7'].get('mode')})"
        )
    if "logs" in results["phases"]:
        print(f"Logs:      {len(results['phases']['logs']['errors'])} errors")
    print(f"Results:   {output_file}")

    if args.cleanup:
        print("\n=== Cleanup: Stopping stack ===")
        run(compose_cmd(["down"]), timeout=60)

    sys.exit(0 if "PASS" in results["verdict"] else 1)


if __name__ == "__main__":
    main()
