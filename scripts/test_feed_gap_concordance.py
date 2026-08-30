#!/usr/bin/env python3
"""Smoke: feed-gap JSONL + socket layer + H_inv / H2 (Pre-Reg FREIGABE).

Usage:
  PYTHONPATH=. python3 scripts/test_feed_gap_concordance.py
  make raas-feed-gap-smoke
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.feed import PaperTick  # noqa: E402
from prototypes.raas_paper_trading.feed_gap import (  # noqa: E402
    FeedGapMonitor,
    analyze_concordance,
    audit_gap_writer_against_worm,
    load_gaps,
    render_feed_gap_metrics_text,
    reset_feed_gap_prom_metrics,
    writer_liveness_status,
)
from prototypes.raas_paper_trading.regime_swarm.worm_fixtures import write_signal_worm  # noqa: E402
from prototypes.raas_paper_trading.ledger import PaperLedger  # noqa: E402
from prototypes.raas_paper_trading.paper_edge_sample import load_edges  # noqa: E402
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


def _iso(base: datetime, offset_s: float) -> str:
    return (base + timedelta(seconds=offset_s)).isoformat()


def test_tick_spacing_gap_schema() -> None:
    reset_feed_gap_prom_metrics()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mon = FeedGapMonitor.from_paths(
            gaps_path=root / "feed_gaps.jsonl",
            state_path=root / "feed_gap_state.json",
            gap_dt_s=30.0,
            emit_restart_marker=True,
        )
        t0 = datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc)
        mon.on_tick(tick_ts=_iso(t0, 0), fsm_state="HOLDING", position_open=True)
        mon.on_tick(
            tick_ts=_iso(t0, 45),
            fsm_state="EXIT_PENDING",
            position_open=True,
            hold_deadline_ts=_iso(t0, 10),
            round_trip_id="sig-1",
        )
        rows = load_gaps(root / "feed_gaps.jsonl")
        sources = [r["source"] for r in rows]
        if "restart_marker" not in sources:
            _fail("schema", "missing restart_marker")
            return
        tick_gaps = [r for r in rows if r["source"] == "tick_spacing"]
        if len(tick_gaps) != 1:
            _fail("schema", f"expected 1 tick_spacing, got {len(tick_gaps)}")
            return
        g = tick_gaps[0]
        for key in (
            "gap_start_ts",
            "gap_end_ts",
            "gap_duration_s",
            "in_exit_window",
            "exit_window_start",
            "round_trip_id",
            "gap_dt_threshold_s",
            "hash",
            "prev_hash",
        ):
            if key not in g:
                _fail("schema", f"missing {key}")
                return
        if abs(float(g["gap_duration_s"]) - 45.0) > 0.01:
            _fail("schema", f"duration {g['gap_duration_s']}")
            return
        if g["gap_dt_threshold_s"] != 30.0:
            _fail("schema", "threshold")
            return
        if g.get("live_execution") is not False:
            _fail("schema", "live_execution")
            return
        text = render_feed_gap_metrics_text()
        if 'feed_gap_events_total{source="tick_spacing"}' not in text:
            _fail("schema", "prometheus text")
            return
        _ok("tick_spacing gap schema + prom ops text")


def test_restart_persists_last_tick() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        gaps = root / "feed_gaps.jsonl"
        state = root / "feed_gap_state.json"
        t0 = datetime(2026, 8, 29, 13, 0, 0, tzinfo=timezone.utc)
        mon1 = FeedGapMonitor.from_paths(
            gaps_path=gaps, state_path=state, gap_dt_s=30.0, emit_restart_marker=True
        )
        mon1.on_tick(tick_ts=_iso(t0, 0), fsm_state="HOLDING", position_open=True)
        # Simulate pod restart: new monitor, same state file
        mon2 = FeedGapMonitor.from_paths(
            gaps_path=gaps, state_path=state, gap_dt_s=30.0, emit_restart_marker=True
        )
        mon2.on_tick(tick_ts=_iso(t0, 120), fsm_state="EXIT_PENDING", position_open=True)
        tick_gaps = [r for r in load_gaps(gaps) if r["source"] == "tick_spacing"]
        if len(tick_gaps) != 1 or float(tick_gaps[0]["gap_duration_s"]) < 100:
            _fail("restart", f"gaps={tick_gaps}")
            return
        markers = [r for r in load_gaps(gaps) if r["source"] == "restart_marker"]
        if len(markers) < 2:
            _fail("restart", f"markers={len(markers)}")
            return
        _ok("pod restart preserves last_tick_ts → tick_spacing gap")


def test_socket_independent_of_tick() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mon = FeedGapMonitor.from_paths(
            gaps_path=root / "g.jsonl",
            state_path=root / "s.json",
            gap_dt_s=30.0,
            emit_restart_marker=False,
        )
        t0 = datetime(2026, 8, 29, 14, 0, 0, tzinfo=timezone.utc)
        mon.on_socket_disconnect(ts=_iso(t0, 0))
        mon.on_socket_reconnect(ts=_iso(t0, 5), fsm_state="HOLDING", position_open=True)
        # No tick gap — only socket (fast reconnect < 30s still recorded)
        rows = [r for r in load_gaps(root / "g.jsonl") if r["source"] == "socket"]
        if len(rows) != 1:
            _fail("socket", f"rows={rows}")
            return
        if abs(float(rows[0]["gap_duration_s"]) - 5.0) > 0.01:
            _fail("socket", "duration")
            return
        _ok("socket disconnect/reconnect without tick_spacing")


def test_h_inv_and_h2_concordance() -> None:
    """Synthetic edges + gaps: invariant holds; socket≈tick hits."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # One RT: entry 0, k=100, exit at 160 → delta=60 > 30 → hold_delta_exceeded
        entry = "2026-08-29T10:00:00+00:00"
        deadline = "2026-08-29T10:01:40+00:00"  # +100s
        exit_ts = "2026-08-29T10:02:40+00:00"  # +160s
        edge = {
            "edge_id": "e1",
            "entry_tick_ts": entry,
            "exit_tick_ts": exit_ts,
            "hold_seconds_actual": 160.0,
            "hold_seconds_target": 100,
            "hold_seconds_delta": 60.0,
            "exit_reason": "hold_expired",
            "live_execution": False,
            "order_send": False,
        }
        edges_path = root / "edges.jsonl"
        edges_path.write_text(json.dumps(edge) + "\n", encoding="utf-8")

        gaps_path = root / "gaps.jsonl"
        # Tick gap overlapping [deadline, exit]
        tick_gap = {
            "source": "tick_spacing",
            "gap_start_ts": "2026-08-29T10:01:00+00:00",
            "gap_end_ts": exit_ts,
            "gap_duration_s": 100.0,
            "symbol": "ETHUSDT",
        }
        sock_gap = {
            "source": "socket",
            "gap_start_ts": "2026-08-29T10:01:30+00:00",
            "gap_end_ts": "2026-08-29T10:02:10+00:00",
            "gap_duration_s": 40.0,
            "symbol": "ETHUSDT",
        }
        gaps_path.write_text(
            json.dumps(tick_gap) + "\n" + json.dumps(sock_gap) + "\n",
            encoding="utf-8",
        )
        report = analyze_concordance(
            gaps=load_gaps(gaps_path),
            edges=load_edges(edges_path),
            freeze_k=100,
            max_delta_s=30.0,
        )
        if report["n_hold_delta_exceeded"] != 1:
            _fail("concordance", f"delta={report}")
            return
        if report["n_gap_exit_window_hits_tick"] != 1:
            _fail("concordance", f"tick hits={report}")
            return
        if report["h_inv"] != "HOLD":
            _fail("concordance", f"h_inv={report['h_inv']}")
            return
        if report["h2"] != "CONCORDANT":
            _fail("concordance", f"h2={report}")
            return
        if report["h1"] != "CONFIRMED":
            _fail("concordance", f"h1={report['h1']}")
            return
        _ok("H_inv HOLD + H2 CONCORDANT + H1 CONFIRMED")


