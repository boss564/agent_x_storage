#!/usr/bin/env python3
"""Agent X MultiChain — REST API (FastAPI).

Exposes the 9 sovereign appchains via REST endpoints:
  GET  /health                    — API health
  GET  /chains                    — All 9 chain states
  GET  /chains/{chain_id}         — Single chain state
  GET  /layers                    — 4 layer aggregates
  GET  /transactions              — Recent cross-chain events
  GET  /compliance                — BHO, GoBD, tax, identity
  GET  /friction                  — Friction analysis
  GET  /volumes                   — 9-point chain volume comparison
  POST /simulate                  — Run a simulation (async)
  GET  /simulate/{job_id}/status  — Simulation status
  GET  /audit/{project_id}        — GoBD audit trail export
  GET  /export/xrechnung          — XRechnung XML stub
  GET  /export/report             — Full JSON report

Usage:
  uvicorn services.multichain_api:app --reload --port 8600
"""

import asyncio
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure repo root on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from agents_b2g.multichain import ChainOrchestrator

# ─── App Setup ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Agent X MultiChain API",
    description="REST API for 9 Sovereign Appchains across 4 Chain Layers",
    version="0.21.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── In-Memory State ────────────────────────────────────────────────────────

_orchestrator: Optional[ChainOrchestrator] = None
_simulations: Dict[str, Dict] = {}
_last_simulation: Optional[Dict] = None


def get_orchestrator() -> ChainOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ChainOrchestrator(
            user_id="api",
            cycles=100,
            sensor_batch=1000,
        )
    return _orchestrator


# ─── Models ─────────────────────────────────────────────────────────────────

class SimulateRequest(BaseModel):
    cycles: int = Field(default=100, ge=1, le=10000, description="Number of cycles")
    user_id: str = Field(default="api", max_length=64)
    sensor_batch: int = Field(default=1000, ge=10, le=10000)


class SimulateResponse(BaseModel):
    job_id: str
    status: str
    message: str


class ChainStateResponse(BaseModel):
    chain_id: str
    block_height: int
    details: Dict[str, Any]


