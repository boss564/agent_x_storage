#!/usr/bin/env python3
"""Phase 4A — train queue-priority prefilter (GBT) + backlog simulation.

Purpose (Gate-Map §4.2): improve wait time of high-severity requests under
backlog vs FIFO. Never skip core. Never train on gateway labels.
Never cite AUC-against-gate as success.

Backend: LightGBM if importable, else sklearn HistGradientBoosting (GBT).

Usage:
  PYTHONPATH=. python3 scripts/train_prefilter_model.py \\
    --data data/synthetic/prefilter/extremes
  make raas-prefilter-train
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"
FEATURE_NAMES = [
    "latency_ms",
    "slippage_pct",
    "pool_depth_usd",
    "volatility_24h",
    "gas_price_gwei",
    "oracle_deviation_pct",
    "mev_bundle_activity",
    "strategy_complexity_score",
]
RISKY_THRESHOLD = 0.85  # severity_score HIGH band


def load_severity_proxy_rows(data_dir: Path) -> List[Dict[str, Any]]:
    jsonl = data_dir / "features.jsonl"
    if not jsonl.is_file():
        raise FileNotFoundError(jsonl)
    rows: List[Dict[str, Any]] = []
    with jsonl.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("label_mode") != "severity_proxy":
                continue
            if row.get("live_execution") is not False:
                continue
            rows.append(row)
    if not rows:
        raise ValueError("no severity_proxy rows in batch")
    return rows


def matrix_from_rows(rows: Sequence[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    x = np.array([[float(r[c]) for c in FEATURE_NAMES] for r in rows], dtype=np.float64)
    y = np.array([float(r["severity_score"]) for r in rows], dtype=np.float64)
    seeds = np.array([int(r["seed"]) for r in rows], dtype=np.int64)
    return x, y, seeds


def seed_split(
    x: np.ndarray,
    y: np.ndarray,
    seeds: np.ndarray,
    *,
    train_frac: float = 0.8,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Holdout by seed order — not shuffled random mix."""
    order = np.argsort(seeds, kind="mergesort")
    n = len(order)
    n_train = max(1, int(n * train_frac))
    if n_train >= n:
        n_train = n - 1
    tr, te = order[:n_train], order[n_train:]
    return x[tr], y[tr], x[te], y[te]


def train_gbt(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_val: np.ndarray,
    y_val: np.ndarray,
    *,
    seed: int = 20260827,
) -> Tuple[Any, str, Dict[str, float]]:
    """Returns (model, backend_name, val_metrics)."""
    try:
        import lightgbm as lgb

        train_set = lgb.Dataset(x_train, label=y_train, feature_name=FEATURE_NAMES)
        val_set = lgb.Dataset(x_val, label=y_val, reference=train_set, feature_name=FEATURE_NAMES)
        params = {
            "objective": "regression",
            "metric": "l2",
            "learning_rate": 0.05,
            "num_leaves": 31,
            "feature_fraction": 0.9,
            "bagging_fraction": 0.8,
            "bagging_freq": 1,
            "verbosity": -1,
            "seed": seed,
        }
        model = lgb.train(
            params,
            train_set,
            num_boost_round=200,
            valid_sets=[val_set],
            callbacks=[lgb.early_stopping(25, verbose=False)],
        )
        pred = model.predict(x_val)
        rmse = float(np.sqrt(np.mean((pred - y_val) ** 2)))
        return model, "lightgbm", {"val_rmse": rmse}
    except ImportError:
        from sklearn.ensemble import HistGradientBoostingRegressor

        model = HistGradientBoostingRegressor(
            max_depth=6,
            learning_rate=0.05,
            max_iter=200,
            random_state=seed,
            early_stopping=True,
            validation_fraction=0.15,
            n_iter_no_change=20,
        )
        model.fit(x_train, y_train)
        pred = model.predict(x_val)
        rmse = float(np.sqrt(np.mean((pred - y_val) ** 2)))
        return model, "sklearn_hist_gradient_boosting", {"val_rmse": rmse}


def predict_scores(model: Any, backend: str, x: np.ndarray) -> np.ndarray:
    if backend == "lightgbm":
        return np.asarray(model.predict(x), dtype=np.float64)
    return np.asarray(model.predict(x), dtype=np.float64)


def feature_importance(
    model: Any,
    backend: str,
    x_val: np.ndarray,
    y_val: np.ndarray,
) -> Dict[str, float]:
    if backend == "lightgbm":
        raw = model.feature_importance(importance_type="gain")
        total = float(np.sum(raw)) or 1.0
        return {FEATURE_NAMES[i]: float(raw[i] / total) for i in range(len(FEATURE_NAMES))}
    try:
        from sklearn.inspection import permutation_importance

        r = permutation_importance(
            model, x_val, y_val, n_repeats=5, random_state=20260827, scoring="neg_mean_squared_error"
        )
        raw = np.maximum(r.importances_mean, 0.0)
        total = float(np.sum(raw)) or 1.0
        return {FEATURE_NAMES[i]: float(raw[i] / total) for i in range(len(FEATURE_NAMES))}
    except Exception:
        return {name: 0.0 for name in FEATURE_NAMES}


