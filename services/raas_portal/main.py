"""RaaS Portal — FastAPI prototype (Option 1, defensive).

Usage (repo root):
  PYTHONPATH=. uvicorn services.raas_portal.main:app --host 0.0.0.0 --port 8020
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.raas_portal import exporter, runner, store  # noqa: E402

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"

app = FastAPI(
    title="Agent X RaaS Portal (Prototype)",
    version="0.1.0",
    description="Defensive contract stress → fail-closed gate → audit certificate. "
    "No live execution.",
)


class ContractUpload(BaseModel):
    tenant_id: str = Field(default="demo")
    name: str
    bytecode_hex: str = ""
    abi: Optional[Dict[str, Any]] = None


class RunCreate(BaseModel):
    tenant_id: str = Field(default="demo")
    contract_id: str
    n_scenarios: int = Field(default=100, ge=1, le=10000)
    profile: str = Field(default="default")


class GateEvaluateBody(BaseModel):
    signal: Dict[str, Any]
    exec_risk: float = 0.0
    cascade_risk: float = 0.0
    latency_spike: Optional[float] = None
    bho_delta: float = 0.0
    respect_human_latch: bool = True


def _scope_wrap(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {**payload, "scope": SCOPE, "live_execution": False}


@app.get("/health")
def health() -> Dict[str, Any]:
    return _scope_wrap(
        {
            "status": "ok",
            "service": "raas-portal-proto",
            "gate_base_url": os.environ.get("GATE_BASE_URL", ""),
        }
    )


@app.post("/api/v1/raas/contracts/upload")
def upload_contract(body: ContractUpload) -> Dict[str, Any]:
    rec = store.save_contract(
        tenant_id=body.tenant_id,
        name=body.name,
        bytecode_hex=body.bytecode_hex,
        abi=body.abi,
    )
    store.append_worm_line(
        body.tenant_id,
        f"contract-{rec['contract_id']}",
        {"phase": "contract_upload", "contract_id": rec["contract_id"]},
    )
    return _scope_wrap({"contract": rec})


@app.post("/api/v1/raas/runs")
def create_run(
    body: RunCreate,
    background_tasks: BackgroundTasks,
    execute: bool = Query(True, description="Start stress runner immediately"),
) -> Dict[str, Any]:
    try:
        rec = store.create_run(
            tenant_id=body.tenant_id,
            contract_id=body.contract_id,
            n_scenarios=body.n_scenarios,
            profile=body.profile,
        )
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    if execute:
        background_tasks.add_task(
            _run_and_certify,
            body.tenant_id,
            rec["run_id"],
        )
    return _scope_wrap({"run": rec, "execute_scheduled": execute})


def _run_and_certify(tenant_id: str, run_id: str) -> None:
    try:
        runner.run_stress_job(tenant_id=tenant_id, run_id=run_id)
        exporter.export_certificate(tenant_id=tenant_id, run_id=run_id, fmt="json")
    except Exception as exc:
        store.update_run(
            tenant_id,
            run_id,
            {"status": "FAILED", "error": str(exc)},
        )


@app.get("/api/v1/raas/runs/{run_id}")
def get_run(
    run_id: str,
    tenant_id: str = Query("demo"),
) -> Dict[str, Any]:
    rec = store.get_run(tenant_id=tenant_id, run_id=run_id)
    if not rec:
        raise HTTPException(404, "run not found")
    return _scope_wrap({"run": rec})


@app.get("/api/v1/raas/runs/{run_id}/certificate")
def get_certificate(
    run_id: str,
    tenant_id: str = Query("demo"),
    format: str = Query("json", alias="format"),
) -> Dict[str, Any]:
    rec = store.get_run(tenant_id=tenant_id, run_id=run_id)
    if not rec:
        raise HTTPException(404, "run not found")
    if rec.get("status") not in ("COMPLETED", "FAILED"):
        raise HTTPException(409, f"run status={rec.get('status')}")
    try:
        out = exporter.export_certificate(
            tenant_id=tenant_id, run_id=run_id, fmt=format
        )
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return _scope_wrap(out)


@app.post("/api/v1/raas/gate/evaluate")
async def gate_evaluate(body: GateEvaluateBody) -> Dict[str, Any]:
    """Proxy to infra-gate when GATE_BASE_URL set; else local gate_core."""
    gate_url = os.environ.get("GATE_BASE_URL", "").rstrip("/")
    payload = body.model_dump()
    if gate_url:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(f"{gate_url}/v1/evaluate", json=payload)
                r.raise_for_status()
                return _scope_wrap(r.json())
        except Exception as exc:
            raise HTTPException(502, f"gate proxy failed: {exc}") from exc
    risks = {
        "stress_score": body.signal.get("stress_score", 0.0),
        "exec_risk": body.exec_risk,
        "cascade_risk": body.cascade_risk,
        "latency_spike": body.latency_spike,
        "bho_delta": body.bho_delta,
        "oracle_ok": body.signal.get("oracle_ok", True),
        "scenario_ok": body.signal.get("scenario_ok", True),
    }
    verdict, backend = runner.evaluate_signal(
        signal_id=body.signal.get("signal_id", "manual"),
        risks=risks,
        human_gate_open=False,
    )
    return _scope_wrap({**verdict, "backend": backend})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("RAAS_PORT", "8020")))
