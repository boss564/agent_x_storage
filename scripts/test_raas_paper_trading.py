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
from prototypes.raas_paper_trading.config_loader import PaperTradingSettings  # noqa: E402
from prototypes.raas_paper_trading.depth_worm import DepthWormLog  # noqa: E402
from prototypes.raas_paper_trading.feed import (  # noqa: E402
    PaperTick,
    ReplayFeed,
    assert_no_order_urls,
    orderbook_to_snapshot,
    parse_orderbook_snapshot,
)
from prototypes.raas_paper_trading.ledger import PaperLedger, ledger_from_config  # noqa: E402
from prototypes.raas_paper_trading.runner import PaperTradingRunner  # noqa: E402
from prototypes.raas_paper_trading.depth_snapshot import (  # noqa: E402
    AGE_STRATA_GT_30,
    DepthSnapshot,
    age_stratum,
    snapshot_age_seconds,
)
from prototypes.raas_paper_trading.slippage import synthetic_orderbook  # noqa: E402
from prototypes.raas_paper_trading.worm_log import PaperWormLog  # noqa: E402
from services.fail_closed_gate.d_suite_enforcer import (  # noqa: E402
    DSuiteEnforcer,
    DSuiteViolation,
    EnforcerContext,
    WormAnchorStore,
)

