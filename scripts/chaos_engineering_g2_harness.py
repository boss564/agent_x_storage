#!/usr/bin/env python3
"""G2 — Chaos Engineering HTTP harness (P6-Trading / fail-closed-gate service).

Fires fixtures against POST /v1/evaluate (TestClient by default; live URL via CHAOS_GATE_EVALUATE_URL).
Pre-Reg: docs/CHAOS_ENGINEERING_PREREG.md §1 probe contract.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Tuple

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.chaos_engineering.harness_common import (  # noqa: E402
    MATRIX_PATH,
    REPORT_DIR,
    fixture_to_evaluate_body,
    load_matrix,
    probe_from_verdict_dict,
    run_matrix,
)

REPORT_PATH = REPORT_DIR / "g2_latest.json"


def _capture_via_url(evaluate_url: str) -> Callable[[str, Dict[str, Any]], Tuple[Dict[str, Any], float]]:
    def _capture(case_id: str, fixture: Dict[str, Any]) -> Tuple[Dict[str, Any], float]:
        body = json.dumps(fixture_to_evaluate_body(fixture)).encode("utf-8")
        req = urllib.request.Request(
            evaluate_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = resp.read().decode("utf-8")
            latency_ms = (time.perf_counter() - started) * 1000.0
            gate_dict = json.loads(raw)
            if "decision" not in gate_dict:
                return (
                    probe_from_verdict_dict(
                        case_id,
                        None,
                        latency_ms,
                        probe_status="DESERIALIZE_ERROR",
                        error="missing decision",
                    ),
                    latency_ms,
                )
            return probe_from_verdict_dict(case_id, gate_dict, latency_ms), latency_ms
        except urllib.error.URLError as exc:
            latency_ms = (time.perf_counter() - started) * 1000.0
            return (
                probe_from_verdict_dict(
                    case_id,
                    None,
                    latency_ms,
                    probe_status="GATE_UNAVAILABLE",
                    error=str(exc),
                ),
                latency_ms,
            )
        except (json.JSONDecodeError, KeyError) as exc:
            latency_ms = (time.perf_counter() - started) * 1000.0
            return (
                probe_from_verdict_dict(
                    case_id,
                    None,
                    latency_ms,
                    probe_status="DESERIALIZE_ERROR",
                    error=str(exc),
                ),
                latency_ms,
            )

    return _capture


def _capture_via_testclient() -> Callable[[str, Dict[str, Any]], Tuple[Dict[str, Any], float]]:
    from fastapi.testclient import TestClient

    gate_dir = _ROOT / "services" / "fail_closed_gate"
    if str(gate_dir) not in sys.path:
        sys.path.insert(0, str(gate_dir))
    from main import app  # noqa: E402

    client = TestClient(app)
    client.post(
        "/v1/evaluate",
        json={
            "signal": {
                "signal_id": "warmup",
                "source": "P4",
                "notional_eur": 0,
                "stress_score": 0,
                "oracle_ok": True,
                "scenario_ok": True,
            },
            "respect_human_latch": True,
        },
    )

    def _capture(case_id: str, fixture: Dict[str, Any]) -> Tuple[Dict[str, Any], float]:
        started = time.perf_counter()
        try:
            resp = client.post("/v1/evaluate", json=fixture_to_evaluate_body(fixture))
            latency_ms = (time.perf_counter() - started) * 1000.0
            if resp.status_code != 200:
                return (
                    probe_from_verdict_dict(
                        case_id,
                        None,
                        latency_ms,
                        probe_status="GATE_UNAVAILABLE",
                        error=f"HTTP {resp.status_code}",
                    ),
                    latency_ms,
                )
            gate_dict = resp.json()
            return probe_from_verdict_dict(case_id, gate_dict, latency_ms), latency_ms
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000.0
            return (
                probe_from_verdict_dict(
                    case_id,
                    None,
                    latency_ms,
                    probe_status="PROBE_ERROR",
                    error=str(exc),
                ),
                latency_ms,
            )

    return _capture


def _resolve_capture() -> Tuple[Callable[..., Tuple[Dict[str, Any], float]], str]:
    url = os.environ.get("CHAOS_GATE_EVALUATE_URL", "").strip()
    if url:
        return _capture_via_url(url), f"http:{url}"
    matrix = load_matrix()
    shadow_url = (matrix.get("shadow_pipeline") or {}).get("gate_evaluate_url", "")
    if os.environ.get("CHAOS_GATE_MODE") == "shadow" and shadow_url:
        return _capture_via_url(shadow_url), f"http:{shadow_url}"
    return _capture_via_testclient(), "http_testclient"


def main() -> int:
    if not MATRIX_PATH.is_file():
        print(f"CHAOS_G2_FAIL missing config: {MATRIX_PATH}", file=sys.stderr)
        return 1
    capture_fn, mode = _resolve_capture()
    report = run_matrix(
        gate_label="G2",
        mode=mode,
        capture_fn=capture_fn,
        report_path=REPORT_PATH,
        pass_verdict="CHAOS_G2_PASS",
        fail_verdict="CHAOS_G2_FAIL",
    )
    print(
        json.dumps(
            {
                "verdict": report["verdict"],
                "passed": report["passed"],
                "total": report["total_tests"],
                "mode": mode,
                "report": str(REPORT_PATH),
            }
        )
    )
    return 0 if report["verdict"] == "CHAOS_G2_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
