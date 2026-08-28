"""B0 — position sizing orchestrator (boundary diagnostics, charter §4)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

from prototypes.raas_paper_trading.ledger import PaperLedger
from prototypes.raas_paper_trading.position_sizing.agents import (
    CapitalManager,
    KellyCalculator,
    NotionalCalculator,
    RiskChecker,
    ShadowPositionSimulator,
    SizingGateAdapter,
    TradeStatisticAggregator,
)
from prototypes.raas_paper_trading.position_sizing.audit_log import SizingAuditLog
from prototypes.raas_paper_trading.position_sizing.types import (
    GATE_INSUFFICIENT_HISTORY,
    GATE_LIMIT_EXCEEDED,
    GATE_LIMIT_OK,
    SIZING_SCHEMA,
    STATUS_COMPLETE,
    STATUS_INSUFFICIENT_HISTORY,
)


class PositionSizingOrchestrator:
    """B0 — coordinates B1→B8; exports Schranken, not recommendations."""

    def __init__(
        self,
        *,
        audit_path: Path,
        gamma: float = 0.25,
        window_size: int = 50,
        min_trades: Optional[int] = None,
        risk_limit_fraction: float = 0.02,
    ) -> None:
        self.capital = CapitalManager()
        self.stats = TradeStatisticAggregator(
            window_size=window_size,
            min_trades=min_trades if min_trades is not None else window_size,
        )
        self.kelly = KellyCalculator(gamma=gamma)
        self.notional = NotionalCalculator()
        self.risk = RiskChecker(risk_limit_fraction=risk_limit_fraction)
        self.gate = SizingGateAdapter()
        self.shadow = ShadowPositionSimulator()
        self.audit = SizingAuditLog(audit_path)

    def run_cycle(
        self,
        *,
        ledger: PaperLedger,
        mark_price: Decimal,
        symbol: str,
        cycle_id: Optional[str] = None,
        stats_override: Optional[TradeStatisticAggregator] = None,
        write_audit: bool = True,
    ) -> Dict[str, Any]:
        cid = cycle_id or f"SIZE-{uuid.uuid4().hex[:8].upper()}"
        price = Decimal(str(mark_price))
        if price <= 0:
            raise ValueError("mark_price must be positive")

        capital_eur = self.capital.total_capital_eur(ledger, price)
        max_notional = self.risk.max_notional_before_limit_breach_eur(capital_eur)
        max_units = (max_notional / price).quantize(Decimal("0.00000001")) if price > 0 else Decimal("0")

        stats_agent = stats_override if stats_override is not None else self.stats
        if stats_override is None:
            stats_agent.load_from_ledger(ledger)
        stats = stats_agent.evaluate()

        kelly_fraction: Optional[float] = None
        hypothetical_notional: Optional[Decimal] = None
        risk_fraction: Optional[float] = None

        if stats["status"] == STATUS_COMPLETE:
            p = float(stats["p"])
            b = float(stats["b"])
            kelly_fraction = round(self.kelly.compute_fraction(p, b), 6)
            hypothetical_notional = self.notional.compute_hypothetical_notional_eur(
                kelly_fraction, capital_eur
            )
            risk_fraction = round(
                self.risk.risk_fraction_notional(hypothetical_notional, capital_eur), 6
            )

        gate_decision = self.gate.decide(
            stats_status=str(stats["status"]),
            hypothetical_notional_eur=hypothetical_notional,
            max_notional_eur=max_notional,
        )

        row: Dict[str, Any] = {
            "schema": SIZING_SCHEMA,
            "cycle_id": cid,
            "symbol": symbol.upper(),
            "capital_eur": float(capital_eur),
            "capital_source": "paper_ledger.mark_equity",
            "price_eur": float(price),
            "stats_window_n": stats.get("stats_window_n"),
            "stats_count": stats.get("stats_count"),
            "status": stats["status"],
            "p": stats.get("p"),
            "b": stats.get("b"),
            "gamma": self.kelly.gamma,
            "kelly_fraction_computed": kelly_fraction,
            "computed_hypothetical_notional_eur": (
                float(hypothetical_notional) if hypothetical_notional is not None else None
            ),
            "risk_limit_fraction": self.risk.risk_limit_fraction,
            "risk_fraction_notional": risk_fraction,
            "max_notional_before_limit_breach_eur": float(max_notional),
            "max_units_before_limit_breach": float(max_units),
            "sizing_gate_decision": gate_decision,
            "agents": {
                "B1": {"agent": self.capital.name, "capital_eur": float(capital_eur)},
                "B2": stats,
                "B3": {"agent": self.kelly.name, "kelly_fraction_computed": kelly_fraction},
                "B4": {
                    "agent": self.notional.name,
                    "computed_hypothetical_notional_eur": (
                        float(hypothetical_notional) if hypothetical_notional is not None else None
                    ),
                },
                "B5": {
                    "agent": self.risk.name,
                    "max_notional_before_limit_breach_eur": float(max_notional),
                    "risk_fraction_notional": risk_fraction,
                },
                "B6": {"agent": self.gate.name, "sizing_gate_decision": gate_decision},
            },
        }

        if write_audit:
            alert_level = "OK"
            if gate_decision == GATE_LIMIT_EXCEEDED:
                alert_level = "CRITICAL"
            elif gate_decision == GATE_INSUFFICIENT_HISTORY:
                alert_level = "INFO"
            row["alert_level"] = alert_level
            self.audit.append(row)
            if gate_decision == GATE_LIMIT_EXCEEDED:
                self.audit.append(
                    {
                        **row,
                        "action": "SIZING_ALERT",
                        "alert_level": "CRITICAL",
                        "message": "computed_hypothetical_notional exceeds risk schranke",
                    }
                )

        self.shadow.simulate(
            {
                "cycle_id": cid,
                "sizing_gate_decision": gate_decision,
                "max_notional_before_limit_breach_eur": float(max_notional),
            }
        )

        envelope = {
            "linked": True,
            "sizing_gate_decision": gate_decision,
            "max_notional_before_limit_breach_eur": float(max_notional),
            "status": stats["status"],
        }
        if gate_decision == GATE_LIMIT_OK:
            envelope["computed_hypothetical_notional_eur"] = (
                float(hypothetical_notional) if hypothetical_notional is not None else None
            )

        row["sizing_envelope"] = envelope
        return row
