"""Wave 40 types — Execution Resilience envelopes and verdicts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ResilienceVerdict(str, Enum):
    """Orchestrator pipeline outcome."""

    READY = "READY"  # all active quadrants green
    DEGRADED = "DEGRADED"  # failover / soft reorg / RPC switch
    HALTED = "HALTED"  # black-swan / circuit open
    BLOCKED = "BLOCKED"  # finality / invariant failure


class ChainLayer(str, Enum):
    L1 = "L1"
    L2 = "L2"


class Quadrant(str, Enum):
    INFRA = "infra"
    MEV = "mev"
    MODEL = "model"
    OPERATIONAL = "operational"


@dataclass(frozen=True)
class ResilienceEnvelope:
    """Wave 40 output — consumed by execution callers / forensic recorder."""

    status: ResilienceVerdict
    job_id: str
    quadrant_results: dict[str, Any] = field(default_factory=dict)
    finality_ok: bool = False
    rpc_ok: bool = False
    mev_ok: bool = False
    gas_ok: bool = False
    confounder_ok: bool = False
    blackswan_ok: bool = False
    fiscal_ok: bool = False
    forensic_ok: bool = False
    gas_bho_delta: float = 0.0
    halt_reason: str | None = None
    active_quadrants: tuple[str, ...] = (Quadrant.INFRA.value,)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "job_id": self.job_id,
            "quadrant_results": self.quadrant_results,
            "finality_ok": self.finality_ok,
            "rpc_ok": self.rpc_ok,
            "mev_ok": self.mev_ok,
            "gas_ok": self.gas_ok,
            "confounder_ok": self.confounder_ok,
            "blackswan_ok": self.blackswan_ok,
            "fiscal_ok": self.fiscal_ok,
            "forensic_ok": self.forensic_ok,
            "gas_bho_delta": self.gas_bho_delta,
            "halt_reason": self.halt_reason,
            "active_quadrants": list(self.active_quadrants),
        }
