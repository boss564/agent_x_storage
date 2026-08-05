"""
Agent X — API Agent 9: TelemetryAuditAgent (Der unsichtbare CFO).

Verantwortung: API-Usage-Tracking, Billing-Metriken, Prometheus-Export,
Audit-Logging (Compliance/DSGVO).

Sub-Agenten:
  9a: BillingMetricsSubAgent — Request-Count, Tenant-Usage, Pay-per-Use
  9b: PrometheusExporterSubAgent — Gauges + Counters + Histograms
  9c: AuditLoggerSubAgent — JSONL-Log mit correlation_id, tenant_id

Usage:
  Die FastAPI-Middleware `TelemetryMiddleware` fängt jeden Request ab und
  tracked Latenz, Status, Tenant — ohne dass Endpunkte Code ändern müssen.
"""

import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("TelemetryAudit")

# ─── Konfiguration ───────────────────────────────────────────────────

AUDIT_LOG_PATH = os.getenv("AUDIT_LOG_PATH", "logs/api_audit.jsonl")
BILLING_RATE_PER_REQUEST = float(os.getenv("BILLING_RATE_PER_REQUEST", "0.001"))  # $0.001/Snapshot
BILLING_TIERS = {
    "free": {"rpm": 10, "daily": 100},
    "pro": {"rpm": 100, "daily": 10_000},
    "enterprise": {"rpm": 1000, "daily": 1_000_000},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Sub-Agent 9a: BillingMetricsSubAgent ────────────────────────────

class BillingMetricsSubAgent:
    """Zählt Requests pro Tenant und berechnet Nutzungsgebühren.

    Pay-per-Use: $0.001 pro Snapshot-Evaluation (Basis-Tier).
    Enterprise: Flatrate, aber Tracking für Capacity-Planning.
    """

    def __init__(self):
        self._counters: dict[str, dict[str, int]] = defaultdict(
            lambda: defaultdict(int))  # tenant → {"requests": N, "errors": N, "snapshots": N}
        self._daily: dict[str, dict[str, int]] = defaultdict(
            lambda: defaultdict(int))  # tenant → date → count

    def record_request(self, tenant_id: str, path: str, status_code: int,
                       snapshot_count: int = 1):
        """Zählt einen Request für Billing."""
        self._counters[tenant_id]["requests"] += 1
        self._counters[tenant_id]["snapshots"] += snapshot_count
        if status_code >= 400:
            self._counters[tenant_id]["errors"] += 1

        # Tageszähler
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._daily[tenant_id][today] += 1

    def get_usage(self, tenant_id: str) -> dict:
        """Holt Nutzungsdaten für einen Tenant."""
        c = self._counters.get(tenant_id, {})
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        daily_count = self._daily.get(tenant_id, {}).get(today, 0)
        est_cost = round(c.get("snapshots", 0) * BILLING_RATE_PER_REQUEST, 4)

        return {
            "tenant_id": tenant_id,
            "total_requests": c.get("requests", 0),
            "total_snapshots": c.get("snapshots", 0),
            "total_errors": c.get("errors", 0),
            "daily_requests_today": daily_count,
            "estimated_cost_usd": est_cost,
            "billing_rate_per_request": BILLING_RATE_PER_REQUEST,
        }

    def get_all_usage(self) -> list[dict]:
        return [self.get_usage(t) for t in self._counters]

    @property
    def total_requests(self) -> int:
        return sum(c.get("requests", 0) for c in self._counters.values())

    @property
    def active_tenants(self) -> int:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return sum(1 for t, days in self._daily.items() if days.get(today, 0) > 0)


# ─── Sub-Agent 9b: PrometheusExporterSubAgent ────────────────────────

class PrometheusExporterSubAgent:
    """Exported API-Metriken im Prometheus-Format.

    Metrics:
      agent_x_api_requests_total{tenant, path, status}
      agent_x_api_latency_seconds{tenant, path}
      agent_x_api_active_tenants
      agent_x_api_billing_usd_total{tenant}
    """

    def __init__(self):
        self._gauges: dict[str, float] = {}
        self._counters: dict[str, dict[str, int]] = defaultdict(
            lambda: defaultdict(int))
        self._histograms: dict[str, list[float]] = defaultdict(list)

    def record(self, tenant: str, path: str, status: int, latency_ms: int):
        """Zeichnet Metrik-Punkt auf."""
        key = f'{tenant}:{path}:{status}'
        self._counters["requests"][key] += 1
        self._histograms[f"latency:{path}"].append(latency_ms)
        self._gauges[f"latency_last_ms:{tenant}"] = latency_ms

    def render(self) -> str:
        """Prometheus-Text-Format."""
        lines = [
            "# HELP agent_x_api_requests_total Total API requests",
            "# TYPE agent_x_api_requests_total counter",
        ]
        for key, count in sorted(self._counters["requests"].items()):
            parts = key.split(":")
            if len(parts) == 3:
                tenant, path, status = parts
                lines.append(
                    f'agent_x_api_requests_total{{tenant="{tenant}",'
                    f'path="{path}",status="{status}"}} {count}'
                )

        lines.extend([
            "# HELP agent_x_api_active_tenants Active tenants today",
            "# TYPE agent_x_api_active_tenants gauge",
            f"agent_x_api_active_tenants {len(self._gauges)}",
        ])

        for key, lat in self._gauges.items():
            if key.startswith("latency_last_ms:"):
                tenant = key.split(":", 1)[1]
                lines.append(
                    f"# HELP agent_x_api_latency_ms Last request latency"
                    f"\n# TYPE agent_x_api_latency_ms gauge"
                    f"\nagent_x_api_latency_ms{{tenant=\"{tenant}\"}} {lat}"
                )

        return "\n".join(lines) + "\n"


# ─── Sub-Agent 9c: AuditLoggerSubAgent ───────────────────────────────

class AuditLoggerSubAgent:
    """Schreibt jeden Request als JSONL-Zeile für Compliance (DSGVO/SOC2).

    Format: {"ts": "...", "correlation_id": "...", "tenant_id": "...",
             "path": "...", "method": "...", "status": N, "duration_ms": N,
             "client_ip": "...", "api_key_hash": "..."}
    """

    def __init__(self, log_path: str = AUDIT_LOG_PATH):
        self.log_path = log_path
        # Ensure directory exists
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

    def log(self, entry: dict):
        entry["ts"] = _now_iso()
        try:
            with open(self.log_path, "a") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error("Audit-Log Fehler: %s", e)


# ─── Agent 9: TelemetryAuditAgent ────────────────────────────────────

class TelemetryAuditAgent:
    """Haupt-Agent: Billing + Prometheus + Audit.

    Usage:
        telemetry = TelemetryAuditAgent()
        telemetry.record(request, response, tenant_id, correlation_id)
    """

    def __init__(self):
        self.billing = BillingMetricsSubAgent()
        self.prometheus = PrometheusExporterSubAgent()
        self.audit = AuditLoggerSubAgent()

    def record(self, path: str, method: str, status_code: int,
               duration_ms: float, tenant_id: str, correlation_id: str,
               client_ip: str = "unknown", snapshot_count: int = 1):
        """Zeichnet einen API-Request in allen drei Sub-Systemen auf."""
        # Billing
        self.billing.record_request(tenant_id, path, status_code, snapshot_count)

        # Prometheus
        self.prometheus.record(tenant_id, path, status_code, int(duration_ms))

        # Audit
        self.audit.log({
            "correlation_id": correlation_id,
            "tenant_id": tenant_id,
            "path": path, "method": method,
            "status": status_code, "duration_ms": round(duration_ms, 2),
            "client_ip": client_ip, "snapshot_count": snapshot_count,
        })

    def get_metrics(self) -> str:
        return self.prometheus.render()

    def get_billing(self, tenant_id: str | None = None) -> dict | list[dict]:
        if tenant_id:
            return self.billing.get_usage(tenant_id)
        return self.billing.get_all_usage()

    @property
    def stats(self) -> dict:
        return {
            "total_requests": self.billing.total_requests,
            "active_tenants": self.billing.active_tenants,
        }


# ─── Telemetry-Middleware (FastAPI) ──────────────────────────────────

# Singleton
_telemetry_agent: Optional[TelemetryAuditAgent] = None


def get_telemetry() -> TelemetryAuditAgent:
    global _telemetry_agent
    if _telemetry_agent is None:
        _telemetry_agent = TelemetryAuditAgent()
    return _telemetry_agent


class TelemetryMiddleware(BaseHTTPMiddleware):
    """Auto-Tracking für jeden API-Request — kein Code in Endpunkten nötig.

    Extrahiert tenant_id und correlation_id aus dem Request-State
    (gesetzt von Gatekeeper-Middleware oder Endpoint).
    """

    async def dispatch(self, request: Request, call_next):
        t0 = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - t0) * 1000

        # Extrahiere Tenant aus API-Key (direkt, unabhängig von Gatekeeper)
        api_key = request.headers.get("X-API-Key", "")
        tenant_id = "anonymous"
        if api_key:
            try:
                from api_agents.agent_1_gatekeeper import TenantMapper
                info = TenantMapper.lookup(api_key)
                if info:
                    tenant_id = info["tenant"]
            except ImportError:
                pass

        # Correlation-ID aus Header oder neu generieren
        corr_id = request.headers.get("X-Correlation-ID", "no_context")
        client_ip = request.client.host if request.client else "unknown"

        # Snapshot-Count aus Request-Body schätzen
        snapshot_count = 1
        try:
            body = await request.body()
            if body:
                payload = json.loads(body)
                positions = payload.get("positions", [])
                snapshot_count = max(1, len(positions))
        except Exception:
            pass

        get_telemetry().record(
            path=request.url.path, method=request.method,
            status_code=response.status_code, duration_ms=duration_ms,
            tenant_id=tenant_id, correlation_id=corr_id,
            client_ip=client_ip, snapshot_count=snapshot_count,
        )

        return response


