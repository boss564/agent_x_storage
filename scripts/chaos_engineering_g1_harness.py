#!/usr/bin/env python3
"""G1 — Chaos Engineering offline harness (P6-Trading / gate_core).

Loads chaos_matrix_v1.json + fixtures, runs complete_matrix against evaluate_gate(),
applies A6 fail-closed assertions per docs/CHAOS_ENGINEERING_PREREG.md §1.

Charter: live_execution=false · shadow only · no HTTP (G2 later).
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.fail_closed_gate.gate_core import (  # noqa: E402
    GateInput,
    TradeSignal,
    evaluate_gate,
)

CONFIG_DIR = _ROOT / "config" / "chaos_engineering"
MATRIX_PATH = CONFIG_DIR / "chaos_matrix_v1.json"
REPORT_DIR = _ROOT / "logs" / "chaos_engineering"
REPORT_PATH = REPORT_DIR / "g1_latest.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_matrix() -> Dict[str, Any]:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def _load_fixture(ref: str) -> Dict[str, Any]:
    path = CONFIG_DIR / ref
    return json.loads(path.read_text(encoding="utf-8"))


def _gate_input_from_fixture(fixture: Dict[str, Any]) -> GateInput:
    gi = fixture["gate_input"]
    sig = gi["signal"]
    return GateInput(
        signal=TradeSignal(
            signal_id=str(sig["signal_id"]),
            source=str(sig["source"]),
            notional_eur=float(sig.get("notional_eur", 0)),
            stress_score=float(sig.get("stress_score", 0)),
            oracle_ok=bool(sig.get("oracle_ok", True)),
            scenario_ok=bool(sig.get("scenario_ok", True)),
        ),
        exec_risk=float(gi.get("exec_risk", 0)),
        cascade_risk=float(gi.get("cascade_risk", 0)),
        latency_spike=gi.get("latency_spike"),
        bho_delta=float(gi.get("bho_delta", 0)),
        human_gate_open=False,
    )


def _capture_probe(case_id: str, fixture: Dict[str, Any]) -> Tuple[Dict[str, Any], float]:
    started = time.perf_counter()
    try:
        inp = _gate_input_from_fixture(fixture)
        verdict = evaluate_gate(inp)
        latency_ms = (time.perf_counter() - started) * 1000.0
        gate_dict = verdict.to_dict()
        order_send = verdict.decision == "RELEASED"
        probe = {
            "schema": "chaos_gate_probe_v1",
            "ts": _now(),
            "case_id": case_id,
            "probe_status": "OK",
            "processing_latency_ms": round(latency_ms, 4),
            "gate_verdict": gate_dict,
            "derived": {"order_send": order_send},
        }
        return probe, latency_ms
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000.0
        probe = {
            "schema": "chaos_gate_probe_v1",
            "ts": _now(),
            "case_id": case_id,
            "probe_status": "PROBE_ERROR",
            "processing_latency_ms": round(latency_ms, 4),
            "error": str(exc),
            "gate_verdict": None,
            "derived": {"order_send": None},
        }
        return probe, latency_ms


def _assert_fail_closed(
    probe: Dict[str, Any],
    expect: Dict[str, Any],
    max_probe_latency_ms: float,
) -> Tuple[bool, Optional[str]]:
    if probe.get("probe_status") != expect.get("probe_status", "OK"):
        return False, f"probe_status={probe.get('probe_status')}"

    verdict = probe.get("gate_verdict") or {}
    decision = verdict.get("decision")
    reasons = list(verdict.get("reasons") or [])
    order_send = probe.get("derived", {}).get("order_send")

    if decision != expect.get("decision"):
        return False, f"decision={decision} expected {expect.get('decision')}"
    if order_send is not expect.get("order_send"):
        return False, f"order_send={order_send} expected {expect.get('order_send')}"

    required_any = set(expect.get("required_reasons_any") or [])
    allowed_only = set(expect.get("allowed_reasons_only") or [])
    reason_set = set(reasons)

    if required_any and not (reason_set & required_any):
        return False, f"reasons {reasons} missing any of {sorted(required_any)}"
    if allowed_only and not reason_set.issubset(allowed_only):
        return False, f"reasons {reasons} not subset of {sorted(allowed_only)}"

    latency = float(probe.get("processing_latency_ms") or 0)
    case_max = expect.get("max_probe_latency_ms")
    limit = float(case_max if case_max is not None else max_probe_latency_ms)
    if latency > limit:
        return False, f"latency_ms={latency} > {limit}"

    return True, None


def run_g1_harness() -> Dict[str, Any]:
    matrix = _load_matrix()
    policy = matrix.get("run_policy") or {}
    max_latency = float(policy.get("max_probe_latency_ms", 10))
    cases_out: List[Dict[str, Any]] = []
    failed: List[str] = []

    for case in matrix.get("cases") or []:
        if not case.get("enabled", True):
            continue
        case_id = str(case["id"])
        fixture = _load_fixture(str(case["fixture_ref"]))
        if policy.get("reset_between_cases", True):
            pass  # gate_core evaluate_gate is stateless for G1 offline

        probe, _ = _capture_probe(case_id, fixture)
        passed, violation = _assert_fail_closed(probe, case["expect"], max_latency)
        row = {
            "id": case_id,
            "fault_type": case.get("fault_type"),
            "passed": passed,
            "violation": violation,
            "probe": probe,
        }
        cases_out.append(row)
        if not passed:
            failed.append(case_id)

    total = len(cases_out)
    passed_n = sum(1 for c in cases_out if c["passed"])
    all_pass = passed_n == total and total > 0
    if policy.get("fail_if_any_case_fails", True) and failed:
        verdict = "CHAOS_G1_FAIL"
    elif all_pass:
        verdict = "CHAOS_G1_PASS"
    else:
        verdict = "CHAOS_G1_FAIL"

    report = {
        "schema": "chaos_engineering_g1_report_v1",
        "ts": _now(),
        "experiment_id": matrix.get("experiment_id"),
        "p6_layer": matrix.get("p6_layer"),
        "gate": "G1",
        "mode": "offline_gate_core",
        "run_policy": policy,
        "total_tests": total,
        "passed": passed_n,
        "failed": total - passed_n,
        "fail_closed_rate": f"{(100.0 * passed_n / total):.2f}%" if total else "0.00%",
        "failed_cases": failed,
        "verdict": verdict,
        "cases": cases_out,
        "live_execution": False,
        "charter": matrix.get("charter"),
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    if not MATRIX_PATH.is_file():
        print(f"CHAOS_G1_FAIL missing config: {MATRIX_PATH}", file=sys.stderr)
        return 1
    report = run_g1_harness()
    print(json.dumps({"verdict": report["verdict"], "passed": report["passed"], "total": report["total_tests"], "report": str(REPORT_PATH)}))
    return 0 if report["verdict"] == "CHAOS_G1_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
