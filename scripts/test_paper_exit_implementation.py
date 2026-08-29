#!/usr/bin/env python3
"""Smoke S1–S6 (+ S3b/S6b) for Option-B paper exit — Pre-Reg IMPLEMENTATION_PREREG.

Usage (repo root):
  PYTHONPATH=. python3 scripts/test_paper_exit_implementation.py
  make raas-paper-exit-smoke
"""
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

from prototypes.raas_paper_trading.feed import PaperTick  # noqa: E402
from prototypes.raas_paper_trading.ledger import PaperLedger  # noqa: E402
from prototypes.raas_paper_trading.paper_exit import (  # noqa: E402
    EXIT_REASONS,
    FORBIDDEN_PAPER_KEYS,
    PositionState,
)
from prototypes.raas_paper_trading.runner import PaperTradingRunner  # noqa: E402
from prototypes.raas_paper_trading.worm_log import PaperWormLog  # noqa: E402

_PASS = 0
_FAIL = 0


def _ok(name: str) -> None:
    global _PASS
    _PASS += 1
    print(f"  PASS  {name}")


def _fail(name: str, detail: str) -> None:
    global _FAIL
    _FAIL += 1
    print(f"  FAIL  {name}: {detail}")


def _tick(ts: str, price: float = 2000.0, symbol: str = "ETHUSDT") -> PaperTick:
    return PaperTick(symbol=symbol, ts=ts, price=price, source="replay")


def _runner(tmp: Path, *, hold: int = 10, gap: float = 30.0, max_wait: float = 50.0):
    worm = PaperWormLog(tenant_id="t", run_id="exit-smoke", data_root=tmp / "worm")
    return PaperTradingRunner(
        tenant_id="t",
        run_id="exit-smoke",
        ledger=PaperLedger(starting_balance_eur=Decimal("1000")),
        worm=worm,
        attach_orderbook=False,
        exit_mode="time_hold",
        hold_seconds=hold,
        gap_dt_s=gap,
        max_wait_s=max_wait,
        position_state_path=tmp / "state" / "paper_position.json",
        edges_path=tmp / "audit" / "paper_edges.jsonl",
        shadow_notional_eur=Decimal("100"),
    )


def _worm_rows(runner: PaperTradingRunner) -> list:
    path = runner.worm.path
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _fills(rows: list, side: str | None = None) -> list:
    out = [r for r in rows if r.get("action") == "SIM_FILL"]
    if side:
        out = [r for r in out if r.get("side") == side]
    return out


def test_s1_single_position_gate() -> None:
    name = "S1 single-position gate"
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        r = _runner(tmp, hold=100)
        r.on_tick(_tick("2026-08-29T10:00:00+00:00", 2000))
        r.on_tick(_tick("2026-08-29T10:00:10+00:00", 2010))  # during hold
        rows = _worm_rows(r)
        buys = _fills(rows, "BUY")
        if len(buys) != 1:
            _fail(name, f"expected 1 BUY, got {len(buys)}")
            return
        if r.exit is None or r.exit.state != PositionState.HOLDING.value:
            _fail(name, f"state={getattr(r.exit, 'state', None)}")
            return
        skipped = [
            x
            for x in rows
            if x.get("skip_reason") == "SIGNAL_IGNORED_POSITION_OPEN"
        ]
        if not skipped:
            _fail(name, "missing SIGNAL_IGNORED_POSITION_OPEN")
            return
        _ok(name)


def test_s2_hold_timer_absolute() -> None:
    name = "S2 hold timer absolute (no reset)"
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        r = _runner(tmp, hold=10)
        # t=0 entry
        r.on_tick(_tick("2026-08-29T10:00:00+00:00", 2000))
        # t=5 "signal" must not extend hold
        r.on_tick(_tick("2026-08-29T10:00:05+00:00", 2005))
        # t=10 → exit (not 15)
        r.on_tick(_tick("2026-08-29T10:00:10+00:00", 2010))
        sells = _fills(_worm_rows(r), "SELL")
        if len(sells) != 1:
            _fail(name, f"expected 1 SELL at t=10, got {len(sells)}")
            return
        hold_actual = float(sells[0]["hold_seconds_actual"])
        if hold_actual < 10 or hold_actual > 10.01:
            _fail(name, f"hold_seconds_actual={hold_actual} (want ≈10)")
            return
        if sells[0].get("exit_reason") != "hold_expired":
            _fail(name, f"exit_reason={sells[0].get('exit_reason')}")
            return
        _ok(name)


