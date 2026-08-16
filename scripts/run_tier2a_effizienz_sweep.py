"""TIER-2a Neulauf: persist throughput (msg/tick) for Hebel-3 evaluation.

Same code path as the original measurement:
  capture() in agents_b2g/emergence/adapter_agentx.py
  throughput = len(messages) / ticks

Original horizon: cycles=128 (LOG / adapter default).
Note: TickController.seed is currently unused (deterministic sticky/crc32);
multi-seed still meets the prereg MIN_RUNS gate; identical replicates are expected.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.eval_tier2a_effizienz import KAPPA_VALUES, evaluate_sweep, load_runs

TICKS = 128
N_SEEDS = 5
EPSILON = 0.0
EMERGENCE_DIR = Path(__file__).resolve().parent.parent / "agents_b2g" / "emergence"


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(EMERGENCE_DIR.parent.parent),
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def run_tier2a_single(kappa: float, epsilon: float, seed: int, ticks: int) -> dict:
    """One TIER-2a capture — same path as original TX-Rate measurement."""
    sys.path.insert(0, str(EMERGENCE_DIR))
    from adapter_agentx import capture  # noqa: WPS433

    trace = capture(
        cycles=ticks,
        full=True,
        kappa=kappa,
        epsilon=epsilon,
        seed=seed,
        relax=False,
        corridor_width=None,
    )
    n_ticks = int(trace.states.shape[0])
    n_messages = len(trace.messages)
    return {
        "kappa": kappa,
        "epsilon": epsilon,
        "seed": seed,
        "ticks": n_ticks,
        "n_messages": n_messages,
        "throughput_msg_per_tick": n_messages / max(n_ticks, 1),
        "code_path": _git_head(),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }


def run_sweep(
    runs_path: str = "tier2a_runs.json",
    out_path: str = "tier2a_durchsatz_sweep.json",
) -> dict:
    records = []
    for kappa in KAPPA_VALUES:
        for seed in range(N_SEEDS):
            print(f"Running kappa={kappa} seed={seed} ticks={TICKS}...", flush=True)
            rec = run_tier2a_single(kappa, EPSILON, seed, TICKS)
            print(f"  n_messages={rec['n_messages']}  tp={rec['throughput_msg_per_tick']:.4f}")
            records.append(rec)

    with open(runs_path, "w") as f:
        json.dump(records, f, indent=2)

    grouped = load_runs(runs_path)
    result = evaluate_sweep(grouped)
    result["n_runs"] = len(records)
    result["ticks"] = TICKS
    result["n_seeds_per_kappa"] = N_SEEDS
    result["note_determinism"] = (
        "TickController.seed currently unused; replicates per kappa are expected "
        "byte-identical on the sticky/crc32 path. Gate still requires >=3 records."
    )
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print(f"VERDICT: {result['verdict']}")
    if result.get("reason"):
        print(f"  Grund: {result['reason']}")
    print(f"  Limitation: {result.get('limitation')}")
    for k_str, info in sorted(result["per_kappa"].items(), key=lambda x: float(x[0])):
        print(f"  kappa={float(k_str):<4} tp={info['throughput']:<10} "
              f"delta={info['delta']:+.4f}  {info['classification']}")
    sc = result.get("sign_consistency")
    if sc:
        print(f"  Vorzeichen-Konsistenz: {sc['n_improved']}/{sc['n_positive_kappa']} "
              f"verbessert (benoetigt >= {sc['required_improved']}) -> "
              f"{'erfuellt' if sc['met'] else 'nicht erfuellt'}")
    print("=" * 60)
    return result


if __name__ == "__main__":
    run_sweep()