AUDIT_PATH = _ROOT / "logs" / "worm" / "paper_trading_audit.jsonl"
PERSIST_WORM_ROOT = _ROOT / "logs" / "worm" / "paper_runs"
MARKETS = ("ETHUSDC", "BTCUSDC")
N_RUNS = 5
SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _persist_worm(run_id: str, worm_path: str) -> Path | None:
    """Copy per-run WORM into logs/worm/paper_runs for slippage replay."""
    src = Path(worm_path)
    if not src.is_file():
        return None
    dest = PERSIST_WORM_ROOT / run_id / "paper_trades.worm.jsonl"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest



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

    try:
        assert_no_order_urls("https://api.binance.com/api/v3/depth?symbol=ETHUSDC")
        print("  PASS  depth URL allowed (read-only)")
    except RuntimeError:
        print("  FAIL  depth URL should be allowed")
        failed += 1

    book = synthetic_orderbook(2500.0, qty_per_level=0.05)
    snap = orderbook_to_snapshot(book)
    roundtrip = parse_orderbook_snapshot(snap)
    if len(roundtrip["asks"]) != len(book["asks"]):
        print("  FAIL  orderbook snapshot roundtrip")
        failed += 1
    else:
        print("  PASS  orderbook snapshot roundtrip")

    depth_path = data_root / "depth_test.jsonl"
    row = DepthWormLog(depth_path).append_snapshot(symbol="ETHUSDC", orderbook=book)
    if row.get("action") != "DEPTH_SNAPSHOT" or row.get("live_execution") is not False:
        print("  FAIL  DepthWormLog")
        failed += 1
    else:
        print("  PASS  DepthWormLog append")

    age = snapshot_age_seconds(
        "2026-08-28T10:01:00+00:00",
        "2026-08-28T10:00:20+00:00",
    )
    if abs(age - 40.0) > 0.01 or age_stratum(age) != AGE_STRATA_GT_30:
        print("  FAIL  snapshot_age_seconds / age_stratum")
        failed += 1
    else:
        print("  PASS  snapshot_age_s strata (40s → gt_30s)")

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
        expected_pairs = ("BTCUSDC", "ETHUSDC", "SOLUSDC")
        if tuple(cfg.depth_symbols) != expected_pairs:
            print(f"  FAIL  depth_symbols expected {expected_pairs} got {cfg.depth_symbols}")
            failed += 1
        elif len(cfg.pairs) != 3:
            print(f"  FAIL  pairs count expected 3 got {len(cfg.pairs)}")
            failed += 1
        elif cfg.notional_for("SOLUSDC") != Decimal("100"):
            print("  FAIL  SOLUSDC notional_eur")
            failed += 1
        elif cfg.volatility_profile_for("BTCUSDC") != "low":
            print("  FAIL  BTC volatility_profile")
            failed += 1
        else:
            print("  PASS  shadow pairs BTC/ETH/SOL + per-pair notional")
        btc_pair_hash = cfg.pair_manifest_hash_for("BTCUSDC")
        if len(btc_pair_hash) != 64:
            print("  FAIL  pair_manifest_hash format")
            failed += 1
        else:
            print(f"  PASS  pair_manifest_hash BTC={btc_pair_hash[:12]}…")
        try:
            from prototypes.raas_paper_trading.config_loader import pair_manifest_hash as pmh_fn

            base_cfg = {
                "exchange": {
                    "name": "binance",
                    "fees": {"maker": 0.00075, "taker": 0.00075},
                },
                "slippage": {
                    "mode": "dynamic",
                    "fallback_percent": 0.001,
                    "orderbook_depth_levels": 10,
                },
                "paper_trading": {"live_execution": False, "initial_balance_eur": 1000},
                "shadow_fill": {"notional_eur": 100.0, "attach_orderbook": True},
                "pairs": [
                    {"symbol": "BTCUSDC", "notional_eur": 100, "volatility_profile": "low"},
                    {"symbol": "ETHUSDC", "notional_eur": 100, "volatility_profile": "medium"},
                ],
            }
            three_pair = {
                **base_cfg,
                "pairs": [
                    *base_cfg["pairs"],
                    {"symbol": "SOLUSDC", "notional_eur": 100, "volatility_profile": "high"},
                ],
            }
            if pmh_fn("BTCUSDC", raw=base_cfg) != pmh_fn("BTCUSDC", raw=three_pair):
                print("  FAIL  BTC pair_manifest_hash changed when only SOL added")
                failed += 1
            else:
                print("  PASS  pair_manifest_hash stable across pair-list expansion")
            full_two = hashlib.sha256(
                json.dumps(base_cfg, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            full_three = hashlib.sha256(
                json.dumps(three_pair, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if full_two == full_three:
                print("  FAIL  full config hash should change when SOL added")
                failed += 1
            else:
                print("  PASS  config_manifest_hash splits on SOL add (expected)")
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL  pair_manifest_hash isolation: {exc}")
            failed += 1
        cfg_led = ledger_from_config(cfg)
        if cfg_led.fee_schedule.taker_bps != Decimal("7.5"):
            print("  FAIL  ledger_from_config fees")
            failed += 1
        else:
            print("  PASS  ledger_from_config")
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL  paper_trading_config: {exc}")
        failed += 1

    try:
        from prototypes.raas_paper_trading.replay import FillTuple, replay_slippage_ab

        sample = [
            FillTuple(
                side="BUY",
                qty=Decimal("0.04"),
                mark_price=Decimal("2500"),
                signal_id="replay-smoke",
                ts="2026-08-28T00:00:00Z",
                run_id="smoke",
            )
        ]
        rep = replay_slippage_ab(sample)
        if rep.get("fill_count") != 1 or "slippage_cost_delta_eur" not in rep.get("metrics", {}):
            print("  FAIL  replay_slippage_ab")
            failed += 1
        elif "snapshot_age_strata" not in rep:
            print("  FAIL  replay missing snapshot_age_strata")
            failed += 1
        elif "by_symbol" not in rep:
            print("  FAIL  replay missing by_symbol")
            failed += 1
        else:
            print("  PASS  replay_slippage_ab fixed-tuple A/B + age strata + by_symbol")
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL  replay_slippage_ab: {exc}")
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
    paper_cfg = PaperTradingSettings.from_file()
    fill_snapshots = 0

    def _shadow_depth(_symbol: str, mid: float, fill_ts: str) -> DepthSnapshot:
        return DepthSnapshot(
            orderbook=synthetic_orderbook(mid, qty_per_level=0.05),
            snapshot_ts=fill_ts,
            source="shadow_synthetic",
            snapshot_age_s=0.0,
        )

    for run_idx in range(N_RUNS):
        symbol = MARKETS[run_idx % len(MARKETS)]
        ticks = _market_ticks(symbol, base=bases[symbol], run_idx=run_idx)
        floor = bases[symbol] * 0.75
        run_id = f"paper-dry-{run_idx + 1:02d}-{symbol.lower()}"
        runner = PaperTradingRunner(
            tenant_id="paper_dry_run",
            run_id=run_id,
            break_price_below=floor,
            shadow_notional_eur=paper_cfg.shadow_notional_eur,
            attach_orderbook=paper_cfg.attach_orderbook,
            depth_fetcher=_shadow_depth,
        )
        summary = runner.run(ReplayFeed(ticks))

        worm_file = Path(summary.get("worm_path", ""))
        if worm_file.is_file():
            for line in worm_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                ev = json.loads(line)
                if ev.get("action") != "SIM_FILL":
                    continue
                if ev.get("orderbook_snapshot"):
                    fill_snapshots += 1
                if ev.get("snapshot_age_s") is None or ev.get("snapshot_ts") is None:
                    print("  FAIL  SIM_FILL missing snapshot_ts/snapshot_age_s")
                    failed += 1
                    break

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
        worm_src = (summary.get("worm_path") or "")
        persisted = _persist_worm(run_id, worm_src)
        worm_note = f" worm→{persisted.name}" if persisted else ""
        print(
            f"  PASS  run {run_idx + 1}/{N_RUNS} {symbol} "
            f"anchor={stamped['_worm_anchor_sha256'][:12]}…{worm_note}"
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
                if fill_snapshots < 1:
                    print("  FAIL  SIM_FILL missing orderbook_snapshot")
                    failed += 1
                else:
                    print(
                        f"  PASS  SIM_FILL provenance "
                        f"({fill_snapshots} fills, snapshot_age_s present)"
                    )

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

    if failed == 0 and PERSIST_WORM_ROOT.is_dir():
        try:
            from prototypes.raas_paper_trading.replay import load_all_fills, replay_slippage_ab

            fills = load_all_fills(persist_dir=PERSIST_WORM_ROOT)
            if fills:
                rep = replay_slippage_ab(fills)
                m = rep["metrics"]
                print(
                    f"  PASS  slippage replay {len(fills)} fills "
                    f"slipΔ={m['slippage_cost_delta_eur']}€ feeΔ={m['fee_delta_eur']}€"
                )
            else:
                print("  WARN  slippage replay: no persisted SIM_FILL rows")
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL  slippage replay: {exc}")
            failed += 1

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
