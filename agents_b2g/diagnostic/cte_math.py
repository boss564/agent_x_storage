"""Pure CTE / LOO / Permutation math — reused from confirmatory, no Bridge data I/O.

Code reuse only: callers supply OccupancyBundle from live captures or test mocks.
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from agents_b2g.diagnostic.live_prereg import Wave38Thresholds

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from bridge_stufe_a_v3_pipeline import cte_observed_grid, encode_z_neu_tertile  # noqa: E402

DIRECTION_IDS = ("ab", "ba")


@dataclass(frozen=True)
class OccupancyBundle:
    """Input for Agent 6 — live or mock, never sealed reference JSON as sole source."""

    bridge_eth: list[int]
    bridge_gnosis: list[int]
    z_alt: list[list[int]]
    z_neu_occ: dict[str, list[int]]
    z_neu_ter: dict[str, list[int]]
    candidate_ids: tuple[str, ...]
    source: str = "live"


@dataclass
class CTEAnalysisResult:
    sum_cte_ref: dict[str, float]
    s_tau_by_candidate: dict[str, dict[str, float]]
    ablations: list[dict[str, Any]]
    permutation: dict[str, Any]
    roles: dict[str, str]
    rel_loo_by_candidate: dict[str, float]
    perm_fail_candidates: list[str]
    perm_fragment: str
    n_unclassified: int
    candidate_roles: dict[str, str] = field(default_factory=dict)


def sum_cte_by_direction(grid: dict[str, list[float]]) -> dict[str, float]:
    return {d: sum(grid[d]) for d in DIRECTION_IDS}


def rel_change(delta: float, ref: float) -> float:
    denom = max(abs(ref), 1e-12)
    return abs(delta) / denom


def circular_shift(occ: Sequence[int], shift: int) -> list[int]:
    n = len(occ)
    if n == 0 or shift % n == 0:
        return list(occ)
    s = shift % n
    return list(occ[-s:]) + list(occ[:-s])


def classify_role(
    *,
    rel_loo: float,
    perm_neutral: bool,
    perm_collapse: float,
    byte_identical: bool,
    thresholds: Wave38Thresholds,
) -> tuple[str, list[str]]:
    if byte_identical or (rel_loo < thresholds.eps_inert and perm_neutral):
        return "inert", (["byte_identical"] if byte_identical else ["rel_loo_and_perm_neutral"])
    if rel_loo >= thresholds.tau_cleansing and perm_collapse > thresholds.rho_collapse:
        return "cleansing_worker", []
    if rel_loo >= thresholds.tau_cleansing and perm_collapse <= thresholds.rho_collapse:
        return "neutral", []
    if rel_loo < thresholds.eps_inert:
        return "inert", ["rel_loo_below_epsilon"]
    return "unclassified", ["gray_zone"]


def compute_verdict(
    *,
    perm_fragment: str,
    n_unclassified: int,
    resampling_fragment: str = "KFOLD_STABLE",
) -> str:
    """Pre-Reg §6 priority — Lag-Spearman verdict-bearing (Amendment A1)."""
    if n_unclassified > 0:
        return "DIAG_INCONCLUSIVE"
    if perm_fragment == "PERM_FAIL":
        return "DIAG_FILTER_ARTIFACT"
    if resampling_fragment == "KFOLD_UNSTABLE":
        return "DIAG_INCONCLUSIVE"
    if perm_fragment == "PERM_PASS" and resampling_fragment == "KFOLD_STABLE":
        return "DIAG_SIGNAL_VALID"
    return "DIAG_INCONCLUSIVE"


def drivers_full(
    z_alt: list[list[int]],
    z_neu_ter: dict[str, list[int]],
    candidate_ids: Sequence[str],
    *,
    exclude: str | None = None,
) -> list[list[int]]:
    ids = [c for c in candidate_ids if c != exclude]
    return z_alt + [z_neu_ter[c] for c in ids]


def run_cte_analysis(
    bundle: OccupancyBundle,
    thresholds: Wave38Thresholds,
    *,
    seed: int | None = None,
    encoding_inert: dict[str, bool] | None = None,
) -> CTEAnalysisResult:
    """LOO ablation + permutation — same logic as confirmatory, parameterized thresholds."""
    seed = seed if seed is not None else thresholds.seed_default
    encoding_inert = encoding_inert or {}
    eth_occ = bundle.bridge_eth
    gno_occ = bundle.bridge_gnosis
    z_alt = bundle.z_alt
    z_neu_occ = bundle.z_neu_occ
    z_neu_ter = bundle.z_neu_ter
    cids = bundle.candidate_ids

    ref_grid = cte_observed_grid(eth_occ, gno_occ, drivers_full(z_alt, z_neu_ter, cids))
    ref_sum = sum_cte_by_direction(ref_grid)

    ablations: list[dict[str, Any]] = []
    rel_loo_by_candidate: dict[str, float] = {}
    occ_rates = {
        cid: (sum(z_neu_occ[cid]) / len(z_neu_occ[cid]) if z_neu_occ[cid] else 0.0)
        for cid in cids
    }

    for cid in cids:
        drivers_loo = drivers_full(z_alt, z_neu_ter, cids, exclude=cid)
        loo_grid = cte_observed_grid(eth_occ, gno_occ, drivers_loo)
        loo_sum = sum_cte_by_direction(loo_grid)
        delta = {d: ref_sum[d] - loo_sum[d] for d in DIRECTION_IDS}
        rel_d = {d: rel_change(delta[d], ref_sum[d]) for d in DIRECTION_IDS}
        rel_loo = max(rel_d.values())
        rel_loo_by_candidate[cid] = rel_loo
        byte_identical = all(
            abs(a - b) < 1e-15
            for d in DIRECTION_IDS
            for a, b in zip(ref_grid[d], loo_grid[d])
        )
        ablations.append(
            {
                "removed_candidate": cid,
                "sum_cte_ref": ref_sum,
                "sum_cte_loo": loo_sum,
                "rel_loo_max": round(rel_loo, 6),
                "byte_identical_to_ref": byte_identical,
                "encoding_inert": encoding_inert.get(cid, False),
            }
        )

    perm_targets: dict[str, Any] = {}
    perm_neutral_map: dict[str, bool] = {}
    perm_collapse_map: dict[str, float] = {}
    n_bins = len(eth_occ)
    shift_step = max(n_bins // thresholds.n_perm_shifts, 1)

    for i, cid in enumerate(cids):
        shifts = [shift_step * k for k in range(1, thresholds.n_perm_shifts + 1)]
        rel_shifts: list[float] = []
        for shift in shifts:
            shifted_occ = circular_shift(z_neu_occ[cid], shift)
            ter_shift = encode_z_neu_tertile(shifted_occ)
            custom = dict(z_neu_ter)
            custom[cid] = ter_shift
            grid_p = cte_observed_grid(
                eth_occ,
                gno_occ,
                drivers_full(z_alt, custom, cids),
            )
            s_p = sum_cte_by_direction(grid_p)
            rel_ab = rel_change(ref_sum["ab"] - s_p["ab"], ref_sum["ab"])
            rel_ba = rel_change(ref_sum["ba"] - s_p["ba"], ref_sum["ba"])
            rel_shifts.append(max(rel_ab, rel_ba))
        p_perm = sum(1 for r in rel_shifts if r >= thresholds.eps_inert) / len(rel_shifts)
        occ = occ_rates[cid]
        rel_loo = rel_loo_by_candidate[cid]
        perm_neutral = p_perm > thresholds.alpha_perm or (
            occ >= thresholds.occ_sat and rel_loo < thresholds.eps_inert
        )
        perm_neutral_map[cid] = perm_neutral
        mean_shift_rel = sum(rel_shifts) / len(rel_shifts) if rel_shifts else 0.0
        perm_collapse = 1.0 - (mean_shift_rel / rel_loo) if rel_loo > 1e-12 else 0.0
        perm_collapse_map[cid] = perm_collapse
        perm_targets[cid] = {
            "occupancy_rate": round(occ, 6),
            "perm_testable": occ < thresholds.occ_sat,
            "p_perm": round(p_perm, 6),
            "perm_neutral": perm_neutral,
            "perm_collapse_ratio": round(perm_collapse, 6),
        }

    perm_fail_ids = [
        cid
        for cid in cids
        if occ_rates[cid] < thresholds.occ_sat
        and perm_targets[cid]["p_perm"] <= thresholds.alpha_perm
    ]
    perm_fragment = "PERM_FAIL" if perm_fail_ids else "PERM_PASS"

    roles: dict[str, str] = {}
    for cid in cids:
        ab = next(a for a in ablations if a["removed_candidate"] == cid)
        if encoding_inert.get(cid):
            roles[cid] = "inert"
            ab["role"] = "inert"
            ab["role_reasons"] = ["INERT_ENCODING"]
            continue
        role, reasons = classify_role(
            rel_loo=rel_loo_by_candidate[cid],
            perm_neutral=perm_neutral_map[cid],
            perm_collapse=perm_collapse_map[cid],
            byte_identical=ab["byte_identical_to_ref"],
            thresholds=thresholds,
        )
        roles[cid] = role
        ab["role"] = role
        ab["role_reasons"] = reasons

    n_unclassified = sum(1 for r in roles.values() if r == "unclassified")

    s_tau: dict[str, dict[str, float]] = {}
    for cid in cids:
        drivers_one = z_alt + [z_neu_ter[cid]]
        grid_one = cte_observed_grid(eth_occ, gno_occ, drivers_one)
        s_one = sum_cte_by_direction(grid_one)
        s_tau[cid] = {d: round(s_one[d], 6) for d in DIRECTION_IDS}

    return CTEAnalysisResult(
        sum_cte_ref={d: round(ref_sum[d], 6) for d in DIRECTION_IDS},
        s_tau_by_candidate=s_tau,
        ablations=ablations,
        permutation={
            "targets": perm_targets,
            "perm_fail_candidates": perm_fail_ids,
            "verdict_fragment": perm_fragment,
        },
        roles=roles,
        rel_loo_by_candidate=rel_loo_by_candidate,
        perm_fail_candidates=perm_fail_ids,
        perm_fragment=perm_fragment,
        n_unclassified=n_unclassified,
        candidate_roles=roles,
    )
