"""A4 — GasBudgetEnforcer (Wave 40 Quadrant 2 / MEV).

Nine subagents: PerTxCapValidator → CostAllocationLogger.
Invariants: Hard Gas-Cap + BHO-Δ=0 (Gas_In = Used + Refunded + Reserve).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from agents_b2g.resilience.agents import make_response
from agents_b2g.resilience.config import ResilienceConfig
from agents_b2g.resilience.logging_utils import JSONLogger, _safe_call


# ---------------------------------------------------------------------------
# Subagents (9)
# ---------------------------------------------------------------------------


class PerTxCapValidator:
    """Enforce MAX_GAS_PER_TX hard cap."""

    name = "PerTxCapValidator"

    def run(self, gas_limit: int, max_gas_per_tx: int) -> dict[str, Any]:
        ok = int(gas_limit) <= int(max_gas_per_tx)
        return {
            "gas_limit": gas_limit,
            "max_gas_per_tx": max_gas_per_tx,
            "ok": ok,
            "reason": None if ok else "per_tx_cap_exceeded",
        }


class CumulativeBurnTracker:
    """Track cumulative gas burn for the day (units)."""

    name = "CumulativeBurnTracker"

    def run(self, prior_burn: int, this_burn: int) -> dict[str, Any]:
        cumulative = int(prior_burn) + int(this_burn)
        return {
            "prior_burn": int(prior_burn),
            "this_burn": int(this_burn),
            "cumulative_burn": cumulative,
        }


class DailyLimitEnforcer:
    """Enforce DAILY_BURN_LIMIT — breach opens budget circuit."""

    name = "DailyLimitEnforcer"

    def run(self, cumulative_burn: int, daily_limit: int) -> dict[str, Any]:
        ok = int(cumulative_burn) <= int(daily_limit)
        return {
            "cumulative_burn": cumulative_burn,
            "daily_limit": daily_limit,
            "ok": ok,
            "reason": None if ok else "daily_burn_limit_exceeded",
        }


class PriorityFeeOptimizer:
    """Suggest priority fee within budget headroom."""

    name = "PriorityFeeOptimizer"

    def run(
        self,
        base_fee_gwei: float,
        target_inclusion_gwei: float,
        max_priority_gwei: float = 50.0,
    ) -> dict[str, Any]:
        tip = max(0.0, min(float(target_inclusion_gwei) - float(base_fee_gwei), max_priority_gwei))
        return {
            "priority_fee_gwei": round(tip, 4),
            "base_fee_gwei": base_fee_gwei,
            "max_fee_gwei": round(base_fee_gwei + tip, 4),
        }


class EIP1559Estimator:
    """Estimate EIP-1559 maxFeePerGas / maxPriorityFeePerGas."""

    name = "EIP1559Estimator"

    def run(
        self,
        base_fee_gwei: float,
        priority_fee_gwei: float,
        base_fee_buffer: float = 1.125,
    ) -> dict[str, Any]:
        max_fee = float(base_fee_gwei) * float(base_fee_buffer) + float(priority_fee_gwei)
        return {
            "max_fee_per_gas_gwei": round(max_fee, 4),
            "max_priority_fee_per_gas_gwei": round(float(priority_fee_gwei), 4),
            "base_fee_gwei": base_fee_gwei,
            "buffer": base_fee_buffer,
        }


class OutOfGasPreventer:
    """Reject if estimated usage approaches limit too closely."""

    name = "OutOfGasPreventer"

    def run(
        self,
        estimated_gas: int,
        gas_limit: int,
        safety_margin: float = 0.1,
    ) -> dict[str, Any]:
        ceiling = int(gas_limit * (1.0 - safety_margin))
        ok = int(estimated_gas) <= ceiling and int(estimated_gas) > 0
        return {
            "estimated_gas": estimated_gas,
            "gas_limit": gas_limit,
            "ceiling": ceiling,
            "ok": ok,
            "reason": None if ok else "out_of_gas_risk",
        }


class RefundAggregator:
    """Aggregate gas refunds into ledger bucket."""

    name = "RefundAggregator"

    def run(self, refunds: Sequence[float] | None = None) -> dict[str, Any]:
        vals = [float(x) for x in (refunds or [])]
        total = round(sum(vals), 6)
        return {"refund_total": total, "refund_count": len(vals), "refunds": vals[:32]}


class BudgetCircuitBreaker:
    """Open circuit on per-tx or daily cap breach."""

    name = "BudgetCircuitBreaker"

    def run(self, per_tx_ok: bool, daily_ok: bool, bho_balanced: bool) -> dict[str, Any]:
        open_ = not (per_tx_ok and daily_ok and bho_balanced)
        reasons = [
            *([] if per_tx_ok else ["per_tx_cap"]),
            *([] if daily_ok else ["daily_limit"]),
            *([] if bho_balanced else ["bho_delta"]),
        ]
        return {
            "circuit_open": open_,
            "state": "OPEN" if open_ else "CLOSED",
            "reasons": reasons,
        }


class CostAllocationLogger:
    """Allocate gas cost to tenant / job for audit."""

    name = "CostAllocationLogger"

    def run(
        self,
        *,
        user_id: str,
        job_id: str,
        gas_used: float,
        effective_gwei: float,
    ) -> dict[str, Any]:
        cost = float(gas_used) * float(effective_gwei)
        return {
            "user_id": user_id,
            "job_id": job_id,
            "gas_used": gas_used,
            "effective_gwei": effective_gwei,
            "cost_gwei_gas": round(cost, 4),
        }


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


@dataclass
class GasBudgetResult:
    gas_ok: bool
    circuit_open: bool
    bho_delta: float
    bho_balanced: bool
    cumulative_burn: int
    per_tx_ok: bool
    daily_ok: bool
    max_fee_gwei: float
    subagent_results: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gas_ok": self.gas_ok,
            "circuit_open": self.circuit_open,
            "bho_delta": self.bho_delta,
            "bho_balanced": self.bho_balanced,
            "cumulative_burn": self.cumulative_burn,
            "per_tx_ok": self.per_tx_ok,
            "daily_ok": self.daily_ok,
            "max_fee_gwei": self.max_fee_gwei,
            "subagents": self.subagent_results,
        }


class GasBudgetEnforcer:
    """A4 — hard gas caps, EIP-1559 estimate, BHO-Δ=0 ledger."""

    agent_name = "GasBudgetEnforcer"

    def __init__(self, user_id: str = "wave40", config: ResilienceConfig | None = None):
        self.user_id = user_id
        self.config = config or ResilienceConfig.load()
        self.logger = JSONLogger(self.agent_name, user_id)
        self._tenant = self.config.tenant_root(user_id)
        self.per_tx = PerTxCapValidator()
        self.burn = CumulativeBurnTracker()
        self.daily = DailyLimitEnforcer()
        self.prio = PriorityFeeOptimizer()
        self.eip1559 = EIP1559Estimator()
        self.oog = OutOfGasPreventer()
        self.refunds = RefundAggregator()
        self.breaker = BudgetCircuitBreaker()
        self.alloc = CostAllocationLogger()

    def run(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        return _safe_call(self.logger, self.agent_name, self._run_inner, payload, job_id)

    def evaluate(self, payload: Mapping[str, Any], *, job_id: str = "gas") -> GasBudgetResult:
        return self._evaluate(payload, job_id=job_id)

    def _run_inner(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        result = self._evaluate(payload, job_id=job_id)
        status = "blocked" if result.circuit_open or not result.gas_ok else "completed"
        return make_response(
            status,  # type: ignore[arg-type]
            job_id,
            artifacts=[
                {
                    "type": "gas_budget_result",
                    "path": str(self._tenant / f"gas_{job_id}.json"),
                    "metadata": result.to_dict(),
                }
            ],
            logs=[
                f"gas_ok={result.gas_ok}",
                f"circuit={result.circuit_open}",
                f"bho_delta={result.bho_delta}",
            ],
        )

    def _evaluate(self, payload: Mapping[str, Any], *, job_id: str) -> GasBudgetResult:
        gas_limit = int(payload.get("gas_limit", payload.get("this_burn", 21000)))
        this_burn = int(payload.get("this_burn", gas_limit))
        prior_burn = int(payload.get("prior_burn", 0))
        estimated = int(payload.get("estimated_gas", max(1, int(gas_limit * 0.8))))
        base_fee = float(payload.get("base_fee_gwei", 20.0))
        target_incl = float(payload.get("target_inclusion_gwei", base_fee + 2.0))
        max_priority = float(payload.get("max_priority_gwei", 50.0))
        refund_list = list(payload.get("refunds", []))
        # BHO ledger inputs
        gas_used = float(payload.get("gas_used", this_burn))
        gas_refunded = float(payload.get("gas_refunded", sum(float(x) for x in refund_list) if refund_list else 0.0))
        gas_reserve = float(payload.get("gas_reserve", 0.0))
        gas_in = float(payload.get("gas_in", gas_used + gas_refunded + gas_reserve))

        per_r = self.per_tx.run(gas_limit, self.config.max_gas_per_tx)
        burn_r = self.burn.run(prior_burn, this_burn)
        day_r = self.daily.run(burn_r["cumulative_burn"], self.config.daily_burn_limit)
        tip_r = self.prio.run(base_fee, target_incl, max_priority)
        eip_r = self.eip1559.run(base_fee, tip_r["priority_fee_gwei"])
        oog_r = self.oog.run(estimated, gas_limit)
        ref_r = self.refunds.run(refund_list if refund_list else [gas_refunded] if gas_refunded else [])

        bho_delta = round(gas_in - (gas_used + gas_refunded + gas_reserve), 6)
        bho_balanced = abs(bho_delta) <= self.config.gas_bho_epsilon

        br_r = self.breaker.run(
            per_tx_ok=bool(per_r["ok"]),
            daily_ok=bool(day_r["ok"]),
            bho_balanced=bho_balanced,
        )
        # Out-of-gas risk also fails gas_ok but may not open daily circuit alone
        if not oog_r["ok"]:
            br_r = {
                **br_r,
                "circuit_open": True,
                "state": "OPEN",
                "reasons": list(br_r["reasons"]) + ["out_of_gas_risk"],
            }

        alloc_r = self.alloc.run(
            user_id=self.user_id,
            job_id=job_id,
            gas_used=gas_used,
            effective_gwei=float(eip_r["max_fee_per_gas_gwei"]),
        )

        gas_ok = (
            bool(per_r["ok"])
            and bool(day_r["ok"])
            and bho_balanced
            and bool(oog_r["ok"])
            and not br_r["circuit_open"]
        )

        return GasBudgetResult(
            gas_ok=gas_ok,
            circuit_open=bool(br_r["circuit_open"]),
            bho_delta=bho_delta,
            bho_balanced=bho_balanced,
            cumulative_burn=int(burn_r["cumulative_burn"]),
            per_tx_ok=bool(per_r["ok"]),
            daily_ok=bool(day_r["ok"]),
            max_fee_gwei=float(eip_r["max_fee_per_gas_gwei"]),
            subagent_results={
                PerTxCapValidator.name: per_r,
                CumulativeBurnTracker.name: burn_r,
                DailyLimitEnforcer.name: day_r,
                PriorityFeeOptimizer.name: tip_r,
                EIP1559Estimator.name: eip_r,
                OutOfGasPreventer.name: oog_r,
                RefundAggregator.name: ref_r,
                BudgetCircuitBreaker.name: br_r,
                CostAllocationLogger.name: alloc_r,
                "bho_ledger": {
                    "gas_in": gas_in,
                    "gas_used": gas_used,
                    "gas_refunded": gas_refunded,
                    "gas_reserve": gas_reserve,
                    "delta": bho_delta,
                    "balanced": bho_balanced,
                },
            },
        )
