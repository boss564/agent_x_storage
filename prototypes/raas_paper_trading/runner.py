"""Paper trading runner — signals + sim fills + WORM; never order send."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence
from uuid import uuid4

from prototypes.raas_paper_trading.envelope_score import (
    EnvelopeHitStats,
    score_envelope_hits,
)
from prototypes.raas_paper_trading.feed import PaperTick
from prototypes.raas_paper_trading.ledger import PaperLedger
from prototypes.raas_paper_trading.worm_log import PaperWormLog

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"


class PaperTradingRunner:
    """Single-tenant paper loop. Primary output = envelope hit stats."""

    def __init__(
        self,
        *,
        tenant_id: str,
        run_id: Optional[str] = None,
        ledger: Optional[PaperLedger] = None,
        worm: Optional[PaperWormLog] = None,
        break_price_below: Optional[float] = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.run_id = run_id or str(uuid4())
        self.ledger = ledger or PaperLedger()
        self.worm = worm or PaperWormLog(tenant_id, self.run_id)
        # Simple envelope condition for smoke: "crash" if price < threshold
        self.break_price_below = break_price_below
        self.predictions: List[Dict[str, Any]] = []
        self.observations: List[Dict[str, Any]] = []
        self._tick_n = 0

    def _predict_break(self, tick: PaperTick) -> bool:
        if self.break_price_below is None:
            return False
        return float(tick.price) < float(self.break_price_below)

    def on_tick(self, tick: PaperTick) -> Dict[str, Any]:
        self._tick_n += 1
        signal_id = f"sig-{self._tick_n}"
        cid = f"price_floor@{self._tick_n}"
        predicted = self._predict_break(tick)
        self.predictions.append({"condition_id": cid, "break": predicted})

        self.worm.append(
            {
                "action": "SIGNAL",
                "signal_id": signal_id,
                "condition_id": cid,
                "mark_price": str(tick.price),
                "symbol": tick.symbol,
                "source": tick.source,
                "predicted_break": predicted,
                "m7_latency_ms": None,
            }
        )

        # Naive paper policy for smoke: buy small on first tick, sell if predicted break
        fill = None
        mark = Decimal(str(tick.price))
        if self._tick_n == 1 and self.ledger.position_qty == 0:
            qty = (Decimal("100") / mark).quantize(Decimal("0.0001"))
            fill = self.ledger.sim_buy(qty, mark, signal_id=signal_id)
        elif predicted and self.ledger.position_qty > 0:
            fill = self.ledger.sim_sell(self.ledger.position_qty, mark, signal_id=signal_id)

        if fill:
            snap = self.ledger.snapshot(mark)
            self.worm.append(
                {
                    **fill,
                    "cash_eur": snap["cash_eur"],
                    "equity_eur": snap["equity_eur"],
                    "qty": fill["qty"],
                    "mark_price": str(tick.price),
                }
            )
        else:
            self.worm.append(
                {
                    "action": "SIM_SKIP",
                    "signal_id": signal_id,
                    "mark_price": str(tick.price),
                    "cash_eur": self.ledger.snapshot(mark)["cash_eur"],
                    "equity_eur": self.ledger.snapshot(mark)["equity_eur"],
                }
            )

        observed = (
            float(tick.price) < float(self.break_price_below)
            if self.break_price_below is not None
            else False
        )
        self.observations.append({"condition_id": cid, "break": observed})

        if self.ledger.order_send_count != 0:
            raise RuntimeError("abort: order_send_count > 0")

        return {"signal_id": signal_id, "predicted_break": predicted, "fill": fill}

    def run(self, ticks: Iterable[PaperTick]) -> Dict[str, Any]:
        last_price = Decimal("0")
        for tick in ticks:
            last_price = Decimal(str(tick.price))
            self.on_tick(tick)
            self.worm.append({"action": "HEARTBEAT", "mark_price": str(tick.price)})

        hits = score_envelope_hits(self.predictions, self.observations)
        snap = self.ledger.snapshot(last_price if last_price > 0 else Decimal("1"))
        diag_pf = self.ledger.diagnostic_profit_factor()
        summary = {
            "verdict_hint": "PAPER_RUN_COMPLETE",
            "tenant_id": self.tenant_id,
            "run_id": self.run_id,
            "scope": SCOPE,
            "live_execution": False,
            "order_send_count": self.ledger.order_send_count,
            "envelope_hit_rate": hits.to_dict(),
            "ledger": snap,
            "profit_factor_diagnostic": diag_pf,
            "worm_path": str(self.worm.path),
            "not_investment_advice": True,
            "primary_metric": "envelope_break_hit_rate",
        }
        self.worm.append(
            {
                "action": "SIGNAL",
                "signal_id": "aggregate",
                "aggregate": True,
                "envelope_hit_rate": hits.to_dict(),
                "profit_factor_diagnostic": diag_pf,
                "order_send_count": 0,
                "mark_price": str(last_price),
                "cash_eur": snap["cash_eur"],
                "equity_eur": snap["equity_eur"],
            }
        )
        return summary
