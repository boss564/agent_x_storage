"""Price-gap PhaseSource — fixture JSONL, no live HTTP, zero cluster."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from astrocore.sources.config import GAP_PROVIDER_ID, GAP_SCALE_1H, GAP_SCALE_24H
from astrocore.sources.price_gap_source import (
    build_phase_signal,
    compute_coverage_scores,
    event_phase_bias,
    load_recent_events,
    run_once,
)

NOW = datetime(2026, 8, 30, 16, 0, tzinfo=timezone.utc)


def _write_jsonl(path: Path, rows: list) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def sample_rows() -> list:
    return [
        {
            "schema": "swarm_gap/v1",
            "ts": (NOW - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "kind": "COVERAGE_GAP",
            "asset": "BTC",
            "pct_1h": 6.2,
            "pct_24h": 2.0,
            "window": "1h",
        },
        {
            "schema": "swarm_gap/v1",
            "ts": (NOW - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "kind": "COVERAGE_GAP",
            "asset": "ETH",
            "pct_1h": 1.0,
            "pct_24h": 9.1,
            "window": "24h",
        },
        {
            "schema": "swarm_gap/v1",
            "ts": (NOW - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "kind": "UNTRACKED_ENTITY",
            "asset": "HYPER",
            "count": 4,
        },
        {
            "schema": "swarm_gap/v1",
            "ts": (NOW - timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "kind": "COVERAGE_GAP",
            "asset": "XRP",
            "pct_1h": 12.0,
            "pct_24h": 1.0,
            "window": "1h",
        },
        {
            "kind": "run_marker",
            "ts": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "coverage_gaps": 0,
        },
    ]


def test_load_recent_skips_marker_and_lookback():
    root = Path(tempfile.mkdtemp())
    path = root / "gap_reports.jsonl"
    _write_jsonl(path, sample_rows())
    entries = load_recent_events(path, lookback_hours=24, now=NOW)
    kinds = {(e["kind"], e.get("asset")) for e in entries}
    assert ("COVERAGE_GAP", "BTC") in kinds
    assert ("COVERAGE_GAP", "ETH") in kinds
    assert ("UNTRACKED_ENTITY", "HYPER") in kinds
    assert ("COVERAGE_GAP", "XRP") not in kinds
    assert all(e.get("kind") != "run_marker" for e in entries)


def test_window_1h_is_not_substring_of_24h():
    only_24 = {
        "kind": "COVERAGE_GAP",
        "asset": "ETH",
        "pct_1h": 99.0,
        "pct_24h": 9.1,
        "window": "24h",
    }
    bias = event_phase_bias(only_24)
    assert abs(bias - 9.1 / GAP_SCALE_24H) < 1e-6
    both = {
        "kind": "COVERAGE_GAP",
        "asset": "BTC",
        "pct_1h": 6.2,
        "pct_24h": 20.0,
        "window": "1h+24h",
    }
    assert abs(event_phase_bias(both) - 6.2 / GAP_SCALE_1H) < 1e-6


def test_clip_and_sign():
    clipped = event_phase_bias(
        {"window": "1h", "pct_1h": -25.0, "pct_24h": 0.0}
    )
    assert clipped == -1.0
    assert GAP_SCALE_1H == 10.0
    assert GAP_SCALE_24H == 16.0


def test_untracked_not_sprayed():
    scores = compute_coverage_scores(sample_rows()[:4])
    assert "HYPER" not in scores
    assert "BTC" in scores
    assert "ETH" in scores
    assert "_overall" in scores
    assert abs(scores["BTC"] - 6.2 / GAP_SCALE_1H) < 1e-6
    assert abs(scores["ETH"] - 9.1 / GAP_SCALE_24H) < 1e-6


def test_build_phase_signal_schema():
    signal = build_phase_signal("BTC", 0.62, confidence=0.9, metadata={"extra": "test"})
    required = {"timestamp", "provider", "phase_bias", "confidence", "metadata"}
    assert required.issubset(signal.keys())
    assert signal["provider"] == GAP_PROVIDER_ID
    assert -1.0 <= signal["phase_bias"] <= 1.0
    assert signal["order_send"] is False
    assert signal["metadata"]["asset"] == "BTC"
    clipped = build_phase_signal("ETH", 2.0)
    assert clipped["phase_bias"] == 1.0


def test_run_once_empty_and_signals():
    root = Path(tempfile.mkdtemp())
    empty = run_once(jsonl_path=root / "missing.jsonl", now=NOW)
    assert empty["status"] == "empty"
    assert empty["signals"] == []
    path = root / "gap_reports.jsonl"
    _write_jsonl(path, sample_rows())
    result = run_once(jsonl_path=path, lookback_hours=24, now=NOW)
    assets = {s["metadata"]["asset"] for s in result["signals"]}
    assert "BTC" in assets
    assert "ETH" in assets
    assert "OVERALL" in assets
    assert "HYPER" not in assets
    assert "XRP" not in assets
    assert result["n_untracked"] == 1
    assert all(s["order_send"] is False for s in result["signals"])


def test_append_jsonl_and_run_marker():
    root = Path(tempfile.mkdtemp())
    gaps = root / "gap_reports.jsonl"
    _write_jsonl(gaps, sample_rows())
    out = root / "phase_signals" / "price_gap.jsonl"
    first = run_once(jsonl_path=gaps, lookback_hours=24, now=NOW, output_jsonl=out)
    assert first["run_marker"] is True
    lines1 = out.read_text(encoding="utf-8").strip().splitlines()
    assert any(json.loads(ln).get("kind") == "run_marker" for ln in lines1)
    assert any(json.loads(ln).get("provider") == GAP_PROVIDER_ID for ln in lines1)
    run_once(jsonl_path=gaps, lookback_hours=24, now=NOW, output_jsonl=out)
    lines2 = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines2) == 2 * len(lines1)
    quiet = [{"kind": "run_marker", "ts": NOW.strftime("%Y-%m-%dT%H:%M:%SZ")}]
    empty_in = root / "quiet.jsonl"
    empty_out = root / "phase_signals" / "empty.jsonl"
    _write_jsonl(empty_in, quiet)
    empty = run_once(jsonl_path=empty_in, now=NOW, output_jsonl=empty_out)
    assert empty["status"] == "empty"
    assert empty["signals"] == []
    marker_only = [json.loads(ln) for ln in empty_out.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(marker_only) == 1
    assert marker_only[0]["kind"] == "run_marker"


def test_handoff_rejects_writeback():
    root = Path(tempfile.mkdtemp())
    gaps = root / "gap_reports.jsonl"
    _write_jsonl(gaps, sample_rows())
    before = gaps.read_text(encoding="utf-8")
    try:
        run_once(jsonl_path=gaps, now=NOW, output_jsonl=gaps)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "order_send_forbidden" in str(exc)
    try:
        run_once(
            jsonl_path=gaps,
            now=NOW,
            output_jsonl=root / "phase_signals" / "gap_reports.jsonl",
        )
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "order_send_forbidden" in str(exc)
    try:
        run_once(jsonl_path=gaps, now=NOW, output_jsonl=root / "derived.jsonl")
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "phase_signals" in str(exc)
    assert gaps.read_text(encoding="utf-8") == before


if __name__ == "__main__":
    test_load_recent_skips_marker_and_lookback()
    test_window_1h_is_not_substring_of_24h()
    test_clip_and_sign()
    test_untracked_not_sprayed()
    test_build_phase_signal_schema()
    test_run_once_empty_and_signals()
    test_append_jsonl_and_run_marker()
    test_handoff_rejects_writeback()
    print("OK: test_phase_source_price_gap 8/8")