def test_h_inv_broken_detectable() -> None:
    """Delta exceeded without tick window hit → BROKEN (instrument error)."""
    edge = {
        "edge_id": "e2",
        "entry_tick_ts": "2026-08-29T11:00:00+00:00",
        "exit_tick_ts": "2026-08-29T11:02:00+00:00",
        "hold_seconds_actual": 120.0,
        "hold_seconds_target": 60,
        "hold_seconds_delta": 60.0,
        "exit_reason": "hold_expired",
    }
    report = analyze_concordance(gaps=[], edges=[edge], freeze_k=60, max_delta_s=30.0)
    if report["h_inv"] != "BROKEN":
        _fail("broken", f"{report}")
        return
    _ok("H_inv BROKEN when delta without tick window hit")


def test_runner_writes_gap_on_pause() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        worm = PaperWormLog(tenant_id="t", run_id="gap-smoke", data_root=root / "worm")
        runner = PaperTradingRunner(
            tenant_id="t",
            run_id="gap-smoke",
            ledger=PaperLedger(starting_balance_eur=Decimal("1000")),
            worm=worm,
            attach_orderbook=False,
            exit_mode="time_hold",
            hold_seconds=10,
            gap_dt_s=30.0,
            max_wait_s=50.0,
            position_state_path=root / "state" / "paper_position.json",
            edges_path=root / "audit" / "paper_edges.jsonl",
            feed_gaps_path=root / "audit" / "feed_gaps.jsonl",
            feed_gap_state_path=root / "state" / "feed_gap_state.json",
            enable_feed_gap=True,
            shadow_notional_eur=Decimal("100"),
        )
        t0 = datetime(2026, 8, 29, 15, 0, 0, tzinfo=timezone.utc)
        runner.on_tick(PaperTick("ETHUSDT", _iso(t0, 0), 2000.0, "replay"))
        runner.on_tick(PaperTick("ETHUSDT", _iso(t0, 5), 2001.0, "replay"))
        runner.on_tick(PaperTick("ETHUSDT", _iso(t0, 50), 2002.0, "replay"))
        gaps = [r for r in load_gaps(root / "audit" / "feed_gaps.jsonl") if r["source"] == "tick_spacing"]
        if len(gaps) != 1:
            _fail("runner", f"gaps={gaps}")
            return
        _ok("runner emits tick_spacing gap after >30s pause")


