#!/usr/bin/env python3
"""RaaS paper-trading dry-run — ETH/USDC · BTC/USDC · D1–D4 · WORM audit.

Map: docs/PAPER_TRADING_SETUP_v0.md

- live_execution=false (strict, never order send)
- DSuiteEnforcer D1–D4 on every audit record
- 5 simulated trade runs → logs/worm/paper_trading_audit.jsonl

Usage (repo root):
  python3 scripts/test_raas_paper_trading.py
  make raas-paper-trading-smoke
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.envelope_score import score_envelope_hits  # noqa: E402
from prototypes.raas_paper_trading.feed import (  # noqa: E402
    PaperTick,
    ReplayFeed,
    assert_no_order_urls,
)
from prototypes.raas_paper_trading.ledger import PaperLedger, ledger_from_config  # noqa: E402
from prototypes.raas_paper_trading.runner import PaperTradingRunner  # noqa: E402
from prototypes.raas_paper_trading.worm_log import PaperWormLog  # noqa: E402
from services.fail_closed_gate.d_suite_enforcer import (  # noqa: E402
    DSuiteEnforcer,
    DSuiteViolation,
    EnforcerContext,
    WormAnchorStore,
)

AUDIT_PATH = _ROOT / "logs" / "worm" / "paper_trading_audit.jsonl"
MARKETS = ("ETHUSDC", "BTCUSDC")
N_RUNS = 5
SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _market_ticks(symbol: str, *, base: float, run_idx: int) -> List[PaperTick]:
    """Deterministic replay ticks (dry-run) — no live order path."""
    # Slight variation per run; mid-series dip triggers optional break floor
    prices = [
        base,
        base * (0.99 - 0.002 * run_idx),
        base * (0.72 if run_idx % 2 == 0 else 0.98),
        base * 0.71 if run_idx % 2 == 0 else base * 0.97,
        base * 0.95,
    ]
    out: List[PaperTick] = []
    for i, px in enumerate(prices):
        out.append(
            PaperTick(
                symbol=symbol,
                ts=f"2026-08-27T{10 + run_idx:02d}:{i:02d}:00Z",
                price=round(float(px), 4),
                source="replay",
            )
        )
    return out


def _append_audit_line(
    path: Path,
    record: Dict[str, Any],
    *,
    prev_hash: str,
) -> str:
    """D4-style SHA-256 hash chain for the shared audit JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        **record,
        "prev_hash": prev_hash,
        "live_execution": False,
        "not_investment_advice": True,
        "scope": SCOPE,
        "order_send": False,
    }
    material = json.dumps(row, sort_keys=True, default=str)
    digest = hashlib.sha256((prev_hash + material).encode("utf-8")).hexdigest()
    row["hash"] = digest
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")
    return digest


