"""Root — ExecutionResilienceOrchestrator (Wave 40).

4-Quadrant pipeline. Phase D activates all quadrants (Infra → Operativ).
"""

from __future__ import annotations

from typing import Any, Mapping

from agents_b2g.resilience.agents import make_response
from agents_b2g.resilience.config import ResilienceConfig
from agents_b2g.resilience.logging_utils import JSONLogger, _safe_call
from agents_b2g.resilience.subagents.black_swan_breaker import BlackSwanCircuitBreaker
from agents_b2g.resilience.subagents.confounder_detector import ConfounderDetector
from agents_b2g.resilience.subagents.execution_forensic_recorder import (
    ExecutionForensicRecorder,
)
from agents_b2g.resilience.subagents.fiscal_compliance_auditor import (
    FiscalComplianceAuditor,
)
from agents_b2g.resilience.subagents.gas_budget_enforcer import GasBudgetEnforcer
from agents_b2g.resilience.subagents.mev_shield import MEVShield
from agents_b2g.resilience.subagents.reorg_monitor import ReorgMonitor
from agents_b2g.resilience.subagents.rpc_health_sentinel import RPCHealthSentinel
from agents_b2g.resilience.types import (
    Quadrant,
    ResilienceEnvelope,
    ResilienceVerdict,
)


# ---------------------------------------------------------------------------
# Orchestrator subagents (9)
# ---------------------------------------------------------------------------


class QuadrantRouter:
    name = "QuadrantRouter"

    def run(self, active: tuple[str, ...]) -> dict[str, Any]:
        order = [
            Quadrant.INFRA.value,
            Quadrant.MEV.value,
            Quadrant.MODEL.value,
            Quadrant.OPERATIONAL.value,
        ]
        return {
            "order": order,
            "active": list(active),
            "pending": [q for q in order if q not in active],
        }


class FinalityGate:
    name = "FinalityGate"

    def run(self, finality_ok: bool) -> dict[str, Any]:
        return {"pass": finality_ok, "gate": "finality"}


class BudgetLedger:
    """Gas BHO ledger — Gas_In = Used + Refunded + Reserve."""

    name = "BudgetLedger"

    def run(
        self,
        gas_in: float = 0.0,
        gas_used: float = 0.0,
        gas_refunded: float = 0.0,
        gas_reserve: float = 0.0,
        epsilon: float = 0.01,
    ) -> dict[str, Any]:
        delta = float(gas_in) - (float(gas_used) + float(gas_refunded) + float(gas_reserve))
        return {
            "gas_in": gas_in,
            "gas_used": gas_used,
            "gas_refunded": gas_refunded,
            "gas_reserve": gas_reserve,
            "delta": round(delta, 6),
            "balanced": abs(delta) <= epsilon,
        }


class CircuitBreakerCoordinator:
    name = "CircuitBreakerCoordinator"

    def run(
        self,
        rpc_circuit_open: bool,
        deep_reorg: bool,
        gas_circuit_open: bool = False,
        mev_leakage: bool = False,
        black_swan_halt: bool = False,
    ) -> dict[str, Any]:
        open_ = (
            rpc_circuit_open
            or deep_reorg
            or gas_circuit_open
            or mev_leakage
            or black_swan_halt
        )
        return {
            "circuit_open": open_,
            "reasons": [
                *(["rpc_timeout"] if rpc_circuit_open else []),
                *(["deep_reorg"] if deep_reorg else []),
                *(["gas_budget"] if gas_circuit_open else []),
                *(["mempool_leakage"] if mev_leakage else []),
                *(["black_swan"] if black_swan_halt else []),
            ],
        }


class TelemetryAggregator:
    name = "TelemetryAggregator"

    def run(self, parts: Mapping[str, Any]) -> dict[str, Any]:
        return {"metrics": dict(parts), "count": len(parts)}


class PolicyEngine:
    name = "PolicyEngine"

    def run(
        self,
        *,
        finality_ok: bool,
        rpc_ok: bool,
        mev_ok: bool,
        gas_ok: bool,
        confounder_ok: bool,
        blackswan_ok: bool,
        fiscal_ok: bool,
        forensic_ok: bool,
        circuit_open: bool,
    ) -> dict[str, Any]:
        if circuit_open or not blackswan_ok:
            verdict = ResilienceVerdict.HALTED.value
        elif (
            not finality_ok
            or not mev_ok
            or not gas_ok
            or not confounder_ok
            or not fiscal_ok
            or not forensic_ok
        ):
            verdict = ResilienceVerdict.BLOCKED.value
        elif not rpc_ok:
            verdict = ResilienceVerdict.DEGRADED.value
        else:
            verdict = ResilienceVerdict.READY.value
        return {"policy_verdict": verdict}


