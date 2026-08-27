"""Virtual 1_000 EUR paper ledger with fees — simulation only."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional


TWOPLACES = Decimal("0.01")


def _d(x: Any) -> Decimal:
    return Decimal(str(x)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


@dataclass
class FeeSchedule:
    """Public-tariff snapshot — freeze before a 30-day run."""

    maker_bps: Decimal = Decimal("10")  # 0.10%
    taker_bps: Decimal = Decimal("10")
    snapshot_note: str = "placeholder_public_spot_taker_10bps"

    def fee_eur(self, notional_eur: Decimal, *, taker: bool = True) -> Decimal:
        bps = self.taker_bps if taker else self.maker_bps
        return (notional_eur * bps / Decimal("10000")).quantize(TWOPLACES)


@dataclass
class PaperLedger:
    starting_balance_eur: Decimal = Decimal("1000.00")
    fee_schedule: FeeSchedule = field(default_factory=FeeSchedule)
    cash_eur: Decimal = field(init=False)
    position_qty: Decimal = field(default_factory=lambda: Decimal("0"))
    avg_entry: Decimal = field(default_factory=lambda: Decimal("0"))
    fees_paid_eur: Decimal = field(default_factory=lambda: Decimal("0"))
    realized_pnl_eur: Decimal = field(default_factory=lambda: Decimal("0"))
    fills: List[Dict[str, Any]] = field(default_factory=list)
    order_send_count: int = 0  # must stay 0

    def __post_init__(self) -> None:
        self.cash_eur = _d(self.starting_balance_eur)

    def mark_equity(self, mark_price: Decimal) -> Decimal:
        mark = _d(mark_price)
        pos_val = (self.position_qty * mark).quantize(TWOPLACES)
        return (self.cash_eur + pos_val).quantize(TWOPLACES)

    def conservation_ok(self, mark_price: Decimal) -> bool:
        """Soft ledger sanity: non-negative cash/equity; never sent an order."""
        equity = self.mark_equity(mark_price)
        return (
            self.order_send_count == 0
            and self.cash_eur >= 0
            and equity >= 0
            and self.fees_paid_eur >= 0
        )

    def sim_buy(self, qty: Decimal, price: Decimal, *, signal_id: str) -> Optional[Dict[str, Any]]:
        """Simulate buy — never sends an order."""
        if self.order_send_count != 0:
            raise RuntimeError("order_send_count must stay 0")
        q = _d(qty)
        p = _d(price)
        if q <= 0 or p <= 0:
            return None
        notional = (q * p).quantize(TWOPLACES)
        fee = self.fee_schedule.fee_eur(notional, taker=True)
        cost = notional + fee
        if cost > self.cash_eur:
            return None
        # average in
        new_qty = self.position_qty + q
        if new_qty == 0:
            self.avg_entry = Decimal("0")
        else:
            self.avg_entry = (
                (self.position_qty * self.avg_entry + notional) / new_qty
            ).quantize(TWOPLACES)
        self.position_qty = new_qty
        self.cash_eur = (self.cash_eur - cost).quantize(TWOPLACES)
        self.fees_paid_eur = (self.fees_paid_eur + fee).quantize(TWOPLACES)
        fill = {
            "action": "SIM_FILL",
            "side": "BUY",
            "qty": str(q),
            "price": str(p),
            "fee_eur": str(fee),
            "signal_id": signal_id,
            "live_execution": False,
            "order_send": False,
        }
        self.fills.append(fill)
        return fill

    def sim_sell(self, qty: Decimal, price: Decimal, *, signal_id: str) -> Optional[Dict[str, Any]]:
        if self.order_send_count != 0:
            raise RuntimeError("order_send_count must stay 0")
        q = _d(qty)
        p = _d(price)
        if q <= 0 or p <= 0 or q > self.position_qty:
            return None
        notional = (q * p).quantize(TWOPLACES)
        fee = self.fee_schedule.fee_eur(notional, taker=True)
        proceeds = notional - fee
        pnl = ((p - self.avg_entry) * q - fee).quantize(TWOPLACES)
        self.position_qty = (self.position_qty - q).quantize(TWOPLACES)
        if self.position_qty == 0:
            self.avg_entry = Decimal("0")
        self.cash_eur = (self.cash_eur + proceeds).quantize(TWOPLACES)
        self.fees_paid_eur = (self.fees_paid_eur + fee).quantize(TWOPLACES)
        self.realized_pnl_eur = (self.realized_pnl_eur + pnl).quantize(TWOPLACES)
        fill = {
            "action": "SIM_FILL",
            "side": "SELL",
            "qty": str(q),
            "price": str(p),
            "fee_eur": str(fee),
            "realized_pnl_eur": str(pnl),
            "signal_id": signal_id,
            "live_execution": False,
            "order_send": False,
        }
        self.fills.append(fill)
        return fill

    def snapshot(self, mark_price: Decimal) -> Dict[str, Any]:
        equity = self.mark_equity(mark_price)
        return {
            "starting_balance_eur": str(_d(self.starting_balance_eur)),
            "cash_eur": str(self.cash_eur),
            "position_qty": str(self.position_qty),
            "avg_entry": str(self.avg_entry),
            "fees_paid_eur": str(self.fees_paid_eur),
            "realized_pnl_eur": str(self.realized_pnl_eur),
            "equity_eur": str(equity),
            "order_send_count": self.order_send_count,
            "conservation_ok": self.conservation_ok(mark_price),
            "live_execution": False,
        }

    def diagnostic_profit_factor(self) -> Dict[str, Any]:
        """Diagnostic only — never a pitch / release criterion."""
        wins = Decimal("0")
        losses = Decimal("0")
        for f in self.fills:
            if f.get("side") != "SELL":
                continue
            pnl = _d(f.get("realized_pnl_eur", "0"))
            if pnl >= 0:
                wins += pnl
            else:
                losses += abs(pnl)
        pf = None
        if losses > 0:
            pf = float(wins / losses)
        elif wins > 0:
            pf = float("inf")
        return {
            "profit_factor": pf,
            "gross_wins_eur": str(wins),
            "gross_losses_eur": str(losses),
            "diagnostic_only": True,
            "not_investment_advice": True,
            "note": "Plausibility check for the simulator — not a track record",
        }
