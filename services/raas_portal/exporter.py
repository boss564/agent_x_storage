"""P9-style audit certificate export (JSON + Markdown proto)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.raas_portal import store

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"


def _worm_tail_hash(tenant_id: str, run_id: str) -> str:
    worm = store.run_dir(tenant_id, run_id) / "audit.worm.jsonl"
    if not worm.exists():
        return hashlib.sha256(b"EMPTY_WORM").hexdigest()
    last = worm.read_text(encoding="utf-8").strip().splitlines()[-1]
    return json.loads(last).get("hash", "")


def build_certificate(*, tenant_id: str, run_id: str) -> Dict[str, Any]:
    run = store.get_run(tenant_id=tenant_id, run_id=run_id)
    if not run:
        raise ValueError(f"run not found: {run_id}")
    contract = store.get_contract(
        tenant_id=tenant_id, contract_id=run["contract_id"]
    )
    rd = store.run_dir(tenant_id, run_id)
    stress_path = rd / "stress_summary.json"
    stress = {}
    if stress_path.exists():
        stress = json.loads(stress_path.read_text(encoding="utf-8"))

    cert = {
        "certificate_type": "RAAS_RISK_ASSESSMENT_PROTO",
        "schema_version": "0.1.0",
        "tenant_id": tenant_id,
        "run_id": run_id,
        "contract_id": run["contract_id"],
        "contract_name": contract.get("name") if contract else None,
        "contract_sha256": run.get("contract_sha256"),
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "scope": SCOPE,
        "live_execution": False,
        "verdict": run.get("audit_verdict") or "PENDING",
        "gate_verdict": run.get("gate_verdict"),
        "status": run.get("status"),
        "metrics": run.get("metrics") or stress.get("metrics", {}),
        "gate_trace": stress.get("cluster_verdicts", []),
        "worm_tail_hash": _worm_tail_hash(tenant_id, run_id),
        "note": (
            "Simulation-only certificate. No on-chain execution. "
            "Human gate default CLOSED."
        ),
    }
    cert["certificate_id"] = hashlib.sha256(
        json.dumps(cert, sort_keys=True, default=str).encode()
    ).hexdigest()[:32]
    return cert


def certificate_to_markdown(cert: Dict[str, Any]) -> str:
    m = cert.get("metrics") or {}
    lines = [
        "# Agent X RaaS — Risikogutachten (Prototype)",
        "",
        f"**Certificate ID:** `{cert.get('certificate_id')}`",
        f"**Verdict:** {cert.get('verdict')} · Gate: {cert.get('gate_verdict')}",
        f"**Scope:** {cert.get('scope')} · live_execution={cert.get('live_execution')}",
        "",
        "## Run",
        f"- Tenant: {cert.get('tenant_id')}",
        f"- Run: {cert.get('run_id')}",
        f"- Contract: {cert.get('contract_name')} (`{cert.get('contract_sha256', '')[:16]}…`)",
        "",
        "## Stress metrics",
        f"- Scenarios: {m.get('n_scenarios')}",
        f"- Risk blocked: {m.get('risk_blocked')} · Human latch only: {m.get('human_latch_only')}",
        f"- Risk block rate: {m.get('risk_block_rate')}",
        f"- Max exec risk: {m.get('max_exec_risk')} · Max cascade: {m.get('max_cascade_risk')}",
        "",
        "## WORM",
        f"- Tail hash: `{cert.get('worm_tail_hash')}`",
        "",
        cert.get("note", ""),
    ]
    return "\n".join(lines)


def export_certificate(
    *,
    tenant_id: str,
    run_id: str,
    fmt: str = "json",
) -> Dict[str, Any]:
    cert = build_certificate(tenant_id=tenant_id, run_id=run_id)
    rd = store.run_dir(tenant_id, run_id)
    rd.mkdir(parents=True, exist_ok=True)
    json_path = rd / "certificate.json"
    json_path.write_text(json.dumps(cert, indent=2), encoding="utf-8")
    md_path = rd / "certificate.md"
    md_path.write_text(certificate_to_markdown(cert), encoding="utf-8")
    store.append_worm_line(
        tenant_id,
        run_id,
        {"phase": "certificate_export", "certificate_id": cert["certificate_id"]},
    )
    if fmt == "markdown":
        return {"format": "markdown", "content": certificate_to_markdown(cert), "certificate": cert}
    return {"format": "json", "certificate": cert, "path": str(json_path)}
