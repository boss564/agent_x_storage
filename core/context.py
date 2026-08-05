"""Agent X — RequestContext mit Correlation-ID & Tenant-Isolation."""

from dataclasses import dataclass, field
from uuid import uuid4
from typing import Optional


@dataclass
class RequestContext:
    """Wird jeder Orchestrator-Methode als erster Parameter übergeben.

    correlation_id: UUID — verfolgt den gesamten Request durch alle Module.
    tenant_id:       String — isoliert Daten pro Mandant (Multi-Tenancy).
    source_ip:       Optional — Client-IP für Audit-Logs.
    api_key:         Optional — API-Key für Rate-Limiting/Authentifizierung.
    """

    correlation_id: str = field(default_factory=lambda: uuid4().hex[:12])
    tenant_id: str = "default"
    source_ip: Optional[str] = None
    api_key: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "correlation_id": self.correlation_id,
            "tenant_id": self.tenant_id,
            "source_ip": self.source_ip or "unknown",
        }
