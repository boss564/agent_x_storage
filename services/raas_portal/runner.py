"""RaaS stress runner — simulated scenarios + fail-closed gate (prototype)."""
from __future__ import annotations

import json
import os
import sys
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Repo root on path for gate_core
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_GATE_PATH = _ROOT / "services" / "fail_closed_gate"
if str(_GATE_PATH) not in sys.path:
    sys.path.insert(0, str(_GATE_PATH))

from gate_core import GateInput, TradeSignal, evaluate_gate  # noqa: E402

from services.raas_portal import store  # noqa: E402

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"
PROFILES = {
    "default": {"exec_scale": 0.35, "cascade_scale": 0.40, "stress_scale": 0.30},
    "aggressive": {"exec_scale": 0.65, "cascade_scale": 0.70, "stress_scale": 0.55},
    "oracle_stress": {"exec_scale": 0.25, "cascade_scale": 0.35, "stress_scale": 0.80},
}


def _crc_u01(material: str) -> float:
    return (zlib.crc32(material.encode()) & 0xFFFFFFFF) / 0xFFFFFFFF


def _scenario_risks(
    *,
    contract_sha: str,
    seed: int,
    profile: str,
) -> Dict[str, float]:
    p = PROFILES.get(profile, PROFILES["default"])
    u = _crc_u01(f"{contract_sha}|{seed}|stress")
    exec_risk = min(1.0, p["exec_scale"] * (0.5 + u))
    cascade = min(1.0, p["cascade_scale"] * (0.4 + _crc_u01(f"{seed}|cascade")))
    stress = min(1.0, p["stress_scale"] * (0.3 + _crc_u01(f"{seed}|oracle")))
    latency = None
    if _crc_u01(f"{seed}|m7") > 0.92:
        latency = 8.0 + 40.0 * _crc_u01(f"{seed}|lat")
    bho = 0.0 if _crc_u01(f"{seed}|bho") > 0.98 else 0.0
    return {
        "exec_risk": round(exec_risk, 6),
        "cascade_risk": round(cascade, 6),
        "stress_score": round(stress, 6),
        "latency_spike": latency,
        "bho_delta": bho,
        "oracle_ok": _crc_u01(f"{seed}|oracle_ok") > 0.05,
        "scenario_ok": _crc_u01(f"{seed}|scenario_ok") > 0.03,
    }


def _evaluate_local(
    *,
    signal_id: str,
    risks: Dict[str, Any],
    human_gate_open: bool = False,
) -> Dict[str, Any]:
    inp = GateInput(
        signal=TradeSignal(
            signal_id=signal_id,
            source="P4",
            notional_eur=1000.0,
            stress_score=float(risks["stress_score"]),
            oracle_ok=bool(risks["oracle_ok"]),
            scenario_ok=bool(risks["scenario_ok"]),
        ),
        exec_risk=float(risks["exec_risk"]),
        cascade_risk=float(risks["cascade_risk"]),
        latency_spike=risks.get("latency_spike"),
        bho_delta=float(risks.get("bho_delta") or 0.0),
        human_gate_open=human_gate_open,
    )
    return evaluate_gate(inp).to_dict()


