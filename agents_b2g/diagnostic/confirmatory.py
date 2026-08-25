"""Confirmatory Bridge Diagnostic pipeline — Pre-Reg §2–§6.

Ablation (LOO observed CTE) + Permutation (circular shift) + descriptive K-Fold.
No surrogate p-values; verdict from binding §6 mapping.
"""

from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from agents_b2g.diagnostic.config import (
    ALPHA_PERM,
    BRIDGE_DIAGNOSTIC_SEED,
    CANDIDATE_IDS,
    EPS_INERT,
    EVENT_DENSITY_RATIO,
    N_PERM_SHIFTS,
    OCC_SAT,
    P_SIGN_MIN,
    PRE_REG_PATH,
    RHO_COLLAPSE,
    TAU_CLEANSING,
)
from agents_b2g.diagnostic.informativity_gate import run_informativity_gate

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from bridge_stufe_a_config import LAGS_MIN  # noqa: E402
from bridge_stufe_a_pipeline import load_driver_series  # noqa: E402
from bridge_stufe_a_stats import encode_drivers_tertiles  # noqa: E402
from bridge_stufe_a_v3_config import (  # noqa: E402
    DEFAULT_INPUTS,
    DIRECTION_IDS,
    fold_minute_ranges,
)
from bridge_stufe_a_v3_load import load_bridge_occupancy, load_candidate_occupancy  # noqa: E402
from bridge_stufe_a_v3_pipeline import (  # noqa: E402
    cte_observed_grid,
    encode_z_neu_tertile,
    load_integrity_gate,
    slice_drivers,
    slice_occ,
)


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


