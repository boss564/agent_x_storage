#!/usr/bin/env python3
"""Live Z3 latency screen — HTTP against infra-z3 (not mock wall_clock).

Measures wall-clock round-trip to POST /prove_bho_invariant on a running
Z3 service (default http://127.0.0.1:8001). Records min/median/p95/max.

Does NOT license “Echtzeit” language by itself — Gate-Map documents numbers.
Charter: DEFENSIVE_CAUSAL_GROUNDING · live_execution=false

Usage:
  PYTHONPATH=. python3 scripts/test_live_z3_latency.py
  make raas-live-z3-latency
  Z3_BASE_URL=http://127.0.0.1:8001 N_RUNS=50 python3 scripts/test_live_z3_latency.py

Requires: infra-z3 reachable (e.g. docker compose -f podman-compose.p9.yml up -d infra-z3)
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

Z3_BASE_URL = os.environ.get("Z3_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
N_RUNS = int(os.environ.get("N_RUNS", "50"))
WARMUP = int(os.environ.get("WARMUP", "5"))
SEED_TAG = os.environ.get("LIVE_Z3_SEED", "20260827")
TIMEOUT_S = float(os.environ.get("Z3_TIMEOUT_S", "5.0"))
SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"

# Representative BHO-valid payload (same numbers as service docstring example)
BHO_OK = {
    "sector": "BAU",
    "gross_amount": 45000.00,
    "net_amount": 36000.00,
    "tax_amount": 6750.00,
    "retention_amount": 2250.00,
}


def _percentile(sorted_vals: List[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def _http_json(method: str, url: str, body: Dict[str, Any] | None = None) -> Tuple[int, Dict[str, Any], float]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            raw = resp.read()
            ms = (time.perf_counter() - t0) * 1000.0
            payload = json.loads(raw.decode()) if raw else {}
            return int(resp.status), payload, ms
    except urllib.error.HTTPError as exc:
        ms = (time.perf_counter() - t0) * 1000.0
        try:
            detail = json.loads(exc.read().decode())
        except Exception:
            detail = {"error": str(exc)}
        return int(exc.code), detail, ms


def measure() -> Dict[str, Any]:
    health_url = f"{Z3_BASE_URL}/health"
    prove_url = f"{Z3_BASE_URL}/prove_bho_invariant"

    try:
        code, health, health_ms = _http_json("GET", health_url)
    except Exception as exc:
        return {
            "verdict": "LIVE_Z3_LATENCY_UNREACHABLE",
            "z3_base_url": Z3_BASE_URL,
            "error": str(exc),
            "scope": SCOPE,
            "live_execution": False,
            "note": "Start infra-z3 (host :8001) then re-run",
        }

    if code != 200:
        return {
            "verdict": "LIVE_Z3_LATENCY_UNREACHABLE",
            "z3_base_url": Z3_BASE_URL,
            "health_status": code,
            "health": health,
            "scope": SCOPE,
            "live_execution": False,
        }

    # Warmup (discarded)
    for _ in range(WARMUP):
        _http_json("POST", prove_url, BHO_OK)

    samples_ms: List[float] = []
    proof_us: List[float] = []
    ok_count = 0
    for i in range(N_RUNS):
        code, body, ms = _http_json("POST", prove_url, BHO_OK)
        samples_ms.append(ms)
        if code == 200 and body.get("bho_invariant_valid") is True:
            ok_count += 1
            if "proof_time_us" in body:
                proof_us.append(float(body["proof_time_us"]))
        else:
            # Still count wall latency; mark failure
            pass

    ordered = sorted(samples_ms)
    result: Dict[str, Any] = {
        "screen": "live_z3_latency_v0",
        "z3_base_url": Z3_BASE_URL,
        "seed_tag": SEED_TAG,
        "n_runs": N_RUNS,
        "warmup": WARMUP,
        "health_ms": round(health_ms, 3),
        "health": health,
        "ok_count": ok_count,
        "payload": BHO_OK,
        "wall_ms": {
            "min": round(min(ordered), 3),
            "median": round(statistics.median(ordered), 3),
            "p50": round(_percentile(ordered, 50), 3),
            "p95": round(_percentile(ordered, 95), 3),
            "p99": round(_percentile(ordered, 99), 3),
            "max": round(max(ordered), 3),
            "mean": round(statistics.fmean(ordered), 3),
        },
        "samples_ms": [round(x, 3) for x in samples_ms],
        "scope": SCOPE,
        "live_execution": False,
        "note": (
            "HTTP RTT to infra-z3 /prove_bho_invariant — not mock wall_clock. "
            "Does not by itself authorize 'Echtzeit' marketing copy."
        ),
    }
    if proof_us:
        pu = sorted(proof_us)
        result["solver_proof_us"] = {
            "min": round(min(pu), 3),
            "median": round(statistics.median(pu), 3),
            "p95": round(_percentile(pu, 95), 3),
            "max": round(max(pu), 3),
            "mean": round(statistics.fmean(pu), 3),
        }

    reachable = ok_count == N_RUNS
    result["verdict"] = (
        "LIVE_Z3_LATENCY_PASS" if reachable else "LIVE_Z3_LATENCY_FAIL"
    )
    return result


def main() -> int:
    print("Live Z3 latency (infra-z3 HTTP)")
    print("=" * 60)
    print(f"Z3_BASE_URL={Z3_BASE_URL}  N_RUNS={N_RUNS}  WARMUP={WARMUP}")
    result = measure()
    verdict = result.get("verdict", "LIVE_Z3_LATENCY_FAIL")
    if "wall_ms" in result:
        w = result["wall_ms"]
        print(
            f"  wall_ms  min={w['min']}  median={w['median']}  "
            f"p95={w['p95']}  p99={w['p99']}  max={w['max']}"
        )
        print(f"  ok={result['ok_count']}/{result['n_runs']}")
        if "solver_proof_us" in result:
            s = result["solver_proof_us"]
            print(
                f"  proof_us median={s['median']}  p95={s['p95']}  "
                f"(server-reported solver only)"
            )
    else:
        print(f"  error={result.get('error') or result.get('health_status')}")
    print("=" * 60)
    print(f"VERDICT: {verdict}")

    out = _ROOT / "prototypes" / "v2_stateful_graph" / "live_z3_latency_results.json"
    try:
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"artifact: {out}")
    except OSError as exc:
        print(f"artifact: skipped ({exc})")

    data_out = _ROOT / "data" / "raas" / "live_z3_latency_last.json"
    try:
        data_out.parent.mkdir(parents=True, exist_ok=True)
        data_out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    except OSError:
        pass

    return 0 if verdict == "LIVE_Z3_LATENCY_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
