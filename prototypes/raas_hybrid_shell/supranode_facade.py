"""Supranode Ingress/Egress facade around TrustedCoreGateway.

Thin outer skin only — does not remap P₁…P₉, no NATS bus, no 9 services.
D4: exterior surface is ingress/egress; core stays behind the gateway.
D1–D4: DSuiteEnforcer runs before core evaluation (layer 2).
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_GATE = _ROOT / "services" / "fail_closed_gate"
if str(_GATE) not in sys.path:
    sys.path.insert(0, str(_GATE))

from d_suite_enforcer import DSuiteEnforcer, DSuiteViolation, EnforcerContext  # noqa: E402

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
    worm_anchor_sha256: str = ""
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
        enforcer: Optional[DSuiteEnforcer] = None,
    ) -> None:
        self.core = core or TrustedCoreGateway(tenant_id=tenant_id)
        self.enforcer = enforcer or DSuiteEnforcer()
        self.tenant_id = tenant_id

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
        worm_anchor_sha256: str = "",
    ) -> ExternalResponse:
        """Seal envelope for exterior — soft seal (HSM later); no auto-exec."""
        material = {
            "correlation_id": correlation_id,
            "envelope_id": envelope.envelope_id,
            "gate_verdict": envelope.gate_verdict,
            "live_execution": False,
            "scope": SCOPE,
            "worm_anchor_sha256": worm_anchor_sha256,
        }
        seal = hashlib.sha256(
            json.dumps(material, sort_keys=True).encode()
        ).hexdigest()
        return ExternalResponse(
            correlation_id=correlation_id,
            envelope=envelope,
            egress_seal=seal,
            sealed_at=datetime.now(timezone.utc).isoformat(),
            worm_anchor_sha256=worm_anchor_sha256,
        )

    def handle_external_request(
        self,
        request: ExternalRequest,
        *,
        n_scenarios: int = 40,
    ) -> ExternalResponse:
        """Ingress → D-suite enforce → core → egress."""
        proposal = self.ingress(request)
        safe = self.enforcer.enforce_all(
            EnforcerContext(
                caller_role="UNTRUSTED_SHELL",
                target_path="/api/v1/raas/evaluate",
                payload=proposal.to_dict(),
            )
        )
        envelope = self.core.evaluate_shell_proposal(
            proposal, n_scenarios=n_scenarios
        )
        return self.egress(
            correlation_id=request.correlation_id,
            envelope=envelope,
            worm_anchor_sha256=str(safe.get("_worm_anchor_sha256") or ""),
        )

    def handle_external_batch(
        self,
        requests: list,
        *,
        n_scenarios: int = 20,
        prefilter_enabled: Optional[bool] = None,
        backlog_threshold: Optional[int] = None,
        score_fn: Optional[Any] = None,
    ) -> Any:
        """Optional backlog prioritization; every item still hits full core."""
        from prototypes.raas_hybrid_shell.prefilter_backlog import (
            PrefilterBacklogController,
        )

        ctrl = PrefilterBacklogController(
            facade=self,
            enabled=(
                self._prefilter_enabled()
                if prefilter_enabled is None
                else bool(prefilter_enabled)
            ),
            backlog_threshold=(
                self._backlog_threshold()
                if backlog_threshold is None
                else int(backlog_threshold)
            ),
            score_fn=score_fn,
        )
        return ctrl.process_batch(requests, n_scenarios=n_scenarios)

    @staticmethod
    def _prefilter_enabled() -> bool:
        import os

        return os.environ.get("PREFILTER_ENABLED", "").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

    @staticmethod
    def _backlog_threshold() -> int:
        import os

        return int(os.environ.get("PREFILTER_BACKLOG_THRESHOLD", "3"))

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
            "d_suite_enforcer": "layer2_active",
            "bus": None,
            "microservices": 0,
            "prefilter_enabled": self._prefilter_enabled(),
            "prefilter_backlog_threshold": self._backlog_threshold(),
            "prefilter_role": "queue_priority_only",
            "prefilter_policy": "M1_per_tenant",
            "tenant_id": self.tenant_id,
        }
