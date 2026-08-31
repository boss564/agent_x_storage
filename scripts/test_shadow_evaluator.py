#!/usr/bin/env python3
"""Smoke S1–S4 — shadow evaluator (fixtures only, no live exports)."""
from __future__ import annotations

import json
import os
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
    _guard_g1,
    _hash_file,
    evaluate_edge,
    is_live_export_path,
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


def test_a1_blocked() -> None:
    name = "A1 regime_flag=0 → BLOCKED, Kelly null"
    rets = [0.01] * 50
    row = evaluate_edge(_fixture_edge(), regime_flag=0, classified_regime="STABLE", returns=rets)
    if row.get("shadow_gate_decision") != "BLOCKED":
        _fail(name, f"decision={row.get('shadow_gate_decision')}")
    for key in ("p", "b", "kelly_fraction_computed", "kelly_fraction_p05"):
        if row.get(key) is not None:
            _fail(name, f"{key} should be null")
    _ok(name)


def test_a2_insufficient() -> None:
    name = "A2 INSUFFICIENT_HISTORY (nw/nl/n)"
    edge = _fixture_edge()
    cases = [
        ("n<50", [0.0] * 10, "INSUFFICIENT_HISTORY"),
        ("nw<5", [0.01] * 4 + [-0.01] * 46, "INSUFFICIENT_HISTORY"),
        ("nl<5", [0.01] * 46 + [-0.01] * 4, "INSUFFICIENT_HISTORY"),
    ]
    for label, rets, expected in cases:
        row = evaluate_edge(edge, regime_flag=1, returns=rets)
        if row.get("shadow_gate_decision") != expected:
            _fail(name, f"{label}: {row.get('shadow_gate_decision')}")
        if row.get("kelly_fraction_computed") is not None:
            _fail(name, f"{label}: kelly should be null")
    _ok(name)


def test_a3_kelly_sign_uncertain() -> None:
    name = "A3 f*_p05≤0 → KELLY_SIGN_UNCERTAIN"
    rets = [0.01] * 5 + [-0.01] * 45
    row = evaluate_edge(_fixture_edge(), regime_flag=1, classified_regime="STABLE", returns=rets)
    if row.get("shadow_gate_decision") != "KELLY_SIGN_UNCERTAIN":
        _fail(name, f"decision={row.get('shadow_gate_decision')}")
    if row.get("kelly_sign_uncertain") is not True:
        _fail(name, "kelly_sign_uncertain not true")
    if row.get("shadow_gate_decision") in ("LIMIT_OK", "LIMIT_EXCEEDED"):
        _fail(name, "must not emit LIMIT_* when p05≤0")
    _ok(name)


def test_g1_blocks_repo_relative_audit() -> None:
    name = "G1 blocks repo data/audit relative path"
    p = _ROOT / "data" / "audit" / "paper_edges.jsonl"
    if not is_live_export_path(p):
        _fail(name, "is_live_export_path should be true")
    try:
        _guard_g1([p])
        _fail(name, "expected SystemExit")
    except SystemExit:
        _ok(name)


def test_g1_blocks_paper_edges_path_env() -> None:
    name = "G1 blocks PAPER_EDGES_PATH"
    target = _ROOT / "data" / "audit" / "paper_edges.jsonl"
    os.environ["PAPER_EDGES_PATH"] = str(target)
    try:
        if not is_live_export_path(target):
            _fail(name, "PAPER_EDGES_PATH not flagged")
        try:
            _guard_g1([target])
            _fail(name, "expected SystemExit")
        except SystemExit:
            _ok(name)
    finally:
        os.environ.pop("PAPER_EDGES_PATH", None)


def test_g1_allows_temp_fixture() -> None:
    name = "G1 allows tempfile fixture paths"
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "audit" / "paper_edges.jsonl"
        if is_live_export_path(p):
            _fail(name, "temp path flagged as live")
        _guard_g1([p])
        _ok(name)


def test_g1_pass_env_allows_live() -> None:
    name = "G1 SHADOW_EVAL_G1_PASS=1 bypass"
    p = _ROOT / "data" / "audit" / "paper_edges.jsonl"
    os.environ["SHADOW_EVAL_G1_PASS"] = "1"
    try:
        _guard_g1([p])
        _ok(name)
    finally:
        os.environ.pop("SHADOW_EVAL_G1_PASS", None)


def test_g1_blocks_data_audit_absolute() -> None:
    name = "G1 blocks /data/audit absolute path"
    live = Path("/data/audit/paper_edges.jsonl")
    if not is_live_export_path(live):
        _fail(name, "/data path not flagged")
    try:
        _guard_g1([live])
        _fail(name, "expected SystemExit")
    except SystemExit:
        _ok(name)


def main() -> int:
    test_s1_valid_decision_enum()
    test_s2_append_two_lines()
    test_s3_edges_file_unchanged()
    test_s4_reject_order_send_true()
    test_a1_blocked()
    test_a2_insufficient()
    test_a3_kelly_sign_uncertain()
    test_g1_blocks_repo_relative_audit()
    test_g1_blocks_paper_edges_path_env()
    test_g1_allows_temp_fixture()
    test_g1_pass_env_allows_live()
    test_g1_blocks_data_audit_absolute()
    print("ALL shadow_evaluator smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