async def evaluate_via_http(body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    gate_url = os.environ.get("GATE_BASE_URL", "").rstrip("/")
    if not gate_url:
        return None
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{gate_url}/v1/evaluate", json=body)
            r.raise_for_status()
            return r.json()
    except Exception:
        return None


def _risk_only_blocked(verdict: Dict[str, Any]) -> bool:
    reasons = set(verdict.get("reasons") or [])
    return bool(reasons - {"HUMAN_GATE_CLOSED"})


def evaluate_signal(
    *,
    signal_id: str,
    risks: Dict[str, Any],
    human_gate_open: bool = False,
) -> Tuple[Dict[str, Any], str]:
    body = {
        "signal": {
            "signal_id": signal_id,
            "source": "P4",
            "notional_eur": 1000.0,
            "stress_score": risks["stress_score"],
            "oracle_ok": risks["oracle_ok"],
            "scenario_ok": risks["scenario_ok"],
        },
        "exec_risk": risks["exec_risk"],
        "cascade_risk": risks["cascade_risk"],
        "bho_delta": risks["bho_delta"],
        "respect_human_latch": True,
    }
    if risks.get("latency_spike") is not None:
        body["latency_spike"] = risks["latency_spike"]
    verdict = _evaluate_local(
        signal_id=signal_id, risks=risks, human_gate_open=human_gate_open
    )
    return verdict, "local_gate_core"


def run_stress_job(
    *,
    tenant_id: str,
    run_id: str,
    n_scenarios: Optional[int] = None,
) -> Dict[str, Any]:
    rec = store.get_run(tenant_id=tenant_id, run_id=run_id)
    if not rec:
        raise ValueError(f"run not found: {run_id}")
    n = int(n_scenarios or rec["n_scenarios"])
    profile = rec.get("profile") or "default"
    contract_sha = rec["contract_sha256"]

    store.update_run(tenant_id, run_id, {"status": "RUNNING"})
    store.append_worm_line(
        tenant_id,
        run_id,
        {"phase": "stress_start", "n_scenarios": n, "profile": profile},
    )

    risk_blocked = 0
    human_latch_only = 0
    cluster_verdicts: List[Dict[str, Any]] = []
    max_exec = 0.0
    max_cascade = 0.0

    for i in range(n):
        seed = 20271100 + (i % 10000)
        risks = _scenario_risks(contract_sha=contract_sha, seed=seed, profile=profile)
        max_exec = max(max_exec, risks["exec_risk"])
        max_cascade = max(max_cascade, risks["cascade_risk"])
        verdict, backend = evaluate_signal(
            signal_id=f"S-{run_id[:8]}-{i:05d}",
            risks=risks,
            human_gate_open=False,
        )
        if _risk_only_blocked(verdict):
            risk_blocked += 1
        elif verdict["decision"] == "BLOCKED":
            human_latch_only += 1
        if i % max(1, n // 20) == 0:
            cluster_verdicts.append(
                {
                    "index": i,
                    "decision": verdict["decision"],
                    "reasons": verdict.get("reasons", []),
                    "risk_blocked": _risk_only_blocked(verdict),
                    "backend": backend,
                }
            )

    risk_block_rate = risk_blocked / max(n, 1)
    if risk_block_rate >= 0.5:
        gate_verdict = "BLOCKED"
        audit_verdict = "ENTLASTUNG_VERWEIGERT"
    elif risk_block_rate >= 0.1:
        gate_verdict = "VORBEHALT"
        audit_verdict = "ENTLASTET_MIT_HINWEIS"
    else:
        gate_verdict = "RELEASED"
        audit_verdict = "ENTLASTET"

    metrics = {
        "n_scenarios": n,
        "risk_blocked": risk_blocked,
        "human_latch_only": human_latch_only,
        "risk_block_rate": round(risk_block_rate, 6),
        "max_exec_risk": round(max_exec, 6),
        "max_cascade_risk": round(max_cascade, 6),
        "profile": profile,
        "gate_backend": "local_gate_core",
        "human_gate_default": "CLOSED",
    }

    rd = store.run_dir(tenant_id, run_id)
    (rd / "stress_summary.json").write_text(
        json.dumps(
            {
                "metrics": metrics,
                "cluster_verdicts": cluster_verdicts,
                "scope": SCOPE,
                "live_execution": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    store.append_worm_line(
        tenant_id,
        run_id,
        {"phase": "stress_done", "gate_verdict": gate_verdict, "metrics": metrics},
    )

    updated = store.update_run(
        tenant_id,
        run_id,
        {
            "status": "COMPLETED",
            "gate_verdict": gate_verdict,
            "audit_verdict": audit_verdict,
            "metrics": metrics,
        },
    )
    return updated
