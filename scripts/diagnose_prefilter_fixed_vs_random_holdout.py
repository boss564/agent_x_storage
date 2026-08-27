#!/usr/bin/env python3
"""§4.3.1 — isolate fixed vs random holdout composition (one factor).

Same trained model per seed; evaluate on k random holdouts of size 1000
from the post-train reservoir. If σ across draws ≈ 4.18pp, composition
explains the frozen-vs-robust gap (no bootstrap at N=n0).

Usage:
  PYTHONPATH=. python3 scripts/diagnose_prefilter_fixed_vs_random_holdout.py
  make raas-prefilter-fixed-vs-random-holdout
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
    p = argparse.ArgumentParser(description="Fixed vs random holdout isolation")
    p.add_argument(
        "--batch-5k",
        type=Path,
        default=_ROOT / "data" / "synthetic" / "prefilter" / "extremes",
    )
    p.add_argument(
        "--batch-20k",
        type=Path,
        default=_ROOT / "data" / "synthetic" / "prefilter" / "extremes_20k",
    )
    p.add_argument(
        "--baseline-report",
        type=Path,
        default=_ROOT / "models" / "prefilter" / "prefilter_queue_seed_spread.json",
    )
    p.add_argument("--n-train", type=int, default=5000)
    p.add_argument("--holdout-n", type=int, default=1000)
    p.add_argument("--n-draws", type=int, default=6, help="random holdouts per model seed")
    p.add_argument("--n-model-seeds", type=int, default=6)
    p.add_argument("--base-seed", type=int, default=20260827)
    p.add_argument(
        "--out",
        type=Path,
        default=_ROOT / "models" / "prefilter" / "prefilter_fixed_vs_random_holdout.json",
    )
    args = p.parse_args(argv)

    print("Fixed vs random holdout isolation (§4.3.1)")
    print("=" * 60)
    for path, label in (
        (args.batch_5k, "5k"),
        (args.batch_20k, "20k"),
        (args.baseline_report, "baseline"),
    ):
        ok = path.is_file() if path.suffix == ".json" else (path / "features.jsonl").is_file()
        if not ok:
            print("VERDICT: PREFILTER_FIXED_VS_RANDOM_FAIL")
            print(f"  missing {label}: {path}")
            return 1

    train = _load("train_prefilter", "scripts/train_prefilter_model.py")
    baseline = json.loads(args.baseline_report.read_text(encoding="utf-8"))
    rows_5k = sorted(
        train.load_severity_proxy_rows(args.batch_5k), key=lambda r: int(r["seed"])
    )
    rows_20k = sorted(
        train.load_severity_proxy_rows(args.batch_20k), key=lambda r: int(r["seed"])
    )
    x5, y5, _ = train.matrix_from_rows(rows_5k)
    x20, y20, _ = train.matrix_from_rows(rows_20k)

    # Fixed holdout = same as seed_split train_frac=0.8 on 5k
    n5 = len(y5)
    n_train = max(1, int(n5 * 0.8))
    if n_train >= n5:
        n_train = n5 - 1
    # seed_split uses argsort(seeds) — rows already seed-sorted
    tr5 = np.arange(0, n_train)
    te5_fixed = np.arange(n_train, n5)
    assert len(te5_fixed) == args.holdout_n, (len(te5_fixed), args.holdout_n)

    # Reservoir for random draws: 20k after first 5k prefix (disjoint from train_5k content)
    # Train always on 5k train split; random holdouts from 20k[5000:…] so composition can vary
    reservoir = np.arange(args.n_train, len(y20))
    if len(reservoir) < args.holdout_n:
        print("VERDICT: PREFILTER_FIXED_VS_RANDOM_FAIL")
        print("  reservoir too small")
        return 1

    fixed_imps: List[float] = []
    # All random-draw improvements pooled (model seed × draw)
    random_imps: List[float] = []
    per_model: List[Dict[str, Any]] = []

    for i in range(args.n_model_seeds):
        seed = args.base_seed + i
        model, backend, _ = train.train_gbt(
            x5[tr5], y5[tr5], x5[te5_fixed], y5[te5_fixed], seed=seed
        )
        # Fixed holdout (frozen composition)
        scores_f = train.predict_scores(model, backend, x5[te5_fixed])
        q_f = train.simulate_backlog_wait(y5[te5_fixed], scores_f, seed=seed)
        fixed_imps.append(float(q_f["improvement_vs_fifo"]))

        draw_imps: List[float] = []
        rng = np.random.default_rng(seed + 777)
        for d in range(args.n_draws):
            pick = rng.choice(reservoir, size=args.holdout_n, replace=False)
            scores_r = train.predict_scores(model, backend, x20[pick])
            q_r = train.simulate_backlog_wait(y20[pick], scores_r, seed=seed + d)
            imp = float(q_r["improvement_vs_fifo"])
            draw_imps.append(imp)
            random_imps.append(imp)

        per_model.append(
            {
                "model_seed": seed,
                "fixed_holdout_improvement": fixed_imps[-1],
                "fixed_n_risky": int(q_f["n_risky"]),
                "random_draw_improvements": draw_imps,
                "random_draw_mean": float(np.mean(draw_imps)),
                "random_draw_std": float(np.std(draw_imps, ddof=1)) if len(draw_imps) > 1 else 0.0,
                "random_neg_count": sum(1 for x in draw_imps if x < 0),
            }
        )
        print(
            f"seed={seed}  fixed={fixed_imps[-1]:+.4f} (n_risky={q_f['n_risky']})  "
            f"random_draws mean={per_model[-1]['random_draw_mean']:+.4f} "
            f"std={per_model[-1]['random_draw_std']:.4f} "
            f"neg={per_model[-1]['random_neg_count']}/{args.n_draws}"
        )

    fixed_arr = np.asarray(fixed_imps, dtype=np.float64)
    rand_arr = np.asarray(random_imps, dtype=np.float64)
    sigma_fixed = float(np.std(fixed_arr, ddof=1))
    sigma_random = float(np.std(rand_arr, ddof=1))
    mean_fixed = float(np.mean(fixed_arr))
    mean_random = float(np.mean(rand_arr))
    # Within-model composition σ: mean of per-model draw stds
    within_model_sigma = float(np.mean([m["random_draw_std"] for m in per_model]))

    # Composition confirmed if, with model held fixed, random draws alone produce
    # σ clearly above model-seed-only σ on the fixed holdout (factor isolation).
    # Nested-random report σ≈4.18pp mixes more factors — not a hard equality target.
    composition_confirmed = bool(within_model_sigma > sigma_fixed and within_model_sigma > 0.015)

    result = {
        "verdict": (
            "PREFILTER_COMPOSITION_VARIANCE_CONFIRMED"
            if composition_confirmed
            else "PREFILTER_COMPOSITION_VARIANCE_INCONCLUSIVE"
        ),
        "criterion": (
            "mean_within_model_draw_std > std_across_model_seeds_on_fixed_holdout "
            "(composition varies; model fixed within draws)"
        ),
        "design": {
            "factor_varied": "holdout_composition_only",
            "model": "retrained per seed on fixed 5k train split; held fixed across draws",
            "fixed_holdout": "extremes 5k seed_split holdout (n=1000, n_risky=581)",
            "random_holdouts": (
                f"{args.n_draws} draws × {args.n_model_seeds} seeds from "
                f"extremes_20k[n_train:] size {args.holdout_n}"
            ),
            "no_bootstrap": True,
            "note": "At N=n0 the draw IS the pool",
        },
        "fixed_holdout": {
            "mean": mean_fixed,
            "std_across_model_seeds": sigma_fixed,
            "per_seed": fixed_imps,
            "neg_seeds": sum(1 for x in fixed_imps if x < 0),
            "baseline_report_mean": baseline.get("improvement_vs_fifo_mean"),
            "baseline_report_std": baseline.get("improvement_vs_fifo_std"),
        },
        "random_holdouts": {
            "mean": mean_random,
            "std_pooled_all_draws": sigma_random,
            "mean_within_model_draw_std": within_model_sigma,
            "n_draws_total": len(random_imps),
            "neg_draws": sum(1 for x in random_imps if x < 0),
            "target_sigma_from_nested_random_report": target,
        },
        "reading": (
            "σ_fixed≈model-only; σ_random≈model+composition. "
            "If σ_random ≫ σ_fixed and near ~4.18pp, composition explains the gap."
        ),
        "reference_scope": (
            "Frozen +4.48%±1.47pp applies to the fixed holdout draw, "
            "not arbitrary draws of size 1000."
        ),
        "per_model": per_model,
        "gate_map": "docs/RaaS_BUS_EXPANSION_v0.md §4.3.1",
        "live_execution": False,
        "path1_recalibration": "still_blocked_until_documented",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("=" * 60)
    print(f"fixed:  mean={mean_fixed:.4f}  σ_seeds={sigma_fixed:.4f}  neg={sum(1 for x in fixed_imps if x<0)}/6")
    print(
        f"random: mean={mean_random:.4f}  σ_pooled={sigma_random:.4f}  "
        f"mean_within_model_σ={within_model_sigma:.4f}  "
        f"neg={sum(1 for x in random_imps if x<0)}/{len(random_imps)}"
    )
    print(f"target σ (nested-random report)≈{target:.4f}")
    print(f"VERDICT: {result['verdict']}")
    print(f"report:  {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