def test_heartbeat_writer_liveness() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mon = FeedGapMonitor.from_paths(
            gaps_path=root / "feed_gaps.jsonl",
            state_path=root / "feed_gap_state.json",
            emit_restart_marker=False,
        )
        row = mon.emit_heartbeat()
        if row.get("source") != "heartbeat":
            _fail("heartbeat", str(row))
            return
        live = writer_liveness_status(gaps_path=root / "feed_gaps.jsonl")
        if live.get("status") != "ACTIVE" or live.get("mode") != "quiet":
            _fail("heartbeat", str(live))
            return
        _ok("heartbeat → writer_liveness ACTIVE/quiet")


def test_worm_null_gaps_and_writer_failed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        worm = root / "worm.jsonl"
        t0 = datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc)
        lines = []
        for i in range(5):
            lines.append(
                json.dumps(
                    {
                        "action": "SIGNAL",
                        "ts": _iso(t0, i * 5),
                        "mark_price": "100.0",
                        "symbol": "ETHUSDT",
                    }
                )
            )
        worm.write_text("\n".join(lines) + "\n", encoding="utf-8")

        gaps_path = root / "feed_gaps.jsonl"
        mon = FeedGapMonitor.from_paths(
            gaps_path=gaps_path,
            state_path=root / "state.json",
            emit_restart_marker=True,
        )
        audit_ok = audit_gap_writer_against_worm(gaps=load_gaps(gaps_path), worm_path=worm)
        if not audit_ok.get("null_gaps_proven"):
            _fail("worm_null", str(audit_ok))
            return
        if audit_ok.get("writer_failed"):
            _fail("worm_null", "unexpected writer_failed")
            return

        # Gap >30s in WORM without tick_spacing line → writer_failed
        worm2 = root / "worm2.jsonl"
        write_signal_worm(worm2, [100.0] * 3, symbol="ETHUSDT")
        # append signals with 60s gap manually
        extra = [
            {"action": "SIGNAL", "ts": _iso(t0, 0), "mark_price": "100", "symbol": "ETHUSDT"},
            {"action": "SIGNAL", "ts": _iso(t0, 65), "mark_price": "100", "symbol": "ETHUSDT"},
        ]
        worm2.write_text("\n".join(json.dumps(r) for r in extra) + "\n", encoding="utf-8")
        audit_bad = audit_gap_writer_against_worm(gaps=load_gaps(gaps_path), worm_path=worm2)
        if not audit_bad.get("writer_failed"):
            _fail("worm_writer", str(audit_bad))
            return
        report = analyze_concordance(gaps=load_gaps(gaps_path), edges=[], worm_audit=audit_ok)
        if report.get("h0_branch") != "gap_jsonl" and not report.get("null_gaps_proven"):
            _fail("h0_branch", str(report))
            return
        _ok("worm null-gaps proven + writer_failed on missing tick_spacing")