def test_s3_gap_protection() -> None:
    name = "S3 gap protection"
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        r = _runner(tmp, hold=10, gap=30)
        r.on_tick(_tick("2026-08-29T10:00:00+00:00", 2000))
        # hold expired but gap 60s > 30
        r.on_tick(_tick("2026-08-29T10:01:00+00:00", 2010))
        sells = _fills(_worm_rows(r), "SELL")
        if sells:
            _fail(name, "SELL on gap tick")
            return
        if r.exit is None or r.exit.state != PositionState.EXIT_PENDING.value:
            _fail(name, f"expected EXIT_PENDING, got {getattr(r.exit, 'state', None)}")
            return
        # valid tick after gap reference: note prev is gap tick — need Δt≤30 from last noted
        r.on_tick(_tick("2026-08-29T10:01:10+00:00", 2011))
        sells = _fills(_worm_rows(r), "SELL")
        if len(sells) != 1:
            _fail(name, f"expected SELL after valid tick, got {len(sells)}")
            return
        _ok(name)


def test_s3b_max_wait_alarm() -> None:
    name = "S3b max-wait alarm (no auto force)"
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        r = _runner(tmp, hold=10, gap=30, max_wait=20)
        r.on_tick(_tick("2026-08-29T10:00:00+00:00", 2000))
        # expire + wait beyond max with large gaps so no exit
        r.on_tick(_tick("2026-08-29T10:00:40+00:00", 2010))  # EXIT_PENDING, gap
        r.on_tick(_tick("2026-08-29T10:01:20+00:00", 2011))  # still gapped, past max wait
        if r.exit is None or "EXIT_WAIT_TIMEOUT" not in r.exit.alarms:
            _fail(name, f"alarms={getattr(r.exit, 'alarms', None)}")
            return
        sells = _fills(_worm_rows(r), "SELL")
        if sells:
            _fail(name, "auto force-exit must not happen")
            return
        _ok(name)


def test_s4_restart_reconstruction() -> None:
    name = "S4 restart reconstruction"
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        r1 = _runner(tmp, hold=30)
        r1.on_tick(_tick("2026-08-29T10:00:00+00:00", 2000))
        r1.exit.persist_for_shutdown()
        state_path = tmp / "state" / "paper_position.json"
        if not state_path.is_file():
            _fail(name, "missing paper_position.json")
            return
        # Restart: new ledger, same state + edges paths, append same worm
        worm2 = PaperWormLog(tenant_id="t", run_id="exit-smoke", data_root=tmp / "worm")
        r2 = PaperTradingRunner(
            tenant_id="t",
            run_id="exit-smoke",
            ledger=PaperLedger(starting_balance_eur=Decimal("1000")),
            worm=worm2,
            attach_orderbook=False,
            exit_mode="time_hold",
            hold_seconds=30,
            gap_dt_s=30,
            max_wait_s=100,
            position_state_path=state_path,
            edges_path=tmp / "audit" / "paper_edges.jsonl",
            shadow_notional_eur=Decimal("100"),
        )
        if r2.exit is None or r2.exit.state != PositionState.HOLDING.value:
            _fail(name, f"state after load={getattr(r2.exit, 'state', None)}")
            return
        if r2.ledger.position_qty <= 0:
            _fail(name, "ledger not seeded after restart")
            return
        # Mid-hold tick must not buy again
        r2.on_tick(_tick("2026-08-29T10:00:10+00:00", 2005))
        buys = _fills(_worm_rows(r2), "BUY")
        # worm continues — only original BUY from r1
        if len(buys) != 1:
            _fail(name, f"expected still 1 BUY total, got {len(buys)}")
            return
        # Exit at entry+30
        r2.on_tick(_tick("2026-08-29T10:00:30+00:00", 2010))
        sells = _fills(_worm_rows(r2), "SELL")
        if len(sells) != 1:
            _fail(name, f"expected SELL after hold, got {len(sells)}")
            return
        if float(sells[0]["hold_seconds_actual"]) < 30:
            _fail(name, "timer reset on restart")
            return
        _ok(name)