# ─── Prometheus-Endpoint (optional via FastAPI) ──────────────────────

def add_metrics_endpoint(app):
    """Hängt /metrics an die FastAPI-App (ohne bestehende Router zu ändern)."""
    from fastapi import APIRouter
    from fastapi.responses import PlainTextResponse

    router = APIRouter()

    @router.get("/metrics", include_in_schema=False)
    def metrics():
        return PlainTextResponse(content=get_telemetry().get_metrics())

    @router.get("/billing", include_in_schema=False)
    def billing(tenant_id: str = "all"):
        data = get_telemetry().get_billing(tenant_id if tenant_id != "all" else None)
        return data

    app.include_router(router)


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Demo: Simuliere ein paar Requests und zeige Billing + Prometheus
    agent = TelemetryAuditAgent()

    for i in range(5):
        agent.record("/v1/evaluate", "POST", 200, 5.2, "tenant_alpha",
                     f"corr_{i:04d}", "192.168.1.1", snapshot_count=3)
    agent.record("/v1/evaluate", "POST", 429, 2.1, "tenant_alpha",
                 "corr_rate_limited", "192.168.1.1")
    agent.record("/v1/evaluate/secure", "POST", 200, 8.3, "tenant_beta",
                 "corr_beta", "10.0.0.1", snapshot_count=1)

    print("=== Billing ===")
    print(json.dumps(agent.get_billing(), indent=2))
    print(f"\nTotal Requests: {agent.stats['total_requests']}")
    print(f"Active Tenants: {agent.stats['active_tenants']}")
    print(f"\n=== Prometheus (/metrics) ===")
    print(agent.get_metrics()[:500])
