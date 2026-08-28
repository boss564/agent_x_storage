"""Chaos Engineering harness shared logic (P6-Trading / gate_core)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from services.fail_closed_gate.gate_core import GateInput, TradeSignal, evaluate_gate

_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = _ROOT / "config" / "chaos_engineering"
MATRIX_PATH = CONFIG_DIR / "chaos_matrix_v1.json"
REPORT_DIR = _ROOT / "logs" / "chaos_engineering"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_matrix() -> Dict[str, Any]:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def load_fixture(ref: str) -> Dict[str, Any]:
    return json.loads((CONFIG_DIR / ref).read_text(encoding="utf-8"))


def gate_input_from_fixture(fixture: Dict[str, Any]) -> GateInput:
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


def fixture_to_evaluate_body(fixture: Dict[str, Any]) -> Dict[str, Any]:
    gi = fixture["gate_input"]
    sig = gi["signal"]
    return {
        "signal": {
            "signal_id": str(sig["signal_id"]),
            "source": str(sig["source"]),
            "notional_eur": float(sig.get("notional_eur", 0)),
            "stress_score": float(sig.get("stress_score", 0)),
            "oracle_ok": bool(sig.get("oracle_ok", True)),
            "scenario_ok": bool(sig.get("scenario_ok", True)),
        },
        "exec_risk": float(gi.get("exec_risk", 0)),
        "cascade_risk": float(gi.get("cascade_risk", 0)),
        "latency_spike": gi.get("latency_spike"),
        "bho_delta": float(gi.get("bho_delta", 0)),
        "respect_human_latch": True,
    }


def probe_from_verdict_dict(
    case_id: str,
    gate_dict: Dict[str, Any],
    latency_ms: float,
    *,
    probe_status: str = "OK",
    error: Optional[str] = None,
) -> Dict[str, Any]:
    decision = gate_dict.get("decision") if gate_dict else None
    order_send = decision == "RELEASED" if decision else None
    probe: Dict[str, Any] = {
        "schema": "chaos_gate_probe_v1",
        "ts": now_iso(),
        "case_id": case_id,
        "probe_status": probe_status,
        "processing_latency_ms": round(latency_ms, 4),
        "gate_verdict": gate_dict,
        "derived": {"order_send": order_send},
    }
    if error:
        probe["error"] = error
    return probe


def capture_probe_offline(case_id: str, fixture: Dict[str, Any]) -> Tuple[Dict[str, Any], float]:
    import time

    started = time.perf_counter()
    try:
        verdict = evaluate_gate(gate_input_from_fixture(fixture))
        latency_ms = (time.perf_counter() - started) * 1000.0
        return probe_from_verdict_dict(case_id, verdict.to_dict(), latency_ms), latency_ms
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000.0
        return (
            probe_from_verdict_dict(case_id, None, latency_ms, probe_status="PROBE_ERROR", error=str(exc)),
            latency_ms,
        )


def assert_fail_closed(
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


def run_matrix(
    *,
    gate_label: str,
    mode: str,
    capture_fn,
    report_path: Path,
    pass_verdict: str,
    fail_verdict: str,
) -> Dict[str, Any]:
    matrix = load_matrix()
    policy = matrix.get("run_policy") or {}
    max_latency = float(policy.get("max_probe_latency_ms", 10))
    cases_out: List[Dict[str, Any]] = []
    failed: List[str] = []

    for case in matrix.get("cases") or []:
        if not case.get("enabled", True):
            continue
        case_id = str(case["id"])
        fixture = load_fixture(str(case["fixture_ref"]))
        probe, _ = capture_fn(case_id, fixture)
        passed, violation = assert_fail_closed(probe, case["expect"], max_latency)
        cases_out.append(
            {
                "id": case_id,
                "fault_type": case.get("fault_type"),
                "passed": passed,
                "violation": violation,
                "probe": probe,
            }
        )
        if not passed:
            failed.append(case_id)

    total = len(cases_out)
    passed_n = sum(1 for c in cases_out if c["passed"])
    if policy.get("fail_if_any_case_fails", True) and failed:
        verdict = fail_verdict
    elif passed_n == total and total > 0:
        verdict = pass_verdict
    else:
        verdict = fail_verdict

    report = {
        "schema": f"chaos_engineering_{gate_label.lower()}_report_v1",
        "ts": now_iso(),
        "experiment_id": matrix.get("experiment_id"),
        "p6_layer": matrix.get("p6_layer"),
        "gate": gate_label,
        "mode": mode,
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
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