def _enforce_paper_record(
    enforcer: DSuiteEnforcer,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Shell/evaluate path — D1 stamps advice flag; D3/D4 quarantine; D2 N/A (not Red)."""
    return enforcer.enforce_all(
        EnforcerContext(
            caller_role="UNTRUSTED_SHELL",
            target_path="/api/v1/raas/evaluate",
            payload=payload,
            write_path=None,
        )
    )


def run_unit_smokes(*, data_root: Path) -> int:
    """Existing unit checks (feed · ledger · hit-rate · per-run WORM)."""
    failed = 0
    os.environ["RAAS_DATA_ROOT"] = str(data_root)

    try:
        assert_no_order_urls("https://api.binance.com/api/v3/order")
        print("  FAIL  order URL should be refused")
        failed += 1
    except RuntimeError:
        print("  PASS  PAPER_FEED order URL refused")

    led = PaperLedger(starting_balance_eur=Decimal("1000.00"))
    buy = led.sim_buy(Decimal("0.1"), Decimal("2000"), signal_id="t0")
    if not buy or led.fees_paid_eur <= 0 or led.order_send_count != 0:
        print("  FAIL  PAPER_LEDGER")
        failed += 1
    else:
        print("  PASS  PAPER_LEDGER sim_buy + fees · order_send_count=0")

    try:
        from prototypes.raas_paper_trading.config_loader import PaperTradingSettings

        cfg = PaperTradingSettings.from_file()
        if cfg.taker_rate != Decimal("0.00075"):
            print("  FAIL  config taker fee expected 0.00075")
            failed += 1
        else:
            print(f"  PASS  config fees VIP1 0.075% hash={cfg.config_hash[:12]}…")
        cfg_led = ledger_from_config(cfg)
        if cfg_led.fee_schedule.taker_bps != Decimal("7.5"):
            print("  FAIL  ledger_from_config fees")
            failed += 1
        else:
            print("  PASS  ledger_from_config")
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL  paper_trading_config: {exc}")
        failed += 1

    pf = led.diagnostic_profit_factor()
    if pf.get("diagnostic_only") is not True:
        print("  FAIL  profit factor must be diagnostic_only")
        failed += 1
    else:
        print("  PASS  profit_factor diagnostic_only")

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
    if abs(hits.precision - 0.5) > 1e-9 or hits.to_dict().get("role") != "primary":
        print("  FAIL  envelope hit-rate")
        failed += 1
    else:
        print("  PASS  envelope hit-rate primary metric")

    denied = False
    try:
        PaperWormLog("paper_demo", "deny-run", data_root=data_root).append(
            {"action": "ORDER_SENT", "live_execution": False}
        )
    except RuntimeError:
        denied = True
    if not denied:
        print("  FAIL  ORDER_SENT should raise")
        failed += 1
    else:
        print("  PASS  ORDER_SENT rejected")

    return failed


def run_five_dry_runs(enforcer: DSuiteEnforcer) -> int:
    """5 paper runs over ETHUSDC / BTCUSDC → logs/worm/paper_trading_audit.jsonl."""
    failed = 0
    if AUDIT_PATH.exists():
        AUDIT_PATH.unlink()
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # D2 negative probe: Red must not write audit outside sandbox
    try:
        enforcer.enforce_all(
            EnforcerContext(
                caller_role="RED",
                target_path="internal://scenario",
                write_path=str(AUDIT_PATH),
                payload={"scenario": "paper"},
            )
        )
        print("  FAIL  D2 should block Red write to logs/worm")
        failed += 1
    except DSuiteViolation as v:
        if v.debt_id != "D2":
            print(f"  FAIL  expected D2 got {v.debt_id}")
            failed += 1
        else:
            print("  PASS  D2 Red isolation (audit path outside sandbox blocked)")

    # D1 negative probe
    try:
        enforcer.enforce_all(
            EnforcerContext(
                caller_role="UNTRUSTED_SHELL",
                target_path="/api/v1/raas/evaluate",
                payload={"advice": "you should buy ETH now"},
            )
        )
        print("  FAIL  D1 should block advisory text")
        failed += 1
    except DSuiteViolation as v:
        if v.debt_id != "D1":
            print(f"  FAIL  expected D1 got {v.debt_id}")
            failed += 1
        else:
            print("  PASS  D1 not_investment_advice enforcement")

    bases = {"ETHUSDC": 2500.0, "BTCUSDC": 65000.0}
    prev = "0" * 64
    written = 0

    for run_idx in range(N_RUNS):
        symbol = MARKETS[run_idx % len(MARKETS)]
        ticks = _market_ticks(symbol, base=bases[symbol], run_idx=run_idx)
        floor = bases[symbol] * 0.75
        run_id = f"paper-dry-{run_idx + 1:02d}-{symbol.lower()}"
        runner = PaperTradingRunner(
            tenant_id="paper_dry_run",
            run_id=run_id,
            break_price_below=floor,
        )
        summary = runner.run(ReplayFeed(ticks))

        if summary.get("live_execution") is not False:
            print(f"  FAIL  run {run_idx + 1} live_execution")
            failed += 1
            continue
        if summary.get("order_send_count", 1) != 0:
            print(f"  FAIL  run {run_idx + 1} order_send_count")
            failed += 1
            continue

        raw = {
            "phase": "paper_trading_dry_run",
            "run_index": run_idx + 1,
            "market": symbol,
            "run_id": run_id,
            "ts": _now(),
            "summary": {
                "primary_metric": summary.get("primary_metric"),
                "envelope_hit_rate": summary.get("envelope_hit_rate"),
                "order_send_count": summary.get("order_send_count"),
                "ledger_equity_eur": (summary.get("ledger") or {}).get("equity_eur"),
                "profit_factor_diagnostic": summary.get("profit_factor_diagnostic"),
                "worm_path": summary.get("worm_path"),
            },
            "free_text": "paper dry-run signal log only — no order routing",
        }
        try:
            stamped = _enforce_paper_record(enforcer, raw)
        except DSuiteViolation as v:
            print(f"  FAIL  D-suite run {run_idx + 1}: {v}")
            failed += 1
            continue

        if stamped.get("not_investment_advice") is not True:
            print(f"  FAIL  D1 stamp missing run {run_idx + 1}")
            failed += 1
            continue
        if stamped.get("live_execution") is not False:
            print(f"  FAIL  live_execution stamp run {run_idx + 1}")
            failed += 1
            continue
        if not stamped.get("_worm_anchor_sha256"):
            print(f"  FAIL  D4 worm anchor missing run {run_idx + 1}")
            failed += 1
            continue
        checked = stamped.get("_d_suite_checked") or []
        if checked != ["D1", "D2", "D3", "D4"]:
            print(f"  FAIL  D-suite checklist run {run_idx + 1}: {checked}")
            failed += 1
            continue

        prev = _append_audit_line(AUDIT_PATH, stamped, prev_hash=prev)
        written += 1
        print(
            f"  PASS  run {run_idx + 1}/{N_RUNS} {symbol} "
            f"anchor={stamped['_worm_anchor_sha256'][:12]}…"
        )

    if written != N_RUNS:
        print(f"  FAIL  expected {N_RUNS} audit lines, wrote {written}")
        failed += 1
    elif not AUDIT_PATH.is_file():
        print("  FAIL  audit file missing")
        failed += 1
    else:
        lines = AUDIT_PATH.read_text(encoding="utf-8").strip().splitlines()
        if len(lines) != N_RUNS:
            print(f"  FAIL  audit line count {len(lines)}")
            failed += 1
        else:
            # Verify hash chain + markets covered
            chain_ok = True
            ph = "0" * 64
            markets_seen = set()
            for ln in lines:
                row = json.loads(ln)
                markets_seen.add(row.get("market"))
                if row.get("prev_hash") != ph or row.get("live_execution") is not False:
                    chain_ok = False
                if row.get("not_investment_advice") is not True:
                    chain_ok = False
                ph = row["hash"]
            if not chain_ok:
                print("  FAIL  audit hash chain / flags")
                failed += 1
            elif not set(MARKETS).issubset(markets_seen):
                print(f"  FAIL  markets {markets_seen}")
                failed += 1
            else:
                print(
                    f"  PASS  audit JSONL ({N_RUNS} lines) → {AUDIT_PATH.relative_to(_ROOT)}"
                )
                print(f"  PASS  markets in audit: {sorted(markets_seen)}")

    return failed


def main() -> int:
    print("RaaS paper-trading smoke + dry-run (ETHUSDC / BTCUSDC)")
    print("=" * 60)
    failed = 0

    tmp = tempfile.mkdtemp(prefix="paper_")
    try:
        failed += run_unit_smokes(data_root=Path(tmp) / "raas")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # D-suite anchors for this dry-run (separate from audit JSONL)
    d_suite_worm = _ROOT / "logs" / "worm" / "paper_trading_d_suite_anchors.jsonl"
    if d_suite_worm.exists():
        d_suite_worm.unlink()
    enforcer = DSuiteEnforcer(worm=WormAnchorStore(d_suite_worm))

    print("-" * 60)
    print("Five dry-runs + DSuiteEnforcer (D1–D4)")
    failed += run_five_dry_runs(enforcer)

    # D3 quarantine smoke: shell must not hit arbitrary targets
    try:
        enforcer.enforce_all(
            EnforcerContext(
                caller_role="UNTRUSTED_SHELL",
                target_path="/admin/secret",
                payload={},
            )
        )
        print("  FAIL  D3 should block shell target")
        failed += 1
    except DSuiteViolation as v:
        if v.debt_id != "D3":
            print(f"  FAIL  expected D3 got {v.debt_id}")
            failed += 1
        else:
            print("  PASS  D3 shell/core quarantine")

    try:
        enforcer.enforce_all(
            EnforcerContext(
                caller_role="EXTERNAL",
                target_path="/api/v1/raas/internal-only",
                payload={},
            )
        )
        print("  FAIL  D4 should block exterior path")
        failed += 1
    except DSuiteViolation as v:
        if v.debt_id != "D4":
            print(f"  FAIL  expected D4 got {v.debt_id}")
            failed += 1
        else:
            print("  PASS  D4 ingress/egress exterior gate")

    verdict = "RAAS_PAPER_TRADING_PASS" if failed == 0 else "RAAS_PAPER_TRADING_FAIL"
    print("=" * 60)
    print(f"VERDICT: {verdict}")
    if failed == 0:
        print(f"audit:   {AUDIT_PATH}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