# ─── Endpoints ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """API health check."""
    orch = get_orchestrator()
    return {
        "status": "healthy",
        "sim_id": orch.sim_id,
        "cycles_configured": orch.cycles,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/chains")
async def list_chains():
    """Get state of all 9 sovereign appchains."""
    orch = get_orchestrator()
    report = orch.generate_report()
    states = report["artifacts"][0]["chain_states"]
    layers = report["artifacts"][0]["layers"]

    return {
        "chains": states,
        "layers": layers,
        "sim_id": orch.sim_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/chains/{chain_key}")
async def get_chain(chain_key: str):
    """Get a single chain's state (e.g., A1_sensor, A4_vob, A9_identity)."""
    orch = get_orchestrator()
    report = orch.generate_report()
    states = report["artifacts"][0]["chain_states"]

    if chain_key not in states:
        valid = list(states.keys())
        raise HTTPException(404, f"Unknown chain '{chain_key}'. Valid: {valid}")

    return {
        "chain_key": chain_key,
        "state": states[chain_key],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/layers")
async def list_layers():
    """Get aggregated 4-layer state."""
    orch = get_orchestrator()
    report = orch.generate_report()
    return {
        "layers": report["artifacts"][0]["layers"],
        "sim_id": orch.sim_id,
    }


@app.get("/compliance")
async def get_compliance():
    """Get BHO, GoBD, tax, and identity compliance status."""
    orch = get_orchestrator()
    report = orch.generate_report()
    return report["artifacts"][0]["compliance"]


@app.get("/friction")
async def get_friction():
    """Get friction analysis with honest accounting."""
    orch = get_orchestrator()
    report = orch.generate_report()
    return report["artifacts"][0]["friction_analysis"]


@app.get("/volumes")
async def get_volumes():
    """Get 9-point chain volume comparison."""
    orch = get_orchestrator()
    report = orch.generate_report()
    return {
        "chain_volumes": report["artifacts"][0]["chain_volumes"],
        "sim_id": orch.sim_id,
    }


@app.get("/transactions")
async def list_transactions(
    limit: int = Query(default=20, ge=1, le=200),
    chain: Optional[str] = None,
):
    """Get recent transactions from cross-chain queue."""
    orch = get_orchestrator()
    envelopes = orch.message_queue[-limit:]

    txs = []
    for env in envelopes:
        for tx in env.payload[:5]:  # max 5 per envelope
            txs.append({
                "source": env.source,
                "target": env.target,
                "merkle_root": env.merkle_root[:16],
                "latency_ms": env.latency_ms,
                "timestamp": env.timestamp,
                "data": {
                    k: v for k, v in tx.items()
                    if k in ("sensor_id", "sensor_type", "amount")
                },
            })

    return {
        "transactions": txs,
        "total_in_queue": len(orch.message_queue),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/simulate", response_model=SimulateResponse)
async def start_simulation(req: SimulateRequest):
    """Start an async simulation."""
    job_id = hashlib.sha256(
        f"{req.user_id}{datetime.now(timezone.utc).isoformat()}".encode()
    ).hexdigest()[:12]

    _simulations[job_id] = {
        "job_id": job_id,
        "status": "running",
        "cycles": req.cycles,
        "user_id": req.user_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "result": None,
    }

    # Run in background
    asyncio.create_task(_run_simulation(job_id, req))

    return SimulateResponse(
        job_id=job_id,
        status="running",
        message=f"Simulation started with {req.cycles} cycles. Check /simulate/{job_id}/status",
    )


@app.get("/simulate/{job_id}/status")
async def simulation_status(job_id: str):
    """Check simulation status."""
    sim = _simulations.get(job_id)
    if not sim:
        raise HTTPException(404, f"No simulation found with job_id '{job_id}'")

    response = {
        "job_id": job_id,
        "status": sim["status"],
        "cycles": sim["cycles"],
        "started_at": sim["started_at"],
    }

    if sim["status"] == "completed":
        response["elapsed_ms"] = sim.get("elapsed_ms", 0)
        response["summary"] = sim.get("summary", {})

    return response


@app.get("/audit/{project_id}")
async def get_audit_trail(project_id: str):
    """Get GoBD audit trail for a project."""
    orch = get_orchestrator()
    entries = [
        e for e in orch.legal.audit_trail
        if e.get("project_id") == project_id
    ]

    if not entries:
        raise HTTPException(404, f"No audit entries for project '{project_id}'")

    return {
        "project_id": project_id,
        "entries": entries,
        "total": len(entries),
        "gobd_compliant": True,
        "merkle_root": orch.legal.merkle_root,
    }


@app.get("/export/xrechnung")
async def export_xrechnung():
    """Export XRechnung XML stub."""
    orch = get_orchestrator()
    entries = orch.legal.audit_trail[:10]

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<CrossIndustryInvoice xmlns="urn:cen.eu:en16931:2017">',
    ]
    for e in entries:
        xml_lines.append(f'  <Invoice>')
        xml_lines.append(f'    <ID>{e["audit_id"]}</ID>')
        xml_lines.append(f'    <GrossAmount>{e["gross"]}</GrossAmount>')
        xml_lines.append(f'    <TaxAmount>{e["tax"]}</TaxAmount>')
        xml_lines.append(f'    <NetAmount>{e["net"]}</NetAmount>')
        xml_lines.append(f'  </Invoice>')

    xml_lines.append('</CrossIndustryInvoice>')
    return PlainTextResponse("\n".join(xml_lines), media_type="application/xml")


@app.get("/export/report")
async def export_report():
    """Export full simulation report as JSON."""
    orch = get_orchestrator()
    report = orch.generate_report()
    return report


# ─── Background Tasks ───────────────────────────────────────────────────────

async def _run_simulation(job_id: str, req: SimulateRequest):
    """Background simulation runner."""
    global _last_simulation
    try:
        orch = ChainOrchestrator(
            user_id=req.user_id,
            cycles=req.cycles,
            sensor_batch=req.sensor_batch,
        )
        t0 = time.time()
        result = await orch.run_simulation(cycles=req.cycles)
        elapsed = round((time.time() - t0) * 1000, 2)

        if result["status"] == "completed":
            r = result["artifacts"][0]
            _simulations[job_id].update({
                "status": "completed",
                "elapsed_ms": elapsed,
                "summary": {
                    "layers": r["layers"],
                    "friction": r["friction_analysis"],
                    "compliance": r["compliance"],
                    "chain_volumes": r["chain_volumes"],
                },
            })
            _last_simulation = result
        else:
            _simulations[job_id].update({
                "status": "failed",
                "error": result.get("error"),
            })
    except Exception as e:
        _simulations[job_id].update({
            "status": "failed",
            "error": str(e),
        })


# ─── Main ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("MULTICHAIN_API_PORT", "8600"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
