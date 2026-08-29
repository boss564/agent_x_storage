"""Paper trading runner — signals + sim fills + WORM; never order send."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

from prototypes.raas_paper_trading.depth_snapshot import DepthFetcher, DepthSnapshot
from prototypes.raas_paper_trading.envelope_score import score_envelope_hits
from prototypes.raas_paper_trading.feed import PaperTick, orderbook_to_snapshot
from prototypes.raas_paper_trading.ledger import PaperLedger
from prototypes.raas_paper_trading.paper_exit import (
    ExitAction,
    PaperExitController,
    enrich_buy_worm_fields,
    enrich_sell_worm_fields,
    exit_config_from_env,
    human_force_exit_requested,
)
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
        exit_mode: Optional[str] = None,
        exit_controller: Optional[PaperExitController] = None,
        hold_seconds: Optional[int] = None,
        gap_dt_s: Optional[float] = None,
        max_wait_s: Optional[float] = None,
        position_state_path: Optional[Path] = None,
        edges_path: Optional[Path] = None,
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
        self._last_exit_decision: Optional[Dict[str, Any]] = None

        mode = (exit_mode or "").strip().lower()
        self.exit_mode = mode
        self.exit: Optional[PaperExitController] = exit_controller
        if self.exit is None and mode == "time_hold":
            cfg = exit_config_from_env()
            self.exit = PaperExitController.from_paths(
                state_path=Path(position_state_path or cfg["state_path"]),
                edges_path=Path(edges_path or cfg["edges_path"]),
                hold_seconds=int(hold_seconds if hold_seconds is not None else cfg["hold_seconds"]),
                gap_dt_s=float(gap_dt_s if gap_dt_s is not None else cfg["gap_dt_s"]),
                max_wait_s=float(max_wait_s if max_wait_s is not None else cfg["max_wait_s"]),
            )
        if self.exit is not None:
            self.exit.seed_ledger_if_needed(
                self.ledger, shadow_notional_eur=self.shadow_notional_eur
            )

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

    def _append_fill_worm(
        self,
        fill: Dict[str, Any],
        *,
        tick: PaperTick,
        fill_ts: str,
        mark: Decimal,
        depth: Optional[DepthSnapshot],
    ) -> Dict[str, Any]:
        snap = self.ledger.snapshot(mark)
        orderbook = depth.orderbook if depth else None
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
        return self.worm.append(worm_row)

    def _on_tick_time_hold(self, tick: PaperTick) -> Dict[str, Any]:
        assert self.exit is not None
        self._tick_n += 1
        signal_id = f"sig-{self._tick_n}"
        cid = f"price_floor@{self._tick_n}"
        predicted = self._predict_break(tick)
        self.predictions.append({"condition_id": cid, "break": predicted})
        fill_ts = _fill_ts(tick)
        mark = Decimal(str(tick.price))
        depth = self._resolve_depth(tick)
        orderbook = depth.orderbook if depth else None

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
                "exit_state": self.exit.state,
            }
        )

        decision = self.exit.decide(
            tick_ts=fill_ts,
            mark_price=float(tick.price),
            signal_id=signal_id,
            symbol=tick.symbol,
            position_open=self.ledger.position_qty > 0,
            force_exit=human_force_exit_requested(),
        )
        self._last_exit_decision = {
            "action": decision.action.value,
            "log_code": decision.log_code,
            "exit_reason": decision.exit_reason,
            "state": decision.state,
            "hold_elapsed_s": decision.hold_elapsed_s,
        }

        # HOLD → EXIT_PENDING transition (I3)
        if decision.log_code == "HOLD_EXPIRED_PENDING":
            self.exit.apply_hold_expired_pending(since_ts=fill_ts)
            decision = self.exit.decide(
                tick_ts=fill_ts,
                mark_price=float(tick.price),
                signal_id=signal_id,
                symbol=tick.symbol,
                position_open=self.ledger.position_qty > 0,
                force_exit=human_force_exit_requested(),
            )
            self._last_exit_decision = {
                "action": decision.action.value,
                "log_code": decision.log_code,
                "exit_reason": decision.exit_reason,
                "state": decision.state,
                "hold_elapsed_s": decision.hold_elapsed_s,
            }

        if decision.log_code == "EXIT_PENDING_FLAT":
            self.exit.apply_exit_to_idle()

        fill = None
        if decision.action == ExitAction.ENTER and self.ledger.position_qty == 0:
            qty = (self.shadow_notional_eur / mark).quantize(Decimal("0.0001"))
            fill = self.ledger.sim_buy(
                qty, mark, signal_id=signal_id, orderbook=orderbook
            )
            if fill:
                fill = enrich_buy_worm_fields(fill, entry_tick_ts=fill_ts)
                worm_row = self._append_fill_worm(
                    fill, tick=tick, fill_ts=fill_ts, mark=mark, depth=depth
                )
                self.exit.apply_enter(
                    entry_tick_ts=fill_ts,
                    entry_price=str(fill["price"]),
                    entry_signal_id=signal_id,
                    symbol=tick.symbol,
                )
                fill = worm_row
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
                        "reason": "insufficient_cash",
                    }
                )
        elif decision.action == ExitAction.EXIT and self.ledger.position_qty > 0:
            entry_ts = self.exit.store.entry_tick_ts or fill_ts
            entry_sig = self.exit.store.entry_signal_id or signal_id
            entry_px = self.exit.store.entry_price or str(self.ledger.avg_entry)
            reason = decision.exit_reason or "hold_expired"
            fill = self.ledger.sim_sell(
                self.ledger.position_qty, mark, signal_id=signal_id, orderbook=orderbook
            )
            if fill:
                fill = enrich_sell_worm_fields(
                    fill,
                    entry_tick_ts=entry_ts,
                    exit_tick_ts=fill_ts,
                    hold_seconds_target=self.exit.hold_seconds,
                    exit_reason=reason,
                )
                worm_row = self._append_fill_worm(
                    fill, tick=tick, fill_ts=fill_ts, mark=mark, depth=depth
                )
                self.exit.record_edge(
                    entry_tick_id=entry_sig,
                    exit_tick_id=signal_id,
                    entry_price=str(entry_px),
                    exit_price=str(fill["price"]),
                    pnl_eur=str(fill.get("realized_pnl_eur", "0")),
                    hold_seconds_actual=float(fill["hold_seconds_actual"]),
                    exit_reason=reason,
                    worm_sell_hash=str(worm_row.get("hash") or ""),
                    entry_tick_ts=entry_ts,
                    exit_tick_ts=fill_ts,
                )
                self.exit.apply_exit_to_idle()
                fill = worm_row
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
                        "reason": "sell_failed",
                    }
                )
        else:
            skip: Dict[str, Any] = {
                "action": "SIM_SKIP",
                "signal_id": signal_id,
                "ts": fill_ts,
                "mark_price": str(tick.price),
                "symbol": tick.symbol,
                "cash_eur": self.ledger.snapshot(mark)["cash_eur"],
                "equity_eur": self.ledger.snapshot(mark)["equity_eur"],
                "exit_state": self.exit.state,
            }
            if decision.log_code:
                skip["skip_reason"] = decision.log_code
            if decision.action == ExitAction.ALARM:
                skip["alarm"] = decision.log_code
            self.worm.append(skip)

        self.exit.note_tick_ts(fill_ts)

        observed = (
            float(tick.price) < float(self.break_price_below)
            if self.break_price_below is not None
            else False
        )
        self.observations.append({"condition_id": cid, "break": observed})

        if self.ledger.order_send_count != 0:
            raise RuntimeError("abort: order_send_count > 0")

        return {
            "signal_id": signal_id,
            "predicted_break": predicted,
            "fill": fill,
            "exit_decision": self._last_exit_decision,
        }

    def on_tick(self, tick: PaperTick) -> Dict[str, Any]:
        if self.exit_mode == "time_hold" and self.exit is not None:
            return self._on_tick_time_hold(tick)

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
            self._append_fill_worm(
                fill, tick=tick, fill_ts=fill_ts, mark=mark, depth=depth
            )
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
        if self.exit is not None:
            summary["exit_mode"] = self.exit_mode
            summary["exit_state"] = self.exit.state
            summary["exit_alarms"] = self.exit.alarms
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
