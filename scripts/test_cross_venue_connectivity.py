#!/usr/bin/env python3
"""Smoke: cross-venue connectivity (t_recv only, Pre-Reg FREIGABE).

Usage:
  PYTHONPATH=. python3 scripts/test_cross_venue_connectivity.py
  make raas-cross-venue-smoke
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.cross_venue import (  # noqa: E402
    CrossVenueMonitor,
    analyze_cross_venue_h2,
    assert_no_price_fields,
    load_jsonl,
    threshold_factor_ok,
    writer_liveness_status,
)
from prototypes.raas_paper_trading.feed import (  # noqa: E402
    CoinbaseMatchRecvFeed,
    coinbase_frame_is_match,
)

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


def _active_gaps_both() -> list:
    t = datetime.now(timezone.utc).isoformat()
    return [
        {"source": "heartbeat", "venue": "v1", "ts": t, "gap_start_recv_ts": t},
        {"source": "heartbeat", "venue": "v2", "ts": t, "gap_start_recv_ts": t},
    ]


def test_price_field_rejected() -> None:
    try:
        assert_no_price_fields({"venue": "v1", "price": 1.0})
        _fail("price_reject", "expected raise")
    except RuntimeError as e:
        if "cross_venue_price_forbidden" not in str(e):
            _fail("price_reject", str(e))
            return
        _ok("price field rejected on audit row")


def test_factor_gate() -> None:
    if not threshold_factor_ok(30, 30):
        _fail("factor", "30/30 should pass")
        return
    if threshold_factor_ok(30, 60):
        _fail("factor", "30/60 should fail (factor 2)")
        return
    if not threshold_factor_ok(30, 40):
        _fail("factor", "30/40 should pass (factor 1.33)")
        return
    _ok("threshold factor ≤1.5 gate")


def test_one_sided_gap_ln() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mon = CrossVenueMonitor.from_paths(
            gaps_path=root / "gaps.jsonl",
            slots_path=root / "slots.jsonl",
            state_path=root / "state.json",
            gap_dt_v1=30.0,
            gap_dt_v2=30.0,
            slot_s=10.0,
        )
        t0 = datetime(2026, 8, 29, 16, 0, 0, tzinfo=timezone.utc)
        # warm both venues
        mon.on_recv("v1", recv_ts=_iso(t0, 0))
        mon.on_recv("v2", recv_ts=_iso(t0, 0))
        mon.on_recv("v2", recv_ts=_iso(t0, 5))
        mon.on_recv("v2", recv_ts=_iso(t0, 10))
        # V1 gap 45s, V2 continues
        mon.on_recv("v1", recv_ts=_iso(t0, 45))
        mon.on_recv("v2", recv_ts=_iso(t0, 45))
        mon.flush_slots_to_now(now_ts=_iso(t0, 50))
        gaps = load_jsonl(root / "gaps.jsonl")
        v1_gaps = [g for g in gaps if g.get("venue") == "v1" and g.get("source") == "recv_gap"]
        if len(v1_gaps) != 1:
            _fail("ln", f"v1 gaps={v1_gaps}")
            return
        if any(k in v1_gaps[0] for k in ("price", "mid", "spread")):
            _fail("ln", "price leaked")
            return
        slots = load_jsonl(root / "slots.jsonl")
        cells = {s["cell"] for s in slots}
        if "LN" not in cells:
            _fail("ln", f"cells={cells} slots={slots[-5:]}")
            return
        _ok("one-sided V1 pause → LN cell + gap without price")


def test_ll_onset_skew() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mon = CrossVenueMonitor.from_paths(
            gaps_path=root / "gaps.jsonl",
            slots_path=root / "slots.jsonl",
            state_path=root / "state.json",
            gap_dt_v1=30.0,
            gap_dt_v2=30.0,
            slot_s=10.0,
        )
        t0 = datetime(2026, 8, 29, 17, 0, 0, tzinfo=timezone.utc)
        mon.on_recv("v1", recv_ts=_iso(t0, 0))
        mon.on_recv("v2", recv_ts=_iso(t0, 0))
        # both gap ~40s with 5s onset skew
        mon.on_recv("v1", recv_ts=_iso(t0, 40))
        mon.on_recv("v2", recv_ts=_iso(t0, 45))
        mon.flush_slots_to_now(now_ts=_iso(t0, 50))
        ll = [s for s in load_jsonl(root / "slots.jsonl") if s.get("cell") == "LL"]
        if not ll:
            _fail("onset", "no LL slots")
            return
        if any("onset_skew_s" not in s for s in ll):
            _fail("onset", "missing onset_skew_s")
            return
        if min(float(s["onset_skew_s"]) for s in ll) > 6.0:
            _fail("onset", f"skew too large {[s['onset_skew_s'] for s in ll]}")
            return
        _ok("LL slots carry onset_skew_s")


def test_h2_priority_v2_noise() -> None:
    slots = [{"cell": "NL"} for _ in range(15)] + [{"cell": "LN"} for _ in range(5)]
    # 20 disturbed, p_NL=0.75 → V2_NOISE first (requires gated observer)
    r = analyze_cross_venue_h2(
        slots, gaps=_active_gaps_both(), min_disturbed=20
    )
    if r["h2"] != "V2_NOISE":
        _fail("h2", f"{r}")
        return
    if r.get("observer_check") != "GATED":
        _fail("h2", f"expected GATED: {r}")
        return
    _ok("H2 priority V2_NOISE")


def test_h2_separable() -> None:
    slots = (
        [{"cell": "LN"} for _ in range(12)]
        + [{"cell": "NL"} for _ in range(6)]
        + [{"cell": "LL", "onset_skew_s": 1.0} for _ in range(2)]
    )
    r = analyze_cross_venue_h2(
        slots, gaps=_active_gaps_both(), min_disturbed=20
    )
    if r["h2"] != "SEPARABLE":
        _fail("separable", f"{r}")
        return
    _ok("H2 SEPARABLE when p_LL≤0.50")


def test_coinbase_match_parse() -> None:
    ok = coinbase_frame_is_match(
        json.dumps(
            {"type": "match", "product_id": "ETH-USD", "price": "999", "size": "1"}
        )
    )
    if not ok:
        _fail("cb", "match not detected")
        return
    # price in frame is fine — must not reach audit
    frames = [
        json.dumps({"type": "match", "product_id": "ETH-USD", "price": "1"}),
        json.dumps({"type": "subscriptions"}),
    ]
    pulses = list(CoinbaseMatchRecvFeed(frames=frames, product_id="ETH-USD"))
    if len(pulses) != 1 or pulses[0].venue != "v2":
        _fail("cb", f"pulses={pulses}")
        return
    if hasattr(pulses[0], "price"):
        _fail("cb", "RecvPulse must not expose price")
        return
    _ok("Coinbase match → RecvPulse without price attr")


def test_per_venue_heartbeat() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mon = CrossVenueMonitor.from_paths(
            gaps_path=root / "gaps.jsonl",
            slots_path=root / "slots.jsonl",
            state_path=root / "state.json",
        )
        row_v1 = mon.emit_heartbeat("v1")
        row_v2 = mon.emit_heartbeat("v2")
        if row_v1.get("source") != "heartbeat" or row_v2.get("venue") != "v2":
            _fail("heartbeat", f"v1={row_v1} v2={row_v2}")
            return
        gaps = load_jsonl(root / "gaps.jsonl")
        live_v1 = writer_liveness_status(gaps=gaps, venue="v1")
        live_v2 = writer_liveness_status(gaps=gaps, venue="v2")
        if live_v1.get("status") != "ACTIVE" or live_v2.get("status") != "ACTIVE":
            _fail("heartbeat", f"v1={live_v1} v2={live_v2}")
            return
        _ok("per-venue heartbeat → writer_liveness ACTIVE/quiet")


def test_h2_observer_down_blocks_verdict() -> None:
    slots = [{"cell": "NL"} for _ in range(15)] + [{"cell": "LN"} for _ in range(5)]
    # Without gaps: NOT_GATED — no clean H2 verdict (not blind V2_NOISE)
    r0 = analyze_cross_venue_h2(slots, min_disturbed=20)
    if r0["h2"] != "UNVERIFIED" or r0.get("observer_check") != "NOT_GATED":
        _fail("observer0", str(r0))
        return
    # Empty gaps: both observers missing → OBSERVER_DOWN not V2_NOISE
    r1 = analyze_cross_venue_h2(slots, gaps=[], min_disturbed=20)
    if r1["h2"] != "OBSERVER_DOWN":
        _fail("observer1", str(r1))
        return
    if r1.get("h0_measurable"):
        _fail("observer1", "h0 should be false")
        return
    _ok("UNVERIFIED without gaps; OBSERVER_DOWN before V2_NOISE when heartbeat missing")


def test_restart_marker_seeds_liveness() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mon = CrossVenueMonitor.from_paths(
            gaps_path=root / "gaps.jsonl",
            slots_path=root / "slots.jsonl",
            state_path=root / "state.json",
        )
        gaps = load_jsonl(root / "gaps.jsonl")
        rm = [g for g in gaps if g.get("source") == "restart_marker"]
        if len(rm) != 2:
            _fail("restart", f"expected 2 restart markers, got {rm}")
            return
        for venue in ("v1", "v2"):
            live = writer_liveness_status(gaps=gaps, venue=venue)
            if live.get("status") != "ACTIVE" or live.get("mode") != "restart_only":
                _fail("restart", f"{venue}={live}")
                return
        _ = mon  # monitor constructed
        _ok("restart_marker on from_paths → ACTIVE restart_only (no false OBSERVER_DOWN)")


def main() -> int:
    print("=== cross-venue connectivity smoke ===")
    test_price_field_rejected()
    test_factor_gate()
    test_one_sided_gap_ln()
    test_ll_onset_skew()
    test_h2_priority_v2_noise()
    test_h2_separable()
    test_coinbase_match_parse()
    test_per_venue_heartbeat()
    test_h2_observer_down_blocks_verdict()
    test_restart_marker_seeds_liveness()
    print(f"--- {_PASS} passed, {_FAIL} failed ---")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
