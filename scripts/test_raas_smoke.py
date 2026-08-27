#!/usr/bin/env python3
"""RaaS E2E smoke — upload → stress → certificate (BLOCKED/RELEASED paths).

Usage:
  PYTHONPATH=. python3 scripts/test_raas_smoke.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.raas_portal import exporter, runner, store  # noqa: E402

TENANT = "smoke-demo"


def _run_profile(name: str, n: int) -> dict:
    c = store.save_contract(
        tenant_id=TENANT,
        name=f"SmokeContract-{name}",
        bytecode_hex="6080604052" + "00" * 32,
    )
    run = store.create_run(
        tenant_id=TENANT,
        contract_id=c["contract_id"],
        n_scenarios=n,
        profile=name,
    )
    out = runner.run_stress_job(tenant_id=TENANT, run_id=run["run_id"])
    cert = exporter.export_certificate(
        tenant_id=TENANT, run_id=run["run_id"], fmt="json"
    )
    return {
        "profile": name,
        "gate_verdict": out.get("gate_verdict"),
        "audit_verdict": out.get("audit_verdict"),
        "risk_block_rate": out.get("metrics", {}).get("risk_block_rate"),
        "certificate_id": cert["certificate"]["certificate_id"],
    }


def _gate_paths() -> dict:
    """Explicit BLOCKED (risk) vs RELEASED (human open, low risk)."""
    high, _ = runner.evaluate_signal(
        signal_id="smoke-high",
        risks={
            "exec_risk": 0.95,
            "cascade_risk": 0.90,
            "stress_score": 0.5,
            "latency_spike": None,
            "bho_delta": 0.0,
            "oracle_ok": True,
            "scenario_ok": True,
        },
        human_gate_open=False,
    )
    low_open, _ = runner.evaluate_signal(
        signal_id="smoke-low-open",
        risks={
            "exec_risk": 0.05,
            "cascade_risk": 0.05,
            "stress_score": 0.05,
            "latency_spike": None,
            "bho_delta": 0.0,
            "oracle_ok": True,
            "scenario_ok": True,
        },
        human_gate_open=True,
    )
    return {
        "high_risk": high["decision"],
        "high_reasons": high.get("reasons"),
        "low_human_open": low_open["decision"],
        "low_reasons": low_open.get("reasons"),
    }


def main() -> int:
    print("RaaS smoke (local, no HTTP)")
    print("=" * 60)
    results = []
    for profile in ("default", "aggressive"):
        row = _run_profile(profile, n=50)
        results.append(row)
        print(
            f"{profile:<12} gate={row['gate_verdict']:<8} "
            f"audit={row['audit_verdict']:<22} risk_block={row['risk_block_rate']}"
        )

    gate = _gate_paths()
    print(
        f"gate-sim     high={gate['high_risk']} ({gate['high_reasons']}) "
        f"low+open={gate['low_human_open']}"
    )

    has_blocked = gate["high_risk"] == "BLOCKED"
    has_released = gate["low_human_open"] == "RELEASED"
    ok = has_blocked and has_released
    verdict = "RAAS_SMOKE_PASS" if ok else "RAAS_SMOKE_FAIL"
    print("=" * 60)
    print(f"VERDICT: {verdict}")
    print(f"  risk_blocked_path={has_blocked}  human_open_released={has_released}")
    out = _ROOT / "data" / "raas" / "smoke_last.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"verdict": verdict, "results": results, "gate": gate}, indent=2)
    )
    print(f"artifact: {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