def test_s5_worm_fields() -> None:
    name = "S5 WORM SELL fields"
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        r = _runner(tmp, hold=5)
        r.on_tick(_tick("2026-08-29T10:00:00+00:00", 2000))
        r.on_tick(_tick("2026-08-29T10:00:05+00:00", 2001))
        sells = _fills(_worm_rows(r), "SELL")
        if len(sells) != 1:
            _fail(name, f"no SELL: {len(sells)}")
            return
        s = sells[0]
        required = (
            "entry_tick_ts",
            "exit_tick_ts",
            "hold_seconds_actual",
            "hold_seconds_target",
            "exit_reason",
        )
        missing = [k for k in required if k not in s]
        if missing:
            _fail(name, f"missing {missing}")
            return
        if s["exit_reason"] not in EXIT_REASONS:
            _fail(name, f"bad exit_reason {s['exit_reason']}")
            return
        if FORBIDDEN_PAPER_KEYS.intersection(s.keys()):
            _fail(name, "sizing keys leaked into paper WORM")
            return
        if s.get("live_execution") is not False or s.get("order_send") is not False:
            _fail(name, "charter flags")
            return
        _ok(name)


def test_s6_edge_ledger() -> None:
    name = "S6 paper_edges 1:1"
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        r = _runner(tmp, hold=5)
        r.on_tick(_tick("2026-08-29T10:00:00+00:00", 2000))
        r.on_tick(_tick("2026-08-29T10:00:05+00:00", 2001))
        sells = _fills(_worm_rows(r), "SELL")
        edges_path = tmp / "audit" / "paper_edges.jsonl"
        if not edges_path.is_file():
            _fail(name, "missing paper_edges.jsonl")
            return
        edges = [json.loads(line) for line in edges_path.read_text().splitlines() if line.strip()]
        if len(edges) != 1 or len(sells) != 1:
            _fail(name, f"sells={len(sells)} edges={len(edges)}")
            return
        if edges[0].get("worm_sell_hash") != sells[0].get("hash"):
            _fail(name, "worm_sell_hash mismatch")
            return
        if edges[0].get("exit_reason") not in EXIT_REASONS:
            _fail(name, "edge exit_reason")
            return
        if not edges[0].get("prev_hash") or not edges[0].get("hash"):
            _fail(name, "hash chain missing")
            return
        _ok(name)


def test_s6b_force_exit() -> None:
    name = "S6b HUMAN_FORCE_EXIT only"
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        r = _runner(tmp, hold=1000)
        r.on_tick(_tick("2026-08-29T10:00:00+00:00", 2000))
        os.environ["HUMAN_FORCE_EXIT"] = "1"
        try:
            r.on_tick(_tick("2026-08-29T10:00:05+00:00", 2001))
        finally:
            os.environ.pop("HUMAN_FORCE_EXIT", None)
        sells = _fills(_worm_rows(r), "SELL")
        if len(sells) != 1:
            _fail(name, f"expected force SELL, got {len(sells)}")
            return
        if sells[0].get("exit_reason") != "force_exit":
            _fail(name, f"exit_reason={sells[0].get('exit_reason')}")
            return
        _ok(name)


def test_round_trip_second_entry() -> None:
    name = "Idle-first-tick after exit (B3)"
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        r = _runner(tmp, hold=5)
        r.on_tick(_tick("2026-08-29T10:00:00+00:00", 2000))
        r.on_tick(_tick("2026-08-29T10:00:05+00:00", 2001))
        r.on_tick(_tick("2026-08-29T10:00:10+00:00", 2002))  # second entry
        buys = _fills(_worm_rows(r), "BUY")
        sells = _fills(_worm_rows(r), "SELL")
        if len(buys) != 2 or len(sells) != 1:
            _fail(name, f"buys={len(buys)} sells={len(sells)}")
            return
        _ok(name)


def main() -> int:
    print("paper exit implementation smoke (S1–S6)")
    test_s1_single_position_gate()
    test_s2_hold_timer_absolute()
    test_s3_gap_protection()
    test_s3b_max_wait_alarm()
    test_s4_restart_reconstruction()
    test_s5_worm_fields()
    test_s6_edge_ledger()
    test_s6b_force_exit()
    test_round_trip_second_entry()
    print(f"\n{ _PASS } passed, { _FAIL } failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
