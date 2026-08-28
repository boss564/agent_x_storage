"""Virtual 1_000 EUR paper ledger with fees — simulation only."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from prototypes.raas_paper_trading.slippage import OrderBook, execution_price


TWOPLACES = Decimal("0.01")
EIGHTPLACES = Decimal("0.00000001")


def _d(x: Any) -> Decimal:
    return Decimal(str(x)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


@dataclass
class FeeSchedule:
    """Public-tariff snapshot — freeze before a 30-day run."""

    maker_bps: Decimal = Decimal("7.5")  # 0.075% Binance VIP1
    taker_bps: Decimal = Decimal("7.5")
    snapshot_note: str = "binance_vip1_0.075pct_2026-08-28"

    @classmethod
    def from_rates(cls, maker: Decimal, taker: Decimal, *, note: str) -> "FeeSchedule":
        return cls(
            maker_bps=(maker * Decimal("10000")).quantize(EIGHTPLACES),
            taker_bps=(taker * Decimal("10000")).quantize(EIGHTPLACES),
            snapshot_note=note,
        )

    def fee_eur(self, notional_eur: Decimal, *, taker: bool = True) -> Decimal:
        bps = self.taker_bps if taker else self.maker_bps
        return (notional_eur * bps / Decimal("10000")).quantize(TWOPLACES)


@dataclass
class SlippageSettings:
    mode: str = "fixed"  # fixed | dynamic
    fallback_percent: Decimal = Decimal("0.001")
    depth_levels: int = 10

    def apply(
        self,
        *,
        mid_price: Decimal,
        qty: Decimal,
        side: str,
        orderbook: Optional[OrderBook] = None,
    ) -> tuple[Decimal, Decimal, str]:
        px, slip, used = execution_price(
            mid=float(mid_price),
            order_size=float(qty),
            side=side,
            mode=self.mode,
            orderbook=orderbook,
            fallback_percent=float(self.fallback_percent),
            orderbook_depth_levels=self.depth_levels,
        )
        return (
            _d(px),
            Decimal(str(slip)).quantize(EIGHTPLACES),
            used,
        )


@dataclass
class PaperLedger:
    starting_balance_eur: Decimal = Decimal("1000.00")
    fee_schedule: FeeSchedule = field(default_factory=FeeSchedule)
    slippage: Optional[SlippageSettings] = None
    fees_paid_eur: Decimal = field(default_factory=lambda: Decimal("0"))
    slippage_cost_eur: Decimal = field(default_factory=lambda: Decimal("0"))
    cash_eur: Decimal = field(init=False)
    position_qty: Decimal = field(default_factory=lambda: Decimal("0"))
    avg_entry: Decimal = field(default_factory=lambda: Decimal("0"))
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
        equity = self.mark_equity(mark_price)
        return (
            self.order_send_count == 0
            and self.cash_eur >= 0
            and equity >= 0
            and self.fees_paid_eur >= 0
        )

    def _resolve_price(
        self,
        qty: Decimal,
        mid: Decimal,
        side: str,
        orderbook: Optional[OrderBook],
    ) -> tuple[Decimal, Dict[str, Any]]:
        meta: Dict[str, Any] = {"mid_price": str(mid), "slippage_mode": "none"}
        if self.slippage is None:
            return mid, meta
        exec_px, slip_pct, used = self.slippage.apply(
            mid_price=mid,
            qty=qty,
            side=side,
            orderbook=orderbook,
        )
        slip_cost = (abs(exec_px - mid) * qty).quantize(TWOPLACES)
        meta.update(
            {
                "execution_price": str(exec_px),
                "slippage_percent": str(slip_pct),
                "slippage_cost_eur": str(slip_cost),
                "slippage_mode": used,
            }
        )
        return exec_px, meta

    def sim_buy(
        self,
        qty: Decimal,
        price: Decimal,
        *,
        signal_id: str,
        orderbook: Optional[OrderBook] = None,
    ) -> Optional[Dict[str, Any]]:
        if self.order_send_count != 0:
            raise RuntimeError("order_send_count must stay 0")
        q = _d(qty)
        mid = _d(price)
        if q <= 0 or mid <= 0:
            return None
        p, slip_meta = self._resolve_price(q, mid, "buy", orderbook)
        notional = (q * p).quantize(TWOPLACES)
        fee = self.fee_schedule.fee_eur(notional, taker=True)
        cost = notional + fee
        if cost > self.cash_eur:
            return None
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
        slip_cost = Decimal(str(slip_meta.get("slippage_cost_eur", "0")))
        self.slippage_cost_eur = (self.slippage_cost_eur + slip_cost).quantize(TWOPLACES)
        fill = {
            "action": "SIM_FILL",
            "side": "BUY",
            "qty": str(q),
            "price": str(p),
            "fee_eur": str(fee),
            "signal_id": signal_id,
            "live_execution": False,
            "order_send": False,
            **slip_meta,
        }
        self.fills.append(fill)
        return fill

    def sim_sell(
        self,
        qty: Decimal,
        price: Decimal,
        *,
        signal_id: str,
        orderbook: Optional[OrderBook] = None,
    ) -> Optional[Dict[str, Any]]:
        if self.order_send_count != 0:
            raise RuntimeError("order_send_count must stay 0")
        q = _d(qty)
        mid = _d(price)
        if q <= 0 or mid <= 0 or q > self.position_qty:
            return None
        p, slip_meta = self._resolve_price(q, mid, "sell", orderbook)
        notional = (q * p).quantize(TWOPLACES)
        fee = self.fee_schedule.fee_eur(notional, taker=True)
        proceeds = notional - fee
        pnl = ((p - self.avg_entry) * q - fee).quantize(TWOPLACES)
        self.position_qty = (self.position_qty - q).quantize(TWOPLACES)
        if self.position_qty == 0:
            self.avg_entry = Decimal("0")
        self.cash_eur = (self.cash_eur + proceeds).quantize(TWOPLACES)
        self.fees_paid_eur = (self.fees_paid_eur + fee).quantize(TWOPLACES)
        slip_cost = Decimal(str(slip_meta.get("slippage_cost_eur", "0")))
        self.slippage_cost_eur = (self.slippage_cost_eur + slip_cost).quantize(TWOPLACES)
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
            **slip_meta,
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
            "slippage_cost_eur": str(self.slippage_cost_eur),
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


def ledger_from_config(settings: Any) -> PaperLedger:
    """Build ledger from PaperTradingSettings."""
    from prototypes.raas_paper_trading.config_loader import PaperTradingSettings

    if not isinstance(settings, PaperTradingSettings):
        raise TypeError("expected PaperTradingSettings")
    fees = FeeSchedule.from_rates(
        settings.maker_rate,
        settings.taker_rate,
        note=settings.exchange_name,
    )
    slip = SlippageSettings(
        mode=settings.slippage_mode,
        fallback_percent=settings.fallback_percent,
        depth_levels=settings.orderbook_depth_levels,
    )
    return PaperLedger(
        starting_balance_eur=settings.initial_balance_eur,
        fee_schedule=fees,
        slippage=slip,
    )
