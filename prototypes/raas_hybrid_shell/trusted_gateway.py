"""TrustedCoreGateway — sole entry from untrusted shell into RaaS core.

Wraps existing store/runner/exporter. Does not remap P₁…P₉ roles.
Does not call execute_*; scenarios only via runner profiles.
Red-sandbox / Blue-sign (D2) and gateway (D3) remain layer-1 policy here.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_hybrid_shell.schemas import (  # noqa: E402
    LLMStrategyProposal,
    SafetyEnvelope,
)
from services.raas_portal import exporter, runner, store  # noqa: E402

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"
# Hard core ceiling — shell cannot raise this by proposing higher slippage
MAX_ALLOWED_SLIPPAGE_PCT = 1.5


class TrustedCoreGateway:
    """Fail-closed gateway: untrusted in → deterministic envelope out."""

    def __init__(self, tenant_id: str = "hybrid-shell") -> None:
        self.tenant_id = tenant_id

    def evaluate_shell_proposal(
        self,
        proposal: LLMStrategyProposal,
        *,
        n_scenarios: int = 40,
    ) -> SafetyEnvelope:
        if not proposal.untrusted:
            # Shell must declare untrusted; flip is rejected
            proposal = LLMStrategyProposal(
                **{**proposal.to_dict(), "untrusted": True}
            )

        countermeasures: List[str] = []
        hard_block = False

        if proposal.max_slippage_pct > MAX_ALLOWED_SLIPPAGE_PCT:
            hard_block = True
            countermeasures.append(
                f"CANDIDATE: clamp max_slippage_pct to "
                f"{MAX_ALLOWED_SLIPPAGE_PCT} (core ceiling; not applied)"
            )

        profile = proposal.profile_hint
        if profile not in runner.PROFILES:
            profile = "default"
            countermeasures.append("CANDIDATE: unknown profile_hint → default")

        # Intake via existing contract-shaped store (v0 proto; strategy intake later)
        contract = store.save_contract(
            tenant_id=self.tenant_id,
            name=f"ShellProposal-{proposal.proposal_id}",
            bytecode_hex="6080604052" + proposal.proposal_id.encode().hex(),
        )
        run = store.create_run(
            tenant_id=self.tenant_id,
            contract_id=contract["contract_id"],
            n_scenarios=n_scenarios,
            profile="aggressive" if hard_block else profile,
        )
        store.append_worm_line(
            self.tenant_id,
            run["run_id"],
            {
                "phase": "shell_intake",
                "proposal": proposal.to_dict(),
                "hard_block_slippage": hard_block,
            },
        )

        result = runner.run_stress_job(
            tenant_id=self.tenant_id, run_id=run["run_id"]
        )
        cert_out = exporter.export_certificate(
            tenant_id=self.tenant_id, run_id=run["run_id"], fmt="json"
        )
        metrics = result.get("metrics") or {}
        gate_verdict = result.get("gate_verdict") or "BLOCKED"
        audit_verdict = result.get("audit_verdict") or "ENTLASTUNG_VERWEIGERT"

        if hard_block:
            gate_verdict = "BLOCKED"
            audit_verdict = "ENTLASTUNG_VERWEIGERT"
            store.update_run(
                self.tenant_id,
                run["run_id"],
                {
                    "gate_verdict": gate_verdict,
                    "audit_verdict": audit_verdict,
                    "shell_hard_block": True,
                },
            )

        if gate_verdict != "RELEASED":
            countermeasures.append(
                "CANDIDATE: widen latency budget / lower stress profile "
                "(simulation only; no auto-deploy)"
            )

        env = {
            "proposal_id": proposal.proposal_id,
            "run_id": run["run_id"],
            "gate_verdict": gate_verdict,
            "audit_verdict": audit_verdict,
            "risk_block_rate": float(metrics.get("risk_block_rate") or 0.0),
            "countermeasures": countermeasures,
            "certificate_id": cert_out["certificate"].get("certificate_id"),
            "scope": SCOPE,
            "live_execution": False,
            "not_investment_advice": True,
            "shell_untrusted": True,
            "core_verified": True,
        }
        eid = hashlib.sha256(
            json.dumps(env, sort_keys=True, default=str).encode()
        ).hexdigest()[:32]

        store.append_worm_line(
            self.tenant_id,
            run["run_id"],
            {"phase": "envelope", "envelope_id": eid, "gate_verdict": gate_verdict},
        )

        return SafetyEnvelope(
            envelope_id=eid,
            proposal_id=proposal.proposal_id,
            run_id=run["run_id"],
            gate_verdict=gate_verdict,
            audit_verdict=audit_verdict,
            risk_block_rate=float(metrics.get("risk_block_rate") or 0.0),
            countermeasures=countermeasures,
            note=(
                "Shell proposal verified by trusted core only. "
                "No LLM decision. No on-chain execution. D1/D2/D3 layer-1."
            ),
        )

    def health(self) -> Dict[str, Any]:
        return {
            "status": "ok",
            "service": "trusted-core-gateway",
            "scope": SCOPE,
            "live_execution": False,
            "max_allowed_slippage_pct": MAX_ALLOWED_SLIPPAGE_PCT,
            "debt": ["D1_not_investment_advice", "D2_red_sandbox", "D3_gateway"],
        }
