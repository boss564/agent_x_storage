#!/usr/bin/env python3
"""Paper-trading smoke — feed · ledger · WORM · envelope hit-rate primary.

Map: docs/PAPER_TRADING_SETUP_v0.md
Usage:
  PYTHONPATH=. python3 scripts/test_raas_paper_trading.py
  make raas-paper-trading-smoke
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.envelope_score import score_envelope_hits  # noqa: E402
from prototypes.raas_paper_trading.feed import (  # noqa: E402
    PaperTick,
    ReplayFeed,
    assert_no_order_urls,
)
from prototypes.raas_paper_trading.ledger import PaperLedger  # noqa: E402
from prototypes.raas_paper_trading.runner import PaperTradingRunner  # noqa: E402
from prototypes.raas_paper_trading.worm_log import PaperWormLog  # noqa: E402


def main() -> int:
    print("RaaS paper-trading smoke")
    print("=" * 60)
    failed = 0
    tmp = tempfile.mkdtemp(prefix="paper_")
    os.environ["RAAS_DATA_ROOT"] = str(Path(tmp) / "raas")

    try:
        # --- Feed guard ---
        try:
            assert_no_order_urls("https://api.binance.com/api/v3/order")
            print("  FAIL  order URL should be refused")
            failed += 1
        except RuntimeError:
            print("  PASS  PAPER_FEED order URL refused")

        ticks = [
            PaperTick("ETHUSDT", "2026-08-27T10:00:00Z", 2000.0, "replay"),
            PaperTick("ETHUSDT", "2026-08-27T10:01:00Z", 1980.0, "replay"),
            PaperTick("ETHUSDT", "2026-08-27T10:02:00Z", 1500.0, "replay"),  # break
            PaperTick("ETHUSDT", "2026-08-27T10:03:00Z", 1490.0, "replay"),
        ]
        feed = ReplayFeed(ticks)
        if len(feed) != 4:
            print("  FAIL  replay len")
            failed += 1
        else:
            print("  PASS  PAPER_FEED replay")

        # --- Ledger ---
        led = PaperLedger(starting_balance_eur=Decimal("1000.00"))
        buy = led.sim_buy(Decimal("0.1"), Decimal("2000"), signal_id="t0")
        if not buy or buy.get("order_send") is not False:
            print("  FAIL  sim_buy")
            failed += 1
        else:
            print("  PASS  PAPER_LEDGER sim_buy + fees")
        if led.fees_paid_eur <= 0:
            print("  FAIL  fees must be > 0")
            failed += 1
        else:
            print(f"  PASS  fees_paid={led.fees_paid_eur}")
        if led.order_send_count != 0:
            print("  FAIL  order_send_count")
            failed += 1
        else:
            print("  PASS  order_send_count=0")

        pf = led.diagnostic_profit_factor()
        if pf.get("diagnostic_only") is not True:
            print("  FAIL  profit factor must be diagnostic_only")
            failed += 1
        else:
            print("  PASS  profit_factor diagnostic_only")

        # --- Envelope primary metric ---
        hits = score_envelope_hits(
            [
                {"condition_id": "a", "break": True},
                {"condition_id": "b", "break": True},
                {"condition_id": "c", "break": False},
            ],
            [
                {"condition_id": "a", "break": True},
                {"condition_id": "b", "break": False},
                {"condition_id": "c", "break": True},
            ],
        )
        # TP=a, FP=b, FN=c → precision 0.5 recall 0.5
        if abs(hits.precision - 0.5) > 1e-9 or abs(hits.recall - 0.5) > 1e-9:
            print(f"  FAIL  hit stats P={hits.precision} R={hits.recall}")
            failed += 1
        elif hits.to_dict().get("role") != "primary":
            print("  FAIL  envelope metric role")
            failed += 1
        else:
            print("  PASS  envelope hit-rate primary metric")

        # --- Runner + WORM ---
        runner = PaperTradingRunner(
            tenant_id="paper_demo",
            run_id="run-smoke",
            break_price_below=1600.0,
        )
        summary = runner.run(feed)
        if summary["order_send_count"] != 0:
            print("  FAIL  runner order_send")
            failed += 1
        else:
            print("  PASS  runner order_send_count=0")
        if summary["primary_metric"] != "envelope_break_hit_rate":
            print("  FAIL  primary_metric field")
            failed += 1
        else:
            print("  PASS  primary_metric=envelope_break_hit_rate")
        if summary["profit_factor_diagnostic"].get("diagnostic_only") is not True:
            print("  FAIL  summary PF not diagnostic")
            failed += 1
        else:
            print("  PASS  summary PF diagnostic_only")

        worm_path = Path(summary["worm_path"])
        lines = worm_path.read_text(encoding="utf-8").strip().splitlines()
        if len(lines) < 4:
            print("  FAIL  WORM too short")
            failed += 1
        else:
            print(f"  PASS  PAPER_WORM lines={len(lines)}")
        bad = False
        prev = "0" * 64
        for ln in lines:
            row = json.loads(ln)
            if row.get("live_execution") is not False or row.get("action") == "ORDER_SENT":
                bad = True
            if row.get("prev_hash") != prev:
                bad = True
            prev = row["hash"]
        if bad:
            print("  FAIL  WORM chain / live_execution")
            failed += 1
        else:
            print("  PASS  WORM hash chain + live_execution=false")

        # WORM rejects ORDER_SENT
        w = PaperWormLog("paper_demo", "deny-run")
        denied = False
        try:
            w.append({"action": "ORDER_SENT", "live_execution": False})
        except RuntimeError:
            denied = True
        if not denied:
            print("  FAIL  ORDER_SENT should raise")
            failed += 1
        else:
            print("  PASS  ORDER_SENT rejected")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    verdict = "RAAS_PAPER_TRADING_PASS" if failed == 0 else "RAAS_PAPER_TRADING_FAIL"
    print("=" * 60)
    print(f"VERDICT: {verdict}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
