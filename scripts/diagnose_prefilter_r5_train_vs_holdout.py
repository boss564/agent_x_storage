#!/usr/bin/env python3
"""§4.3.1 R5 — isolate training size vs holdout size.

Condition A: train fixed 5k; holdout 1000 vs 4000 (nested from same reservoir).
Condition B: holdout fixed 1000; train 5k vs train (20k − holdout).

Same sim params / seeds as seed-spread. No feature calibration.

Usage:
  PYTHONPATH=. python3 scripts/diagnose_prefilter_r5_train_vs_holdout.py
  make raas-prefilter-r5-train-vs-holdout
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load(name: str, rel: str):
    path = _ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _summarize(spread: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "verdict": spread.get("verdict"),
        "mean": spread.get("improvement_vs_fifo_mean"),
        "std": spread.get("improvement_vs_fifo_std"),
        "n_train": spread.get("n_train"),
        "n_holdout": spread.get("n_holdout"),
        "n_risky": (spread.get("runs") or [{}])[0].get("n_risky"),
        "per_seed": spread.get("improvement_vs_fifo_per_seed"),
        "seeds": spread.get("seeds"),
    }


def _reading(cond_a: Dict[str, Any], cond_b: Dict[str, Any]) -> str:
    m_a1 = float(cond_a["holdout_1000"]["mean"])
    m_a4 = float(cond_a["holdout_4000"]["mean"])
    m_b5 = float(cond_b["train_5k"]["mean"])
    m_bL = float(cond_b["train_large"]["mean"])
    d_hold = m_a4 - m_a1
    d_train = m_bL - m_b5
    # Which factor moves the metric more / flips sign?
    parts = [
        f"A: holdout 1k→4k Δmean={d_hold:+.4f} (train fixed 5k)",
        f"B: train 5k→large Δmean={d_train:+.4f} (holdout fixed 1k)",
    ]
    if abs(d_hold) >= 2.0 * abs(d_train) and abs(d_hold) > 0.01:
        parts.append(
            "Dominant: EVAL/holdout-n (large move with holdout size; train-n secondary)"
        )
    elif abs(d_train) >= 2.0 * abs(d_hold) and abs(d_train) > 0.01:
        parts.append(
            "Dominant: TRAIN-n (large move with training size; holdout-n secondary)"
        )
    elif abs(d_hold) > 0.01 or abs(d_train) > 0.01:
        parts.append(
            "Both factors move the metric; compare magnitudes — neither ruled out"
        )
    else:
        parts.append("Neither factor moves mean much under these splits — check R4")
    # Sign flips
    if (m_a1 > 0) != (m_a4 > 0):
        parts.append("holdout-size flip of sign under fixed train")
    if (m_b5 > 0) != (m_bL > 0):
        parts.append("train-size flip of sign under fixed holdout")
    return "; ".join(parts)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="§4.3.1 R5 train-n vs holdout-n")
    p.add_argument(
        "--batch-20k",
        type=Path,
        default=_ROOT / "data" / "synthetic" / "prefilter" / "extremes_20k",
    )
    p.add_argument("--n-train-small", type=int, default=5000)
    p.add_argument("--n-holdout-small", type=int, default=1000)
    p.add_argument("--n-holdout-large", type=int, default=4000)
    p.add_argument("--n-seeds", type=int, default=6)
    p.add_argument("--base-seed", type=int, default=20260827)
    p.add_argument(
        "--out",
        type=Path,
        default=_ROOT / "models" / "prefilter" / "prefilter_r5_train_vs_holdout.json",
    )
    args = p.parse_args(argv)

    print("Prefilter R5: train-n vs holdout-n (§4.3.1)")
    print("=" * 60)
    if not (args.batch_20k / "features.jsonl").is_file():
        print("VERDICT: PREFILTER_R5_FAIL")
        print(f"  missing {args.batch_20k}")
        return 1

    train = _load("train_prefilter", "scripts/train_prefilter_model.py")
    rows = train.load_severity_proxy_rows(args.batch_20k)
    # seed-order like seed_split
    rows = sorted(rows, key=lambda r: int(r["seed"]))
    x, y, _seeds = train.matrix_from_rows(rows)
    n = len(rows)
    need = args.n_train_small + args.n_holdout_large
    if n < need:
        print("VERDICT: PREFILTER_R5_FAIL")
        print(f"  need >= {need} rows, have {n}")
        return 1

    # Disjoint: train prefix, holdout from following reservoir (nested 1k ⊂ 4k)
    tr_idx = np.arange(0, args.n_train_small)
    h1_idx = np.arange(args.n_train_small, args.n_train_small + args.n_holdout_small)
    h4_idx = np.arange(args.n_train_small, args.n_train_small + args.n_holdout_large)
    # Large train = everything except fixed H1000 (same H as condition B)
    # H1000 for B = last 1000 of pool (no overlap with train_5k prefix)
    h_b_idx = np.arange(n - args.n_holdout_small, n)
    large_tr_mask = np.ones(n, dtype=bool)
    large_tr_mask[h_b_idx] = False
    large_tr_idx = np.nonzero(large_tr_mask)[0]
    # Small train for B: first 5k (disjoint from last-1000 holdout)
    tr_b_small = np.arange(0, args.n_train_small)

    print(
        f"pool n={n}  A: train={args.n_train_small} H∈{{{args.n_holdout_small},{args.n_holdout_large}}} "
        f"from offset {args.n_train_small}"
    )
    print(
        f"B: H=last {args.n_holdout_small}  train_small={args.n_train_small}  "
        f"train_large={len(large_tr_idx)} (20k−H)"
    )

    def _run(tr: np.ndarray, te: np.ndarray, label: str) -> Dict[str, Any]:
        print(f"  running {label} …")
        sp = train.run_queue_seed_spread_on_split(
            x[tr],
            y[tr],
            x[te],
            y[te],
            n_seeds=args.n_seeds,
            base_seed=args.base_seed,
        )
        s = _summarize(sp)
        print(
            f"    mean={s['mean']:.6f} std={s['std']:.6f} "
            f"n_train={s['n_train']} n_holdout={s['n_holdout']} n_risky={s['n_risky']}"
        )
        return s

    cond_a = {
        "holdout_1000": _run(tr_idx, h1_idx, "A train5k / H1000"),
        "holdout_4000": _run(tr_idx, h4_idx, "A train5k / H4000"),
        "note": "Same train_5k; nested holdouts from reservoir after train prefix",
    }
    cond_b = {
        "train_5k": _run(tr_b_small, h_b_idx, "B train5k / H1000(last)"),
        "train_large": _run(large_tr_idx, h_b_idx, "B train(20k-H) / H1000(last)"),
        "note": "Same last-1000 holdout; train 5k vs all remaining rows",
    }

    reading = _reading(cond_a, cond_b)
    print("reading:", reading)

    # Frozen reference reminder
    reference = {
        "n_train": 5000,
        "n_holdout": 1000,
        "improvement_vs_fifo_mean": 0.04478771063541457,
        "improvement_vs_fifo_std": 0.014704756211992848,
        "frozen_until_r5_documented": True,
    }

    result = {
        "verdict": "PREFILTER_R5_COMPLETE",
        "gate_map": "docs/RaaS_BUS_EXPANSION_v0.md §4.3.1 R5",
        "condition_a_train_fixed_holdout_varies": cond_a,
        "condition_b_holdout_fixed_train_varies": cond_b,
        "reading": reading,
        "delta_holdout_4k_minus_1k": (
            float(cond_a["holdout_4000"]["mean"]) - float(cond_a["holdout_1000"]["mean"])
        ),
        "delta_train_large_minus_5k": (
            float(cond_b["train_large"]["mean"]) - float(cond_b["train_5k"]["mean"])
        ),
        "frozen_reference": reference,
        "blocked": [
            "feature_coupling",
            "public_ingest_retrain_as_success",
            "PREFILTER_ENABLED default true",
        ],
        "live_execution": False,
        "purpose_statement": (
            "Model approximates the gate verdict for sorting; "
            "it does not predict market risk."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("=" * 60)
    print(f"VERDICT: {result['verdict']}")
    print(f"Δholdout(4k−1k)={result['delta_holdout_4k_minus_1k']:+.6f}")
    print(f"Δtrain(large−5k)={result['delta_train_large_minus_5k']:+.6f}")
    print(f"report: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
