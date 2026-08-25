"""Hebel 4: Class-B flexibility waterfall dispatch.

Order (reaction time × degradation cost):
  battery_storage → ev_mobility → heat_pump

Granularity: cover deficit fully per step while capacity/SoC remain;
if Class-B sum is insufficient, residual deficit lowers W_dyn.

Treatment replaces PASSIVE_FLEX_FRACTION (no max with 0.4).
"""

from __future__ import annotations

from typing import Dict, List, Tuple

PASSIVE_FLEX_FRACTION = 0.4  # stub baseline for null arm — not a measured quantity

# Waterfall order: fast/cheap → slow/costly
WATERFALL_ORDER: List[str] = [
    "battery_storage",
    "ev_mobility",
    "heat_pump",
]

SOC_FLOOR = 0.10
EV_POWER_SHARE = 0.70
BATTERY_HOURS_FULL = 2.0
EV_HOURS_FULL = 1.0
DT_HOURS = 1.0 / 60.0  # one sim-minute step → hours


def passive_flex_kw(class_b_capacities: Dict[str, float]) -> float:
    """Null-arm flex: stub fraction × sum of Class-B capacities."""
    return PASSIVE_FLEX_FRACTION * sum(class_b_capacities.values())


def max_contrib(uid: str, capacity: float, soc: float, shed_headroom: float = 1.0) -> float:
    """Maximum dispatchable kW this step for one Class-B unit."""
    if uid == "battery_storage":
        if soc <= SOC_FLOOR:
            return 0.0
        budget = (soc - SOC_FLOOR) * capacity * BATTERY_HOURS_FULL / max(DT_HOURS, 1e-9)
        # Cap at rated power for this step
        return min(capacity, budget)
    if uid == "ev_mobility":
        if soc <= SOC_FLOOR:
            return 0.0
        budget = (soc - SOC_FLOOR) * capacity * EV_HOURS_FULL / max(DT_HOURS, 1e-9)
        return min(EV_POWER_SHARE * capacity, budget)
    if uid == "heat_pump":
        return capacity * shed_headroom
    return 0.0


def run_waterfall(
    deficit: float,
    capacities: Dict[str, float],
    soc: Dict[str, float],
    shed_headroom: float = 1.0,
) -> Tuple[Dict[str, float], float, Dict[str, float]]:
    """Cover deficit fully in waterfall order while capacity remains.

    Returns: (dispatch_kw, residual_deficit, updated_soc)
    """
    remaining = max(0.0, float(deficit))
    dispatch: Dict[str, float] = {uid: 0.0 for uid in WATERFALL_ORDER}
    new_soc = dict(soc)

    for uid in WATERFALL_ORDER:
        if remaining <= 1e-12:
            break
        if uid not in capacities:
            continue
        cap = capacities[uid]
        s = new_soc.get(uid, 1.0)
        avail = max_contrib(uid, cap, s, shed_headroom)
        take = min(remaining, avail)
        if take <= 0:
            continue
        dispatch[uid] = take
        remaining -= take
        if uid in ("battery_storage", "ev_mobility"):
            hours_full = BATTERY_HOURS_FULL if uid == "battery_storage" else EV_HOURS_FULL
            energy = take * DT_HOURS
            denom = max(cap * hours_full, 1e-9)
            new_soc[uid] = max(SOC_FLOOR, s - energy / denom)

    return dispatch, remaining, new_soc


def flex_available_null(capacities: Dict[str, float]) -> float:
    return passive_flex_kw(capacities)


def flex_available_treatment(dispatch: Dict[str, float]) -> float:
    """Treatment: active dispatch only — replaces 0.4, no max()."""
    return sum(dispatch.values())
