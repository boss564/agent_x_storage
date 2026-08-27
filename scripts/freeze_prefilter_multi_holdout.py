#!/usr/bin/env python3
"""§4.3.1 Decision A — freeze stratified multi-holdout sets BEFORE any eval.

Bridge-seal discipline: draw indices, hash canonical lists, write git-tracked
manifest. Evaluation is a separate step (eval_prefilter_multi_holdout.py).

Usage:
  PYTHONPATH=. python3 scripts/freeze_prefilter_multi_holdout.py
  make raas-prefilter-multi-holdout-freeze
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

DEFAULT_MANIFEST = _ROOT / "config" / "prefilter" / "prefilter_multi_holdout_manifest.json"
DRAW_SEED = 202608271  # fixed; changing this is a new freeze
N_SETS = 8
HOLDOUT_N = 1000


def _load(name: str, rel: str):
    path = _ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _indices_sha256(indices: Sequence[int]) -> str:
    payload = ",".join(str(int(i)) for i in indices).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonical_sets_payload(sets: Sequence[Dict[str, Any]]) -> str:
    """Byte-stable payload for manifest_sha256 (indices only, ordered by set id)."""
    blocks: List[str] = []
    for s in sorted(sets, key=lambda x: str(x["id"])):
        idx = ",".join(str(int(i)) for i in s["indices"])
        blocks.append(f"{s['id']}:{idx}")
    return "\n".join(blocks) + "\n"


def manifest_sha256(sets: Sequence[Dict[str, Any]]) -> str:
    return hashlib.sha256(canonical_sets_payload(sets).encode("utf-8")).hexdigest()


def verify_manifest(manifest: Dict[str, Any]) -> bool:
    expected = str(manifest.get("manifest_sha256") or "")
    sets = manifest.get("sets") or []
    return bool(expected) and expected == manifest_sha256(sets)


def draw_stratified_disjoint(
    y: np.ndarray,
    reservoir: np.ndarray,
    *,
    n_sets: int,
    holdout_n: int,
    draw_seed: int,
    risky_threshold: float,
) -> List[Dict[str, Any]]:
    """Carve reservoir into n_sets stratified holdouts without replacement."""
    y_res = y[reservoir]
    risky_mask = y_res >= risky_threshold
    risky_local = np.flatnonzero(risky_mask)
    safe_local = np.flatnonzero(~risky_mask)
    n_res = len(reservoir)
    n_risky_target = int(round(holdout_n * (len(risky_local) / max(n_res, 1))))
    n_risky_target = min(max(n_risky_target, 0), holdout_n)
    n_safe_target = holdout_n - n_risky_target

    need_r = n_sets * n_risky_target
    need_s = n_sets * n_safe_target
    if need_r > len(risky_local) or need_s > len(safe_local):
        raise ValueError(
            f"reservoir too small for {n_sets}×{holdout_n} stratified "
            f"(need risky={need_r}/{len(risky_local)}, safe={need_s}/{len(safe_local)})"
        )

    rng = np.random.default_rng(draw_seed)
    risky_perm = rng.permutation(risky_local)
    safe_perm = rng.permutation(safe_local)
    r_off = 0
    s_off = 0
    sets: List[Dict[str, Any]] = []
    for i in range(n_sets):
        pick_r = risky_perm[r_off : r_off + n_risky_target]
        pick_s = safe_perm[s_off : s_off + n_safe_target]
        r_off += n_risky_target
        s_off += n_safe_target
        local = np.concatenate([pick_r, pick_s])
        rng.shuffle(local)
        global_idx = sorted(int(reservoir[j]) for j in local)
        sets.append(
            {
                "id": f"H{i + 1:02d}",
                "indices": global_idx,
                "n_risky": int(n_risky_target),
                "n_safe": int(n_safe_target),
                "indices_sha256": _indices_sha256(global_idx),
            }
        )
    return sets


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Freeze multi-holdout manifest (Decision A)")
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
    p.add_argument("--n-train", type=int, default=5000)
    p.add_argument("--n-sets", type=int, default=N_SETS)
    p.add_argument("--holdout-n", type=int, default=HOLDOUT_N)
    p.add_argument("--draw-seed", type=int, default=DRAW_SEED)
    p.add_argument("--out", type=Path, default=DEFAULT_MANIFEST)
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing manifest (invalidates prior A claims)",
    )
    args = p.parse_args(argv)

    print("Multi-holdout freeze (§4.3.1 Decision A)")
    print("=" * 60)

    if args.out.is_file() and not args.force:
        existing = json.loads(args.out.read_text(encoding="utf-8"))
        print("VERDICT: PREFILTER_MULTI_HOLDOUT_FREEZE_SKIP")
        print(f"  manifest exists: {args.out}")
        print(f"  manifest_sha256: {existing.get('manifest_sha256')}")
        print("  refuse overwrite (Bridge-seal). Use --force to invalidate prior A claims.")
        return 0

    for path, label in ((args.batch_5k, "5k"), (args.batch_20k, "20k")):
        if not (path / "features.jsonl").is_file():
            print("VERDICT: PREFILTER_MULTI_HOLDOUT_FREEZE_FAIL")
            print(f"  missing {label}: {path / 'features.jsonl'}")
            return 1

    train = _load("train_prefilter", "scripts/train_prefilter_model.py")
    rows_5k = sorted(
        train.load_severity_proxy_rows(args.batch_5k), key=lambda r: int(r["seed"])
    )
    rows_20k = sorted(
        train.load_severity_proxy_rows(args.batch_20k), key=lambda r: int(r["seed"])
    )
    _, y5, _ = train.matrix_from_rows(rows_5k)
    _, y20, _ = train.matrix_from_rows(rows_20k)

    n5 = len(y5)
    n_train_5k = max(1, int(n5 * 0.8))
    if n_train_5k >= n5:
        n_train_5k = n5 - 1
    # Historical single holdout (documentation only — not part of A claim sets)
    hist_indices = list(range(n_train_5k, n5))
    hist_n_risky = int(np.sum(y5[hist_indices] >= train.RISKY_THRESHOLD))

    if args.n_train > len(y20):
        print("VERDICT: PREFILTER_MULTI_HOLDOUT_FREEZE_FAIL")
        print("  n_train exceeds 20k corpus")
        return 1
    reservoir = np.arange(args.n_train, len(y20))
    try:
        sets = draw_stratified_disjoint(
            y20,
            reservoir,
            n_sets=args.n_sets,
            holdout_n=args.holdout_n,
            draw_seed=args.draw_seed,
            risky_threshold=float(train.RISKY_THRESHOLD),
        )
    except ValueError as e:
        print("VERDICT: PREFILTER_MULTI_HOLDOUT_FREEZE_FAIL")
        print(f"  {e}")
        return 1

    feat_5k = args.batch_5k / "features.jsonl"
    feat_20k = args.batch_20k / "features.jsonl"
    m_hash = manifest_sha256(sets)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest: Dict[str, Any] = {
        "schema": "prefilter_multi_holdout_manifest_v1",
        "decision": "A",
        "gate_map": "docs/RaaS_BUS_EXPANSION_v0.md §4.3.1",
        "frozen_at_utc": now,
        "draw_seed": args.draw_seed,
        "n_sets": args.n_sets,
        "holdout_n": args.holdout_n,
        "claim_rule": "mean ± std across sets; never best set",
        "overwrite_policy": "refuse unless --force (invalidates prior A claims)",
        "path1": "blocked_until_baseline_claim_after_this_freeze",
        "corpus": {
            "batch_5k": str(args.batch_5k.relative_to(_ROOT)),
            "batch_20k": str(args.batch_20k.relative_to(_ROOT)),
            "features_5k_sha256": _file_sha256(feat_5k),
            "features_20k_sha256": _file_sha256(feat_20k),
            "train": "extremes_5k seed_split first 80% (n=4000)",
            "reservoir": f"extremes_20k[{args.n_train}:] stratified risky/non-risky",
            "n_train_prefix_20k": args.n_train,
            "risky_threshold": float(train.RISKY_THRESHOLD),
        },
        "historical_single_holdout": {
            "role": "historical_raw_reference_only_not_in_A_claim",
            "source": "extremes_5k seed_split holdout",
            "indices": hist_indices,
            "n": len(hist_indices),
            "n_risky": hist_n_risky,
            "claim_note": "+4.48% ± 1.47pp model-seed σ; composition variance excluded",
        },
        "sets": sets,
        "manifest_sha256": m_hash,
        "live_execution": False,
    }
    assert verify_manifest(manifest)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"n_sets={args.n_sets}  holdout_n={args.holdout_n}  draw_seed={args.draw_seed}")
    for s in sets:
        print(f"  {s['id']}: n_risky={s['n_risky']}  indices_sha256={s['indices_sha256'][:12]}…")
    print(f"manifest_sha256: {m_hash}")
    print(f"wrote: {args.out}")
    print("VERDICT: PREFILTER_MULTI_HOLDOUT_FREEZE_OK")
    print("  next: make raas-prefilter-multi-holdout-eval (no re-draw)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