def p_sign_fold(full: dict[str, list[float]], fold: dict[str, list[float]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for d in DIRECTION_IDS:
        matches = sum(1 for a, b in zip(full[d], fold[d]) if (a >= 0) == (b >= 0))
        out[d] = matches / len(LAGS_MIN) if LAGS_MIN else 0.0
    return out


def classify_role(
    *,
    rel_loo: float,
    perm_neutral: bool,
    perm_collapse: float,
    byte_identical: bool,
) -> tuple[str, list[str]]:
    if byte_identical or (rel_loo < EPS_INERT and perm_neutral):
        return "inert", (["byte_identical"] if byte_identical else ["rel_loo_and_perm_neutral"])
    if rel_loo >= TAU_CLEANSING and perm_collapse > RHO_COLLAPSE:
        return "cleansing_worker", []
    if rel_loo >= TAU_CLEANSING and perm_collapse <= RHO_COLLAPSE:
        return "neutral", []
    if rel_loo < EPS_INERT:
        return "inert", ["rel_loo_below_epsilon"]
    return "unclassified", ["gray_zone"]


def compute_verdict(
    *,
    perm_fragment: str,
    n_unclassified: int,
    skip_ex_post: bool,
) -> str:
    """Pre-Reg §6.2 priority table (Phase 1 only when skip_ex_post)."""
    if n_unclassified > 0:
        return "DIAG_INCONCLUSIVE"
    if perm_fragment == "PERM_FAIL":
        return "DIAG_FILTER_ARTIFACT"
    if perm_fragment == "PERM_PASS":
        return "DIAG_SIGNAL_VALID"
    return "DIAG_INCONCLUSIVE"


def run_confirmatory(
    *,
    input_dir: Path,
    informativity_gate_path: Path,
    integrity_gate_path: Path,
    v3_ergebnis_path: Path,
    bridge_eth: str = DEFAULT_INPUTS["bridge_eth"],
    bridge_gnosis: str = DEFAULT_INPUTS["bridge_gnosis"],
    drivers_path: str = DEFAULT_INPUTS["drivers"],
    skip_ex_post: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    gate = json.loads(informativity_gate_path.read_text(encoding="utf-8"))
    if gate.get("status") != "PASS":
        raise SystemExit(f"informativity gate blocked: {gate.get('blockers')}")

    load_integrity_gate(integrity_gate_path)
    v3_body = json.loads(v3_ergebnis_path.read_text(encoding="utf-8"))
    if v3_body.get("verdict") != "V3_PERSISTENZ":
        raise SystemExit(f"v3 verdict not V3_PERSISTENZ: {v3_body.get('verdict')}")

    eth_occ, _ = load_bridge_occupancy(input_dir / bridge_eth)
    gno_occ, _ = load_bridge_occupancy(input_dir / bridge_gnosis)
    gas, btc, cex = load_driver_series(str(input_dir / drivers_path))
    g_ter, b_ter, c_ter, _ = encode_drivers_tertiles(gas, btc, cex)
    z_alt = [g_ter, b_ter, c_ter]

    z_neu_occ: dict[str, list[int]] = {}
    z_neu_ter: dict[str, list[int]] = {}
    occ_rates: dict[str, float] = {}
    for cid in CANDIDATE_IDS:
        occ, _ = load_candidate_occupancy(cid, input_dir / DEFAULT_INPUTS[cid])
        z_neu_occ[cid] = occ
        z_neu_ter[cid] = encode_z_neu_tertile(occ)
        occ_rates[cid] = sum(occ) / len(occ) if occ else 0.0

    def drivers_full(custom_ter: dict[str, list[int]] | None = None) -> list[list[int]]:
        ter = custom_ter or z_neu_ter
        return z_alt + [ter[c] for c in CANDIDATE_IDS]

    ref_grid = cte_observed_grid(eth_occ, gno_occ, drivers_full())
    ref_sum = sum_cte_by_direction(ref_grid)
    ref_total = {d: ref_sum[d] for d in DIRECTION_IDS}

    # --- Ablation LOO ---
    print("Ablation LOO (6 driver sets)...", flush=True)
    ablations: list[dict[str, Any]] = []
    rel_loo_by_candidate: dict[str, float] = {}
    for cid in CANDIDATE_IDS:
        loo_ter = {k: v for k, v in z_neu_ter.items() if k != cid}
        drivers_loo = z_alt + [loo_ter[k] for k in CANDIDATE_IDS if k != cid]
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
                "delta_sum_cte": delta,
                "rel_loo": {d: round(rel_d[d], 6) for d in DIRECTION_IDS},
                "rel_loo_max": round(rel_loo, 6),
                "byte_identical_to_ref": byte_identical,
                "encoding_status_gate": gate["candidates"][cid]["encoding_status"],
            }
        )

    # --- Permutation per candidate ---
    print("Permutation (5 candidates × 100 shifts)...", flush=True)
    perm_targets: dict[str, Any] = {}
    perm_neutral_map: dict[str, bool] = {}
    perm_collapse_map: dict[str, float] = {}
    n_bins = len(eth_occ)
    shift_step = max(n_bins // 100, 1)

    for i, cid in enumerate(CANDIDATE_IDS):
        rng = random.Random(BRIDGE_DIAGNOSTIC_SEED + 1000 * (i + 1))
        shifts = [shift_step * k for k in range(1, N_PERM_SHIFTS + 1)]
        rel_shifts: list[float] = []
        for shift in shifts:
            shifted_occ = circular_shift(z_neu_occ[cid], shift)
            ter_shift = encode_z_neu_tertile(shifted_occ)
            custom = dict(z_neu_ter)
            custom[cid] = ter_shift
            grid_p = cte_observed_grid(eth_occ, gno_occ, drivers_full(custom))
            s_p = sum_cte_by_direction(grid_p)
            rel_ab = rel_change(ref_sum["ab"] - s_p["ab"], ref_sum["ab"])
            rel_ba = rel_change(ref_sum["ba"] - s_p["ba"], ref_sum["ba"])
            rel_shifts.append(max(rel_ab, rel_ba))
        p_perm = sum(1 for r in rel_shifts if r >= EPS_INERT) / len(rel_shifts)
        occ = occ_rates[cid]
        rel_loo = rel_loo_by_candidate[cid]
        perm_neutral = p_perm > ALPHA_PERM or (occ >= OCC_SAT and rel_loo < EPS_INERT)
        perm_neutral_map[cid] = perm_neutral

        # perm_collapse for role: LOO effect vs mean permuted LOO-like shift
        mean_shift_rel = sum(rel_shifts) / len(rel_shifts) if rel_shifts else 0.0
        if rel_loo > 1e-12:
            perm_collapse = 1.0 - (mean_shift_rel / rel_loo)
        else:
            perm_collapse = 0.0
        perm_collapse_map[cid] = perm_collapse

        perm_targets[cid] = {
            "occupancy_rate": round(occ, 6),
            "perm_testable": occ < OCC_SAT,
            "p_perm": round(p_perm, 6),
            "perm_neutral": perm_neutral,
            "mean_shift_rel": round(mean_shift_rel, 6),
            "perm_collapse_ratio": round(perm_collapse, 6),
            "n_shifts": N_PERM_SHIFTS,
        }

    perm_fail_ids = [
        cid
        for cid in CANDIDATE_IDS
        if occ_rates[cid] < OCC_SAT and perm_targets[cid]["p_perm"] <= ALPHA_PERM
    ]
    perm_fragment = "PERM_FAIL" if perm_fail_ids else "PERM_PASS"

    # Assign roles
    roles: dict[str, str] = {}
    for cid in CANDIDATE_IDS:
        ab = next(a for a in ablations if a["removed_candidate"] == cid)
        role, reasons = classify_role(
            rel_loo=rel_loo_by_candidate[cid],
            perm_neutral=perm_neutral_map[cid],
            perm_collapse=perm_collapse_map[cid],
            byte_identical=ab["byte_identical_to_ref"],
        )
        roles[cid] = role
        ab["role"] = role
        ab["role_reasons"] = reasons
        ab["perm_collapse_ratio"] = round(perm_collapse_map[cid], 6)

    n_unclassified = sum(1 for r in roles.values() if r == "unclassified")

    # --- Descriptive K-Fold (no verdict weight per Leserhinweise §6) ---
    folds: list[dict[str, Any]] = []
    fold_ranges = fold_minute_ranges()
    fold_event_counts: dict[str, list[int]] = {cid: [] for cid in CANDIDATE_IDS}
    for k, (start, end) in enumerate(fold_ranges):
        eth_f = slice_occ(eth_occ, start, end)
        gno_f = slice_occ(gno_occ, start, end)
        zf = slice_drivers(z_alt, start, end)
        zall = [slice_occ(z_neu_ter[c], start, end) for c in CANDIDATE_IDS]
        fold_grid = cte_observed_grid(eth_f, gno_f, zf + zall)
        ps = p_sign_fold(ref_grid, fold_grid)
        unstable = ps["ab"] < P_SIGN_MIN or ps["ba"] < P_SIGN_MIN
        for cid in CANDIDATE_IDS:
            fold_event_counts[cid].append(sum(slice_occ(z_neu_occ[cid], start, end)))
        folds.append(
            {
                "fold_index": k,
                "minute_range": [start, end],
                "p_sign_ab": round(ps["ab"], 6),
                "p_sign_ba": round(ps["ba"], 6),
                "localized_break": unstable,
            }
        )

    medians = {cid: sorted(v)[len(v) // 2] for cid, v in fold_event_counts.items()}
    for fold in folds:
        k = fold["fold_index"]
        start, end = fold_ranges[k]
        if not fold["localized_break"]:
            fold["attribution"] = None
            continue
        market = any(
            fold_event_counts[cid][k] > EVENT_DENSITY_RATIO * medians[cid]
            for cid in CANDIDATE_IDS
            if medians[cid] > 0
        )
        fold["attribution"] = "MARKET_EVENT" if market else "UNEXPLAINED_LOCAL"

    n_break = sum(1 for f in folds if f["localized_break"])
    kfold_fragment = "KFOLD_STABLE" if n_break <= 1 else "KFOLD_LOCALIZED_BREAK"

    in_silico_pass = perm_fragment == "PERM_PASS" and (
        kfold_fragment == "KFOLD_STABLE"
        or all(f.get("attribution") == "MARKET_EVENT" for f in folds if f["localized_break"])
    )
    in_silico_fragment = "DIAG_IN_SILICO_PASS" if in_silico_pass else "DIAG_FILTER_ARTIFACT"

    final_verdict = compute_verdict(
        perm_fragment=perm_fragment,
        n_unclassified=n_unclassified,
        skip_ex_post=skip_ex_post,
    )

    ablation_doc = {
        "reference": "Z_alt_union_all_z_neu_ter",
        "sum_cte_ref": ref_sum,
        "ablations": ablations,
        "cleansing_workers": [c for c, r in roles.items() if r == "cleansing_worker"],
        "inert_components": [c for c, r in roles.items() if r == "inert"],
        "neutral_components": [c for c, r in roles.items() if r == "neutral"],
        "unclassified": [c for c, r in roles.items() if r == "unclassified"],
    }

    permutation_doc = {
        "n_shifts": N_PERM_SHIFTS,
        "alpha_perm": ALPHA_PERM,
        "eps_inert": EPS_INERT,
        "targets": perm_targets,
        "perm_fail_candidates": perm_fail_ids,
        "verdict_fragment": perm_fragment,
    }

    kfold_doc = {
        "k_folds": len(folds),
        "note": "Descriptive only — P_sign non-discriminative (Leserhinweise §6)",
        "folds": folds,
        "n_unstable_folds": n_break,
        "verdict_fragment": kfold_fragment,
    }

    sens = v3_body.get("sensitivity_all_z_neu") or {}
    sens_tests = sens.get("tests") or []
    sens_sums = {
        direction: sum(row["observed"] for row in sens_tests if row.get("direction") == direction)
        for direction in DIRECTION_IDS
    }

    result: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pre_reg": PRE_REG_PATH,
        "seed": BRIDGE_DIAGNOSTIC_SEED,
        "informativity_gate": str(informativity_gate_path),
        "integrity_gate": str(integrity_gate_path),
        "v3_ergebnis_ref": str(v3_ergebnis_path),
        "skip_ex_post": skip_ex_post,
        "phase1": {
            "ablation": ablation_doc,
            "permutation": permutation_doc,
            "kfold": kfold_doc,
            "fragment_verdict": in_silico_fragment,
            "perm_fragment": perm_fragment,
        },
        "roles": roles,
        "n_unclassified": n_unclassified,
        "registered_prediction": {
            "expected_verdict": "DIAG_SIGNAL_VALID",
            "expected_inert": ["intent_relayers", "stablecoin_mint_burn"],
            "encoding_gate_confirmed_inert": [
                c
                for c in CANDIDATE_IDS
                if gate["candidates"][c]["encoding_status"] == "INERT_ENCODING"
            ],
        },
        "final_verdict": final_verdict,
        "interpretation_notes": {
            "leserhinweise": "docs/BRIDGE_DIAGNOSTIC_LESERHINWEISE.md",
            "diag_signal_valid_caveat": (
                "One permutation test over three perm-testable candidates; "
                "not three independent checks."
            ),
        },
        "v3_reference_read_only": {
            "verdict": v3_body.get("verdict"),
            "sensitivity_observed_sums": sens_sums,
        },
    }

    if output_dir is not None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = {
            "ablation": output_dir / "bridge_diagnostic_ablation.json",
            "permutation": output_dir / "bridge_diagnostic_permutation.json",
            "kfold": output_dir / "bridge_diagnostic_kfold.json",
            "ergebnis": output_dir / "bridge_diagnostic_ergebnis.json",
        }
        paths["ablation"].write_text(json.dumps(ablation_doc, indent=2), encoding="utf-8")
        paths["permutation"].write_text(json.dumps(permutation_doc, indent=2), encoding="utf-8")
        paths["kfold"].write_text(json.dumps(kfold_doc, indent=2), encoding="utf-8")
        result["artifact_paths"] = {k: str(v) for k, v in paths.items()}
        paths["ergebnis"].write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Wrote {paths['ergebnis']}", flush=True)

    return result
