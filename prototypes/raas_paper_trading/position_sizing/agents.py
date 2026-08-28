"""B1–B7 agents — sizing mechanics (charter §4 output vocabulary)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from prototypes.raas_paper_trading.ledger import PaperLedger
from prototypes.raas_paper_trading.position_sizing.types import (
    GATE_INSUFFICIENT_HISTORY,
    GATE_LIMIT_EXCEEDED,
    GATE_LIMIT_OK,
    STATUS_COMPLETE,
    STATUS_INSUFFICIENT_HISTORY,
)


@dataclass
class CapitalManager:
    """B1 — mark-to-market equity from paper ledger."""

    name: str = "B1_CapitalManager"

    def total_capital_eur(self, ledger: PaperLedger, mark_price: Decimal) -> Decimal:
        return ledger.mark_equity(mark_price)


@dataclass
class TradeStatisticAggregator:
    """B2 — p and b from trade return window; hard block if insufficient."""

    name: str = "B2_TradeStatisticAggregator"
    window_size: int = 50
    min_trades: int = 50
    trade_history: List[float] = field(default_factory=list)

    def add_trade(self, profit_fraction: float) -> None:
        self.trade_history.append(float(profit_fraction))
        if len(self.trade_history) > self.window_size:
            self.trade_history.pop(0)

    def load_from_ledger(self, ledger: PaperLedger) -> None:
        self.trade_history.clear()
        for fill in ledger.fills:
            if fill.get("side") != "SELL":
                continue
            pnl = Decimal(str(fill.get("realized_pnl_eur", "0")))
            qty = Decimal(str(fill.get("qty", "0")))
            price = Decimal(str(fill.get("price", "0")))
            notional = (qty * price).quantize(Decimal("0.01"))
            if notional <= 0:
                continue
            self.add_trade(float(pnl / notional))

    def evaluate(self) -> Dict[str, Any]:
        n = len(self.trade_history)
        if n < self.min_trades:
            return {
                "agent": self.name,
                "status": STATUS_INSUFFICIENT_HISTORY,
                "stats_count": n,
                "stats_window_n": self.window_size,
                "p": None,
                "b": None,
            }
        wins = [t for t in self.trade_history if t > 0]
        losses = [t for t in self.trade_history if t < 0]
        p = len(wins) / n
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
        b = avg_win / avg_loss if avg_loss > 0 else 0.0
        if b <= 0:
            return {
                "agent": self.name,
                "status": STATUS_INSUFFICIENT_HISTORY,
                "stats_count": n,
                "stats_window_n": self.window_size,
                "p": None,
                "b": None,
                "reason": "non_positive_b",
            }
        return {
            "agent": self.name,
            "status": STATUS_COMPLETE,
            "stats_count": n,
            "stats_window_n": self.window_size,
            "p": round(p, 6),
            "b": round(b, 6),
        }


@dataclass
class KellyCalculator:
    """B3 — fractional Kelly (diagnostic fraction only)."""

    name: str = "B3_KellyCalculator"
    gamma: float = 0.25

    def compute_fraction(self, p: float, b: float) -> float:
        if b <= 0:
            return 0.0
        kelly = (p * b - (1.0 - p)) / b
        return max(0.0, self.gamma * kelly)


@dataclass
class NotionalCalculator:
    """B4 — hypothetical notional EUR (not a recommendation)."""

    name: str = "B4_NotionalCalculator"

    def compute_hypothetical_notional_eur(
        self, kelly_fraction: float, capital_eur: Decimal
    ) -> Decimal:
        return (capital_eur * Decimal(str(kelly_fraction))).quantize(Decimal("0.01"))


@dataclass
class RiskChecker:
    """B5 — compare notional EUR vs capital fraction (never units/capital)."""

    name: str = "B5_RiskChecker"
    risk_limit_fraction: float = 0.02

    def max_notional_before_limit_breach_eur(self, capital_eur: Decimal) -> Decimal:
        return (capital_eur * Decimal(str(self.risk_limit_fraction))).quantize(Decimal("0.01"))

    def risk_fraction_notional(
        self, hypothetical_notional_eur: Decimal, capital_eur: Decimal
    ) -> float:
        if capital_eur <= 0:
            return 0.0
        return float(hypothetical_notional_eur / capital_eur)


@dataclass
class SizingGateAdapter:
    """B6 — gate entire export layer (LIMIT_OK / LIMIT_EXCEEDED / INSUFFICIENT_HISTORY)."""

    name: str = "B6_SizingGateAdapter"

    def decide(
        self,
        *,
        stats_status: str,
        hypothetical_notional_eur: Optional[Decimal],
        max_notional_eur: Decimal,
    ) -> str:
        if stats_status == STATUS_INSUFFICIENT_HISTORY:
            return GATE_INSUFFICIENT_HISTORY
        if hypothetical_notional_eur is None:
            return GATE_INSUFFICIENT_HISTORY
        if hypothetical_notional_eur > max_notional_eur:
            return GATE_LIMIT_EXCEEDED
        return GATE_LIMIT_OK


@dataclass
class ShadowPositionSimulator:
    """B7 — offline replay history (no live thread)."""

    name: str = "B7_ShadowPositionSimulator"
    history: List[Dict[str, Any]] = field(default_factory=list)

    def simulate(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        row = {**entry, "agent": self.name, "shadow_only": True}
        self.history.append(row)
        return row

    def replay_returns(
        self,
        returns: Sequence[float],
        *,
        orchestrator: Any,
        symbol: str,
        price_eur: Decimal,
        ledger: PaperLedger,
    ) -> List[Dict[str, Any]]:
        agg = TradeStatisticAggregator(
            window_size=orchestrator.stats.window_size,
            min_trades=orchestrator.stats.min_trades,
        )
        out: List[Dict[str, Any]] = []
        for i, ret in enumerate(returns):
            agg.add_trade(ret)
            stub = PaperLedger(starting_balance_eur=ledger.starting_balance_eur)
            stub.cash_eur = ledger.cash_eur
            result = orchestrator.run_cycle(
                ledger=stub,
                mark_price=price_eur,
                symbol=symbol,
                cycle_id=f"SIZE-REPLAY-{i:04d}",
                stats_override=agg,
                write_audit=False,
            )
            self.simulate({"replay_index": i, "sizing_gate_decision": result.get("sizing_gate_decision")})
            out.append(result)
        return out
