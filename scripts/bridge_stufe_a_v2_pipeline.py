"""Stufe A v2 confirmatory pipeline: matched-N thinning + signed Hawkes hits.

Reuses Stufe-A loaders, Hawkes jitter, CTE shuffle, and BH. Does not retune
Stufe A. Treatment surrogates run once; control is thinned per draw.

Usage:
  python3 scripts/bridge_stufe_a_v2_pipeline.py \\
    --bridge-eth bridge_eth.jsonl --bridge-gnosis bridge_gnosis.jsonl \\
    --uniswap-eth uniswap_eth.jsonl --uniswap-arb uniswap_arb.jsonl \\
    --drivers drivers_90d.jsonl --output bridge_stufe_a_v2_ergebnis.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bridge_stufe_a_config import (
    DIRECTION_IDS,
    DRIVER_COVERAGE_MIN,
    FDR_Q,
    LAGS_MIN,
    METRIC_IDS,
    N_MIN_EVENTS,
    N_SURROGATES,
    N_TESTS,
    PAIR_IDS,
    WINDOW_END_UTC,
    WINDOW_START_UTC,
)
from bridge_stufe_a_pipeline import (
    cte_direction,
    hawkes_direction,
    load_driver_series,
    load_event_times,
    occupancy,
    refuse_smoke_manifest,
)
from bridge_stufe_a_stats import (
    benjamini_hochberg,
    driver_coverage,
    encode_drivers_tertiles,
)
from bridge_stufe_a_v2_config import BRIDGE_STUFE_A_V2_SEED, N_DRAWS
from bridge_stufe_a_v2_stats import (
    aggregate_draw_labels,
    control_surrogate_rng,
    count_cte_hits,
    count_hawkes_hits,
    exact_n_subset,
    thinning_rng,
    treatment_rng,
    v2_verdict,
)


def _pair_tests(pair: str, metric: str, direction: str, observed: list[float], pvals: list[float]) -> list[dict]:
    rows: list[dict] = []
    for lag, val, p in zip(LAGS_MIN, observed, pvals):
        rows.append(
            {
                "pair": pair,
                "metric": metric,
                "direction": direction,
                "lag_min": lag,
                "observed": val,
                "p": p,
            }
        )
    return rows


def _run_pair_metrics(src_t, tgt_t, src_o, tgt_o, drivers, rng, n_surrogates, pair: str) -> tuple[list[dict], list[dict], dict, dict]:
    hawkes_obs: dict[str, list[float]] = {}
    hawkes_rows: list[dict] = []
    for direction, (src, tgt) in (("ab", (src_t, tgt_t)), ("ba", (tgt_t, src_t))):
        print(f"  Hawkes {pair} {direction}", flush=True)
        obs, pvals = hawkes_direction(src, tgt, rng, n_surrogates)
        hawkes_obs[direction] = obs
        hawkes_rows.extend(_pair_tests(pair, "hawkes", direction, obs, pvals))
    cte_obs: dict[str, list[float]] = {}
    ute_obs: dict[str, list[float]] = {}
    cte_rows: list[dict] = []
    for direction, (src, tgt) in (("ab", (src_o, tgt_o)), ("ba", (tgt_o, src_o))):
        print(f"  CTE {pair} {direction}", flush=True)
        obs, pvals, ute = cte_direction(src, tgt, drivers, rng, n_surrogates)
        cte_obs[direction] = obs
        ute_obs[direction] = ute
        cte_rows.extend(_pair_tests(pair, "cte", direction, obs, pvals))
    return hawkes_rows, cte_rows, hawkes_obs, ute_obs


def _assemble_and_label(
    treat_h: list[dict],
    treat_c: list[dict],
    ctrl_h: list[dict],
    ctrl_c: list[dict],
    n_events: dict[str, int],
    coverage: float,
) -> tuple[list[dict], dict, str]:
    tests = [dict(t) for t in treat_h + ctrl_h + treat_c + ctrl_c]
    if len(tests) != N_TESTS:
        raise RuntimeError(f"expected {N_TESTS} tests, got {len(tests)}")
    reject = benjamini_hochberg([t["p"] for t in tests], q=FDR_Q)
    for t, sig in zip(tests, reject):
        t["bh_reject"] = bool(sig)
    n_sig = {
        "hawkes_treat": count_hawkes_hits(tests, "treatment"),
        "cte_treat": count_cte_hits(tests, "treatment"),
        "hawkes_ctrl": count_hawkes_hits(tests, "control"),
        "cte_ctrl": count_cte_hits(tests, "control"),
    }
    label = v2_verdict(
        n_events=n_events,
        driver_coverage=coverage,
        n_sig_hawkes_treat=n_sig["hawkes_treat"],
        n_sig_cte_treat=n_sig["cte_treat"],
        n_sig_hawkes_ctrl=n_sig["hawkes_ctrl"],
        n_sig_cte_ctrl=n_sig["cte_ctrl"],
    )
    return tests, n_sig, label


def _dump_draw(row: dict, dump_dir: str | None) -> None:
    """Per-draw JSON so a late PermissionError cannot drop the 248-vectors again."""
    if not dump_dir:
        return
    os.makedirs(dump_dir, exist_ok=True)
    path = os.path.join(dump_dir, f"bridge_stufe_a_v2_draw_{row['draw']:02d}.json")
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(row, fh)
            fh.write("\n")
        print(f"  dumped {path}", flush=True)
    except PermissionError:
        print(f"  dump failed {path}", flush=True)


def run_pipeline(
    *,
    bridge_eth: str,
    bridge_gnosis: str,
    uniswap_eth: str,
    uniswap_arb: str,
    drivers_path: str,
    n_surrogates: int,
    n_draws: int,
    allow_smoke: bool,
    dump_dir: str | None = ".",
) -> dict:
    for path in (bridge_eth, bridge_gnosis, uniswap_eth, uniswap_arb):
        refuse_smoke_manifest(path, allow_smoke)

    treat_a = load_event_times(bridge_eth)
    treat_b = load_event_times(bridge_gnosis)
    ctrl_a = load_event_times(uniswap_eth)
    ctrl_b = load_event_times(uniswap_arb)
    gas, btc, cex = load_driver_series(drivers_path)
    coverage = driver_coverage(gas, btc, cex)
    g_ter, b_ter, c_ter, edges = encode_drivers_tertiles(gas, btc, cex)
    drivers = [g_ter, b_ter, c_ter]

    n_star = {"ctrl_eth": len(treat_a), "ctrl_arbitrum": len(treat_b)}
    n_events_full = {
        "treat_eth": len(treat_a),
        "treat_gnosis": len(treat_b),
        "ctrl_eth": len(ctrl_a),
        "ctrl_arbitrum": len(ctrl_b),
    }
    confirmatory_run = n_draws == N_DRAWS and n_surrogates == N_SURROGATES

    def _inconclusive_payload(reason: str) -> dict:
        labels = ["V2_INCONCLUSIVE"] * n_draws
        agg = aggregate_draw_labels(labels, n_draws=n_draws)
        return {
            "pre_reg": "docs/BRIDGE_STUFE_A_V2_PREREG.md",
            "window_start": WINDOW_START_UTC.isoformat(),
            "window_end": WINDOW_END_UTC.isoformat(),
            "n_tests": N_TESTS,
            "n_surrogates": n_surrogates,
            "n_draws": n_draws,
            "seed": BRIDGE_STUFE_A_V2_SEED,
            "fdr_q": FDR_Q,
            "n_events_full": n_events_full,
            "n_star": n_star,
            "driver_coverage": coverage,
            "skipped_compute": True,
            "skip_reason": reason,
            "confirmatory_run": confirmatory_run,
            "draws": [{"draw": d, "label": "V2_INCONCLUSIVE"} for d in range(n_draws)],
            "aggregation": agg,
            "majority_label": agg["majority_label"],
            "confirmatory_verdict": agg["confirmatory_verdict"],
            "borderline": agg["borderline"],
            "definitive": agg["definitive"],
            "utc_evaluated_at": datetime.now(timezone.utc).isoformat(),
            "pair_order": list(PAIR_IDS),
            "metric_order": list(METRIC_IDS),
            "direction_order": list(DIRECTION_IDS),
        }

    if coverage < DRIVER_COVERAGE_MIN:
        return _inconclusive_payload("driver_coverage")
    if any(n_events_full[k] < N_MIN_EVENTS for k in ("treat_eth", "treat_gnosis")):
        return _inconclusive_payload("treatment_n_min")
    if len(ctrl_a) < n_star["ctrl_eth"] or len(ctrl_b) < n_star["ctrl_arbitrum"]:
        return _inconclusive_payload("control_shorter_than_n_star")

    treat_occ_a = occupancy(treat_a)
    treat_occ_b = occupancy(treat_b)
    print("Treatment metrics (once)", flush=True)
    treat_h, treat_c, treat_hawkes_obs, treat_ute = _run_pair_metrics(
        treat_a,
        treat_b,
        treat_occ_a,
        treat_occ_b,
        drivers,
        treatment_rng(),
        n_surrogates,
        "treatment",
    )

    draws: list[dict] = []
    for d in range(n_draws):
        print(f"Draw {d + 1}/{n_draws} thinning", flush=True)
        thinned_a = exact_n_subset(ctrl_a, n_star["ctrl_eth"], thinning_rng(d))
        thinned_b = exact_n_subset(ctrl_b, n_star["ctrl_arbitrum"], thinning_rng(d))
        n_events = {
            "treat_eth": len(treat_a),
            "treat_gnosis": len(treat_b),
            "ctrl_eth": len(thinned_a),
            "ctrl_arbitrum": len(thinned_b),
        }
        ctrl_h, ctrl_c, ctrl_hawkes_obs, ctrl_ute = _run_pair_metrics(
            thinned_a,
            thinned_b,
            occupancy(thinned_a),
            occupancy(thinned_b),
            drivers,
            control_surrogate_rng(d),
            n_surrogates,
            "control",
        )
        tests, n_sig, label = _assemble_and_label(treat_h, treat_c, ctrl_h, ctrl_c, n_events, coverage)
        draws.append(
            {
                "draw": d,
                "n_events": n_events,
                "n_sig": n_sig,
                "label": label,
                "effect_present": label == "V2_POSITIVBEFUND",
                "alpha_descriptive": {
                    "treatment_ab": float(sum(treat_hawkes_obs["ab"])),
                    "treatment_ba": float(sum(treat_hawkes_obs["ba"])),
                    "control_ab": float(sum(ctrl_hawkes_obs["ab"])),
                    "control_ba": float(sum(ctrl_hawkes_obs["ba"])),
                },
                "ute_descriptive": {"treatment": treat_ute, "control": ctrl_ute},
                "tests": tests,
            }
        )
        _dump_draw(draws[-1], dump_dir)
        print(f"Draw {d + 1}/{n_draws} {label} n_sig={n_sig}", flush=True)

    labels = [row["label"] for row in draws]
    agg = aggregate_draw_labels(labels, n_draws=n_draws)
    return {
        "pre_reg": "docs/BRIDGE_STUFE_A_V2_PREREG.md",
        "window_start": WINDOW_START_UTC.isoformat(),
        "window_end": WINDOW_END_UTC.isoformat(),
        "n_tests": N_TESTS,
        "n_surrogates": n_surrogates,
        "n_draws": n_draws,
        "seed": BRIDGE_STUFE_A_V2_SEED,
        "fdr_q": FDR_Q,
        "n_events_full": n_events_full,
        "n_star": n_star,
        "driver_coverage": coverage,
        "tertile_edges": {k: list(v) for k, v in edges.items()},
        "skipped_compute": False,
        "confirmatory_run": confirmatory_run,
        "draws": draws,
        "aggregation": agg,
        "majority_label": agg["majority_label"],
        "confirmatory_verdict": agg["confirmatory_verdict"],
        "borderline": agg["borderline"],
        "definitive": agg["definitive"],
        "utc_evaluated_at": datetime.now(timezone.utc).isoformat(),
        "pair_order": list(PAIR_IDS),
        "metric_order": list(METRIC_IDS),
        "direction_order": list(DIRECTION_IDS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stufe A v2 matched-N Hawkes + CTE pipeline")
    parser.add_argument("--bridge-eth", required=True)
    parser.add_argument("--bridge-gnosis", required=True)
    parser.add_argument("--uniswap-eth", required=True)
    parser.add_argument("--uniswap-arb", required=True)
    parser.add_argument("--drivers", required=True)
    parser.add_argument("--output", default="bridge_stufe_a_v2_ergebnis.json")
    parser.add_argument("--n-surrogates", type=int, default=N_SURROGATES)
    parser.add_argument("--n-draws", type=int, default=N_DRAWS)
    parser.add_argument("--allow-smoke", action="store_true")
    parser.add_argument("--dump-dir", default=".")
    args = parser.parse_args()
    result = run_pipeline(
        bridge_eth=args.bridge_eth,
        bridge_gnosis=args.bridge_gnosis,
        uniswap_eth=args.uniswap_eth,
        uniswap_arb=args.uniswap_arb,
        drivers_path=args.drivers,
        n_surrogates=args.n_surrogates,
        n_draws=args.n_draws,
        allow_smoke=args.allow_smoke,
        dump_dir=args.dump_dir,
    )
    print(f"n_events_full={result['n_events_full']}")
    print(f"coverage={result['driver_coverage']:.3f}")
    print(f"majority_label={result['majority_label']}")
    print(f"confirmatory_verdict={result['confirmatory_verdict']}")
    print(f"borderline={result['borderline']} definitive={result['definitive']}")
    print(f"aggregation={json.dumps(result['aggregation'], sort_keys=True)}")
    try:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
            fh.write("\n")
        print(f"Wrote {args.output}")
    except PermissionError:
        compact = {k: v for k, v in result.items() if k != "draws"}
        compact["draws"] = [
            {kk: vv for kk, vv in row.items() if kk not in {"tests", "ute_descriptive"}}
            for row in result.get("draws", [])
        ]
        compact["write_error"] = "PermissionError on full JSON; compact draw summaries only"
        fallback = args.output + ".compact.json"
        with open(fallback, "w", encoding="utf-8") as fh:
            json.dump(compact, fh, indent=2)
            fh.write("\n")
        print(f"Wrote compact fallback {fallback}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
