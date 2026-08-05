"""
Penalty Aggregation Methods for CHI computation.

Replaces the additive sum (Modell A) with configurable alternatives:
  Modell A (SUM):       total = Σ penalties      (current, over-penalizes)
  Modell B (MAX_DAMP):  total = max + λ·Σ(rest)   (dominant maximum)
  Modell C (L2_NORM):   total = √(Σ p_i²)         (euclidean, self-limiting)
  Modell D (MULT):      factor = ∏(1 - p_i/100)    (multiplicative decay)

Usage:
    from agent_x_aggregation import aggregate, AggregationMethod
    total = aggregate(penalties_dict, method=AggregationMethod.MAX_WITH_DAMPING)
"""
from enum import Enum
from typing import Dict


class AggregationMethod(str, Enum):
    SUM = "sum"
    MAX_WITH_DAMPING = "max_damp"
    L2_NORM = "l2_norm"
    P_NORM = "p_norm"
    MULTIPLICATIVE = "mult"


def aggregate(
    penalties: Dict[str, float],
    method: AggregationMethod = AggregationMethod.P_NORM,
    damping_factor: float = 0.2,
    p_exponent: float = 1.5,
) -> float:
    """
    Aggregate penalty values from multiple risk channels into a single deduction.

    Args:
        penalties: Dict mapping channel names to their penalty values (≥0).
        method: Aggregation strategy.
        damping_factor: λ for MAX_WITH_DAMPING (0.0 = only max, 1.0 = full sum).

    Returns:
        Total penalty to subtract from CHI.
    """
    values = [v for v in penalties.values() if v > 0]
    if not values:
        return 0.0

    if method == AggregationMethod.SUM:
        return sum(values)

    elif method == AggregationMethod.MAX_WITH_DAMPING:
        max_val = max(values)
        rest_sum = sum(v for v in values if v < max_val)
        return max_val + damping_factor * rest_sum

    elif method == AggregationMethod.P_NORM:
        # P-Norm: sub-additive but still sensitive to multi-channel activation.
        # p=1.5: between linear sum (p=1) and max (p=∞).
        # Two active channels amplify more than one, but less than full addition.
        return (sum(v ** p_exponent for v in values)) ** (1.0 / p_exponent)

    elif method == AggregationMethod.L2_NORM:
        return (sum(v ** 2 for v in values)) ** 0.5

    elif method == AggregationMethod.MULTIPLICATIVE:
        # Returns the factor to multiply CHI_raw by (1.0 = no penalty)
        factor = 1.0
        for v in values:
            factor *= max(0.0, 1.0 - v / 100.0)
        return factor  # Caller does: score = chi_raw * factor

    return sum(values)  # Fallback


# ============================================================
# Test helper: run all 4 methods against the compound scenario
# ============================================================


def compare_methods(chi_raw: float, penalties: Dict[str, float]) -> Dict[str, float]:
    """Compare all aggregation methods for a given block."""
    results = {"chi_raw": chi_raw}
    for method in AggregationMethod:
        total = aggregate(penalties, method=method)
        if method == AggregationMethod.MULTIPLICATIVE:
            final = max(0.0, min(100.0, round(chi_raw * total, 1)))
        else:
            final = max(0.0, min(100.0, round(chi_raw - total, 1)))
        zone = ("healthy" if final >= 80 else "caution" if final >= 60
                else "stressed" if final >= 40 else "critical")
        results[f"{method.value}_penalty"] = round(total, 1)
        results[f"{method.value}_final"] = final
        results[f"{method.value}_zone"] = zone
    return results
