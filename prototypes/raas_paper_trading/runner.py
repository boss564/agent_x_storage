"""Paper trading runner — signals + sim fills + WORM; never order send."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

from prototypes.raas_paper_trading.depth_snapshot import DepthFetcher, DepthSnapshot
from prototypes.raas_paper_trading.envelope_score import score_envelope_hits
from prototypes.raas_paper_trading.feed import PaperTick, orderbook_to_snapshot
from prototypes.raas_paper_trading.ledger import PaperLedger
from prototypes.raas_paper_trading.worm_log import PaperWormLog

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"


def _fill_ts(tick: PaperTick) -> str:
    return tick.ts or datetime.now(timezone.utc).isoformat()


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
        shadow_notional_eur: Decimal = Decimal("100"),
        attach_orderbook: bool = True,
        depth_fetcher: Optional[DepthFetcher] = None,
        depth_source: str = "shadow",
        volatility_profile: Optional[str] = None,
        pair_manifest_hash: Optional[str] = None,
        config_hash: Optional[str] = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.run_id = run_id or str(uuid4())
        self.ledger = ledger or PaperLedger()
        self.worm = worm or PaperWormLog(tenant_id, self.run_id)
        self.break_price_below = break_price_below
        self.shadow_notional_eur = shadow_notional_eur
        self.attach_orderbook = attach_orderbook
        self.depth_fetcher = depth_fetcher
        self.depth_source = depth_source
        self.volatility_profile = volatility_profile
        self.pair_manifest_hash = pair_manifest_hash
        self.config_hash = config_hash
        self.predictions: List[Dict[str, Any]] = []
        self.observations: List[Dict[str, Any]] = []
        self._tick_n = 0

    def _predict_break(self, tick: PaperTick) -> bool:
        if self.break_price_below is None:
            return False
        return float(tick.price) < float(self.break_price_below)

    def _resolve_depth(self, tick: PaperTick) -> Optional[DepthSnapshot]:
        if not self.attach_orderbook or self.depth_fetcher is None:
            return None
        result = self.depth_fetcher(tick.symbol, float(tick.price), _fill_ts(tick))
        if result.source == "shadow" and self.depth_source:
            return DepthSnapshot(
                orderbook=result.orderbook,
                snapshot_ts=result.snapshot_ts,
                source=self.depth_source,
                snapshot_age_s=result.snapshot_age_s,
                depth_snapshot_hash=result.depth_snapshot_hash,
            )
        return result

    def on_tick(self, tick: PaperTick) -> Dict[str, Any]:
        self._tick_n += 1
        signal_id = f"sig-{self._tick_n}"
        cid = f"price_floor@{self._tick_n}"
        predicted = self._predict_break(tick)
        self.predictions.append({"condition_id": cid, "break": predicted})
        fill_ts = _fill_ts(tick)

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
                "ts": fill_ts,
            }
        )

        fill = None
        mark = Decimal(str(tick.price))
        depth = self._resolve_depth(tick)
        orderbook = depth.orderbook if depth else None

        if self._tick_n == 1 and self.ledger.position_qty == 0:
            qty = (self.shadow_notional_eur / mark).quantize(Decimal("0.0001"))
            fill = self.ledger.sim_buy(
                qty, mark, signal_id=signal_id, orderbook=orderbook
            )
        elif predicted and self.ledger.position_qty > 0:
            fill = self.ledger.sim_sell(
                self.ledger.position_qty, mark, signal_id=signal_id, orderbook=orderbook
            )

        if fill:
            snap = self.ledger.snapshot(mark)
            worm_row: Dict[str, Any] = {
                **fill,
                "ts": fill_ts,
                "symbol": tick.symbol,
                "cash_eur": snap["cash_eur"],
                "equity_eur": snap["equity_eur"],
                "qty": fill["qty"],
                "mark_price": str(tick.price),
            }
            if self.volatility_profile:
                worm_row["volatility_profile"] = self.volatility_profile
            if self.pair_manifest_hash:
                worm_row["pair_manifest_hash"] = self.pair_manifest_hash
            if self.config_hash:
                worm_row["config_hash"] = self.config_hash
            if depth is not None:
                worm_row["orderbook_snapshot"] = orderbook_to_snapshot(depth.orderbook)
                worm_row["depth_source"] = depth.source
                worm_row["snapshot_ts"] = depth.snapshot_ts
                if depth.snapshot_age_s is not None:
                    worm_row["snapshot_age_s"] = round(float(depth.snapshot_age_s), 3)
                if depth.depth_snapshot_hash:
                    worm_row["depth_snapshot_hash"] = depth.depth_snapshot_hash
            self.worm.append(worm_row)
        else:
            self.worm.append(
                {
                    "action": "SIM_SKIP",
                    "signal_id": signal_id,
                    "ts": fill_ts,
                    "mark_price": str(tick.price),
                    "symbol": tick.symbol,
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
