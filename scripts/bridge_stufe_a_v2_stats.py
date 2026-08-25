"""Stufe-A v2 stats: exact-N thinning, signed Hawkes hits, V2 verdict, majority.

Does not retune Stufe A. Hawkes/CTE/BH stay in bridge_stufe_a_stats.
"""

from __future__ import annotations

import random
from collections import Counter
from typing import Sequence

from bridge_stufe_a_config import DRIVER_COVERAGE_MIN, N_MIN_EVENTS
from bridge_stufe_a_v2_config import (
    BORDERLINE_K,
    BRIDGE_STUFE_A_V2_SEED,
    DEFINITIVE_MIN,
    MAJORITY_MIN,
    N_DRAWS,
    SURROGATE_SEED_OFFSET,
    THINNING_SEED_OFFSET,
    V2_LABELS,
)


def treatment_rng(seed: int = BRIDGE_STUFE_A_V2_SEED) -> random.Random:
    return random.Random(seed)


def thinning_rng(draw: int, seed: int = BRIDGE_STUFE_A_V2_SEED) -> random.Random:
    if draw < 0:
        raise ValueError("draw must be >= 0")
    return random.Random(seed + THINNING_SEED_OFFSET + draw)


def control_surrogate_rng(draw: int, seed: int = BRIDGE_STUFE_A_V2_SEED) -> random.Random:
    if draw < 0:
        raise ValueError("draw must be >= 0")
    return random.Random(seed + SURROGATE_SEED_OFFSET + draw)


def exact_n_subset(times: Sequence[float], n_star: int, rng: random.Random) -> list[float]:
    """Conditional independent thinning: uniform subset without replacement."""
    if n_star < 0:
        raise ValueError("n_star must be >= 0")
    n = len(times)
    if n < n_star:
        raise ValueError(f"control shorter than N* ({n} < {n_star})")
    if n_star == 0:
        return []
    if n == n_star:
        return sorted(float(t) for t in times)
    idx = rng.sample(range(n), n_star)
    return sorted(float(times[i]) for i in idx)


def hawkes_hit(bh_reject: bool, gamma_hat: float) -> bool:
    """Pre-reg §3.1: sign conjunction on Hawkes only."""
    return bool(bh_reject) and gamma_hat > 0.0


def cte_hit(bh_reject: bool) -> bool:
    """Pre-reg §3.1: CTE is pure BH-reject (plugin CTE >= 0)."""
    return bool(bh_reject)


def count_hawkes_hits(tests: Sequence[dict], pair: str) -> int:
    return sum(
        1
        for t in tests
        if t["pair"] == pair and t["metric"] == "hawkes" and hawkes_hit(t["bh_reject"], float(t["observed"]))
    )


def count_cte_hits(tests: Sequence[dict], pair: str) -> int:
    return sum(
        1
        for t in tests
        if t["pair"] == pair and t["metric"] == "cte" and cte_hit(t["bh_reject"])
    )


def v2_verdict(
    *,
    n_events: dict[str, int],
    driver_coverage: float,
    n_sig_hawkes_treat: int,
    n_sig_cte_treat: int,
    n_sig_hawkes_ctrl: int,
    n_sig_cte_ctrl: int,
) -> str:
    """Pre-reg §5 labels. Hawkes counts must already apply γ̂ > 0."""
    if any(n < N_MIN_EVENTS for n in n_events.values()) or driver_coverage < DRIVER_COVERAGE_MIN:
        return "V2_INCONCLUSIVE"
    treat_h = n_sig_hawkes_treat > 0
    treat_c = n_sig_cte_treat > 0
    ctrl_any = n_sig_hawkes_ctrl > 0 or n_sig_cte_ctrl > 0
    if not treat_h and not treat_c:
        return "V2_NEGATIVBEFUND"
    if ctrl_any:
        return "V2_UNSPEZIFISCH"
    if treat_h and treat_c:
        return "V2_POSITIVBEFUND"
    return "V2_DISSOZIIERT"


def draw_effect_present(label: str) -> bool:
    """Pre-reg §5.0: effect in this draw ⇔ V2_POSITIVBEFUND (full IUT)."""
    return label == "V2_POSITIVBEFUND"


def aggregate_draw_labels(
    labels: Sequence[str],
    *,
    n_draws: int = N_DRAWS,
    majority_min: int = MAJORITY_MIN,
    borderline_k: frozenset[int] = BORDERLINE_K,
    definitive_min: int = DEFINITIVE_MIN,
) -> dict:
    """Majority over per-draw labels. No pooled BH."""
    if len(labels) != n_draws:
        raise ValueError(f"expected {n_draws} draw labels, got {len(labels)}")
    unknown = [lab for lab in labels if lab not in V2_LABELS]
    if unknown:
        raise ValueError(f"unknown v2 labels: {unknown}")
    counts = Counter(labels)
    k_star = max(counts.values())
    leaders = sorted(lab for lab, k in counts.items() if k == k_star)
    unique_leader = len(leaders) == 1
    unique_majority = unique_leader and k_star >= majority_min
    majority_label = leaders[0] if unique_majority else "V2_UNSPEZIFISCH"
    definitive = unique_leader and k_star >= definitive_min
    confirmatory = leaders[0] if definitive else "V2_UNSPEZIFISCH"
    return {
        "n_draws": n_draws,
        "counts": {lab: counts.get(lab, 0) for lab in V2_LABELS},
        "k_star": k_star,
        "leading_labels": leaders,
        "majority_label": majority_label,
        "borderline": unique_leader and k_star in borderline_k,
        "definitive": definitive,
        "confirmatory_verdict": confirmatory,
        "n_effect_present": sum(1 for lab in labels if draw_effect_present(lab)),
    }
