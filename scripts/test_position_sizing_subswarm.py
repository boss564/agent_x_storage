#!/usr/bin/env python3
"""Position sizing sub-swarm (B0–B8) — charter §4 smoke tests."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.ledger import PaperLedger
from prototypes.raas_paper_trading.position_sizing.agents import TradeStatisticAggregator
from prototypes.raas_paper_trading.position_sizing.audit_log import SizingAuditLog
from prototypes.raas_paper_trading.position_sizing.config import (
    load_gamma_map,
    position_sizing_enabled,
    resolve_gamma,
)
from prototypes.raas_paper_trading.position_sizing.integration import (
    run_sizing_if_enabled,
    should_run_sizing,
)
from prototypes.raas_paper_trading.position_sizing.orchestrator import PositionSizingOrchestrator
from prototypes.raas_paper_trading.position_sizing.types import (
    FORBIDDEN_EXPORT_KEYS,
    GATE_INSUFFICIENT_HISTORY,
    GATE_LIMIT_EXCEEDED,
    GATE_LIMIT_OK,
)


def _fail(msg: str) -> None:
    print(f"FAIL {msg}")
    raise SystemExit(1)


def _ledger_with_sells(n: int, *, win_pct: float = 0.05, loss_pct: float = -0.03) -> PaperLedger:
    led = PaperLedger(starting_balance_eur=Decimal("1000"))
    for i in range(n):
        qty = Decimal("0.01")
        buy_px = Decimal("2000") + Decimal(i)
        led.sim_buy(qty, buy_px, signal_id=f"sig-b-{i}")
        sell_px = buy_px * (Decimal("1") + Decimal(str(win_pct if i % 2 == 0 else loss_pct)))
        led.sim_sell(qty, sell_px, signal_id=f"sig-s-{i}")
    return led


def test_insufficient_history_hard_block() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        audit = Path(tmp) / "position_sizing.jsonl"
        orch = PositionSizingOrchestrator(audit_path=audit, window_size=50, min_trades=50)
        led = _ledger_with_sells(5)
        out = orch.run_cycle(ledger=led, mark_price=Decimal("2500"), symbol="ETHUSDT")
        if out["status"] != "INSUFFICIENT_HISTORY":
            _fail(f"status {out['status']}")
        if out["sizing_gate_decision"] != GATE_INSUFFICIENT_HISTORY:
            _fail(f"gate {out['sizing_gate_decision']}")
        if out.get("p") is not None or out.get("kelly_fraction_computed") is not None:
            _fail("must not emit kelly on insufficient history")
        text = audit.read_text(encoding="utf-8")
        if "advisory_position_size" in text:
            _fail("forbidden key in audit")


def test_limit_exceeded_notional() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        audit = Path(tmp) / "position_sizing.jsonl"
        orch = PositionSizingOrchestrator(
            audit_path=audit,
            gamma=1.0,
            window_size=50,
            min_trades=50,
            risk_limit_fraction=0.02,
        )
        agg = TradeStatisticAggregator(window_size=50, min_trades=50)
        for i in range(50):
            agg.add_trade(0.10 if i % 2 == 0 else -0.01)
        led = PaperLedger(starting_balance_eur=Decimal("1000"))
        out = orch.run_cycle(
            ledger=led,
            mark_price=Decimal("2500"),
            symbol="ETHUSDT",
            stats_override=agg,
        )
        if out["sizing_gate_decision"] != GATE_LIMIT_EXCEEDED:
            _fail(f"expected LIMIT_EXCEEDED got {out['sizing_gate_decision']} {out}")
        hypo = out.get("computed_hypothetical_notional_eur")
        schranke = out.get("max_notional_before_limit_breach_eur")
        if hypo is None or schranke is None or hypo <= schranke:
            _fail(f"hypo {hypo} should exceed schranke {schranke}")


def test_limit_ok_low_kelly() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        audit = Path(tmp) / "position_sizing.jsonl"
        orch = PositionSizingOrchestrator(
            audit_path=audit,
            gamma=0.01,
            window_size=50,
            min_trades=50,
            risk_limit_fraction=0.02,
        )
        agg = TradeStatisticAggregator(window_size=50, min_trades=50)
        for i in range(50):
            agg.add_trade(0.01 if i % 2 == 0 else -0.01)
        led = PaperLedger(starting_balance_eur=Decimal("1000"))
        out = orch.run_cycle(
            ledger=led,
            mark_price=Decimal("2500"),
            symbol="ETHUSDT",
            stats_override=agg,
        )
        if out["sizing_gate_decision"] != GATE_LIMIT_OK:
            _fail(f"expected LIMIT_OK got {out['sizing_gate_decision']}")


def test_audit_charter_stamps() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "position_sizing.jsonl"
        log = SizingAuditLog(path)
        row = log.append(
            {
                "cycle_id": "SIZE-TEST",
                "max_notional_before_limit_breach_eur": 20.0,
                "sizing_gate_decision": GATE_LIMIT_OK,
            }
        )
        if row.get("live_execution") is not False:
            _fail("live_execution must be false")
        if row.get("order_send") is not False:
            _fail("order_send must be false")
        if row.get("not_investment_advice") is not True:
            _fail("not_investment_advice must be true")
        if row.get("diagnostic_only") is not True:
            _fail("diagnostic_only must be true")
        try:
            log.append({"advisory_position_size": 1.0, "cycle_id": "X"})
            _fail("forbidden key must raise")
        except RuntimeError:
            pass


def test_feature_flag_default_off() -> None:
    os.environ.pop("POSITION_SIZING_ENABLED", None)
    if position_sizing_enabled():
        _fail("default must be disabled")
    if run_sizing_if_enabled(symbol="ETHUSDT", mark_price=2500.0) is not None:
        _fail("integration must no-op when disabled")


def test_envelope_no_forbidden_keys() -> None:
    if FORBIDDEN_EXPORT_KEYS & {"max_notional_before_limit_breach_eur", "kelly_fraction_computed"}:
        _fail("allowed keys misclassified")


def test_resolve_gamma_iid_safe_mode() -> None:
    gamma, source = resolve_gamma("DRIFT_IID_UNRELIABLE")
    if gamma != 0.0 or source != "iid_safe_mode":
        _fail(f"IID must force gamma=0 got {gamma} {source}")


def test_resolve_gamma_regime_map() -> None:
    gamma, source = resolve_gamma("HIGH_VOL_TREND")
    if gamma != 0.40 or source != "regime_map":
        _fail(f"HIGH_VOL_TREND gamma {gamma} {source}")


def test_gamma_map_env_override() -> None:
    os.environ["POSITION_SIZING_GAMMA_MAP"] = '{"STABLE": 0.99}'
    try:
        gmap = load_gamma_map()
        if gmap["STABLE"] != 0.99:
            _fail("env override STABLE")
        if gmap["HIGH_VOL_TREND"] != 0.40:
            _fail("defaults must remain for non-overridden regimes")
    finally:
        os.environ.pop("POSITION_SIZING_GAMMA_MAP", None)


def test_trigger_skip_flag_zero() -> None:
    os.environ["POSITION_SIZING_ENABLED"] = "true"
    try:
        if should_run_sizing(regime_flag=0):
            _fail("flag 0 must not trigger")
        out = run_sizing_if_enabled(
            symbol="ETHUSDT",
            mark_price=2500.0,
            classified_regime="STABLE",
            regime_flag=0,
        )
        if out is None or not out.get("skipped"):
            _fail(f"expected skipped dict got {out}")
        if out.get("reason") != "regime_flag_below_threshold":
            _fail(f"reason {out.get('reason')}")
    finally:
        os.environ.pop("POSITION_SIZING_ENABLED", None)


def test_orchestrator_regime_gamma_in_row() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        audit = Path(tmp) / "position_sizing.jsonl"
        orch = PositionSizingOrchestrator(audit_path=audit, window_size=50, min_trades=50)
        led = _ledger_with_sells(5)
        out = orch.run_cycle(
            ledger=led,
            mark_price=Decimal("2500"),
            symbol="ETHUSDT",
            classified_regime="DRIFT_IID_UNRELIABLE",
            regime_flag=1,
            swarm_cycle_id="SWARM-TEST-1",
        )
        if out.get("gamma") != 0.0:
            _fail(f"IID gamma {out.get('gamma')}")
        if out.get("gamma_source") != "iid_safe_mode":
            _fail(f"gamma_source {out.get('gamma_source')}")
        if out.get("classified_regime") != "DRIFT_IID_UNRELIABLE":
            _fail("classified_regime missing")
        if out.get("linked_swarm_cycle_id") != "SWARM-TEST-1":
            _fail("linked_swarm_cycle_id missing")
        row = json.loads(audit.read_text(encoding="utf-8").strip().split("\n")[0])
        if row.get("gamma_source") != "iid_safe_mode":
            _fail("audit row missing gamma_source")


def main() -> int:
    test_insufficient_history_hard_block()
    test_limit_exceeded_notional()
    test_limit_ok_low_kelly()
    test_audit_charter_stamps()
    test_feature_flag_default_off()
    test_envelope_no_forbidden_keys()
    test_resolve_gamma_iid_safe_mode()
    test_resolve_gamma_regime_map()
    test_gamma_map_env_override()
    test_trigger_skip_flag_zero()
    test_orchestrator_regime_gamma_in_row()
    print("POSITION_SIZING_SUBSWARM_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
