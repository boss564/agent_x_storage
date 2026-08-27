"""Supranode Ingress/Egress facade around TrustedCoreGateway.

Thin outer skin only — does not remap P₁…P₉, no NATS bus, no 9 services.
D4: exterior surface is ingress/egress; core stays behind the gateway.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from prototypes.raas_hybrid_shell.schemas import LLMStrategyProposal, SafetyEnvelope
from prototypes.raas_hybrid_shell.trusted_gateway import TrustedCoreGateway

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"


@dataclass
class ExternalRequest:
    """Ingress input — external / shell shaped."""

    correlation_id: str
    proposal: LLMStrategyProposal
    source: str = "external"


@dataclass
class ExternalResponse:
    """Egress output — sole exterior reply."""

    correlation_id: str
    envelope: SafetyEnvelope
    egress_seal: str
    sealed_at: str
    scope: str = SCOPE
    live_execution: bool = False
    not_investment_advice: bool = True
    debt: list = field(
        default_factory=lambda: [
            "D1_not_investment_advice",
            "D2_red_sandbox",
            "D3_gateway",
            "D4_ingress_egress_only",
        ]
    )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["envelope"] = self.envelope.to_dict()
        return d


class SupranodeFacade:
    """P₁-ingress / P₉-egress skin; TrustedCoreGateway unchanged inside."""

    def __init__(
        self,
        tenant_id: str = "supranode",
        core: Optional[TrustedCoreGateway] = None,
    ) -> None:
        self.core = core or TrustedCoreGateway(tenant_id=tenant_id)

    def ingress(self, request: ExternalRequest) -> LLMStrategyProposal:
        """Validate exterior request; force untrusted boundary."""
        prop = request.proposal
        if not isinstance(prop, LLMStrategyProposal):
            raise TypeError("ingress requires LLMStrategyProposal")
        if not prop.untrusted:
            prop = LLMStrategyProposal(**{**prop.to_dict(), "untrusted": True})
        return prop

    def egress(
        self,
        *,
        correlation_id: str,
        envelope: SafetyEnvelope,
    ) -> ExternalResponse:
        """Seal envelope for exterior — soft seal (HSM later); no auto-exec."""
        material = {
            "correlation_id": correlation_id,
            "envelope_id": envelope.envelope_id,
            "gate_verdict": envelope.gate_verdict,
            "live_execution": False,
            "scope": SCOPE,
        }
        seal = hashlib.sha256(
            json.dumps(material, sort_keys=True).encode()
        ).hexdigest()
        return ExternalResponse(
            correlation_id=correlation_id,
            envelope=envelope,
            egress_seal=seal,
            sealed_at=datetime.now(timezone.utc).isoformat(),
        )

    def handle_external_request(
        self,
        request: ExternalRequest,
        *,
        n_scenarios: int = 40,
    ) -> ExternalResponse:
        """Ingress → core → egress. Sole public entry for the facade."""
        proposal = self.ingress(request)
        envelope = self.core.evaluate_shell_proposal(
            proposal, n_scenarios=n_scenarios
        )
        return self.egress(
            correlation_id=request.correlation_id, envelope=envelope
        )

    def health(self) -> Dict[str, Any]:
        h = self.core.health()
        debts = list(h.get("debt") or [])
        if "D4_ingress_egress_only" not in debts:
            debts.append("D4_ingress_egress_only")
        return {
            **h,
            "service": "supranode-facade",
            "facade": "ingress_egress",
            "core_service": h.get("service"),
            "debt": debts,
            "bus": None,
            "microservices": 0,
        }
