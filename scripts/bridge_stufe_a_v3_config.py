"""Frozen Stufe-A v3 pre-reg constants (Z_neu CTE extension)."""

from __future__ import annotations

from bridge_stufe_a_config import (
    FDR_Q,
    LAGS_MIN,
    N_LAGS,
    N_SURROGATES,
    WINDOW_END_UTC,
    WINDOW_START_UTC,
    n_minute_bins,
)

BRIDGE_STUFE_A_V3_SEED = 20260819
K_FOLDS = 9
FOLD_DAYS = 10
MINUTES_PER_DAY = 24 * 60

CANDIDATE_IDS: tuple[str, ...] = (
    "chainlink",
    "intent_relayers",
    "liquidations",
    "stablecoin_mint_burn",
    "mev_cluster",
)

N_CANDIDATES = len(CANDIDATE_IDS)
N_DIRECTIONS = 2
DIRECTION_IDS: tuple[str, ...] = ("ab", "ba")
N_V3_TESTS = N_CANDIDATES * N_DIRECTIONS * N_LAGS  # 310
N_BASELINE_TESTS = N_DIRECTIONS * N_LAGS  # 62, Z_alt only (descriptive gate)

# Chainlink feed-strikt exclusion (Pre-Reg §3.0.1).
CHAINLINK_EXCLUDED: tuple[tuple[str, str], ...] = (("ethereum", "USDT/USD"),)

DEFAULT_INPUTS = {
    "coverage_gate": "bridge_stufe_a_v3_coverage_gate.json",
    "bridge_eth": "bridge_eth.jsonl",
    "bridge_gnosis": "bridge_gnosis.jsonl",
    "drivers": "drivers_90d.jsonl",
    "chainlink": "bridge_stufe_a_v3_chainlink.jsonl",
    "intent_relayers": "bridge_stufe_a_v3_intent_relayers.jsonl",
    "liquidations": "bridge_stufe_a_v3_liquidations.jsonl",
    "stablecoin_mint_burn": "bridge_stufe_a_v3_stablecoin_mint_burn.jsonl",
    "mev_cluster": "bridge_stufe_a_v3_mev_cluster.jsonl",
}


def n_bins() -> int:
    return n_minute_bins()


def fold_minute_ranges() -> list[tuple[int, int]]:
    """Nine disjoint 10-day blocks covering the 90-day window."""
    n = n_bins()
    block = FOLD_DAYS * MINUTES_PER_DAY
    if K_FOLDS * block != n:
        raise ValueError(f"fold geometry mismatch: {K_FOLDS}×{block} != {n}")
    return [(k * block, (k + 1) * block) for k in range(K_FOLDS)]
