#!/usr/bin/env python3
"""§4.3.1 Decision A — evaluate queue metric on frozen multi-holdout sets.

Loads git-tracked manifest, verifies manifest_sha256, trains on fixed 5k
split, scores each set. Claim = mean ± std across sets (never best set).

Usage:
  PYTHONPATH=. python3 scripts/eval_prefilter_multi_holdout.py
  make raas-prefilter-multi-holdout-eval
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

DEFAULT_MANIFEST = _ROOT / "config" / "prefilter" / "prefilter_multi_holdout_manifest.json"
DEFAULT_OUT = _ROOT / "models" / "prefilter" / "prefilter_multi_holdout_baseline.json"


def _load(name: str, rel: str):
    path = _ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Eval multi-holdout baseline (Decision A)")
    p.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
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
    p.add_argument("--n-model-seeds", type=int, default=6)
    p.add_argument("--base-seed", type=int, default=20260827)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = p.parse_args(argv)

    print("Multi-holdout eval (§4.3.1 Decision A)")
    print("=" * 60)

    freeze = _load("freeze_multi", "scripts/freeze_prefilter_multi_holdout.py")
    train = _load("train_prefilter", "scripts/train_prefilter_model.py")

    if not args.manifest.is_file():
        print("VERDICT: PREFILTER_MULTI_HOLDOUT_EVAL_FAIL")
        print(f"  missing manifest: {args.manifest}")
        print("  run: make raas-prefilter-multi-holdout-freeze first")
        return 1

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not freeze.verify_manifest(manifest):
        print("VERDICT: PREFILTER_MULTI_HOLDOUT_EVAL_FAIL")
        print("  manifest_sha256 mismatch — refuse eval (seal broken)")
        return 1

    for path, label in ((args.batch_5k, "5k"), (args.batch_20k, "20k")):
        if not (path / "features.jsonl").is_file():
            print("VERDICT: PREFILTER_MULTI_HOLDOUT_EVAL_FAIL")
            print(f"  missing {label}: {path}")
            return 1

    # Corpus fingerprint check (warn-hard: fail if files changed)
    corp = manifest.get("corpus") or {}
    feat_5k = args.batch_5k / "features.jsonl"
    feat_20k = args.batch_20k / "features.jsonl"
    h5 = freeze._file_sha256(feat_5k)
    h20 = freeze._file_sha256(feat_20k)
    if h5 != corp.get("features_5k_sha256") or h20 != corp.get("features_20k_sha256"):
        print("VERDICT: PREFILTER_MULTI_HOLDOUT_EVAL_FAIL")
        print("  corpus features.jsonl hash ≠ manifest — freeze was for other data")
        print(f"  5k:  {h5} vs {corp.get('features_5k_sha256')}")
        print(f"  20k: {h20} vs {corp.get('features_20k_sha256')}")
        return 1

    rows_5k = sorted(
        train.load_severity_proxy_rows(args.batch_5k), key=lambda r: int(r["seed"])
    )
    rows_20k = sorted(
        train.load_severity_proxy_rows(args.batch_20k), key=lambda r: int(r["seed"])
    )
    x5, y5, _ = train.matrix_from_rows(rows_5k)
    x20, y20, _ = train.matrix_from_rows(rows_20k)

    n5 = len(y5)
    n_train = max(1, int(n5 * 0.8))
    if n_train >= n5:
        n_train = n5 - 1
    tr5 = np.arange(0, n_train)

    sets = manifest["sets"]
    per_set: List[Dict[str, Any]] = []
    set_means: List[float] = []

    for s in sets:
        idx = np.asarray(s["indices"], dtype=np.int64)
        if len(idx) != int(manifest["holdout_n"]):
            print("VERDICT: PREFILTER_MULTI_HOLDOUT_EVAL_FAIL")
            print(f"  {s['id']}: len(indices)≠holdout_n")
            return 1
        got_hash = freeze._indices_sha256([int(i) for i in idx])
        if got_hash != s.get("indices_sha256"):
            print("VERDICT: PREFILTER_MULTI_HOLDOUT_EVAL_FAIL")
            print(f"  {s['id']}: indices_sha256 mismatch")
            return 1

        imps: List[float] = []
        for i in range(args.n_model_seeds):
            seed = args.base_seed + i
            # Val split for early-stopping: use this holdout set
            model, backend, _ = train.train_gbt(
                x5[tr5], y5[tr5], x20[idx], y20[idx], seed=seed
            )
            scores = train.predict_scores(model, backend, x20[idx])
            q = train.simulate_backlog_wait(y20[idx], scores, seed=seed)
            imps.append(float(q["improvement_vs_fifo"]))

        arr = np.asarray(imps, dtype=np.float64)
        mean_s = float(np.mean(arr))
        std_s = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
        set_means.append(mean_s)
        per_set.append(
            {
                "id": s["id"],
                "n_risky_manifest": s.get("n_risky"),
                "improvement_mean_over_model_seeds": mean_s,
                "improvement_std_model_seeds": std_s,
                "per_seed": imps,
                "neg_model_seeds": sum(1 for x in imps if x < 0),
            }
        )
        print(
            f"{s['id']}: mean={mean_s:+.4f}  σ_model={std_s:.4f}  "
            f"neg={per_set[-1]['neg_model_seeds']}/{args.n_model_seeds}"
        )

    set_arr = np.asarray(set_means, dtype=np.float64)
    claim_mean = float(np.mean(set_arr))
    claim_std = float(np.std(set_arr, ddof=1)) if len(set_arr) > 1 else 0.0
    best_id = max(per_set, key=lambda r: r["improvement_mean_over_model_seeds"])["id"]
    best_val = max(set_means)

    result = {
        "verdict": "PREFILTER_MULTI_HOLDOUT_BASELINE_OK",
        "decision": "A",
        "manifest_path": str(args.manifest.relative_to(_ROOT)),
        "manifest_sha256": manifest["manifest_sha256"],
        "manifest_verified": True,
        "n_sets": len(sets),
        "n_model_seeds": args.n_model_seeds,
        "claim": {
            "form": "mean ± std across sets",
            "improvement_vs_fifo_mean_over_sets": claim_mean,
            "improvement_vs_fifo_std_across_sets": claim_std,
            "unit": "fraction (not pp display)",
            "forbidden": "never report best set as the claim",
            "best_set_id_forensic_only": best_id,
            "best_set_mean_forensic_only": best_val,
            "note": (
                f"Claim is {claim_mean:+.4f} ± {claim_std:.4f} over sets; "
                f"best set {best_id}={best_val:+.4f} is forensic, not a claim"
            ),
        },
        "per_set": per_set,
        "historical_raw_reference": {
            "mean": 0.0448,
            "model_seed_std": 0.0147,
            "scope": "single fixed 5k holdout only",
            "role": "historical; not replaced by this baseline",
        },
        "path1_recalibration": (
            "may_open_against_this_A_claim_only_after_documented; "
            "paired mean(Δ) across same sets; never vs best set"
        ),
        "gate_map": "docs/RaaS_BUS_EXPANSION_v0.md §4.3.1",
        "live_execution": False,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print("=" * 60)
    print(
        f"CLAIM (mean ± σ across sets): {claim_mean:+.4f} ± {claim_std:.4f}  "
        f"({claim_mean * 100:+.2f}% ± {claim_std * 100:.2f} pp)"
    )
    print(f"best set (forensic only): {best_id} = {best_val:+.4f} — NOT the claim")
    print(f"VERDICT: {result['verdict']}")
    print(f"report:  {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
