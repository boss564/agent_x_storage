#!/usr/bin/env python3
"""§4.3.1 Reference diagnosis — why +4.5% (5k) flips to −1.8% (20k).

Steps:
  R1  Re-run seed-spread on extremes 5k; compare to stored report.
  R3  Draw a 5k subset from extremes_20k (same kind counts as 5k);
      seed-spread and compare to original 5k (data-size vs charge).

Does not calibrate features. Does not claim DEFAULT_ON.

Usage:
  PYTHONPATH=. python3 scripts/diagnose_prefilter_reference.py
  make raas-prefilter-reference-diagnosis
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

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


def _read_rows(batch: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with (batch / "features.jsonl").open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("label_mode") != "severity_proxy":
                continue
            rows.append(r)
    return rows


def _kind_counts(rows: Sequence[Dict[str, Any]]) -> Counter:
    return Counter(str(r.get("scenario_kind", "?")) for r in rows)


def _subset_matching_kinds(
    pool: Sequence[Dict[str, Any]],
    target_counts: Counter,
) -> List[Dict[str, Any]]:
    """Take first N of each kind (seed-ordered) to match target kind counts."""
    by_kind: Dict[str, List[Dict[str, Any]]] = {}
    for r in sorted(pool, key=lambda x: int(x["seed"])):
        by_kind.setdefault(str(r.get("scenario_kind", "?")), []).append(r)
    out: List[Dict[str, Any]] = []
    missing: List[str] = []
    for kind, need in sorted(target_counts.items()):
        avail = by_kind.get(kind, [])
        if len(avail) < need:
            missing.append(f"{kind}: need {need} have {len(avail)}")
            out.extend(avail)
        else:
            out.extend(avail[:need])
    if missing:
        raise ValueError("subset undersupplied: " + "; ".join(missing))
    # Preserve seed order like full batches
    out.sort(key=lambda r: int(r["seed"]))
    return out


def _write_subset(rows: Sequence[Dict[str, Any]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl = out_dir / "features.jsonl"
    with jsonl.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True, default=str) + "\n")
    manifest = {
        "n": len(rows),
        "purpose": "reference_diagnosis_5k_subset_from_20k",
        "label_modes": sorted({r["label_mode"] for r in rows}),
        "scenario_kinds": sorted({r["scenario_kind"] for r in rows}),
        "kind_counts": dict(_kind_counts(rows)),
        "training_allowed": True,
        "calibration_applied": False,
        "note": "§4.3.1 R3 — not a training claim; isolates n vs charge",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _spread_summary(spread: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "verdict": spread.get("verdict"),
        "mean": spread.get("improvement_vs_fifo_mean"),
        "std": spread.get("improvement_vs_fifo_std"),
        "seeds": spread.get("seeds"),
        "per_seed": spread.get("improvement_vs_fifo_per_seed"),
        "n_holdout": (spread.get("runs") or [{}])[0].get("n_holdout"),
        "n_risky": (spread.get("runs") or [{}])[0].get("n_risky"),
    }


def _close(a: float, b: float, *, atol: float = 1e-6, rtol: float = 1e-5) -> bool:
    return abs(a - b) <= atol + rtol * max(abs(a), abs(b))


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="§4.3.1 prefilter reference diagnosis")
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
    p.add_argument(
        "--subset-out",
        type=Path,
        default=_ROOT / "data" / "synthetic" / "prefilter" / "extremes_5k_from_20k",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=_ROOT / "models" / "prefilter" / "prefilter_reference_diagnosis.json",
    )
    p.add_argument("--n-seeds", type=int, default=6)
    p.add_argument("--base-seed", type=int, default=20260827)
    p.add_argument("--train-frac", type=float, default=0.8)
    p.add_argument(
        "--repro-tol",
        type=float,
        default=1e-6,
        help="abs tol for mean/std match on R1",
    )
    args = p.parse_args(argv)

    print("Prefilter reference diagnosis (§4.3.1)")
    print("=" * 60)

    for path, label in ((args.batch_5k, "5k"), (args.batch_20k, "20k")):
        if not (path / "features.jsonl").is_file():
            print(f"VERDICT: PREFILTER_REFERENCE_DIAGNOSIS_FAIL")
            print(f"  missing {label} batch: {path}")
            return 1
    if not args.baseline_report.is_file():
        print("VERDICT: PREFILTER_REFERENCE_DIAGNOSIS_FAIL")
        print(f"  missing baseline report {args.baseline_report}")
        return 1

    train = _load("train_prefilter", "scripts/train_prefilter_model.py")
    baseline = json.loads(args.baseline_report.read_text(encoding="utf-8"))
    rows_5k = _read_rows(args.batch_5k)
    rows_20k = _read_rows(args.batch_20k)
    kinds_5k = _kind_counts(rows_5k)

    # --- R1 reproducibility ---
    print("R1: re-run seed-spread on extremes 5k …")
    spread_5k = train.run_queue_seed_spread(
        args.batch_5k,
        n_seeds=args.n_seeds,
        base_seed=args.base_seed,
        train_frac=args.train_frac,
    )
    mean_b = float(baseline["improvement_vs_fifo_mean"])
    std_b = float(baseline["improvement_vs_fifo_std"])
    mean_r = float(spread_5k["improvement_vs_fifo_mean"])
    std_r = float(spread_5k["improvement_vs_fifo_std"])
    r1_pass = _close(mean_b, mean_r, atol=args.repro_tol) and _close(
        std_b, std_r, atol=args.repro_tol
    )
    print(f"  baseline mean={mean_b:.6f} std={std_b:.6f}")
    print(f"  rerun    mean={mean_r:.6f} std={std_r:.6f}")
    print(f"  R1={'PASS' if r1_pass else 'FAIL'} (deterministic match)")

    # --- R3 5k subset from 20k ---
    print("R3: 5k subset from 20k matching kind counts …")
    subset = _subset_matching_kinds(rows_20k, kinds_5k)
    _write_subset(subset, args.subset_out)
    print(f"  subset n={len(subset)} kinds={dict(_kind_counts(subset))}")
    print(f"  wrote {args.subset_out}")
    spread_sub = train.run_queue_seed_spread(
        args.subset_out,
        n_seeds=args.n_seeds,
        base_seed=args.base_seed,
        train_frac=args.train_frac,
    )
    mean_s = float(spread_sub["improvement_vs_fifo_mean"])
    std_s = float(spread_sub["improvement_vs_fifo_std"])
    # Same n + same kind mix: if subset ≈ 5k → charge-equivalent; if ≈ 20k sign → size not charge
    delta_vs_5k = mean_s - mean_r
    print(f"  subset   mean={mean_s:.6f} std={std_s:.6f}")
    print(f"  Δ(subset−5k_rerun)={delta_vs_5k:+.6f}")

    # Interpretation (descriptive, not a PASS gate for calibration)
    if abs(delta_vs_5k) <= 2 * float(spread_5k["improvement_vs_fifo_std"]) / math.sqrt(
        args.n_seeds
    ):
        r3_reading = (
            "subset≈5k within ~2·SEM(5k) → same n+kind recovers baseline; "
            "20k flip is a data-size / holdout-n effect, not a different charge"
        )
    elif mean_s < 0 and mean_r > 0:
        r3_reading = (
            "subset still negative while 5k positive → charge/feature content "
            "differs even at matched n+kinds (not pure size)"
        )
    else:
        r3_reading = (
            "subset diverges from 5k at matched n+kinds → investigate feature "
            "distributions (R4) before blaming n alone"
        )
    print(f"  reading: {r3_reading}")

    result = {
        "verdict": (
            "PREFILTER_REFERENCE_DIAGNOSIS_PASS"
            if r1_pass
            else "PREFILTER_REFERENCE_DIAGNOSIS_FAIL"
        ),
        "gate_map": "docs/RaaS_BUS_EXPANSION_v0.md §4.3.1",
        "r1_reproducibility": {
            "pass": r1_pass,
            "baseline": {"mean": mean_b, "std": std_b, "path": str(args.baseline_report)},
            "rerun": _spread_summary(spread_5k),
            "tol": args.repro_tol,
        },
        "r3_subset_from_20k": {
            "subset_path": str(args.subset_out),
            "n": len(subset),
            "kind_counts_target": dict(kinds_5k),
            "kind_counts_subset": dict(_kind_counts(subset)),
            "spread": _spread_summary(spread_sub),
            "delta_vs_5k_rerun_mean": delta_vs_5k,
            "reading": r3_reading,
        },
        "blocked_until_resolved": [
            "feature_coupling",
            "public_ingest_retrain_as_success",
            "PREFILTER_ENABLED default true",
        ],
        "note": (
            "Composition (n_risky/n) already ruled out. R1/R3 isolate "
            "determinism and data-size vs charge. No risk forecast claim."
        ),
        "live_execution": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("=" * 60)
    print(f"VERDICT: {result['verdict']}")
    print(f"report:  {args.out}")
    return 0 if r1_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
