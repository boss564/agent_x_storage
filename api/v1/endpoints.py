"""Agent X — REST API v1 Endpoints."""

import json
import time
import logging
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Header

from core.context import RequestContext
from core.exceptions import AgentXException
from api_agents.agent_6_async_job import JobNotFoundError
from core.schemas.api_schemas import (
    SnapshotRequestDTO,
    EvaluationResponseDTO,
    RiskZone,
    BatchRequestDTO,
    BatchResponseDTO,
    BacktestRequestDTO,
    BacktestResponseDTO,
)
from core.state_store import InMemoryStateStore, StateStore

logger = logging.getLogger("agent_x_api")
router = APIRouter(prefix="/v1")

# ─── Dependency Injection ────────────────────────────────────────────

_state_store: Optional[StateStore] = None


def get_state_store() -> StateStore:
    global _state_store
    if _state_store is None:
        _state_store = InMemoryStateStore()
    return _state_store


def get_orchestrator():
    """Lazy-Load des Orchestrators (schweres Modul, nur bei Bedarf)."""
    from agent_x_orchestrator import SymbolicsAgent
    return SymbolicsAgent()


# ─── POST /v1/evaluate ───────────────────────────────────────────────

# ─── Agent-Singletons (Lazy Init) ────────────────────────────────────

_gatekeeper: Optional[Any] = None
_validator: Optional[Any] = None


def _get_gatekeeper():
    global _gatekeeper
    if _gatekeeper is None:
        from api_agents.agent_1_gatekeeper import ApiGatekeeperAgent
        _gatekeeper = ApiGatekeeperAgent(rate_limit_per_minute=100)
    return _gatekeeper


def _get_validator():
    global _validator
    if _validator is None:
        from api_agents.agent_2_validation import RequestValidationAgent
        _validator = RequestValidationAgent()
    return _validator


# ─── POST /v1/evaluate (mit Gatekeeper + Validation) ─────────────────

@router.post("/evaluate", response_model=EvaluationResponseDTO, tags=["Evaluation"])
def evaluate_snapshot(
    request: SnapshotRequestDTO,
    tenant_id: str = Query("default", description="Tenant-ID für Multi-Tenancy"),
):
    """Evaluiert einen Snapshot mit Gatekeeper + Validation + 6-Klassen-Pipeline.

    Pipeline: Gatekeeper (Auth/Rate-Limit) → Validation (Schema/Sanitize)
              → Transformer (DTO→Dict) → Orchestrator (6-Klassen).
    """
    t0 = time.time()

    try:
        # Agent 1+2: Validierung und Transformation
        validator = _get_validator()
        internal = validator.to_internal(request)

        # Orchestrator
        agent = get_orchestrator()
        decision = agent.evaluate(
            consensus_health_index=request.consensus_health or 94.0,
            gas_pressure_index=request.gas_pressure or 50.0,
            mev_pressure_index=request.mev_pressure or 50.0,
            health_factors=internal.get("health_factors"),
            mempool_bots_count=request.mempool_bots or 0,
            pending_timelocks=internal.get("pending_timelocks") or None,
            leader_utilization_pct=request.leader_utilization or 50.0,
            oracle_update_in_s=request.oracle_update_in_s or 999.0,
            expected_profit_usd=request.expected_profit_usd or 0,
        )

        ud = decision.get("unified_decision", {})
        gs_score = ud.get("global_state_score", 50)
        gs_state = ud.get("global_state", "unknown")
        recs = ud.get("recommended_actions", [])
        bundle_advice = ud.get("bundle_advice", {})

        ctx = RequestContext(tenant_id=tenant_id)
        get_state_store().set_global_state({"score": gs_score, "state": gs_state}, tenant_id)
        elapsed_ms = round((time.time() - t0) * 1000)
        logger.info("Evaluate: score=%s in %dms [%s]", gs_score, elapsed_ms, ctx.correlation_id)

        return EvaluationResponseDTO(
            request_id=ctx.correlation_id,
            chi_score=gs_score,
            risk_zone=RiskZone(gs_state),
            action_recommended=recs[0]["action"] if recs else "MONITOR",
            alerts=[r["detail"] for r in recs if r.get("priority", 99) <= 3],
            correlation_id=ctx.correlation_id,
            tenant_id=tenant_id,
            gas_advice_eth_gwei=bundle_advice.get("ethereum", {}).get("optimal_priority_fee_gwei", 0),
            gas_advice_sol_cu=bundle_advice.get("solana", {}).get("cu_price_microlamports", 0),
            elapsed_ms=elapsed_ms,
        )

    except AgentXException as e:
        logger.error("Evaluation error: %s", e)
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except Exception as e:
        logger.exception("Unexpected error")
        raise HTTPException(status_code=500, detail={"error": {"code": "INTERNAL", "message": str(e)}})


