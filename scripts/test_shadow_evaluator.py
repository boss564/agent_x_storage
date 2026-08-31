#!/usr/bin/env python3
"""Smoke S1–S4 — shadow evaluator (fixtures only, no live exports)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.shadow_evaluator import (  # noqa: E402
    DEFAULT_FREEZE_K,
    ShadowEvalWriter,
    VALID_DECISIONS,
    _hash_file,
    evaluate_edge,
    run_once,
)


def _ok(name: str) -> None:
    print(f"OK {name}")


def _fail(name: str, msg: str) -> None:
    print(f"FAIL {name}: {msg}")
    raise SystemExit(1)


def _fixture_edge(
    *,
    edge_id: str = "fix-edge-1",
    pnl_eur: str = "0.50",
    exit_ts: str = "2026-08-31T12:00:00+00:00",
) -> dict:
    return {
        "edge_id": edge_id,
        "entry_price": "2000",
        "exit_price": "2010",
        "pnl_eur": pnl_eur,
        "hold_seconds_target": DEFAULT_FREEZE_K,
        "hold_seconds_actual": float(DEFAULT_FREEZE_K),
        "hold_seconds_delta": 0.0,
        "exit_reason": "hold_expired",
        "entry_tick_ts": "2026-08-29T10:00:00+00:00",
        "exit_tick_ts": exit_ts,
        "live_execution": False,
        "order_send": False,
    }


def _write_edges(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def test_s1_valid_decision_enum() -> None:
    name = "S1 shadow_gate_decision enum"
    edge = _fixture_edge()
    row = evaluate_edge(
        edge,
        regime_flag=0,
        classified_regime="STABLE",
        returns=[],
        news_rows=[],
        gap_rows=[],
    )
    if row.get("shadow_gate_decision") not in VALID_DECISIONS:
        _fail(name, str(row.get("shadow_gate_decision")))
    _ok(name)


def test_s2_append_two_lines() -> None:
    name = "S2 two append lines"
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "shadow_eval.jsonl"
        w = ShadowEvalWriter(out)
        base = evaluate_edge(
            _fixture_edge(edge_id="a"),
            regime_flag=0,
            classified_regime=None,
            returns=[],
        )
        w.append(base)
        w.append(evaluate_edge(_fixture_edge(edge_id="b"), regime_flag=0, returns=[]))
        lines = [ln for ln in out.read_text().splitlines() if ln.strip()]
        if len(lines) != 2:
            _fail(name, f"lines={len(lines)}")
        second = json.loads(lines[1])
        if not second.get("prev_hash") or not second.get("hash"):
            _fail(name, "hash chain missing on second line")
        _ok(name)


def test_s3_edges_file_unchanged() -> None:
    name = "S3 paper_edges hash unchanged"
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        edges = root / "audit" / "paper_edges.jsonl"
        news = root / "phase_signals" / "news_sentiment.jsonl"
        gap = root / "phase_signals" / "price_gap.jsonl"
        _write_edges(edges, [_fixture_edge()])
        news.parent.mkdir(parents=True, exist_ok=True)
        news.write_text("", encoding="utf-8")
        gap.write_text("", encoding="utf-8")
        before = _hash_file(edges)
        run_once(
            edges_path=edges,
            out_path=root / "audit" / "shadow_eval.jsonl",
            news_path=news,
            gap_path=gap,
            regime_flag=0,
        )
        after = _hash_file(edges)
        if before != after:
            _fail(name, "paper_edges.jsonl mutated")
        _ok(name)


def test_s4_reject_order_send_true() -> None:
    name = "S4 reject order_send true"
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "shadow_eval.jsonl"
        w = ShadowEvalWriter(out)
        bad = evaluate_edge(_fixture_edge(), regime_flag=0, returns=[])
        bad["order_send"] = True
        try:
            w.append(bad)
            _fail(name, "expected RuntimeError")
        except RuntimeError:
            _ok(name)


def test_g1_blocks_data_audit() -> None:
    name = "G1 guard blocks /data/audit without pass"
    with tempfile.TemporaryDirectory() as td:
        live = Path("/data/audit/paper_edges.jsonl")
        if not live.parent.exists():
            _ok(f"{name} (skip — no /data/audit on host)")
            return
        try:
            run_once(
                edges_path=live,
                out_path=Path(td) / "shadow_eval.jsonl",
                news_path=Path(td) / "news.jsonl",
                gap_path=Path(td) / "gap.jsonl",
            )
            _fail(name, "expected SystemExit")
        except SystemExit:
            _ok(name)


def main() -> int:
    test_s1_valid_decision_enum()
    test_s2_append_two_lines()
    test_s3_edges_file_unchanged()
    test_s4_reject_order_send_true()
    test_g1_blocks_data_audit()
    print("ALL shadow_evaluator smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
