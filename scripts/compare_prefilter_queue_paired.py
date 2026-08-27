#!/usr/bin/env python3
"""§4.3 paired queue comparison — same seeds before/after calibration.

Criterion: mean(Δ) > 2 · SEM(Δ) where Δ_i = improvement_after_i − improvement_before_i
on the same six train seeds. Single-run % is not success.

Usage:
  PYTHONPATH=. python3 scripts/compare_prefilter_queue_paired.py \\
    --baseline models/prefilter/prefilter_queue_seed_spread.json \\
    --data data/synthetic/prefilter/calibrated
  make raas-prefilter-paired-compare
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    p = argparse.ArgumentParser(description="§4.3 paired prefilter queue compare")
    p.add_argument(
        "--baseline",
        type=Path,
        default=_ROOT / "models" / "prefilter" / "prefilter_queue_seed_spread.json",
    )
    p.add_argument(
        "--data",
        type=Path,
        default=_ROOT / "data" / "synthetic" / "prefilter" / "calibrated",
    )
    p.add_argument("--n-seeds", type=int, default=6)
    p.add_argument("--base-seed", type=int, default=20260827)
    p.add_argument("--train-frac", type=float, default=0.8)
    p.add_argument(
        "--out",
        type=Path,
        default=_ROOT / "models" / "prefilter" / "prefilter_queue_profile_calibrated.json",
    )
    args = p.parse_args(argv)

    print("Public-Ingest paired queue compare (Gate-Map §4.3)")
    print("=" * 60)
    if not args.baseline.is_file():
        print("VERDICT: PREFILTER_PAIRED_COMPARE_FAIL")
        print(f"  missing baseline {args.baseline}")
        return 1
    if not (args.data / "features.jsonl").is_file():
        print("VERDICT: PREFILTER_PAIRED_COMPARE_FAIL")
        print(f"  missing calibrated corpus {args.data}")
        return 1

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    before_map = {
        int(s): float(v)
        for s, v in zip(baseline["seeds"], baseline["improvement_vs_fifo_per_seed"])
    }
    seeds = [args.base_seed + i for i in range(args.n_seeds)]
    for s in seeds:
        if s not in before_map:
            print("VERDICT: PREFILTER_PAIRED_COMPARE_FAIL")
            print(f"  baseline missing seed {s}")
            return 1

    train = _load("train_prefilter", "scripts/train_prefilter_model.py")
    after = train.run_queue_seed_spread(
        args.data,
        n_seeds=args.n_seeds,
        base_seed=args.base_seed,
        train_frac=args.train_frac,
    )
    after_map = {
        int(s): float(v)
        for s, v in zip(after["seeds"], after["improvement_vs_fifo_per_seed"])
    }

    deltas: List[float] = []
    pairs: List[Dict[str, Any]] = []
    for s in seeds:
        d = after_map[s] - before_map[s]
        deltas.append(d)
        pairs.append(
            {
                "seed": s,
                "improvement_before": before_map[s],
                "improvement_after": after_map[s],
                "delta": d,
            }
        )

    n = len(deltas)
    mean_d = sum(deltas) / n
    if n > 1:
        var = sum((x - mean_d) ** 2 for x in deltas) / (n - 1)
        std_d = math.sqrt(max(var, 0.0))
        sem_d = std_d / math.sqrt(n)
    else:
        std_d = 0.0
        sem_d = 0.0
    threshold = 2.0 * sem_d
    passed = bool(mean_d > threshold)

    result = {
        "verdict": (
            "PREFILTER_PAIRED_COMPARE_PASS" if passed else "PREFILTER_PAIRED_COMPARE_FAIL"
        ),
        "criterion": "mean(Δ) > 2·SEM(Δ) on paired seeds (Δ=after−before improvement_vs_fifo)",
        "seeds": seeds,
        "pairs": pairs,
        "delta_mean": mean_d,
        "delta_std": std_d,
        "delta_sem": sem_d,
        "threshold_2sem": threshold,
        "baseline_mean": baseline.get("improvement_vs_fifo_mean"),
        "after_mean": after.get("improvement_vs_fifo_mean"),
        "baseline_path": str(args.baseline),
        "calibrated_data": str(args.data),
        "purpose": "queue_prioritization_under_backlog",
        "purpose_statement": (
            "Model approximates the gate verdict for sorting; "
            "it does not predict market risk."
        ),
        "label_mode": "severity_proxy",
        "live_execution": False,
        "gate_map": "docs/RaaS_BUS_EXPANSION_v0.md §4.3",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"seeds={seeds}")
    for pr in pairs:
        print(
            f"  seed={pr['seed']}  before={pr['improvement_before']:.4f}  "
            f"after={pr['improvement_after']:.4f}  Δ={pr['delta']:+.4f}"
        )
    print(f"mean(Δ)={mean_d:.6f}  SEM(Δ)={sem_d:.6f}  threshold_2SEM={threshold:.6f}")
    print(f"baseline_mean={result['baseline_mean']}  after_mean={result['after_mean']}")
    print("=" * 60)
    print(f"VERDICT: {result['verdict']}")
    print(f"report:  {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
