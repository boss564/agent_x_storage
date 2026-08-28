"""A0 — core sanity adapter (tick → GateInput → evaluate_gate)."""
from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple

from prototypes.raas_paper_trading.regime_swarm.gates.common import (
    InfraGateResult,
    infra_verdict_passed,
)
from services.fail_closed_gate.gate_core import EXEC_RISK_BLOCK, CASCADE_BLOCK, GateInput, TradeSignal, evaluate_gate


class CoreSanityAdapter:
    """Maps the latest tick/price into gate_core and never duplicates gate rules."""

    name = "A0_CoreSanity"

    def __init__(
        self,
        *,
        max_price_change_pct: float = 20.0,
        max_spread_pct: float = 5.0,
    ) -> None:
        self.max_price_change = max_price_change_pct / 100.0
        self.max_spread = max_spread_pct / 100.0
        self.last_valid_price: Optional[float] = None

    def _build_gate_input(
        self,
        *,
        price: float,
        bid: float,
        ask: float,
        reference_price: Optional[float],
    ) -> GateInput:
        oracle_ok = (
            math.isfinite(price)
            and price > 0
            and math.isfinite(bid)
            and bid > 0
            and math.isfinite(ask)
            and ask > 0
        )
        scenario_ok = ask > bid
        spread_pct = (ask - bid) / bid if bid > 0 else float("inf")
        if spread_pct > self.max_spread:
            scenario_ok = False

        exec_risk = 0.1
        cascade_risk = 0.1
        stress_score = 0.0
        ref = reference_price if reference_price and reference_price > 0 else self.last_valid_price
        if ref and ref > 0 and oracle_ok:
            move = abs((price - ref) / ref)
            stress_score = min(0.99, move)
            if move > self.max_price_change:
                exec_risk = max(EXEC_RISK_BLOCK, min(0.99, 0.80 + move))
                cascade_risk = max(CASCADE_BLOCK, min(0.99, 0.75 + move))

        return GateInput(
            signal=TradeSignal(
                signal_id="swarm-a0-tick",
                source="P4",
                notional_eur=0.0,
                stress_score=stress_score,
                oracle_ok=oracle_ok,
                scenario_ok=scenario_ok,
            ),
            exec_risk=exec_risk,
            cascade_risk=cascade_risk,
            latency_spike=None,
            bho_delta=0.0,
            human_gate_open=False,
        )

    def validate_tick(
        self,
        tick: Dict[str, Any],
        *,
        reference_price: Optional[float] = None,
    ) -> Tuple[bool, InfraGateResult]:
        raw_price = tick.get("price")
        if raw_price is None:
            raw_price = tick.get("mark_price")
        price = float(raw_price)
        default_half_spread = min(0.001, self.max_spread / 4.0)
        bid = float(tick.get("bid", price * (1.0 - default_half_spread)))
        ask = float(tick.get("ask", price * (1.0 + default_half_spread)))

        gate_input = self._build_gate_input(
            price=price,
            bid=bid,
            ask=ask,
            reference_price=reference_price,
        )
        verdict = evaluate_gate(gate_input)
        passed = infra_verdict_passed(verdict)
        infra_reasons = [r for r in verdict.reasons if r != "HUMAN_GATE_CLOSED"]

        if not passed:
            self.last_valid_price = None
            return False, InfraGateResult(
                passed=False,
                agent=self.name,
                message=f"A0_BLOCKED: {','.join(infra_reasons) or verdict.decision}",
                gate_verdict=verdict.to_dict(),
                infra_reasons=infra_reasons,
            )

        self.last_valid_price = price
        return True, InfraGateResult(
            passed=True,
            agent=self.name,
            message="PASSED",
            gate_verdict=verdict.to_dict(),
            infra_reasons=[],
        )