def simulate_backlog_wait(
    true_severity: np.ndarray,
    priority_scores: np.ndarray,
    *,
    service_time_s: float = 1.0,
    arrival_interval_s: float = 0.2,
    seed: int = 20260827,
) -> Dict[str, Any]:
    """Backlog sim: arrivals faster than core → queue builds.

    Core processes one request per service_time_s (full check always).
    Compare FIFO vs score-priority vs random for mean wait of risky jobs.
    """
    n = len(true_severity)
    arrivals = np.arange(n, dtype=np.float64) * arrival_interval_s
    risky = true_severity >= RISKY_THRESHOLD

    def _mean_risky_wait(order: np.ndarray) -> float:
        """Process in `order` (indices); wait = start - arrival."""
        t = 0.0
        waits = []
        for idx in order:
            start = max(t, float(arrivals[idx]))
            wait = start - float(arrivals[idx])
            if risky[idx]:
                waits.append(wait)
            t = start + service_time_s
        if not waits:
            return float("nan")
        return float(np.mean(waits))

    fifo_order = np.arange(n)
    prio_order = np.argsort(-priority_scores, kind="mergesort")
    rng = np.random.default_rng(seed)
    rand_order = rng.permutation(n)

    fifo_w = _mean_risky_wait(fifo_order)
    prio_w = _mean_risky_wait(prio_order)
    rand_w = _mean_risky_wait(rand_order)

    # Improvement vs FIFO: positive = better (lower wait)
    improvement_vs_fifo = (
        float("nan")
        if np.isnan(fifo_w) or np.isnan(prio_w) or fifo_w == 0
        else (fifo_w - prio_w) / fifo_w
    )
    beats_fifo = bool(prio_w < fifo_w) if not (np.isnan(prio_w) or np.isnan(fifo_w)) else False
    beats_random = bool(prio_w < rand_w) if not (np.isnan(prio_w) or np.isnan(rand_w)) else False

    return {
        "n": n,
        "n_risky": int(np.sum(risky)),
        "service_time_s": service_time_s,
        "arrival_interval_s": arrival_interval_s,
        "mean_wait_risky_fifo_s": fifo_w,
        "mean_wait_risky_priority_s": prio_w,
        "mean_wait_risky_random_s": rand_w,
        "improvement_vs_fifo": improvement_vs_fifo,
        "beats_fifo": beats_fifo,
        "beats_random": beats_random,
        "metric": "mean_wait_time_of_risky_requests",
        "note": "Full core check for every request; score only reorders queue",
    }


