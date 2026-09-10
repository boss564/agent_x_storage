#!/usr/bin/env python3
"""E8 POSITION_ABANDONED + Option-B epoch pairing (no synthetic SELL).

Usage (repo root):
  PYTHONPATH=. python3 scripts/test_position_abandoned.py
  make raas-paper-abandon-smoke
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.paper_exit import (  # noqa: E402
    ACTION_POSITION_ABANDONED,
    OPTION_B_EXIT_EPOCH_TS,
    PaperPositionStore,
    is_abandon_event,
    position_abandoned_payload,
)
from prototypes.raas_paper_trading.replay import pair_option_b_fills  # noqa: E402

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


def _write_jsonl(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r) + "\n" for r in rows),
        encoding="utf-8",
    )


def test_payload_is_not_a_fill() -> None:
    name = "payload diagnostic, pnl null, no fill side"
    row = position_abandoned_payload(
        signal_id="sig-11434",
        reason="feed_stall_recovery",
        entry_price="2455.59",
        entry_tick_ts="2026-08-30T08:54:59.047000+00:00",
        prior_state="HOLDING",
    )
    if row.get("action") != ACTION_POSITION_ABANDONED:
        _fail(name, f"action={row.get('action')}")
        return
    if row.get("pnl_eur") is not None:
        _fail(name, f"pnl_eur={row.get('pnl_eur')}")
        return
    if row.get("side") is not None or row.get("qty") is not None:
        _fail(name, "looks like a fill")
        return
    if row.get("realized_pnl_eur") is not None:
        _fail(name, "realized_pnl present")
        return
    if not row.get("diagnostic_only"):
        _fail(name, "diagnostic_only")
        return
    if not is_abandon_event(row):
        _fail(name, "is_abandon_event False")
        return
    _ok(name)


def test_legacy_restart_marker_is_abandon() -> None:
    name = "legacy RESTART_MARKER pairs as abandon"
    marker = {
        "action": "RESTART_MARKER",
        "prior_state": "HOLDING",
        "entry_signal_id": "sig-11434",
        "entry_tick_ts": "2026-08-30T08:54:59.047000+00:00",
        "reason": "feed_stall_recovery",
        "diagnostic_only": True,
    }
    idle = {"action": "RESTART_MARKER", "prior_state": "IDLE", "reason": "x"}
    if not is_abandon_event(marker):
        _fail(name, "HOLDING marker not abandon")
        return
    if is_abandon_event(idle):
        _fail(name, "IDLE marker must not pair")
        return
    _ok(name)


def test_epoch_pairing_conservation() -> None:
    name = "epoch: 1 RT + 1 abandon + 1 open, pre-epoch ignored"
    with tempfile.TemporaryDirectory() as td:
        worm = Path(td) / "paper_trades.worm.jsonl"
        _write_jsonl(
            worm,
            [
                {
                    "action": "SIM_FILL",
                    "side": "BUY",
                    "ts": "2026-08-28T12:00:00+00:00",
                    "signal_id": "legacy",
                    "qty": "0.04",
                    "price": "1",
                },
                {
                    "action": "SIM_FILL",
                    "side": "BUY",
                    "ts": OPTION_B_EXIT_EPOCH_TS,
                    "signal_id": "rt-a",
                    "qty": "0.04",
                    "price": "2436.67",
                },
                {
                    "action": "SIM_FILL",
                    "side": "SELL",
                    "ts": "2026-08-29T09:53:10.049000+00:00",
                    "signal_id": "rt-a",
                    "qty": "0.04",
                    "price": "2436.67",
                    "exit_reason": "hold_expired",
                    "realized_pnl_eur": "1.00",
                },
                {
                    "action": "SIM_FILL",
                    "side": "BUY",
                    "ts": "2026-08-30T08:54:59.047000+00:00",
                    "signal_id": "sig-11434",
                    "qty": "0.04",
                    "price": "2455.59",
                },
                {
                    "action": ACTION_POSITION_ABANDONED,
                    "signal_id": "sig-11434",
                    "reason": "feed_stall_recovery",
                    "entry_price": "2455.59",
                    "entry_tick_ts": "2026-08-30T08:54:59.047000+00:00",
                    "pnl_eur": None,
                    "diagnostic_only": True,
                },
                {
                    "action": "SIM_FILL",
                    "side": "BUY",
                    "ts": "2026-08-30T15:30:17.309000+00:00",
                    "signal_id": "sig-1",
                    "qty": "0.04",
                    "price": "2478.24",
                },
            ],
        )
        p = pair_option_b_fills(worm)
        if p.n_pre_epoch_buys != 1:
            _fail(name, f"pre={p.n_pre_epoch_buys}")
            return
        if (p.n_buy, p.n_sell, p.n_abandoned, p.n_open) != (3, 1, 1, 1):
            _fail(name, f"counts buy/sell/ab/open={p.n_buy}/{p.n_sell}/{p.n_abandoned}/{p.n_open}")
            return
        if not p.conservation_ok:
            _fail(name, f"conservation {p.to_dict()}")
            return
        if p.completed[0][1].get("realized_pnl_eur") != "1.00":
            _fail(name, "equity RT missing")
            return
        if p.abandoned[0][1].get("pnl_eur") is not None:
            _fail(name, "abandon invented pnl")
            return
        if (p.open_buy or {}).get("signal_id") != "sig-1":
            _fail(name, f"open={p.open_buy}")
            return
        _ok(name)


def test_restart_then_abandoned_not_double_counted() -> None:
    name = "RESTART_MARKER + POSITION_ABANDONED close once"
    with tempfile.TemporaryDirectory() as td:
        worm = Path(td) / "paper_trades.worm.jsonl"
        _write_jsonl(
            worm,
            [
                {
                    "action": "SIM_FILL",
                    "side": "BUY",
                    "ts": "2026-08-29T20:55:31.943000+00:00",
                    "signal_id": "sig-92875",
                    "qty": "0.04",
                    "price": "2453.26",
                },
                {
                    "action": "RESTART_MARKER",
                    "prior_state": "HOLDING",
                    "entry_signal_id": "sig-92875",
                    "entry_tick_ts": "2026-08-29T20:55:31.943000+00:00",
                    "recovery_ts": "2026-08-30T04:43:44.903713+00:00",
                    "ts": "2026-08-30T04:43:44.903713+00:00",
                    "reason": "oom_recovery",
                    "diagnostic_only": True,
                },
                {
                    "action": ACTION_POSITION_ABANDONED,
                    "signal_id": "sig-92875",
                    "reason": "oom_recovery",
                    "entry_tick_ts": "2026-08-29T20:55:31.943000+00:00",
                    "pnl_eur": None,
                    "diagnostic_only": True,
                    "ts": "2026-08-30T04:43:44.910000+00:00",
                },
            ],
        )
        p = pair_option_b_fills(worm)
        if p.n_abandoned != 1 or p.n_duplicate_abandon != 1:
            _fail(name, f"ab={p.n_abandoned} dup={p.n_duplicate_abandon}")
            return
        if not p.conservation_ok or p.n_open != 0:
            _fail(name, f"conservation {p.to_dict()}")
            return
        _ok(name)


def test_recover_writes_abandoned_not_sell() -> None:
    name = "recover: POSITION_ABANDONED, no SIM_FILL SELL"
    from scripts.recover_regime_swarm_rt_abort import main as recover_main

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        pos = tmp / "paper_position.json"
        store = PaperPositionStore(path=pos)
        store.set_holding(
            entry_tick_ts="2026-08-30T08:54:59.047000+00:00",
            entry_price="2455.59",
            entry_signal_id="sig-11434",
            symbol="ETHUSDT",
        )
        worm_root = tmp / "worm"
        gaps = tmp / "feed_gaps.jsonl"
        gap_state = tmp / "feed_gap_state.json"
        edges = tmp / "paper_edges.jsonl"
        os.environ["PAPER_EDGES_PATH"] = str(edges)
        argv = [
            "recover_regime_swarm_rt_abort.py",
            "--position",
            str(pos),
            "--worm-root",
            str(worm_root),
            "--gaps",
            str(gaps),
            "--gap-state",
            str(gap_state),
            "--symbol",
            "ETHUSDT",
            "--reason",
            "feed_stall_recovery",
        ]
        buf = io.StringIO()
        old = sys.argv
        try:
            sys.argv = argv
            with redirect_stdout(buf):
                rc = recover_main()
        finally:
            sys.argv = old
            os.environ.pop("PAPER_EDGES_PATH", None)
        if rc != 0:
            _fail(name, f"rc={rc} out={buf.getvalue()[:400]}")
            return
        report = json.loads(buf.getvalue())
        if report.get("worm_abandoned_action") != ACTION_POSITION_ABANDONED:
            _fail(name, f"report={report}")
            return
        worm = worm_root / "live" / "paper" / "runs" / "ethusdt" / "paper_trades.worm.jsonl"
        rows = [json.loads(ln) for ln in worm.read_text().splitlines() if ln.strip()]
        actions = [r.get("action") for r in rows]
        if ACTION_POSITION_ABANDONED not in actions or "RESTART_MARKER" not in actions:
            _fail(name, f"actions={actions}")
            return
        sells = [r for r in rows if r.get("action") == "SIM_FILL" and r.get("side") == "SELL"]
        if sells:
            _fail(name, "synthetic SELL written")
            return
        abd = [r for r in rows if r.get("action") == ACTION_POSITION_ABANDONED][0]
        if abd.get("pnl_eur") is not None:
            _fail(name, "pnl invented")
            return
        if abd.get("signal_id") != "sig-11434":
            _fail(name, f"signal_id={abd.get('signal_id')}")
            return
        store.load()
        if store.state != "IDLE":
            _fail(name, f"state={store.state}")
            return
        _ok(name)


def test_conservation_false_on_unmatched_sell() -> None:
    name = "conservation_ok false on unmatched SELL"
    with tempfile.TemporaryDirectory() as td:
        worm = Path(td) / "paper_trades.worm.jsonl"
        _write_jsonl(
            worm,
            [
                {
                    "action": "SIM_FILL",
                    "side": "SELL",
                    "ts": "2026-08-29T09:53:10.049000+00:00",
                    "signal_id": "orphan-sell",
                    "qty": "0.04",
                    "price": "2436.67",
                    "exit_reason": "hold_expired",
                },
            ],
        )
        p = pair_option_b_fills(worm)
        if p.conservation_ok:
            _fail(name, f"expected false, got {p.to_dict()}")
            return
        if p.n_sell != 1 or p.n_unmatched_sell != 1 or p.n_buy != 0:
            _fail(name, f"counts {p.to_dict()}")
            return
        _ok(name)


def test_epoch_at_sell_ts_splits_first_rt() -> None:
    name = "epoch at SELL ts splits first RT (conservation false)"
    # Same first RT as live WORM; wrong anchor = SELL ts, not entry.
    sell_ts = "2026-08-29T09:53:10.049000+00:00"
    with tempfile.TemporaryDirectory() as td:
        worm = Path(td) / "paper_trades.worm.jsonl"
        _write_jsonl(
            worm,
            [
                {
                    "action": "SIM_FILL",
                    "side": "BUY",
                    "ts": OPTION_B_EXIT_EPOCH_TS,
                    "signal_id": "sig-32310",
                    "qty": "0.04",
                    "price": "2436.67",
                },
                {
                    "action": "SIM_FILL",
                    "side": "SELL",
                    "ts": sell_ts,
                    "entry_tick_ts": OPTION_B_EXIT_EPOCH_TS,
                    "signal_id": "sig-32310",
                    "qty": "0.04",
                    "price": "2436.67",
                    "exit_reason": "hold_expired",
                },
                {
                    "action": "SIM_FILL",
                    "side": "BUY",
                    "ts": "2026-08-30T15:30:17.309000+00:00",
                    "signal_id": "sig-1",
                    "qty": "0.04",
                    "price": "2478.24",
                },
            ],
        )
        wrong = pair_option_b_fills(worm, epoch_start_ts=sell_ts)
        if wrong.conservation_ok:
            _fail(name, f"SELL-anchored epoch must fail: {wrong.to_dict()}")
            return
        if wrong.n_pre_epoch_buys != 1 or wrong.n_unmatched_sell != 1:
            _fail(name, f"expected BUY in pre-epoch + unmatched SELL, got {wrong.to_dict()}")
            return
        right = pair_option_b_fills(worm)
        if not right.conservation_ok or right.n_buy != 2 or right.n_sell != 1 or right.n_open != 1:
            _fail(name, f"entry-anchored epoch should pass: {right.to_dict()}")
            return
        _ok(name)


def main() -> int:
    print("position abandoned / Option-B epoch pairing")
    test_payload_is_not_a_fill()
    test_legacy_restart_marker_is_abandon()
    test_epoch_pairing_conservation()
    test_restart_then_abandoned_not_double_counted()
    test_recover_writes_abandoned_not_sell()
    test_conservation_false_on_unmatched_sell()
    test_epoch_at_sell_ts_splits_first_rt()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    if _FAIL:
        print("POSITION_ABANDONED_FAIL")
        return 1
    print("POSITION_ABANDONED_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
