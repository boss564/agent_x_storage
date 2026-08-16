"""TIER-2a efficiency re-evaluation against the HEBEL3 prereg threshold.

Evaluates throughput (msg/tick) across the kappa sweep and decides
POSITIVE / NEGATIVE / INCONCLUSIVE strictly against the pre-registered
thresholds. Consumes persisted run records only.

Prereg (docs/HEBEL3_TIER2A_EFFIZIENZ_PREREG.md, 00ee07a3 + amendment):
  - IMPROVED:      delta >= +5%
  - WORSENED:      delta <= -5%
  - NO CLEAR:      -5% < delta < +5%
  - sign consistency: >= ceil(2/3) of kappa>0 values improved
  - INCONCLUSIVE if |delta| < 5% OR < 3 runs per kappa OR mixed signs
"""

from __future__ import annotations

import json
import math
from typing import Dict, List, Optional

IMPROVED_THRESHOLD = 0.05
WORSENED_THRESHOLD = -0.05
MIN_RUNS_PER_KAPPA = 3
KAPPA_VALUES = [0.0, 0.25, 0.5, 1.0, 2.0]
BASELINE_KAPPA = 0.0

VERDICT_IMPROVED = "VERBESSERT"
VERDICT_WORSENED = "VERSCHLECHTERT"
VERDICT_UNCLEAR = "KEINE_KLARE_WIRKUNG"


def compute_delta(throughput_k0: float, throughput_k: float) -> float:
    if throughput_k0 <= 0:
        raise ValueError("baseline throughput must be positive")
    return (throughput_k - throughput_k0) / throughput_k0


def classify_delta(delta: float) -> str:
    if delta >= IMPROVED_THRESHOLD:
        return VERDICT_IMPROVED
    if delta <= WORSENED_THRESHOLD:
        return VERDICT_WORSENED
    return VERDICT_UNCLEAR


def sign_consistency_required(n_positive_kappa: int) -> int:
    return math.ceil((2.0 / 3.0) * n_positive_kappa)


def mean_throughput(runs: List[dict]) -> Optional[float]:
    vals = [r["throughput_msg_per_tick"] for r in runs]
    if not vals:
        return None
    return sum(vals) / len(vals)


def evaluate_sweep(runs_by_kappa: Dict[float, List[dict]]) -> dict:
    for k in KAPPA_VALUES:
        if len(runs_by_kappa.get(k, [])) < MIN_RUNS_PER_KAPPA:
            return {
                "verdict": "INCONCLUSIVE",
                "reason": (
                    f"zu duenne Datenbasis: kappa={k} hat "
                    f"{len(runs_by_kappa.get(k, []))} Laeufe, "
                    f"benoetigt >= {MIN_RUNS_PER_KAPPA}"
                ),
                "per_kappa": {},
                "sign_consistency": None,
            }

    baseline = mean_throughput(runs_by_kappa[BASELINE_KAPPA])
    positive_kappas = [k for k in KAPPA_VALUES if k > BASELINE_KAPPA]

    per_kappa = {}
    deltas = []
    for k in positive_kappas:
        tp_k = mean_throughput(runs_by_kappa[k])
        delta = compute_delta(baseline, tp_k)
        deltas.append(delta)
        per_kappa[k] = {
            "throughput": round(tp_k, 6),
            "delta": round(delta, 6),
            "classification": classify_delta(delta),
        }
    per_kappa[BASELINE_KAPPA] = {
        "throughput": round(baseline, 6),
        "delta": 0.0,
        "classification": "BASELINE",
    }

    n_improved = sum(1 for d in deltas if d >= IMPROVED_THRESHOLD)
    n_worsened = sum(1 for d in deltas if d <= WORSENED_THRESHOLD)
    required = sign_consistency_required(len(positive_kappas))
    consistency_met = n_improved >= required

    if consistency_met and n_worsened == 0:
        verdict = "POSITIVBEFUND"
    elif n_worsened >= required and n_improved == 0:
        verdict = "NEGATIVBEFUND"
    else:
        verdict = "INCONCLUSIVE"

    return {
        "verdict": verdict,
        "reason": None,
        "per_kappa": {str(k): v for k, v in per_kappa.items()},
        "sign_consistency": {
            "n_positive_kappa": len(positive_kappas),
            "n_improved": n_improved,
            "n_worsened": n_worsened,
            "required_improved": required,
            "met": consistency_met,
        },
        "limitation": (
            "Quote und RT out-of-scope (HEBEL3). Durchsatz-Befund unter Vorbehalt, "
            "dass die Quote nicht geprueft wurde."
        ),
    }


def load_runs(path: str) -> Dict[float, List[dict]]:
    with open(path) as f:
        records = json.load(f)
    grouped: Dict[float, List[dict]] = {k: [] for k in KAPPA_VALUES}
    for rec in records:
        k = float(rec["kappa"])
        if k in grouped:
            grouped[k].append(rec)
    return grouped


def main(runs_path: str = "tier2a_runs.json",
         out_path: str = "tier2a_durchsatz_sweep.json") -> None:
    runs_by_kappa = load_runs(runs_path)
    result = evaluate_sweep(runs_by_kappa)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
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


if __name__ == "__main__":
    main()