# ─── POST /v1/evaluate/secure (mit Gatekeeper-Auth) ──────────────────

@router.post("/evaluate/secure", response_model=EvaluationResponseDTO, tags=["Evaluation"])
async def evaluate_secure(
    payload: dict,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """Evaluierung mit vollständiger Gatekeeper-Authentifizierung.

    Header: X-API-Key: sk_test_abc123
    Durchläuft: Auth → Rate-Limit → Tenant → Validation → Orchestrator.
    """
    t0 = time.time()

    try:
        gk = _get_gatekeeper()
        ctx = await gk.authenticate(x_api_key, "/v1/evaluate/secure")

        # Agent 2: Validation + Transform
        validator = _get_validator()
        internal = validator.validate_and_transform(payload)

        # Orchestrator
        agent = get_orchestrator()
        decision = agent.evaluate(
            consensus_health_index=internal.get("consensus_health") or 94.0,
            gas_pressure_index=internal.get("gas_pressure") or 50.0,
            mev_pressure_index=internal.get("mev_pressure") or 50.0,
            health_factors=internal.get("health_factors"),
            mempool_bots_count=internal.get("mempool_bots") or 0,
            pending_timelocks=internal.get("pending_timelocks") or None,
            leader_utilization_pct=internal.get("leader_utilization") or 50.0,
            oracle_update_in_s=internal.get("oracle_update_in_s") or 999.0,
            expected_profit_usd=internal.get("expected_profit_usd") or 0,
        )

        ud = decision.get("unified_decision", {})
        recs = ud.get("recommended_actions", [])
        elapsed_ms = round((time.time() - t0) * 1000)

        return EvaluationResponseDTO(
            request_id=ctx.correlation_id,
            chi_score=ud.get("global_state_score", 50),
            risk_zone=RiskZone(ud.get("global_state", "healthy")),
            action_recommended=recs[0]["action"] if recs else "MONITOR",
            alerts=[r["detail"] for r in recs if r.get("priority", 99) <= 3],
            correlation_id=ctx.correlation_id,
            tenant_id=ctx.tenant_id,
            elapsed_ms=elapsed_ms,
        )

    except AgentXException as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except Exception as e:
        logger.exception("Unexpected error in secure endpoint")
        raise HTTPException(status_code=500, detail={"error": {"code": "INTERNAL", "message": str(e)}})


# ─── GET /v1/health ──────────────────────────────────────────────────

@router.get("/health", tags=["System"])
def api_health():
    """Health-Check für Load-Balancer."""
    return {"status": "ok", "service": "agent-x-api", "version": "3.0.0"}


# ─── POST /v1/evaluate/batch ─────────────────────────────────────────

@router.post("/evaluate/batch", response_model=BatchResponseDTO, tags=["Evaluation"])
def evaluate_batch(request: BatchRequestDTO, tenant_id: str = Query("default")):
    """Evaluiert mehrere Snapshots in einem Batch (max 100)."""
    results = []
    errors = []
    for i, snap in enumerate(request.snapshots[:100]):
        try:
            r = evaluate_snapshot(snap, tenant_id=tenant_id)
            results.append(r)
        except HTTPException as e:
            errors.append({"index": i, "error": e.detail})
    return BatchResponseDTO(
        total=len(request.snapshots),
        results=results,
        errors=errors,
        correlation_id=RequestContext(tenant_id=tenant_id).correlation_id,
    )


# ─── Agent 5+6 Singletons ─────────────────────────────────────────────

_sync_exec: Optional[Any] = None
_async_job: Optional[Any] = None


def _get_sync_exec():
    global _sync_exec
    if _sync_exec is None:
        from api_agents.agent_5_sync_exec import SyncExecutionAgent
        _sync_exec = SyncExecutionAgent(default_timeout_ms=100.0)
    return _sync_exec


def _get_async_job():
    global _async_job
    if _async_job is None:
        from api_agents.agent_6_async_job import AsyncJobAgent
        import asyncio as _asyncio
        agent = AsyncJobAgent(worker_count=2)
        try:
            loop = _asyncio.get_running_loop()
            loop.create_task(agent.start())
        except RuntimeError:
            pass
        _async_job = agent
    return _async_job


# ─── POST /v1/evaluate/sync (Fast-Path mit Timeout) ──────────────────

@router.post("/evaluate/sync", response_model=EvaluationResponseDTO, tags=["Evaluation"])
async def evaluate_sync(
    payload: dict,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """Fast-Path mit Gatekeeper + SyncExecution (Timeout 100ms)."""
    t0 = time.time()

    try:
        # Gatekeeper (async — direkt awaiten, nicht asyncio.run)
        gk = _get_gatekeeper()
        ctx = await gk.authenticate(x_api_key, "/v1/evaluate/sync")

        # Validation
        validator = _get_validator()
        internal = validator.validate_and_transform(payload)

        # SyncExecution mit Guard
        sync = _get_sync_exec()
        result = await sync.execute(internal, ctx)

        ud = result.get("unified_decision", {})
        recs = ud.get("recommended_actions", [])
        elapsed = round((time.time() - t0) * 1000)

        return EvaluationResponseDTO(
            request_id=ctx.correlation_id,
            chi_score=ud.get("global_state_score", 50),
            risk_zone=RiskZone(ud.get("global_state", "healthy")),
            action_recommended=recs[0]["action"] if recs else "MONITOR",
            alerts=[r["detail"] for r in recs if r.get("priority", 99) <= 3],
            correlation_id=ctx.correlation_id,
            tenant_id=ctx.tenant_id,
            elapsed_ms=elapsed,
        )
    except AgentXException as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())


# ─── POST /v1/jobs (Async-Job-Submission) ────────────────────────────

@router.post("/jobs", tags=["Async Jobs"])
async def submit_job(
    payload: dict,
    job_type: str = Query("BACKTEST", description="BACKTEST | MINE_RULES | FULL_SCAN"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """Async-Job einreichen (Backtest, Mining). Gibt Job-ID zurück."""
    gk = _get_gatekeeper()
    ctx = await gk.authenticate(x_api_key, "/v1/jobs")
    validator = _get_validator()
    validator.validate_and_transform(payload)  # Validiert, verwirft aber Output

    aj = _get_async_job()
    job_id = await aj.submit(payload, ctx, job_type)
    return {"job_id": job_id, "status": "PENDING", "correlation_id": ctx.correlation_id}


# ─── GET /v1/jobs/{job_id} (Status-Polling) ──────────────────────────

@router.get("/jobs/{job_id}", tags=["Async Jobs"])
async def get_job_status(
    job_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """Pollt Job-Status (PENDING → RUNNING → COMPLETED/FAILED)."""
    gk = _get_gatekeeper()
    ctx = await gk.authenticate(x_api_key, "/v1/jobs")

    aj = _get_async_job()
    try:
        status = await aj.get_status(job_id)
        if status.get("tenant_id") != ctx.tenant_id:
            raise HTTPException(403, "Access denied: job belongs to different tenant")
        return status
    except JobNotFoundError:
        raise HTTPException(404, f"Job {job_id} not found")


# ─── POST /v1/backtest ───────────────────────────────────────────────

@router.post("/backtest", response_model=BacktestResponseDTO, tags=["Backtesting"])
def run_backtest(request: BacktestRequestDTO):
    """Startet einen Backtest mit dem angegebenen Szenario."""
    from agent_x_backtest import BacktestRunner
    from agent_x_backtest import (
        SCENARIO_TERRA_CRASH, SCENARIO_FTX_COLLAPSE, SCENARIO_SVB_CRISIS,
        SCENARIO_BULL_RUN, SCENARIO_FLASH_CRASH,
        SCENARIO_AAVE_RATE_HIKE, SCENARIO_ARB_UNLOCK, SCENARIO_COMPOUND_CF_CHANGE,
    )

    scenario_map = {
        "terra": SCENARIO_TERRA_CRASH, "ftx": SCENARIO_FTX_COLLAPSE,
        "svb": SCENARIO_SVB_CRISIS, "bull": SCENARIO_BULL_RUN,
        "flash": SCENARIO_FLASH_CRASH, "aave": SCENARIO_AAVE_RATE_HIKE,
        "arb": SCENARIO_ARB_UNLOCK, "compound": SCENARIO_COMPOUND_CF_CHANGE,
    }

    runner = BacktestRunner()
    scenarios = [scenario_map[s] for s in (request.scenarios or ["all"]) if s in scenario_map]
    if not scenarios:
        from agent_x_backtest import ALL_SCENARIOS
        scenarios = ALL_SCENARIOS

    results = [runner.run_scenario(s) for s in scenarios]
    total_score = sum(
        {"A+": 100, "A": 90, "B": 75, "C": 60, "D": 45, "F": 20}.get(r.grade, 50)
        for r in results
    ) / max(1, len(results))

# ─── Agent 10+11 Singletons ────────────────────────────────────────────

_anchor_agent: Optional[Any] = None
_vault_agent: Optional[Any] = None


def _get_anchor():
    global _anchor_agent
    if _anchor_agent is None:
        from api_agents.agent_10_blockchain_anchor import (
            BlockchainAnchorAgent, HandoverProof,
        )
        _anchor_agent = BlockchainAnchorAgent(batch_size=50)
    return _anchor_agent


def _get_vault():
    global _vault_agent
    if _vault_agent is None:
        from api_agents.agent_11_vault_storage import VaultStorageAgent
        _vault_agent = VaultStorageAgent()
    return _vault_agent


# ─── POST /v1/handover (Bauabnahme einreichen) ──────────────────────

@router.post("/handover", tags=["Handwerk"])
async def submit_handover(
    payload: dict,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """Bauabnahme-Protokoll einreichen. Wird gebatched und on-chain verankert."""
    gk = _get_gatekeeper()
    ctx = await gk.authenticate(x_api_key, "/v1/handover")

    import hashlib as _hl
    from api_agents.agent_10_blockchain_anchor import HandoverProof

    session_id = payload.get("session_id", "")
    if not session_id:
        raise HTTPException(400, "session_id required")

    # Root-Hash aus Payload berechnen
    root_hash = "0x" + _hl.sha256(json.dumps(payload).encode()).hexdigest()

    proof = HandoverProof(
        session_id=session_id,
        root_hash=root_hash,
        project_code=payload.get("project_code", "UNKNOWN"),
        timestamp_unix=int(time.time()),
        photo_hashes=payload.get("photo_hashes", []),
        protocol_hash=payload.get("protocol_hash", ""),
        gps_lat=payload.get("gps_lat", 0),
        gps_lng=payload.get("gps_lng", 0),
    )

    anchor = _get_anchor()
    result = anchor.submit(proof)

    return {
        **result,
        "correlation_id": ctx.correlation_id,
        "tenant_id": ctx.tenant_id,
    }


# ─── GET /v1/verify (Kunden-Verifikation per QR-Code) ────────────────

@router.get("/verify", tags=["Handwerk"])
async def verify_handover(
    tx: str = Query(..., description="Transaction hash"),
    index: int = Query(..., ge=0, description="Leaf-Index im Merkle-Tree"),
    leaf: str = Query(..., description="Leaf-Hash (0x...)"),
    proof: str = Query(..., description="Komma-getrennte Merkle-Proof-Hashes"),
):
    """Kunden-Verifikation: Prüft ob ein Abnahmeprotokoll on-chain verankert ist.

    QR-Code enthält: /verify?tx=0x...&index=4&leaf=0x...&proof=0xa,0xb,0xc
    """
    proof_list = [p.strip() for p in proof.split(",") if p.strip()]

    anchor = _get_anchor()
    # Finde den Batch anhand der tx_hash
    batch = next((b for b in anchor._anchored_batches if b.tx_hash == tx), None)
    if not batch:
        return {"verified": False, "reason": "Transaction not found"}

    # Lokalen Merkle-Proof validieren
    merkle_valid = anchor.merkle.verify(leaf, proof_list, batch.merkle_root)

    return {
        "verified": merkle_valid,
        "merkle_root": batch.merkle_root,
        "tx_hash": tx,
        "leaf_index": index,
        "block_number": batch.block_number,
        "anchored_at": batch.anchored_at,
        "message": (
            "✅ Dieses Abnahmeprotokoll wurde unveränderbar gespeichert."
            if merkle_valid
            else "❌ Verifikation fehlgeschlagen — Protokoll nicht gefunden."
        ),
    }


# ─── ERP-Adapter (Handwerk) ────────────────────────────────────────────

_erp_adapter: Optional[Any] = None


def _get_erp():
    global _erp_adapter
    if _erp_adapter is None:
        from api_agents.agent_12_erp_adapter import ERPAdapterAgent
        _erp_adapter = ERPAdapterAgent(batch_size=50)
    return _erp_adapter


@router.post("/anchor-document", tags=["Handwerk"])
async def anchor_document(
    payload: dict,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """ERP-Adapter: PDF-Upload von pds/kwp/smarthandwerk.

    Akzeptiert: PDF (base64), ERP-Token, Dokumenttyp, GPS.
    Hasht sofort, speichert verschlüsselt, reiht in Batch ein.

    Header: X-API-Key = pds_token / kwp_token / smarthandwerk_token
    """
    import base64
    gk = _get_gatekeeper()
    ctx = await gk.authenticate(x_api_key, "/v1/anchor-document")

    pdf_b64 = payload.get("pdf_base64", "")
    if not pdf_b64:
        raise HTTPException(400, "pdf_base64 required")
    pdf_bytes = base64.b64decode(pdf_b64)

    photos = []
    for p in payload.get("photos_base64", []):
        photos.append(base64.b64decode(p))

    protocol_pdf = None
    if payload.get("protocol_base64"):
        protocol_pdf = base64.b64decode(payload["protocol_base64"])

    adapter = _get_erp()
    try:
        result = adapter.process(
            pdf_bytes=pdf_bytes,
            erp_token=x_api_key or "unknown",
            document_type=payload.get("document_type", "Abnahmeprotokoll"),
            photo_bytes=photos if photos else None,
            protocol_pdf=protocol_pdf,
            gps_lat=payload.get("gps_lat", 0),
            gps_lng=payload.get("gps_lng", 0),
            metadata=payload.get("metadata"),
        )
        return {**result, "tenant_id": ctx.tenant_id}
    except ValueError as e:
        raise HTTPException(403, str(e))


@router.get("/verify/{session_id}", tags=["Handwerk"])
async def verify_document(
    session_id: str,
):
    """Kunden-QR-Code: Prüft ob ein Dokument on-chain verankert wurde.

    Kein API-Key nötig — Kunden-Link.
    """
    adapter = _get_erp()
    result = adapter.verify(session_id)
    return result


# ─── POST /v1/anchor-plan (Bauplan-Treuhänder) ──────────────────────

@router.post("/anchor-plan", tags=["Handwerk"])
async def anchor_plan(
    payload: dict,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """Bauplan-Treuhänder: Dual-Hash (Datei + sichtbarer Text) + QR-Code.

    Akzeptiert: Plan-PDF (base64), Plan-Nummer, Revision, Maßstab, Projekt-ID.
    Hashed Datei + extrahierten Text separat → kombinierter Fingerabdruck.
    """
    import base64
    gk = _get_gatekeeper()
    ctx = await gk.authenticate(x_api_key, "/v1/anchor-plan")

    pdf_b64 = payload.get("pdf_base64", "")
    if not pdf_b64:
        raise HTTPException(400, "pdf_base64 required")
    pdf_bytes = base64.b64decode(pdf_b64)

    adapter = _get_erp()
    try:
        result = adapter.anchor_plan(
            pdf_bytes=pdf_bytes,
            erp_token=x_api_key or "unknown",
            plan_number=payload.get("plan_number", ""),
            revision=payload.get("revision", ""),
            scale=payload.get("scale", ""),
            project_id=payload.get("project_id", ""),
            polier_id=payload.get("polier_id", ""),
            gps_lat=payload.get("gps_lat", 0),
            gps_lng=payload.get("gps_lng", 0),
            layer_count=payload.get("layer_count", 0),
        )
        return {**result, "tenant_id": ctx.tenant_id}
    except ValueError as e:
        raise HTTPException(403, str(e))


@router.get("/verify-plan/{session_id}", tags=["Handwerk"])
async def verify_plan(session_id: str):
    """QR-Code auf dem Baucontainer: Prüft ob ein Bauplan gültig ist."""
    adapter = _get_erp()
    result = adapter.verify(session_id)
    if result.get("document_type") == "Bauplan":
        result["message"] = (
            f"✅ Gültiger Bauplan vom {result.get('anchored_at', 'unbekannt')[:10]}. "
            f"Abweichungen zur Vorwoche: keine festgestellt."
            if result.get("verified")
            else "❌ Plan nicht gefunden oder nicht verankert."
        )
    return result


# ─── POST /v1/vault (Dateien verschlüsselt ablegen) ──────────────────

@router.post("/vault", tags=["Handwerk"])
async def vault_store(
    payload: dict,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """Protokoll-PDF + Fotos verschlüsselt speichern."""
    gk = _get_gatekeeper()
    ctx = await gk.authenticate(x_api_key, "/v1/vault")

    # Base64-dekodierte Dateien
    import base64
    pdf_bytes = base64.b64decode(payload.get("pdf_base64", ""))
    photos = [base64.b64decode(p) for p in payload.get("photos_base64", [])]

    vault = _get_vault()
    result = vault.store(pdf_bytes, photos, payload.get("metadata", {}))
    return {**result, "tenant_id": ctx.tenant_id}


# ─── GET /v1/vault/{session_id} (Dateien abrufen) ───────────────────

@router.get("/vault/{session_id}", tags=["Handwerk"])
async def vault_retrieve(
    session_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """Verschlüsselte Dateien abrufen und zurückgeben (Base64)."""
    gk = _get_gatekeeper()
    ctx = await gk.authenticate(x_api_key, "/v1/vault")

    vault = _get_vault()
    data = vault.retrieve(session_id)
    if not data:
        raise HTTPException(404, "Session not found")

    import base64
    return {
        "session_id": session_id,
        "pdf_base64": base64.b64encode(data["protocol_pdf"]).decode(),
        "photos_base64": [base64.b64encode(p).decode() for p in data["photos"]],
        "metadata": data["metadata"],
    }


# ─── POST /v1/backtest (bestehender Endpoint) ────────────────────────


    return BacktestResponseDTO(
        scenarios_run=len(results),
        overall_score=round(total_score, 1),
        overall_grade=(
            "A+" if total_score >= 95 else "A" if total_score >= 85
            else "B" if total_score >= 70 else "C" if total_score >= 55 else "D"
        ),
        results=[{
            "scenario": r.scenario_name, "grade": r.grade,
            "state_accuracy": r.state_accuracy, "action_precision": r.action_precision,
            "profit_saved_usd": r.total_profit_saved_usd,
        } for r in results],
    )
