#!/usr/bin/env python3
"""P3 wiring smoke: fixed vs dynamic slippage on synthetic identical fills.

Not an empirical slippage estimate — direction is set by fallback_percent vs book params.
First informative measurement = WORM replay with fixed (side, qty, mark_price) tuples.
See docs/RaaS_PAPER_FEES_SLIPPAGE_v0.md
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.config_loader import (  # noqa: E402
    PaperTradingSettings,
    config_manifest_hash,
)
from prototypes.raas_paper_trading.ledger import (  # noqa: E402
    FeeSchedule,
    PaperLedger,
    SlippageSettings,
    ledger_from_config,
)
from prototypes.raas_paper_trading.slippage import synthetic_orderbook  # noqa: E402

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"


def _run_round_trip(
    *,
    label: str,
    slip_mode: str,
    mid: float,
    qty: Decimal,
    book: Dict[str, Any],
    settings: PaperTradingSettings,
) -> Dict[str, Any]:
    fees = FeeSchedule.from_rates(
        settings.maker_rate,
        settings.taker_rate,
        note=settings.exchange_name,
    )
    led = PaperLedger(
        starting_balance_eur=settings.initial_balance_eur,
        fee_schedule=fees,
        slippage=SlippageSettings(
            mode=slip_mode,
            fallback_percent=settings.fallback_percent,
            depth_levels=settings.orderbook_depth_levels,
        ),
    )
    mid_d = Decimal(str(mid))
    buy = led.sim_buy(qty, mid_d, signal_id=f"{label}-buy", orderbook=book)
    sell = led.sim_sell(qty, mid_d, signal_id=f"{label}-sell", orderbook=book)
    snap = led.snapshot(mid_d)
    buy_slip = buy.get("slippage_percent") if buy else None
    sell_slip = sell.get("slippage_percent") if sell else None
    return {
        "mode": label,
        "slippage_mode": slip_mode,
        "buy_slippage_percent": buy_slip,
        "sell_slippage_percent": sell_slip,
        "fees_paid_eur": snap["fees_paid_eur"],
        "slippage_cost_eur": snap["slippage_cost_eur"],
        "equity_eur": snap["equity_eur"],
        "realized_pnl_eur": snap["realized_pnl_eur"],
    }


def compare(*, sizes: List[float], mid: float = 2500.0) -> Dict[str, Any]:
    settings = PaperTradingSettings.from_file()
    book = synthetic_orderbook(
        mid,
        spread_bps=5.0,
        depth_levels=settings.orderbook_depth_levels,
        qty_per_level=0.05,
    )
    rows: List[Dict[str, Any]] = []
    for size in sizes:
        qty = Decimal(str(size))
        fixed = _run_round_trip(
            label=f"fixed-{size}",
            slip_mode="fixed",
            mid=mid,
            qty=qty,
            book=book,
            settings=settings,
        )
        dynamic = _run_round_trip(
            label=f"dynamic-{size}",
            slip_mode="dynamic",
            mid=mid,
            qty=qty,
            book=book,
            settings=settings,
        )
        eq_f = Decimal(fixed["equity_eur"])
        eq_d = Decimal(dynamic["equity_eur"])
        slip_f = Decimal(fixed["slippage_cost_eur"])
        slip_d = Decimal(dynamic["slippage_cost_eur"])
        rows.append(
            {
                "order_size": size,
                "fixed": fixed,
                "dynamic": dynamic,
                "equity_delta_eur": str((eq_d - eq_f).quantize(Decimal("0.01"))),
                "slippage_cost_delta_eur": str((slip_d - slip_f).quantize(Decimal("0.01"))),
            }
        )
    return {
        "schema": "raas_paper_slippage_compare_v0",
        "scope": SCOPE,
        "live_execution": False,
        "not_investment_advice": True,
        "config_hash": config_manifest_hash(),
        "fallback_percent": str(settings.fallback_percent),
        "fee_taker": str(settings.taker_rate),
        "rows": rows,
        "note": (
            "Screen only — direction determined by fallback_percent vs synthetic book spread; "
            "not an empirical estimate. First informative measurement = WORM replay with fixed "
            "(side, qty, mark_price) tuples. Do not cite equity_delta as slippage tendency."
        ),
    }


def main() -> int:
    print("RaaS Paper Slippage Compare (fixed vs dynamic)")
    print("=" * 60)
    sizes = [0.01, 0.05, 0.1, 0.2, 0.35]  # fit 1_000 EUR @ ~2_500 mid
    result = compare(sizes=sizes)
    print(f"config_hash={result['config_hash'][:16]}…")
    for row in result["rows"]:
        print(
            f"size={row['order_size']}: "
            f"slipΔ={row['slippage_cost_delta_eur']}€ "
            f"equityΔ={row['equity_delta_eur']}€ "
            f"fixed_slip={row['fixed']['slippage_cost_eur']} "
            f"dyn_slip={row['dynamic']['slippage_cost_eur']}"
        )
    out = _ROOT / "exports" / "reports" / "paper_slippage_compare_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"report: {out}")
    print("=" * 60)
    print("VERDICT: RAAS_PAPER_SLIPPAGE_COMPARE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