class MultiTenantIsolator:
    name = "MultiTenantIsolator"

    def run(self, user_id: str, tenant_path: str) -> dict[str, Any]:
        return {"user_id": user_id, "tenant_path": tenant_path, "isolated": True}


class GoBDExporter:
    """Export forensic tip into GoBD package metadata."""

    name = "GoBDExporter"

    def run(
        self,
        job_id: str,
        *,
        tip_hash: str | None = None,
        fiscal_seal: str | None = None,
        export: bool = True,
    ) -> dict[str, Any]:
        return {
            "job_id": job_id,
            "exported": export and bool(tip_hash),
            "tip_hash": tip_hash,
            "fiscal_seal": fiscal_seal,
            "phase": "D",
        }


class HealthReporter:
    name = "HealthReporter"

    def run(self, envelope: ResilienceEnvelope) -> dict[str, Any]:
        return {
            "status": envelope.status.value,
            "finality_ok": envelope.finality_ok,
            "rpc_ok": envelope.rpc_ok,
            "mev_ok": envelope.mev_ok,
            "gas_ok": envelope.gas_ok,
            "confounder_ok": envelope.confounder_ok,
            "blackswan_ok": envelope.blackswan_ok,
            "fiscal_ok": envelope.fiscal_ok,
            "forensic_ok": envelope.forensic_ok,
            "gas_bho_delta": envelope.gas_bho_delta,
        }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class ExecutionResilienceOrchestrator:
    """Root orchestrator — Phase D: all four quadrants."""

    agent_name = "ExecutionResilienceOrchestrator"
    ACTIVE_QUADRANTS: tuple[str, ...] = (
        Quadrant.INFRA.value,
        Quadrant.MEV.value,
        Quadrant.MODEL.value,
        Quadrant.OPERATIONAL.value,
    )

    def __init__(self, user_id: str = "wave40", config: ResilienceConfig | None = None):
        self.user_id = user_id
        self.config = config or ResilienceConfig.load()
        self.logger = JSONLogger(self.agent_name, user_id)
        self._tenant = self.config.tenant_root(user_id)

        self.reorg = ReorgMonitor(user_id, self.config)
        self.rpc = RPCHealthSentinel(user_id, self.config)
        self.mev = MEVShield(user_id, self.config)
        self.gas = GasBudgetEnforcer(user_id, self.config)
        self.confounder = ConfounderDetector(user_id, self.config)
        self.black_swan = BlackSwanCircuitBreaker(user_id, self.config)
        self.fiscal = FiscalComplianceAuditor(user_id, self.config)
        self.forensic = ExecutionForensicRecorder(user_id, self.config)

        self.quadrant_router = QuadrantRouter()
        self.finality_gate = FinalityGate()
        self.budget_ledger = BudgetLedger()
        self.circuit_coord = CircuitBreakerCoordinator()
        self.telemetry = TelemetryAggregator()
        self.policy = PolicyEngine()
        self.tenant_isolator = MultiTenantIsolator()
        self.gobd = GoBDExporter()
        self.health = HealthReporter()

    def run(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        return _safe_call(self.logger, self.agent_name, self._run_inner, payload, job_id)

    def evaluate(self, payload: Mapping[str, Any], *, job_id: str) -> ResilienceEnvelope:
        return self._evaluate(payload, job_id=job_id)

    def _run_inner(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        envelope = self._evaluate(payload, job_id=job_id)
        status_map = {
            ResilienceVerdict.READY: "completed",
            ResilienceVerdict.DEGRADED: "completed",
            ResilienceVerdict.HALTED: "blocked",
            ResilienceVerdict.BLOCKED: "blocked",
        }
        return make_response(
            status_map[envelope.status],  # type: ignore[arg-type]
            job_id,
            artifacts=[
                {
                    "type": "resilience_envelope",
                    "format": "json",
                    "path": str(self._tenant / f"envelope_{job_id}.json"),
                    "metadata": envelope.to_dict(),
                }
            ],
            logs=[
                f"verdict={envelope.status.value}",
                f"finality_ok={envelope.finality_ok}",
                f"rpc_ok={envelope.rpc_ok}",
                f"mev_ok={envelope.mev_ok}",
                f"gas_ok={envelope.gas_ok}",
                f"confounder_ok={envelope.confounder_ok}",
                f"blackswan_ok={envelope.blackswan_ok}",
                f"fiscal_ok={envelope.fiscal_ok}",
                f"forensic_ok={envelope.forensic_ok}",
            ],
        )

    def _evaluate(self, payload: Mapping[str, Any], *, job_id: str) -> ResilienceEnvelope:
        route = self.quadrant_router.run(self.ACTIVE_QUADRANTS)
        tenant = self.tenant_isolator.run(self.user_id, str(self._tenant))

        reorg_payload = dict(payload.get("reorg", payload))
        rpc_payload = dict(payload.get("rpc", payload))
        mev_payload = dict(payload.get("mev", payload))
        gas_payload = dict(payload.get("gas", payload))
        conf_payload = dict(payload.get("confounder", payload))
        swan_payload = dict(payload.get("black_swan", payload))
        fiscal_payload = dict(payload.get("fiscal", payload))
        forensic_payload = dict(payload.get("forensic", payload))

        reorg_result = self.reorg.evaluate(reorg_payload)
        rpc_result = self.rpc.evaluate(rpc_payload)
        mev_result = self.mev.evaluate(mev_payload)
        gas_result = self.gas.evaluate(gas_payload, job_id=job_id)
        conf_result = self.confounder.evaluate(conf_payload)
        swan_result = self.black_swan.evaluate(swan_payload)
        fiscal_result = self.fiscal.evaluate(fiscal_payload)

        # Forensic records quadrant outcomes as execution steps
        if "execution_events" not in forensic_payload:
            forensic_payload = {
                **forensic_payload,
                "execution_events": [
                    {"event_id": f"{job_id}-infra", "step": "infra", "payload": {"finality_ok": reorg_result.finality_ok}},
                    {"event_id": f"{job_id}-mev", "step": "mev", "payload": {"mev_ok": mev_result.mev_ok, "gas_ok": gas_result.gas_ok}},
                    {"event_id": f"{job_id}-model", "step": "model", "payload": {"confounder_ok": conf_result.confounder_ok}},
                    {
                        "event_id": f"{job_id}-ops",
                        "step": "operational",
                        "payload": {"fiscal_ok": fiscal_result.fiscal_ok},
                    },
                ],
            }
        forensic_result = self.forensic.evaluate(forensic_payload, job_id=job_id)

        finality = self.finality_gate.run(reorg_result.finality_ok)
        deep_reorg = reorg_result.severity >= 3 or reorg_result.forked
        mev_leakage = mev_result.leakage_count > 0
        circuit = self.circuit_coord.run(
            rpc_result.circuit_open,
            deep_reorg,
            gas_circuit_open=gas_result.circuit_open,
            mev_leakage=mev_leakage,
            black_swan_halt=swan_result.halted,
        )

        bho = gas_result.subagent_results.get("bho_ledger", {})
        ledger = self.budget_ledger.run(
            gas_in=float(bho.get("gas_in", gas_payload.get("gas_in", 0))),
            gas_used=float(bho.get("gas_used", gas_payload.get("gas_used", 0))),
            gas_refunded=float(bho.get("gas_refunded", gas_payload.get("gas_refunded", 0))),
            gas_reserve=float(bho.get("gas_reserve", gas_payload.get("gas_reserve", 0))),
            epsilon=self.config.gas_bho_epsilon,
        )

        fiscal_seal = None
        seal = fiscal_result.subagent_results.get("AuditTrailSealer", {})
        if isinstance(seal, dict):
            fiscal_seal = seal.get("seal_hash")

        gobd = self.gobd.run(
            job_id,
            tip_hash=forensic_result.tip_hash,
            fiscal_seal=fiscal_seal,
            export=forensic_result.forensic_ok,
        )

        policy = self.policy.run(
            finality_ok=reorg_result.finality_ok,
            rpc_ok=rpc_result.rpc_ok,
            mev_ok=mev_result.mev_ok,
            gas_ok=gas_result.gas_ok,
            confounder_ok=conf_result.confounder_ok,
            blackswan_ok=swan_result.blackswan_ok,
            fiscal_ok=fiscal_result.fiscal_ok,
            forensic_ok=forensic_result.forensic_ok,
            circuit_open=circuit["circuit_open"],
        )
        verdict = ResilienceVerdict(policy["policy_verdict"])

        if (
            verdict == ResilienceVerdict.BLOCKED
            and reorg_result.severity == 0
            and not reorg_result.forked
            and not rpc_result.circuit_open
            and rpc_result.rpc_ok
            and mev_result.mev_ok
            and gas_result.gas_ok
            and conf_result.confounder_ok
            and swan_result.blackswan_ok
            and fiscal_result.fiscal_ok
            and forensic_result.forensic_ok
            and not reorg_result.finality_ok
        ):
            verdict = ResilienceVerdict.DEGRADED

        if rpc_result.failover and verdict == ResilienceVerdict.READY:
            verdict = ResilienceVerdict.DEGRADED

        halt_reason = None
        if circuit["circuit_open"] or not swan_result.blackswan_ok:
            halt_reason = ",".join(circuit["reasons"]) or "black_swan"
        elif verdict == ResilienceVerdict.BLOCKED:
            if not fiscal_result.fiscal_ok:
                halt_reason = "fiscal_compliance"
            elif not forensic_result.forensic_ok:
                halt_reason = "forensic_worm"
            elif not conf_result.confounder_ok:
                halt_reason = "confounder_quarantine"
            elif not mev_result.mev_ok:
                halt_reason = "mev_shield"
            elif not gas_result.gas_ok:
                halt_reason = "gas_budget"
            else:
                halt_reason = "finality_gate"

        tel = self.telemetry.run(
            {
                "reorg_severity": reorg_result.severity,
                "rpc_latency_ms": rpc_result.latency_ms,
                "failover": rpc_result.failover,
                "mev_leakage": mev_result.leakage_count,
                "gas_cumulative": gas_result.cumulative_burn,
                "confounder_quarantined": conf_result.quarantined,
                "blackswan_sigma": swan_result.abs_sigma,
                "fiscal_ok": fiscal_result.fiscal_ok,
                "forensic_tip": forensic_result.tip_hash[:16],
            }
        )

        model_blocked = not conf_result.confounder_ok or not swan_result.blackswan_ok
        ops_blocked = not fiscal_result.fiscal_ok or not forensic_result.forensic_ok
        quadrant_results: dict[str, Any] = {
            Quadrant.INFRA.value: {
                "status": "completed",
                "reorg": reorg_result.to_dict(),
                "rpc": rpc_result.to_dict(),
            },
            Quadrant.MEV.value: {
                "status": "completed" if mev_result.mev_ok and gas_result.gas_ok else "blocked",
                "mev": mev_result.to_dict(),
                "gas": gas_result.to_dict(),
            },
            Quadrant.MODEL.value: {
                "status": "blocked" if model_blocked else "completed",
                "confounder": conf_result.to_dict(),
                "black_swan": swan_result.to_dict(),
            },
            Quadrant.OPERATIONAL.value: {
                "status": "blocked" if ops_blocked else "completed",
                "fiscal": fiscal_result.to_dict(),
                "forensic": forensic_result.to_dict(),
            },
            "orchestrator_subagents": {
                QuadrantRouter.name: route,
                FinalityGate.name: finality,
                BudgetLedger.name: ledger,
                CircuitBreakerCoordinator.name: circuit,
                TelemetryAggregator.name: tel,
                PolicyEngine.name: policy,
                MultiTenantIsolator.name: tenant,
                GoBDExporter.name: gobd,
            },
        }

        envelope = ResilienceEnvelope(
            status=verdict,
            job_id=job_id,
            quadrant_results=quadrant_results,
            finality_ok=reorg_result.finality_ok,
            rpc_ok=rpc_result.rpc_ok,
            mev_ok=mev_result.mev_ok,
            gas_ok=gas_result.gas_ok,
            confounder_ok=conf_result.confounder_ok,
            blackswan_ok=swan_result.blackswan_ok,
            fiscal_ok=fiscal_result.fiscal_ok,
            forensic_ok=forensic_result.forensic_ok,
            gas_bho_delta=float(ledger["delta"]),
            halt_reason=halt_reason,
            active_quadrants=self.ACTIVE_QUADRANTS,
        )
        quadrant_results["orchestrator_subagents"][HealthReporter.name] = self.health.run(
            envelope
        )
        return envelope


def demo() -> dict[str, Any]:
    """Smoke demo for Phase D (all quadrants)."""
    orch = ExecutionResilienceOrchestrator(user_id="demo")
    return orch.run(
        {
            "tip_block": 120,
            "signal_block": 100,
            "layer": "L1",
            "reorg_depth": 0,
            "block_hash": "0xdeadbeef01",
            "parent_hash": "0xcafebabe01",
            "expected_parent": "0xcafebabe01",
            "latency_samples_ms": [12.0, 15.0, 11.0, 14.0],
            "primary_endpoint": "https://rpc.primary.local",
            "fallback_endpoints": [
                "https://rpc.fallback.local",
                "https://builder.private.local",
            ],
            "use_public_mempool": False,
            "from_address": "0xown",
            "to_address": "0xtarget",
            "nonce": 5,
            "quoted_price": 1.0,
            "limit_price": 1.002,
            "gas_limit": 21000,
            "this_burn": 21000,
            "prior_burn": 0,
            "estimated_gas": 18000,
            "gas_in": 100.0,
            "gas_used": 70.0,
            "gas_refunded": 20.0,
            "gas_reserve": 10.0,
            "registered_factors": ["oracle_lag", "mev_density"],
            "signal_factors": ["oracle_lag"],
            "candidate_factors": ["oracle_lag"],
            "abs_sigma": 1.0,
            "current_vol": 0.1,
            "vol_30d": 0.1,
        },
        job_id="wave40-demo-d",
    )


if __name__ == "__main__":
    out = demo()
    logger = JSONLogger("wave40_demo", "demo")
    logger.info(
        "demo_complete",
        status=out.get("status"),
        job_id=out.get("job_id"),
        artifact_types=[a.get("type") for a in out.get("artifacts", [])],
    )
