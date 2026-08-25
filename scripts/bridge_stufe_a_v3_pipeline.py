"""Stufe A v3 confirmatory CTE pipeline: Z_neu conditioning, 310 tests, BH-FDR.

Usage:
  python3 scripts/bridge_stufe_a_v3_integrity_gate.py
  python3 scripts/bridge_stufe_a_v3_pipeline.py \\
    --integrity-gate bridge_stufe_a_v3_integrity_gate.json \\
    --output bridge_stufe_a_v3_ergebnis.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bridge_stufe_a_config import FDR_Q, LAGS_MIN, N_SURROGATES
from bridge_stufe_a_pipeline import load_driver_series, refuse_smoke_manifest
from bridge_stufe_a_stats import (
    apply_tertiles,
    benjamini_hochberg,
    encode_drivers_tertiles,
    plus_one_p,
    shuffle_occupancy,
    tertile_edges,
    transfer_entropy_binary,
)
from bridge_stufe_a_v3_config import (
    BRIDGE_STUFE_A_V3_SEED,
    CANDIDATE_IDS,
    DEFAULT_INPUTS,
    DIRECTION_IDS,
    FOLD_DAYS,
    K_FOLDS,
    MINUTES_PER_DAY,
    N_V3_TESTS,
    fold_minute_ranges,
    n_bins,
)
from bridge_stufe_a_v3_load import load_bridge_occupancy, load_candidate_occupancy


def encode_z_neu_tertile(occ: Sequence[int]) -> list[int]:
    """Quantile bins for Z_neu (Pre-Reg §4.3), same {-1,0,1,2} scheme as Z_alt."""
    vals = [float(v) for v in occ]
    edges = tertile_edges(vals)
    return apply_tertiles(vals, edges)


def load_integrity_gate(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"missing integrity gate: {path}")
    body = json.loads(path.read_text(encoding="utf-8"))
    if body.get("status") != "PASS":
        raise SystemExit(f"integrity gate blocked: {body.get('issues')}")
    return body


def slice_occ(occ: Sequence[int], start: int, end: int) -> list[int]:
    return list(occ[start:end])


def slice_drivers(drivers: list[list[int]], start: int, end: int) -> list[list[int]]:
    return [list(d[start:end]) for d in drivers]


def cte_observed_grid(
    src: Sequence[int],
    tgt: Sequence[int],
    drivers: list[list[int]],
) -> dict[str, list[float]]:
    return {
        direction: [
            transfer_entropy_binary(s, t, drivers, tau)
            for tau in LAGS_MIN
        ]
        for direction, (s, t) in (
            ("ab", (src, tgt)),
            ("ba", (tgt, src)),
        )
    }


def cte_direction_slice(
    src: Sequence[int],
    tgt: Sequence[int],
    drivers: list[list[int]],
    rng: random.Random,
    n_surr: int,
) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    """Return (observed_by_dir, pvals_by_dir) without UTE."""
    observed: dict[str, list[float]] = {}
    pvals: dict[str, list[float]] = {}
    for direction, (s, t) in (("ab", (src, tgt)), ("ba", (tgt, src))):
        obs = [transfer_entropy_binary(s, t, drivers, tau) for tau in LAGS_MIN]
        nulls = [[] for _ in LAGS_MIN]
        for _ in range(n_surr):
            src_s = shuffle_occupancy(s, rng)
            for i, tau in enumerate(LAGS_MIN):
                nulls[i].append(transfer_entropy_binary(src_s, t, drivers, tau))
        observed[direction] = obs
        pvals[direction] = [plus_one_p(obs[i], nulls[i]) for i in range(len(LAGS_MIN))]
    return observed, pvals


def mean_delta_cte(
    baseline: dict[str, list[float]],
    conditioned: dict[str, list[float]],
) -> float:
    deltas: list[float] = []
    for direction in DIRECTION_IDS:
        for b, c in zip(baseline[direction], conditioned[direction]):
            deltas.append(b - c)
    return sum(deltas) / len(deltas) if deltas else 0.0


def peak_lag_minutes(
    candidate_occ: Sequence[int],
    treat_eth: Sequence[int],
    treat_gno: Sequence[int],
) -> int:
    """Earliest minute index where candidate and either treatment leg co-occur."""
    for i in range(len(candidate_occ)):
        if candidate_occ[i] and (treat_eth[i] or treat_gno[i]):
            return i
    return len(candidate_occ)


def candidate_collapsed(tests: list[dict], candidate: str) -> bool:
    for t in tests:
        if t["candidate"] == candidate and t.get("bh_reject"):
            return False
    return True


def fold_collapse_count(
    *,
    eth: Sequence[int],
    gno: Sequence[int],
    z_alt: list[list[int]],
    z_cand: list[int],
    rng: random.Random,
    n_surr: int,
) -> bool:
    """Single fold: collapsed if no raw p below FDR threshold heuristic — use no sig at q=0.05 on 62 fold tests."""
    drivers = z_alt + [z_cand]
    _, pvals = cte_direction_slice(eth, gno, drivers, rng, n_surr)
    flat = [p for d in DIRECTION_IDS for p in pvals[d]]
    reject = benjamini_hochberg(flat, q=FDR_Q)
    return not any(reject)


def run_pipeline(
    *,
    input_dir: Path,
    integrity_gate: Path,
    bridge_eth: str,
    bridge_gnosis: str,
    drivers_path: str,
    n_surrogates: int,
    allow_smoke: bool,
) -> dict:
    load_integrity_gate(integrity_gate)
    for p in (bridge_eth, bridge_gnosis, drivers_path):
        refuse_smoke_manifest(str(input_dir / p), allow_smoke)

    eth_occ, _ = load_bridge_occupancy(input_dir / bridge_eth)
    gno_occ, _ = load_bridge_occupancy(input_dir / bridge_gnosis)
    gas, btc, cex = load_driver_series(str(input_dir / drivers_path))
    g_ter, b_ter, c_ter, edges = encode_drivers_tertiles(gas, btc, cex)
    z_alt = [g_ter, b_ter, c_ter]

    z_neu: dict[str, list[int]] = {}
    z_neu_ter: dict[str, list[int]] = {}
    for cid in CANDIDATE_IDS:
        occ, _ = load_candidate_occupancy(cid, input_dir / DEFAULT_INPUTS[cid])
        z_neu[cid] = occ
        z_neu_ter[cid] = encode_z_neu_tertile(occ)

    rng = random.Random(BRIDGE_STUFE_A_V3_SEED)

    # Baseline: Z_alt only (62 tests, separate BH for replication gate).
    print("Baseline CTE (Z_alt only)", flush=True)
    base_obs, base_p = cte_direction_slice(eth_occ, gno_occ, z_alt, rng, n_surrogates)
    base_tests: list[dict] = []
    base_flat: list[float] = []
    for direction in DIRECTION_IDS:
        for lag, val, p in zip(LAGS_MIN, base_obs[direction], base_p[direction]):
            base_tests.append(
                {
                    "scope": "baseline_z_alt",
                    "direction": direction,
                    "lag_min": lag,
                    "observed": val,
                    "p": p,
                }
            )
            base_flat.append(p)
    base_reject = benjamini_hochberg(base_flat, q=FDR_Q)
    for t, sig in zip(base_tests, base_reject):
        t["bh_reject"] = bool(sig)
    n_base_sig = sum(1 for t in base_tests if t["bh_reject"])

    # Primary 310: each candidate separately.
    tests: list[dict] = []
    cond_obs: dict[str, dict[str, list[float]]] = {}
    for cid in CANDIDATE_IDS:
        print(f"CTE candidate {cid}", flush=True)
        drivers = z_alt + [z_neu_ter[cid]]
        obs, pvals = cte_direction_slice(eth_occ, gno_occ, drivers, rng, n_surrogates)
        cond_obs[cid] = obs
        for direction in DIRECTION_IDS:
            for lag, val, p in zip(LAGS_MIN, obs[direction], pvals[direction]):
                tests.append(
                    {
                        "candidate": cid,
                        "direction": direction,
                        "lag_min": lag,
                        "observed": val,
                        "p": p,
                    }
                )

    if len(tests) != N_V3_TESTS:
        raise RuntimeError(f"expected {N_V3_TESTS} tests, got {len(tests)}")

    reject = benjamini_hochberg([t["p"] for t in tests], q=FDR_Q)
    for t, sig in zip(tests, reject):
        t["bh_reject"] = bool(sig)

    collapses = {cid: candidate_collapsed(tests, cid) for cid in CANDIDATE_IDS}
    collapsed_ids = [cid for cid, ok in collapses.items() if ok]

    # ΔCTE descriptive + fold robustness for tie-break.
    candidate_metrics: dict[str, dict] = {}
    fold_ranges = fold_minute_ranges()
    for cid in CANDIDATE_IDS:
        n_fold_collapses = 0
        for start, end in fold_ranges:
            eth_f = slice_occ(eth_occ, start, end)
            gno_f = slice_occ(gno_occ, start, end)
            zf = slice_drivers(z_alt, start, end)
            zc = slice_occ(z_neu_ter[cid], start, end)
            if fold_collapse_count(
                eth=eth_f,
                gno=gno_f,
                z_alt=zf,
                z_cand=zc,
                rng=random.Random(BRIDGE_STUFE_A_V3_SEED + start),
                n_surr=min(200, n_surrogates),
            ):
                n_fold_collapses += 1
        candidate_metrics[cid] = {
            "collapsed_full_window": collapses[cid],
            "mean_delta_cte": round(mean_delta_cte(base_obs, cond_obs[cid]), 8),
            "n_folds_mit_kollaps": n_fold_collapses,
            "peak_lag_minute_index": peak_lag_minutes(z_neu[cid], eth_occ, gno_occ),
        }

    # Sensitivity: all Z_neu together.
    print("Sensitivity CTE (all Z_neu)", flush=True)
    drivers_all = z_alt + [z_neu_ter[c] for c in CANDIDATE_IDS]
    sens_obs, sens_p = cte_direction_slice(eth_occ, gno_occ, drivers_all, rng, n_surrogates)
    sens_tests: list[dict] = []
    sens_flat: list[float] = []
    for direction in DIRECTION_IDS:
        for lag, val, p in zip(LAGS_MIN, sens_obs[direction], sens_p[direction]):
            sens_tests.append({"direction": direction, "lag_min": lag, "observed": val, "p": p})
            sens_flat.append(p)
    sens_reject = benjamini_hochberg(sens_flat, q=FDR_Q)
    for t, sig in zip(sens_tests, sens_reject):
        t["bh_reject"] = bool(sig)
    n_sens_sig = sum(1 for t in sens_tests if t["bh_reject"])
    persistency = n_sens_sig > 0

    # Verdict (Pre-Reg §1.4, §4.1).
    if len(collapsed_ids) >= 2:
        verdict = "V3_MEHRFACH_KOLLAPS"
        ranked = sorted(
            collapsed_ids,
            key=lambda c: (
                -candidate_metrics[c]["mean_delta_cte"],
                -candidate_metrics[c]["n_folds_mit_kollaps"],
                candidate_metrics[c]["peak_lag_minute_index"],
            ),
        )
        winner = ranked[0]
    elif len(collapsed_ids) == 1:
        verdict = "V3_EINZEL_KOLLAPS"
        winner = collapsed_ids[0]
    elif persistency:
        verdict = "V3_PERSISTENZ"
        winner = None
    else:
        verdict = "V3_GEMEINSAM_KOLLAPS"
        winner = None

    return {
        "pre_reg": "docs/BRIDGE_STUFE_A_V3_PREREG.md",
        "integrity_gate": str(integrity_gate),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": BRIDGE_STUFE_A_V3_SEED,
        "fdr_q": FDR_Q,
        "n_surrogates": n_surrogates,
        "n_tests_primary": N_V3_TESTS,
        "baseline": {
            "n_bh_significant": n_base_sig,
            "tests": base_tests,
            "observed": base_obs,
        },
        "primary_tests": tests,
        "n_bh_significant_primary": sum(1 for t in tests if t["bh_reject"]),
        "collapses": collapses,
        "candidate_metrics": candidate_metrics,
        "sensitivity_all_z_neu": {
            "n_bh_significant": n_sens_sig,
            "persistency": persistency,
            "tests": sens_tests,
            "observed": sens_obs,
        },
        "tertile_edges": {
            "z_alt": {k: list(v) for k, v in edges.items()},
        },
        "verdict": verdict,
        "winner_candidate": winner,
        "interpretation_notes": {
            "mev_density_caveat": (
                "High MEV occupancy (~57%) may induce partial collapse via correlation "
                "with other drivers; not part of collapse decision logic."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stufe A V3 CTE pipeline")
    parser.add_argument("--input-dir", default=".")
    parser.add_argument(
        "--integrity-gate",
        default="bridge_stufe_a_v3_integrity_gate.json",
    )
    parser.add_argument("--bridge-eth", default=DEFAULT_INPUTS["bridge_eth"])
    parser.add_argument("--bridge-gnosis", default=DEFAULT_INPUTS["bridge_gnosis"])
    parser.add_argument("--drivers", default=DEFAULT_INPUTS["drivers"])
    parser.add_argument("--output", default="bridge_stufe_a_v3_ergebnis.json")
    parser.add_argument("--n-surrogates", type=int, default=N_SURROGATES)
    parser.add_argument("--allow-smoke", action="store_true")
    args = parser.parse_args()

    root = Path(args.input_dir)
    result = run_pipeline(
        input_dir=root,
        integrity_gate=root / args.integrity_gate,
        bridge_eth=args.bridge_eth,
        bridge_gnosis=args.bridge_gnosis,
        drivers_path=args.drivers,
        n_surrogates=args.n_surrogates,
        allow_smoke=args.allow_smoke,
    )
    out = Path(args.output)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"baseline_bh_sig={result['baseline']['n_bh_significant']}")
    print(f"primary_bh_sig={result['n_bh_significant_primary']}")
    print(f"collapses={result['collapses']}")
    print(f"Verdict: {result['verdict']} winner={result['winner_candidate']}")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
