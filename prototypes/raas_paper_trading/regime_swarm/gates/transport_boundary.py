"""A2.5 — transport boundary (latency / frame / sequence → evaluate_gate)."""
from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional, Tuple

from prototypes.raas_paper_trading.regime_swarm.gates.common import InfraGateResult
from services.fail_closed_gate.gate_core import GateInput, TradeSignal, evaluate_gate


def _blocked_transport_gate_input(
    *,
    latency_spike: Optional[float] = None,
    oracle_ok: bool = True,
    scenario_ok: bool = True,
) -> GateInput:
    return GateInput(
        signal=TradeSignal(
            signal_id="swarm-a25-transport",
            source="P4",
            notional_eur=0.0,
            stress_score=0.0,
            oracle_ok=oracle_ok,
            scenario_ok=scenario_ok,
        ),
        exec_risk=0.1,
        cascade_risk=0.1,
        latency_spike=latency_spike,
        bho_delta=0.0,
        human_gate_open=False,
    )


class TransportBoundaryGate:
    """Validates transport metadata before feature engineering (A3+)."""

    name = "A2.5_TransportBoundary"

    def __init__(self, *, max_latency_ms: float = 500.0) -> None:
        self.max_latency_ms = max_latency_ms
        self.last_seq_num: Optional[int] = None

    def validate_frame(self, raw_data: Dict[str, Any]) -> Tuple[bool, InfraGateResult]:
        latency_ms = float(raw_data.get("latency_ms", 0) or 0)
        if latency_ms > self.max_latency_ms:
            verdict = evaluate_gate(
                _blocked_transport_gate_input(latency_spike=max(latency_ms, 600.0))
            )
            infra_reasons = [r for r in verdict.reasons if r != "HUMAN_GATE_CLOSED"]
            return False, InfraGateResult(
                passed=False,
                agent=self.name,
                message=f"A25_BLOCKED: {','.join(infra_reasons) or f'latency {latency_ms}ms'}",
                gate_verdict=verdict.to_dict(),
                infra_reasons=infra_reasons,
            )

        raw_bytes = raw_data.get("raw_bytes")
        if raw_bytes is not None:
            payload = raw_bytes
            if isinstance(payload, str):
                payload = bytes.fromhex(payload)
            if len(payload) >= 10:
                expected = payload[-8:].hex()
                calculated = hashlib.md5(payload[:-8], usedforsecurity=False).hexdigest()[:8]
                if expected != calculated:
                    verdict = evaluate_gate(
                        _blocked_transport_gate_input(oracle_ok=False, scenario_ok=False)
                    )
                    infra_reasons = [r for r in verdict.reasons if r != "HUMAN_GATE_CLOSED"]
                    return False, InfraGateResult(
                        passed=False,
                        agent=self.name,
                        message="A25_BLOCKED: frame_checksum_mismatch",
                        gate_verdict=verdict.to_dict(),
                        infra_reasons=infra_reasons,
                    )

        seq_num = raw_data.get("seq_num")
        if seq_num is not None:
            seq_i = int(seq_num)
            if self.last_seq_num is not None and seq_i - self.last_seq_num > 1:
                verdict = evaluate_gate(
                    _blocked_transport_gate_input(oracle_ok=False, scenario_ok=False)
                )
                infra_reasons = [r for r in verdict.reasons if r != "HUMAN_GATE_CLOSED"]
                return False, InfraGateResult(
                    passed=False,
                    agent=self.name,
                    message=f"A25_BLOCKED: seq_gap {self.last_seq_num}->{seq_i}",
                    gate_verdict=verdict.to_dict(),
                    infra_reasons=infra_reasons,
                )
            self.last_seq_num = seq_i

        verdict = evaluate_gate(_blocked_transport_gate_input())
        return True, InfraGateResult(
            passed=True,
            agent=self.name,
            message="PASSED",
            gate_verdict=verdict.to_dict(),
            infra_reasons=[],
        )