def test_worm_restart_span_unobservable() -> None:
    """Pod-Restart: großer WORM-Δt ohne tick_spacing ist unbeobachtbar, kein writer_failed."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        worm = root / "worm_restart.jsonl"
        t0 = datetime(2026, 8, 29, 13, 0, 0, tzinfo=timezone.utc)
        lines = [
            json.dumps(
                {"action": "SIGNAL", "ts": _iso(t0, 0), "mark_price": "100", "symbol": "ETHUSDT"}
            ),
            json.dumps(
                {"action": "SIGNAL", "ts": _iso(t0, 5), "mark_price": "100", "symbol": "ETHUSDT"}
            ),
            json.dumps(
                {"action": "SIGNAL", "ts": _iso(t0, 125), "mark_price": "100", "symbol": "ETHUSDT"}
            ),
        ]
        worm.write_text("\n".join(lines) + "\n", encoding="utf-8")

        gaps_path = root / "feed_gaps.jsonl"
        mon = FeedGapMonitor.from_paths(
            gaps_path=gaps_path,
            state_path=root / "state.json",
            emit_restart_marker=False,
        )
        mon.log.append(
            {
                "source": "restart_marker",
                "ts": _iso(t0, 60),
                "gap_start_ts": _iso(t0, 60),
                "gap_end_ts": None,
                "gap_duration_s": None,
                "gap_dt_threshold_s": 30.0,
            }
        )

        audit = audit_gap_writer_against_worm(gaps=load_gaps(gaps_path), worm_path=worm)
        if audit.get("writer_failed"):
            _fail("restart_unobs", f"unexpected writer_failed: {audit}")
            return
        if audit.get("n_unobservable_spacings") != 1:
            _fail("restart_unobs", f"n_unobservable={audit.get('n_unobservable_spacings')}")
            return
        if audit.get("null_gaps_proven"):
            _fail("restart_unobs", f"null_gaps_proven despite low coverage: {audit}")
            return
        if not audit.get("insufficient_coverage"):
            _fail("restart_unobs", f"expected insufficient_coverage: {audit}")
            return
        if "INSUFFICIENT_COVERAGE" not in str(audit.get("coverage_summary", "")):
            _fail("restart_unobs", str(audit.get("coverage_summary")))
            return
        _ok("restart-spanning WORM gap → unobservable, INSUFFICIENT_COVERAGE not null_gaps")


def test_insufficient_coverage_blocks_h0_worm_branch() -> None:
    worm_audit = {
        "null_gaps_proven": False,
        "insufficient_coverage": True,
        "coverage_fraction": 0.001,
        "min_observable_fraction": 0.80,
    }
    report = analyze_concordance(gaps=[], edges=[{"hold_seconds_target": 4966, "exit_reason": "hold_expired", "exit_tick_ts": "2026-08-30T00:00:00+00:00"}], worm_audit=worm_audit)
    if report.get("h0_measurable"):
        _fail("h0_insuff", str(report))
        return
    if report.get("h0_branch") != "insufficient_coverage":
        _fail("h0_insuff", f"branch={report.get('h0_branch')}")
        return
    _ok("INSUFFICIENT_COVERAGE → h0_branch insufficient_coverage, H0 false")


def main() -> int:
    print("=== feed-gap concordance smoke ===")
    test_tick_spacing_gap_schema()
    test_restart_persists_last_tick()
    test_socket_independent_of_tick()
    test_h_inv_and_h2_concordance()
    test_h_inv_broken_detectable()
    test_runner_writes_gap_on_pause()
    test_heartbeat_writer_liveness()
    test_worm_null_gaps_and_writer_failed()
    test_worm_restart_span_unobservable()
    test_insufficient_coverage_blocks_h0_worm_branch()
    print(f"--- {_PASS} passed, {_FAIL} failed ---")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
