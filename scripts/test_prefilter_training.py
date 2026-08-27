#!/usr/bin/env python3
"""Phase 4A — prefilter training + scorer smoke (PREFILTER_TRAINING_PASS).

Usage:
  PYTHONPATH=. python3 scripts/test_prefilter_training.py
  make raas-prefilter-train
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

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


def main() -> int:
    print("Phase 4A prefilter training smoke")
    print("=" * 60)
    failed = 0
    data = _ROOT / "data" / "synthetic" / "prefilter" / "extremes"
    if not (data / "features.jsonl").is_file():
        print("  FAIL  missing extremes corpus — run make raas-prefilter-batch-extremes")
        return 1

    train = _load("train_prefilter", "scripts/train_prefilter_model.py")
    out_model = _ROOT / "models" / "prefilter" / "prefilter_gbt.pkl"
    result = train.run_training(data, out_model=out_model, train_frac=0.8, seed=20260827)

    if not result["verdict_training"].endswith("_PASS"):
        print(f"  FAIL  {result['verdict_training']}")
        failed += 1
    else:
        print(f"  PASS  {result['verdict_training']} backend={result['backend']}")

    print(f"  INFO  {result['verdict_queue']} (may FAIL honestly)")
    q = result["queue_metric"]
    if "improvement_vs_fifo" not in q or "beats_fifo" not in q:
        print("  FAIL  queue metric shape")
        failed += 1
    else:
        print(
            f"  PASS  queue metric present "
            f"(improvement_vs_fifo={q['improvement_vs_fifo']})"
        )

    # Scorer must not emit gate fields
    from plugins.risk_prefilter.scorer import score_features

    sample = {
        "latency_ms": 100.0,
        "slippage_pct": 0.5,
        "pool_depth_usd": 500000.0,
        "volatility_24h": 0.05,
        "gas_price_gwei": 40.0,
        "oracle_deviation_pct": 10.0,
        "mev_bundle_activity": 0.5,
        "strategy_complexity_score": 0.4,
    }
    scored = score_features(sample, model_path=out_model)
    if "prefilter_score" not in scored or "gate_verdict" in scored:
        print(f"  FAIL  scorer output {scored.keys()}")
        failed += 1
    else:
        print(f"  PASS  scorer prefilter_score={scored['prefilter_score']:.4f}")

    # Optional NATS
    try:
        from plugins.risk_prefilter.nats_bridge import run_nats_roundtrip

        nats_out = run_nats_roundtrip(sample)
        if nats_out.get("via") != "nats_queue_group" or "prefilter_score" not in nats_out:
            print("  FAIL  NATS roundtrip")
            failed += 1
        else:
            print("  PASS  NATS Queue-Group roundtrip")
    except Exception as exc:
        print(f"  SKIP  NATS ({exc})")

    report = {
        "verdict": "PREFILTER_TRAINING_PASS" if failed == 0 else "PREFILTER_TRAINING_FAIL",
        "queue_verdict": result["verdict_queue"],
        "queue_metric": q,
        "backend": result["backend"],
    }
    art = _ROOT / "data" / "raas" / "prefilter_train_last.json"
    try:
        art.parent.mkdir(parents=True, exist_ok=True)
        art.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except OSError:
        pass

    print("=" * 60)
    print(f"VERDICT: {report['verdict']}")
    print(f"QUEUE:   {report['queue_verdict']}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
