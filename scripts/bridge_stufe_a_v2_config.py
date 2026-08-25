"""Frozen Stufe-A v2 constants. Do not retune after 2026-08-18 without a new pre-reg."""

from __future__ import annotations

BRIDGE_STUFE_A_V2_SEED = 20260818
N_DRAWS = 21
MAJORITY_MIN = 11
BORDERLINE_K = frozenset({10, 11, 12})
DEFINITIVE_MIN = 13
THINNING_SEED_OFFSET = 1_000
SURROGATE_SEED_OFFSET = 10_000

V2_LABELS: tuple[str, ...] = (
    "V2_POSITIVBEFUND",
    "V2_NEGATIVBEFUND",
    "V2_DISSOZIIERT",
    "V2_UNSPEZIFISCH",
    "V2_INCONCLUSIVE",
)
