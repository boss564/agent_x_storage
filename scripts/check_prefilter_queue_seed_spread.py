#!/usr/bin/env python3
"""Gate-Map §4.2 — queue metric seed-spread (≥6 train seeds).

Reports mean/std of improvement_vs_fifo. A single-run % is not success.
Public-Ingest (§4.3) may only claim gains relative to this noise floor.

Usage:
  PYTHONPATH=. python3 scripts/check_prefilter_queue_seed_spread.py
  make raas-prefilter-queue-seed-spread
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import List, Optional

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
    p = argparse.ArgumentParser(description="Prefilter queue seed-spread check")
    p.add_argument(
        "--data",
        type=Path,
        default=_ROOT / "data" / "synthetic" / "prefilter" / "extremes",
    )
    p.add_argument("--n-seeds", type=int, default=6)
    p.add_argument("--base-seed", type=int, default=20260827)
    p.add_argument("--train-frac", type=float, default=0.8)
    p.add_argument(
        "--out",
        type=Path,
        default=_ROOT / "models" / "prefilter" / "prefilter_queue_seed_spread.json",
    )
    args = p.parse_args(argv)

    print("Prefilter queue seed-spread (Gate-Map §4.2)")
    print("=" * 60)
    print(f"data={args.data}  n_seeds={args.n_seeds}  base_seed={args.base_seed}")
    if not (args.data / "features.jsonl").is_file():
        print("VERDICT: PREFILTER_QUEUE_SEED_SPREAD_FAIL")
        print("  error: missing corpus — run make raas-prefilter-batch-extremes")
        return 1

    train = _load("train_prefilter", "scripts/train_prefilter_model.py")
    try:
        result = train.run_queue_seed_spread(
            args.data,
            n_seeds=args.n_seeds,
            base_seed=args.base_seed,
            train_frac=args.train_frac,
        )
    except Exception as exc:
        print("VERDICT: PREFILTER_QUEUE_SEED_SPREAD_FAIL")
        print(f"  error: {exc}")
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")

    mean = result["improvement_vs_fifo_mean"]
    std = result["improvement_vs_fifo_std"]
    print(f"seeds={result['seeds']}")
    print(f"improvement_vs_fifo per seed={result['improvement_vs_fifo_per_seed']}")
    print(f"improvement_vs_fifo_mean={mean:.6f}  std={std:.6f}")
    print(f"separable_from_zero_2sigma={result['separable_from_zero_2sigma']}")
    print(f"criterion: {result['criterion']}")
    print("=" * 60)
    print(f"VERDICT: {result['verdict']}")
    print(f"report:  {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
