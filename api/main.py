"""Agent X — FastAPI Application (v3.0)."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.v1.endpoints import router as v1_router
from core.exceptions import AgentXException

app = FastAPI(
    title="Agent X — SymbolicsAgent API",
    description="6-Klassen-Risikomanagement-System. "
                "/v1/evaluate — Schnelle Evaluierung (ohne Auth). "
                "/v1/evaluate/secure — Mit API-Key (X-API-Key Header).",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router)

# Agent 9: Telemetry-Middleware (automatisches Tracking)
from api_agents.agent_9_telemetry import TelemetryMiddleware, add_metrics_endpoint
app.add_middleware(TelemetryMiddleware)
add_metrics_endpoint(app)


@app.exception_handler(AgentXException)
async def agentx_exception_handler(request: Request, exc: AgentXException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": str(exc)}},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    import logging
    logging.getLogger("agent_x_api").error("Unhandled: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}},
    )


@app.get("/")
def root():
    return {
        "service": "Agent X — SymbolicsAgent API",
        "version": "3.0.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health():
    from datetime import datetime, timezone
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "3.0.0",
    }
