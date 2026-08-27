#!/usr/bin/env python3
"""M1 isolation screen — M2 shared model as negative control only.

Synth-A: label driven by latency_ms.
Synth-B: label driven by mev_bundle_activity (latency noise).

M2: train on A, score B → A's latency rule leaks into B scores (high corr).
M1: train on B, score B → latency corr low; mev corr high.

PASS when M2 shows leak AND M1 does not (scientific negative control).

Usage:
  PYTHONPATH=. python3 scripts/screen_prefilter_m1_isolation.py
  make raas-prefilter-m1-isolation-screen
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from plugins.risk_prefilter.scorer import FEATURE_NAMES  # noqa: E402
from prototypes.raas_hybrid_shell.prefilter_backlog import (  # noqa: E402
    resolve_tenant_prefilter_model,
    tenant_prefilter_dir,
)

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3:
        return 0.0
    ra = np.argsort(np.argsort(a)).astype(np.float64)
    rb = np.argsort(np.argsort(b)).astype(np.float64)
    ra -= ra.mean()
    rb -= rb.mean()
    denom = float(np.sqrt(np.sum(ra * ra) * np.sum(rb * rb)))
    if denom < 1e-12:
        return 0.0
    return float(np.sum(ra * rb) / denom)


def _make_rows(
    n: int,
    *,
    seed: int,
    latency_weight: float,
    mev_weight: float,
) -> Tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    x = np.zeros((n, len(FEATURE_NAMES)), dtype=np.float64)
    # indices: latency_ms=0, mev_bundle_activity=6
    x[:, 0] = rng.uniform(1.0, 200.0, size=n)
    x[:, 1] = rng.uniform(0.0, 3.0, size=n)
    x[:, 2] = 500_000.0
    x[:, 3] = rng.uniform(0.01, 0.08, size=n)
    x[:, 4] = rng.uniform(10.0, 40.0, size=n)
    x[:, 5] = rng.uniform(0.0, 2.0, size=n)
    x[:, 6] = rng.uniform(0.0, 1.0, size=n)
    x[:, 7] = rng.uniform(0.2, 0.8, size=n)
    y = (
        latency_weight * (x[:, 0] / 200.0)
        + mev_weight * x[:, 6]
        + rng.normal(0.0, 0.02, size=n)
    )
    y = np.clip(y, 0.0, 1.0)
    return x, y


def _train_and_dump(x: np.ndarray, y: np.ndarray, path: Path, seed: int) -> str:
    from sklearn.ensemble import HistGradientBoostingRegressor

    model = HistGradientBoostingRegressor(
        max_depth=4,
        learning_rate=0.1,
        max_iter=80,
        random_state=seed,
    )
    model.fit(x, y)
    path.parent.mkdir(parents=True, exist_ok=True)
    import pickle

    with path.open("wb") as f:
        pickle.dump(
            {
                "backend": "sklearn_hist_gradient_boosting",
                "model": model,
                "features": FEATURE_NAMES,
            },
            f,
        )
    return "sklearn_hist_gradient_boosting"


def _score_matrix(model_path: Path, x: np.ndarray) -> np.ndarray:
    from plugins.risk_prefilter.scorer import load_scorer

    scorer = load_scorer(model_path)
    scores = []
    for row in x:
        feats = {FEATURE_NAMES[i]: float(row[i]) for i in range(len(FEATURE_NAMES))}
        scores.append(float(scorer.score(feats)["prefilter_score"]))
    return np.asarray(scores, dtype=np.float64)


def main() -> int:
    print("M1 isolation screen (M2 = negative control only)")
    print("=" * 60)

    # Path isolation (no stats needed)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        a_dir = tenant_prefilter_dir("tenant_a", data_root=root)
        b_dir = tenant_prefilter_dir("tenant_b", data_root=root)
        a_dir.mkdir(parents=True)
        b_dir.mkdir(parents=True)
        (a_dir / "prefilter_gbt.pkl").write_bytes(b"A-WEIGHTS")
        (b_dir / "prefilter_gbt.pkl").write_bytes(b"B-WEIGHTS")
        ra = resolve_tenant_prefilter_model("tenant_a", data_root=root)
        rb = resolve_tenant_prefilter_model("tenant_b", data_root=root)
        path_ok = (
            ra is not None
            and rb is not None
            and ra.resolve() != rb.resolve()
            and ra.read_bytes() == b"A-WEIGHTS"
            and rb.read_bytes() == b"B-WEIGHTS"
            and resolve_tenant_prefilter_model("tenant_missing", data_root=root) is None
        )
        print(f"  {'PASS' if path_ok else 'FAIL'}  path isolation (A≠B, missing→None)")

    x_a, y_a = _make_rows(400, seed=20260827, latency_weight=0.9, mev_weight=0.05)
    x_b, y_b = _make_rows(400, seed=20260828, latency_weight=0.05, mev_weight=0.9)
    # Holdout B
    x_b_te, y_b_te = x_b[300:], y_b[300:]
    x_b_tr, y_b_tr = x_b[:300], y_b[:300]
    x_a_tr, y_a_tr = x_a[:300], y_a[:300]

    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        m_a = tmp_p / "model_a.pkl"
        m_b = tmp_p / "model_b.pkl"
        _train_and_dump(x_a_tr, y_a_tr, m_a, seed=1)
        _train_and_dump(x_b_tr, y_b_tr, m_b, seed=2)

        # M2 negative control: A's weights on B holdout
        scores_m2 = _score_matrix(m_a, x_b_te)
        corr_lat_m2 = _spearman(x_b_te[:, 0], scores_m2)
        corr_mev_m2 = _spearman(x_b_te[:, 6], scores_m2)

        # M1: B's weights on B holdout
        scores_m1 = _score_matrix(m_b, x_b_te)
        corr_lat_m1 = _spearman(x_b_te[:, 0], scores_m1)
        corr_mev_m1 = _spearman(x_b_te[:, 6], scores_m1)

    # Leak visible under M2: latency rule from A shows up on B
    m2_leak = corr_lat_m2 > 0.35 and corr_lat_m2 > corr_mev_m2
    # M1 isolated: mev dominates, latency does not
    m1_ok = corr_mev_m1 > 0.35 and corr_lat_m1 < 0.35 and corr_mev_m1 > corr_lat_m1
    screen_pass = bool(path_ok and m2_leak and m1_ok)

    print(
        f"  M2 (neg): corr(latency,score)={corr_lat_m2:+.3f}  "
        f"corr(mev,score)={corr_mev_m2:+.3f}  leak={m2_leak}"
    )
    print(
        f"  M1:       corr(latency,score)={corr_lat_m1:+.3f}  "
        f"corr(mev,score)={corr_mev_m1:+.3f}  isolated={m1_ok}"
    )

    result: Dict[str, Any] = {
        "verdict": (
            "PREFILTER_M1_ISOLATION_PASS" if screen_pass else "PREFILTER_M1_ISOLATION_FAIL"
        ),
        "path_isolation_ok": path_ok,
        "m2_negative_control": {
            "role": "demonstrate_leak_channel_only_not_operations",
            "corr_latency_score": corr_lat_m2,
            "corr_mev_score": corr_mev_m2,
            "leak_detected": m2_leak,
        },
        "m1": {
            "corr_latency_score": corr_lat_m1,
            "corr_mev_score": corr_mev_m1,
            "isolated": m1_ok,
        },
        "criterion": (
            "M2 shows A's latency rule on B scores; M1 uses B weights → mev dominates, "
            "latency corr low; paths A≠B"
        ),
        "m2_operations": "rejected_v3_4_2",
        "scope": SCOPE,
        "live_execution": False,
        "gate_map": "docs/RaaS_MULTI_TENANT_PREFILTER_M1_PROTO_v0.md §3.3",
    }

    out = _ROOT / "models" / "prefilter" / "prefilter_m1_isolation_screen.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print("=" * 60)
    print(f"VERDICT: {result['verdict']}")
    print(f"report:  {out}")
    return 0 if screen_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
