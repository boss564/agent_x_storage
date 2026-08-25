"""Synthetic occupancy for Agent 6 tests — not sealed Bridge data."""

from __future__ import annotations

import sys
from pathlib import Path

from agents_b2g.diagnostic.config import CANDIDATE_IDS
from agents_b2g.diagnostic.cte_math import OccupancyBundle

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from bridge_stufe_a_v3_pipeline import encode_z_neu_tertile  # noqa: E402


def make_mock_bundle(*, n_bins: int = 512, seed: int = 42) -> OccupancyBundle:
    """Deterministic small bundle for unit tests."""
    import random

    rng = random.Random(seed)
    eth = [1 if rng.random() > 0.7 else 0 for _ in range(n_bins)]
    gno = [1 if rng.random() > 0.65 else 0 for _ in range(n_bins)]
    z_alt = [
        [rng.randint(0, 2) for _ in range(n_bins)],
        [rng.randint(0, 2) for _ in range(n_bins)],
        [rng.randint(0, 2) for _ in range(n_bins)],
    ]
    z_neu_occ: dict[str, list[int]] = {}
    z_neu_ter: dict[str, list[int]] = {}
    for i, cid in enumerate(CANDIDATE_IDS):
        if cid in ("intent_relayers", "stablecoin_mint_burn"):
            occ = [1 if rng.random() > 0.02 else 0 for _ in range(n_bins)]
        elif cid == "liquidations":
            occ = [1 if rng.random() > 0.995 else 0 for _ in range(n_bins)]
        else:
            occ = [1 if rng.random() > (0.85 + 0.02 * i) else 0 for _ in range(n_bins)]
        z_neu_occ[cid] = occ
        z_neu_ter[cid] = encode_z_neu_tertile(occ)

    return OccupancyBundle(
        bridge_eth=eth,
        bridge_gnosis=gno,
        z_alt=z_alt,
        z_neu_occ=z_neu_occ,
        z_neu_ter=z_neu_ter,
        candidate_ids=CANDIDATE_IDS,
        source="mock",
    )
