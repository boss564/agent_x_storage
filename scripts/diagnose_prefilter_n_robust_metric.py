#!/usr/bin/env python3
"""§4.3.1 — verify holdout-N-robust queue metric (fixed n0 bootstrap).

Fair test (avoids prefix≠random confound from R5-A):
  Shuffle holdout reservoir once per seed; grow nested pools N∈{1000,2000,4000}.
  Raw M(N) may drift; robust bootstrap at n0=1000 should stay flatter.

Usage:
  PYTHONPATH=. python3 scripts/diagnose_prefilter_n_robust_metric.py
  make raas-prefilter-n-robust-metric
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="N-robust queue metric check")
    p.add_argument(
        "--batch-20k",
        type=Path,
        default=_ROOT / "data" / "synthetic" / "prefilter" / "extremes_20k",
    )
    p.add_argument("--n-train", type=int, default=5000)
    p.add_argument("--n-reservoir", type=int, default=4000)
    p.add_argument("--pool-sizes", type=int, nargs="+", default=[1000, 2000, 4000])
    p.add_argument("--n-seeds", type=int, default=6)
    p.add_argument("--base-seed", type=int, default=20260827)
    p.add_argument("--n-bootstraps", type=int, default=40)
    p.add_argument("--eval-n", type=int, default=1000)
    p.add_argument(
        "--out",
        type=Path,
        default=_ROOT / "models" / "prefilter" / "prefilter_n_robust_metric.json",
    )
    args = p.parse_args(argv)

    print("Prefilter N-robust queue metric (§4.3.1)")
    print("=" * 60)
    if not (args.batch_20k / "features.jsonl").is_file():
        print("VERDICT: PREFILTER_N_ROBUST_FAIL")
        print(f"  missing {args.batch_20k}")
        return 1
    if min(args.pool_sizes) < args.eval_n:
        print("VERDICT: PREFILTER_N_ROBUST_FAIL")
        print("  pool sizes must be >= eval_n")
        return 1

    train = _load("train_prefilter", "scripts/train_prefilter_model.py")
    rows = sorted(
        train.load_severity_proxy_rows(args.batch_20k), key=lambda r: int(r["seed"])
    )
    x, y, _ = train.matrix_from_rows(rows)
    tr = np.arange(0, args.n_train)
    reservoir = np.arange(args.n_train, args.n_train + args.n_reservoir)

    # per pool size → list of means across seeds
    raw_by_n: Dict[int, List[float]] = {n: [] for n in args.pool_sizes}
    rob_by_n: Dict[int, List[float]] = {n: [] for n in args.pool_sizes}

    for i in range(args.n_seeds):
        seed = args.base_seed + i
        print(f"seed={seed}")
        model, backend, _ = train.train_gbt(
            x[tr], y[tr], x[reservoir[: args.eval_n]], y[reservoir[: args.eval_n]], seed=seed
        )
        scores_res = train.predict_scores(model, backend, x[reservoir])
        y_res = y[reservoir]
        rng = np.random.default_rng(seed + 99)
        order = rng.permutation(args.n_reservoir)

        for n_pool in args.pool_sizes:
            idx = order[:n_pool]
            sub_y = y_res[idx]
            sub_s = scores_res[idx]
            raw = train.simulate_backlog_wait(sub_y, sub_s, seed=seed)
            rob = train.queue_metric_n_robust(
                sub_y,
                sub_s,
                eval_n=args.eval_n,
                n_bootstraps=1 if n_pool == args.eval_n else args.n_bootstraps,
                seed=seed,
                stratified=True,
            )
            raw_by_n[n_pool].append(float(raw["improvement_vs_fifo"]))
            rob_by_n[n_pool].append(float(rob["improvement_vs_fifo_mean"]))
            print(
                f"  N={n_pool}: raw={raw['improvement_vs_fifo']:+.4f}  "
                f"robust_n0={rob['improvement_vs_fifo_mean']:+.4f}"
            )

    def _ms(xs: List[float]) -> Dict[str, float]:
        a = np.asarray(xs, dtype=np.float64)
        return {
            "mean": float(np.mean(a)),
            "std": float(np.std(a, ddof=1)) if len(a) > 1 else 0.0,
            "per_seed": xs,
        }

    sizes = sorted(args.pool_sizes)
    n_lo, n_hi = sizes[0], sizes[-1]
    raw_lo, raw_hi = _ms(raw_by_n[n_lo]), _ms(raw_by_n[n_hi])
    rob_lo, rob_hi = _ms(rob_by_n[n_lo]), _ms(rob_by_n[n_hi])
    d_raw = raw_hi["mean"] - raw_lo["mean"]
    d_rob = rob_hi["mean"] - rob_lo["mean"]

    # PASS if robust drift is < half the raw drift (or both near zero)
    if abs(d_raw) < 0.005:
        reduced = abs(d_rob) <= abs(d_raw) + 0.005
    else:
        reduced = abs(d_rob) < 0.5 * abs(d_raw)

    result = {
        "verdict": (
            "PREFILTER_N_ROBUST_PASS" if reduced else "PREFILTER_N_ROBUST_FAIL"
        ),
        "criterion": (
            f"|Δrobust(N={n_hi}−N={n_lo})| < 0.5·|Δraw| on nested random pools "
            f"(same train 5k, {args.n_seeds} seeds, stratified bootstrap n0={args.eval_n})"
        ),
        "design": {
            "train_n": args.n_train,
            "reservoir": args.n_reservoir,
            "pool_sizes": sizes,
            "nested_random_order": True,
            "note": "Avoids contiguous-prefix confound (R5-A H1000≠random from H4000)",
        },
        "raw_by_n": {str(k): _ms(v) for k, v in sorted(raw_by_n.items())},
        "robust_by_n": {str(k): _ms(v) for k, v in sorted(rob_by_n.items())},
        "delta_raw_hi_minus_lo": d_raw,
        "delta_robust_hi_minus_lo": d_rob,
        "eval_n_reference": args.eval_n,
        "n_bootstraps": args.n_bootstraps,
        "frozen_reference_unchanged": {
            "n_train": 5000,
            "n_holdout": 1000,
            "metric_for_claims": "raw improvement_vs_fifo at Holdout=1000",
            "n_robust_role": "cross-N comparison / secondary score",
        },
        "gate_map": "docs/RaaS_BUS_EXPANSION_v0.md §4.3.1 N-robust",
        "live_execution": False,
        "purpose_statement": (
            "Model approximates the gate verdict for sorting; "
            "it does not predict market risk."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("=" * 60)
    print(f"Δraw(N{n_hi}−N{n_lo})={d_raw:+.4f}  Δrobust={d_rob:+.4f}")
    print(f"VERDICT: {result['verdict']}")
    print(f"report:  {args.out}")
    return 0 if reduced else 1


if __name__ == "__main__":
    raise SystemExit(main())