def save_model(model: Any, backend: str, path: Path, meta: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    if backend == "lightgbm":
        model.save_model(str(path))
    else:
        import pickle

        with path.open("wb") as f:
            pickle.dump({"backend": backend, "model": model, "features": FEATURE_NAMES}, f)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def run_training_once(
    data_dir: Path,
    *,
    train_frac: float = 0.8,
    seed: int = 20260827,
    persist_importance: bool = True,
) -> Dict[str, Any]:
    """Train + queue metric for one seed (no model write)."""
    rows = load_severity_proxy_rows(data_dir)
    x, y, seeds = matrix_from_rows(rows)
    x_tr, y_tr, x_te, y_te = seed_split(x, y, seeds, train_frac=train_frac)
    model, backend, val_m = train_gbt(x_tr, y_tr, x_te, y_te, seed=seed)
    scores_te = predict_scores(model, backend, x_te)
    queue = simulate_backlog_wait(y_te, scores_te, seed=seed)
    imp = (
        feature_importance(model, backend, x_te, y_te)
        if persist_importance
        else {name: 0.0 for name in FEATURE_NAMES}
    )
    return {
        "model": model,
        "backend": backend,
        "n_total": len(rows),
        "n_train": int(len(x_tr)),
        "n_holdout": int(len(x_te)),
        "val_metrics": val_m,
        "feature_importance": imp,
        "queue_metric": queue,
        "seed": seed,
    }


def run_queue_seed_spread(
    data_dir: Path,
    *,
    n_seeds: int = 6,
    base_seed: int = 20260827,
    train_frac: float = 0.8,
) -> Dict[str, Any]:
    """Retrain n_seeds times; report mean/std of improvement_vs_fifo.

    Gate-Map §4.2: a single-run % is not an success criterion until spread is known.
    """
    if n_seeds < 2:
        raise ValueError("n_seeds must be >= 2")
    seeds_used: List[int] = []
    improvements: List[float] = []
    runs: List[Dict[str, Any]] = []
    for i in range(n_seeds):
        seed = base_seed + i
        once = run_training_once(
            data_dir, train_frac=train_frac, seed=seed, persist_importance=False
        )
        q = once["queue_metric"]
        imp = q.get("improvement_vs_fifo")
        seeds_used.append(seed)
        improvements.append(float(imp) if imp is not None and not np.isnan(imp) else float("nan"))
        runs.append(
            {
                "seed": seed,
                "backend": once["backend"],
                "improvement_vs_fifo": improvements[-1],
                "beats_fifo": q.get("beats_fifo"),
                "beats_random": q.get("beats_random"),
                "mean_wait_risky_fifo_s": q.get("mean_wait_risky_fifo_s"),
                "mean_wait_risky_priority_s": q.get("mean_wait_risky_priority_s"),
                "n_holdout": once["n_holdout"],
                "n_risky": q.get("n_risky"),
            }
        )

    arr = np.asarray(improvements, dtype=np.float64)
    mean = float(np.nanmean(arr))
    std = float(np.nanstd(arr, ddof=1)) if n_seeds > 1 else 0.0
    # Separable from zero if |mean| > 2σ (and σ finite); can fail honestly
    separable = bool(np.isfinite(mean) and np.isfinite(std) and abs(mean) > 2.0 * std and std >= 0)
    # Also require mean positive (priority better than FIFO on average)
    spread_pass = bool(separable and mean > 0)

    return {
        "verdict": (
            "PREFILTER_QUEUE_SEED_SPREAD_PASS"
            if spread_pass
            else "PREFILTER_QUEUE_SEED_SPREAD_FAIL"
        ),
        "n_seeds": n_seeds,
        "seeds": seeds_used,
        "improvement_vs_fifo_per_seed": improvements,
        "improvement_vs_fifo_mean": mean,
        "improvement_vs_fifo_std": std,
        "separable_from_zero_2sigma": separable,
        "criterion": "mean>0 and |mean|>2*std (ddof=1); single-run % is not success",
        "runs": runs,
        "label_mode": "severity_proxy",
        "purpose": "queue_prioritization_under_backlog",
        "note": "Model approximates gate for sorting; does not predict market risk",
        "scope": SCOPE,
        "live_execution": False,
    }


def run_training_on_split(
    x_tr: np.ndarray,
    y_tr: np.ndarray,
    x_te: np.ndarray,
    y_te: np.ndarray,
    *,
    seed: int = 20260827,
) -> Dict[str, Any]:
    """Train on explicit arrays; queue metric on explicit holdout (no re-split)."""
    model, backend, val_m = train_gbt(x_tr, y_tr, x_te, y_te, seed=seed)
    scores_te = predict_scores(model, backend, x_te)
    queue = simulate_backlog_wait(y_te, scores_te, seed=seed)
    return {
        "backend": backend,
        "n_train": int(len(x_tr)),
        "n_holdout": int(len(x_te)),
        "val_metrics": val_m,
        "queue_metric": queue,
        "seed": seed,
    }


def run_queue_seed_spread_on_split(
    x_tr: np.ndarray,
    y_tr: np.ndarray,
    x_te: np.ndarray,
    y_te: np.ndarray,
    *,
    n_seeds: int = 6,
    base_seed: int = 20260827,
) -> Dict[str, Any]:
    """Like run_queue_seed_spread but train/holdout matrices are fixed."""
    if n_seeds < 2:
        raise ValueError("n_seeds must be >= 2")
    seeds_used: List[int] = []
    improvements: List[float] = []
    runs: List[Dict[str, Any]] = []
    for i in range(n_seeds):
        seed = base_seed + i
        once = run_training_on_split(x_tr, y_tr, x_te, y_te, seed=seed)
        q = once["queue_metric"]
        imp = q.get("improvement_vs_fifo")
        seeds_used.append(seed)
        improvements.append(float(imp) if imp is not None and not np.isnan(imp) else float("nan"))
        runs.append(
            {
                "seed": seed,
                "backend": once["backend"],
                "improvement_vs_fifo": improvements[-1],
                "beats_fifo": q.get("beats_fifo"),
                "beats_random": q.get("beats_random"),
                "mean_wait_risky_fifo_s": q.get("mean_wait_risky_fifo_s"),
                "mean_wait_risky_priority_s": q.get("mean_wait_risky_priority_s"),
                "n_holdout": once["n_holdout"],
                "n_train": once["n_train"],
                "n_risky": q.get("n_risky"),
            }
        )

    arr = np.asarray(improvements, dtype=np.float64)
    mean = float(np.nanmean(arr))
    std = float(np.nanstd(arr, ddof=1)) if n_seeds > 1 else 0.0
    separable = bool(np.isfinite(mean) and np.isfinite(std) and abs(mean) > 2.0 * std and std >= 0)
    spread_pass = bool(separable and mean > 0)
    return {
        "verdict": (
            "PREFILTER_QUEUE_SEED_SPREAD_PASS"
            if spread_pass
            else "PREFILTER_QUEUE_SEED_SPREAD_FAIL"
        ),
        "n_seeds": n_seeds,
        "seeds": seeds_used,
        "improvement_vs_fifo_per_seed": improvements,
        "improvement_vs_fifo_mean": mean,
        "improvement_vs_fifo_std": std,
        "separable_from_zero_2sigma": separable,
        "n_train": int(len(x_tr)),
        "n_holdout": int(len(x_te)),
        "runs": runs,
        "label_mode": "severity_proxy",
        "purpose": "queue_prioritization_under_backlog",
        "live_execution": False,
    }


def run_training(
    data_dir: Path,
    *,
    out_model: Path,
    train_frac: float = 0.8,
    seed: int = 20260827,
) -> Dict[str, Any]:
    once = run_training_once(data_dir, train_frac=train_frac, seed=seed, persist_importance=True)
    model = once["model"]
    backend = once["backend"]
    queue = once["queue_metric"]
    imp = once["feature_importance"]
    val_m = once["val_metrics"]

    # Primary success: can fail
    queue_pass = bool(queue["beats_fifo"] and queue["beats_random"])
    training_pass = True  # pipeline completed; queue may still fail

    result = {
        "verdict_training": "PREFILTER_TRAINING_PASS" if training_pass else "PREFILTER_TRAINING_FAIL",
        "verdict_queue": (
            "PREFILTER_QUEUE_METRIC_PASS" if queue_pass else "PREFILTER_QUEUE_METRIC_FAIL"
        ),
        "backend": backend,
        "n_total": once["n_total"],
        "n_train": once["n_train"],
        "n_holdout": once["n_holdout"],
        "label_mode": "severity_proxy",
        "features": FEATURE_NAMES,
        "val_metrics": val_m,
        "feature_importance": imp,
        "queue_metric": queue,
        "seeds": [seed],
        "scope": SCOPE,
        "live_execution": False,
        "purpose": "queue_prioritization_under_backlog",
        "purpose_statement": (
            "Model approximates the gate verdict for sorting; "
            "it does not predict market risk."
        ),
        "banned": ["auc_against_gate", "core_skip", "model_only_release", "risk_forecast_claim"],
    }

    save_model(
        model,
        backend,
        out_model,
        {k: result[k] for k in result if k != "feature_importance"}
        | {"feature_importance": imp},
    )
    report = out_model.parent / "prefilter_train_report.json"
    report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    result["model_path"] = str(out_model)
    result["report_path"] = str(report)
    return result


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Phase 4A prefilter train + queue metric")
    p.add_argument(
        "--data",
        type=Path,
        default=_ROOT / "data" / "synthetic" / "prefilter" / "extremes",
    )
    p.add_argument(
        "--out-model",
        type=Path,
        default=_ROOT / "models" / "prefilter" / "prefilter_gbt.pkl",
    )
    p.add_argument("--train-frac", type=float, default=0.8)
    p.add_argument("--seed", type=int, default=20260827)
    args = p.parse_args(argv)

    print("Phase 4A prefilter training + queue metric")
    print("=" * 60)
    print(f"data={args.data}")
    try:
        result = run_training(
            args.data,
            out_model=args.out_model,
            train_frac=args.train_frac,
            seed=args.seed,
        )
    except Exception as exc:
        print(f"VERDICT: PREFILTER_TRAINING_FAIL")
        print(f"  error: {exc}")
        return 1

    q = result["queue_metric"]
    print(f"backend={result['backend']}  n_train={result['n_train']}  holdout={result['n_holdout']}")
    print(f"val_rmse={result['val_metrics'].get('val_rmse')}")
    print(
        f"queue mean_wait_risky  fifo={q['mean_wait_risky_fifo_s']:.3f}s  "
        f"prio={q['mean_wait_risky_priority_s']:.3f}s  "
        f"rand={q['mean_wait_risky_random_s']:.3f}s"
    )
    print(f"improvement_vs_fifo={q['improvement_vs_fifo']}")
    print(f"feature_importance={result['feature_importance']}")
    print("=" * 60)
    print(f"VERDICT: {result['verdict_training']}")
    print(f"QUEUE:   {result['verdict_queue']}")
    print(f"report:  {result['report_path']}")
    # Exit 0 if training pipeline OK; queue FAIL is an honest scientific outcome
    return 0 if result["verdict_training"].endswith("_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
