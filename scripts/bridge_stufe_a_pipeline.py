"""Stufe A confirmatory pipeline: Hawkes γ(τ) + CTE, 248 tests, BH-FDR, frozen verdict.

Does not invent function names from the draft sketch. Uses bridge_stufe_a_stats
exactly as pre-registered: per-lag p-values, source-only jitter, occupancy shuffle,
one BH over 248 tests.

Usage:
  python3 scripts/bridge_stufe_a_pipeline.py \\
    --bridge-eth bridge_eth.jsonl --bridge-gnosis bridge_gnosis.jsonl \\
    --uniswap-eth uniswap_eth.jsonl --uniswap-arb uniswap_arb.jsonl \\
    --drivers drivers_90d.jsonl --output bridge_stufe_a_ergebnis.json
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bridge_stufe_a_config import (
    BRIDGE_STUFE_A_SEED,
    DIRECTION_IDS,
    FDR_Q,
    LAGS_MIN,
    METRIC_IDS,
    N_SURROGATES,
    N_TESTS,
    PAIR_IDS,
    WINDOW_END_UTC,
    WINDOW_START_UTC,
    n_minute_bins,
)
from bridge_stufe_a_stats import (
    WINDOW_END_TS,
    WINDOW_START_TS,
    benjamini_hochberg,
    driver_coverage,
    encode_drivers_tertiles,
    hawkes_gamma_histogram,
    interpolate_short_gaps,
    jitter_timestamps,
    occupancy_1min,
    plus_one_p,
    shuffle_occupancy,
    transfer_entropy_binary,
    verdict,
)

N_BINS = n_minute_bins()


def load_event_times(path: str) -> list[float]:
    times: list[float] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            ts = rec.get("blockTime", rec.get("timestamp"))
            if ts is None:
                continue
            t = float(ts)
            if WINDOW_START_TS <= t <= WINDOW_END_TS:
                times.append(t)
    times.sort()
    return times


def load_driver_series(path: str) -> tuple[list[float | None], list[float | None], list[float | None]]:
    gas: list[float | None] = [None] * N_BINS
    btc: list[float | None] = [None] * N_BINS
    cex: list[float | None] = [None] * N_BINS
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            ts = int(rec["timestamp"])
            idx = int((ts - int(WINDOW_START_TS)) // 60)
            if not 0 <= idx < N_BINS:
                continue
            gas[idx] = rec.get("gas_price_gwei")
            btc[idx] = rec.get("btc_price_usd")
            cex[idx] = rec.get("cex_volume_usd")
    return (
        interpolate_short_gaps(gas, max_gap=5),
        interpolate_short_gaps(btc, max_gap=5),
        interpolate_short_gaps(cex, max_gap=5),
    )


def refuse_smoke_manifest(path: str, allow_smoke: bool) -> None:
    man = path + ".manifest.json"
    if not os.path.exists(man):
        return
    with open(man, encoding="utf-8") as fh:
        body = json.load(fh)
    mode = body.get("window_mode", "")
    if mode.startswith("smoke") and not allow_smoke:
        raise SystemExit(
            f"{man} is a smoke capture (not the frozen 90-day window). "
            "Refusing confirmatory eval. Pass --allow-smoke only for wiring tests."
        )


def hawkes_direction(src: list[float], tgt: list[float], rng: random.Random, n_surr: int) -> tuple[list[float], list[float]]:
    print(f"  hawkes n_src={len(src)} n_tgt={len(tgt)} surrogates={n_surr}", flush=True)
    observed = hawkes_gamma_histogram(src, tgt)
    nulls = [[] for _ in LAGS_MIN]
    for k in range(n_surr):
        src_j = jitter_timestamps(src, rng)
        gamma_j = hawkes_gamma_histogram(src_j, tgt)
        for i, val in enumerate(gamma_j):
            nulls[i].append(val)
        if k == 0 or (k + 1) % 50 == 0:
            print(f"    hawkes surrogate {k + 1}/{n_surr}", flush=True)
    pvals = [plus_one_p(observed[i], nulls[i]) for i in range(len(LAGS_MIN))]
    return observed, pvals


def cte_direction(
    src_occ: list[int],
    tgt_occ: list[int],
    drivers: list[list[int]],
    rng: random.Random,
    n_surr: int,
) -> tuple[list[float], list[float], list[float]]:
    observed = [transfer_entropy_binary(src_occ, tgt_occ, drivers, tau) for tau in LAGS_MIN]
    ute = [transfer_entropy_binary(src_occ, tgt_occ, None, tau) for tau in LAGS_MIN]
    print(f"  cte bins={len(src_occ)} surrogates={n_surr}", flush=True)
    nulls = [[] for _ in LAGS_MIN]
    for k in range(n_surr):
        src_s = shuffle_occupancy(src_occ, rng)
        for i, tau in enumerate(LAGS_MIN):
            nulls[i].append(transfer_entropy_binary(src_s, tgt_occ, drivers, tau))
        if k == 0 or (k + 1) % 50 == 0:
            print(f"    cte surrogate {k + 1}/{n_surr}", flush=True)
    pvals = [plus_one_p(observed[i], nulls[i]) for i in range(len(LAGS_MIN))]
    return observed, pvals, ute


def occupancy(times: list[float]) -> list[int]:
    return occupancy_1min(times, window_start=WINDOW_START_TS, window_end=WINDOW_START_TS + N_BINS * 60)


def run_pipeline(
    *,
    bridge_eth: str,
    bridge_gnosis: str,
    uniswap_eth: str,
    uniswap_arb: str,
    drivers_path: str,
    n_surrogates: int,
    allow_smoke: bool,
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

    n_events = {
        "treat_eth": len(treat_a),
        "treat_gnosis": len(treat_b),
        "ctrl_eth": len(ctrl_a),
        "ctrl_arbitrum": len(ctrl_b),
    }

    rng = random.Random(BRIDGE_STUFE_A_SEED)
    tests: list[dict] = []

    pair_streams = {
        "treatment": (treat_a, treat_b, occupancy(treat_a), occupancy(treat_b)),
        "control": (ctrl_a, ctrl_b, occupancy(ctrl_a), occupancy(ctrl_b)),
    }

    hawkes_obs: dict[str, dict[str, list[float]]] = {}
    for pair in PAIR_IDS:
        src_t, tgt_t, _, _ = pair_streams[pair]
        hawkes_obs[pair] = {}
        for direction, (src, tgt) in (("ab", (src_t, tgt_t)), ("ba", (tgt_t, src_t))):
            print(f"Hawkes {pair} {direction}", flush=True)
            obs, pvals = hawkes_direction(src, tgt, rng, n_surrogates)
            hawkes_obs[pair][direction] = obs
            for lag, gamma, p in zip(LAGS_MIN, obs, pvals):
                tests.append(
                    {
                        "pair": pair,
                        "metric": "hawkes",
                        "direction": direction,
                        "lag_min": lag,
                        "observed": gamma,
                        "p": p,
                    }
                )

    cte_obs: dict[str, dict[str, list[float]]] = {}
    ute_obs: dict[str, dict[str, list[float]]] = {}
    for pair in PAIR_IDS:
        _, _, src_o, tgt_o = pair_streams[pair]
        cte_obs[pair] = {}
        ute_obs[pair] = {}
        for direction, (src, tgt) in (("ab", (src_o, tgt_o)), ("ba", (tgt_o, src_o))):
            print(f"CTE {pair} {direction}", flush=True)
            obs, pvals, ute = cte_direction(src, tgt, drivers, rng, n_surrogates)
            cte_obs[pair][direction] = obs
            ute_obs[pair][direction] = ute
            for lag, val, p in zip(LAGS_MIN, obs, pvals):
                tests.append(
                    {
                        "pair": pair,
                        "metric": "cte",
                        "direction": direction,
                        "lag_min": lag,
                        "observed": val,
                        "p": p,
                    }
                )

    if len(tests) != N_TESTS:
        raise RuntimeError(f"expected {N_TESTS} tests, got {len(tests)}")

    # Frozen order: treatment/control × hawkes/cte × ab/ba × lag — already appended that way
    # except we did all hawkes pairs first then all CTE. Pre-reg: 2 dir × 31 × 2 metrics × 2 pairs.
    # Spec §6: one BH over the 248-vector. Order is documented in `tests`.
    reject = benjamini_hochberg([t["p"] for t in tests], q=FDR_Q)
    for t, sig in zip(tests, reject):
        t["bh_reject"] = bool(sig)

    def n_sig(pair: str, metric: str) -> int:
        return sum(1 for t in tests if t["pair"] == pair and t["metric"] == metric and t["bh_reject"])

    n_h_t = n_sig("treatment", "hawkes")
    n_c_t = n_sig("treatment", "cte")
    n_h_c = n_sig("control", "hawkes")
    n_c_c = n_sig("control", "cte")
    label = verdict(
        n_events=n_events,
        driver_coverage=coverage,
        n_sig_hawkes_treat=n_h_t,
        n_sig_cte_treat=n_c_t,
        n_sig_hawkes_ctrl=n_h_c,
        n_sig_cte_ctrl=n_c_c,
    )

    def alpha(gammas: list[float]) -> float:
        return float(sum(gammas))

    return {
        "pre_reg": "docs/BRIDGE_STUFE_A_PREREG.md",
        "window_start": WINDOW_START_UTC.isoformat(),
        "window_end": WINDOW_END_UTC.isoformat(),
        "n_tests": N_TESTS,
        "n_surrogates": n_surrogates,
        "seed": BRIDGE_STUFE_A_SEED,
        "fdr_q": FDR_Q,
        "n_events": n_events,
        "driver_coverage": coverage,
        "tertile_edges": {k: list(v) for k, v in edges.items()},
        "n_sig": {
            "hawkes_treat": n_h_t,
            "cte_treat": n_c_t,
            "hawkes_ctrl": n_h_c,
            "cte_ctrl": n_c_c,
        },
        "alpha_descriptive": {
            "treatment_ab": alpha(hawkes_obs["treatment"]["ab"]),
            "treatment_ba": alpha(hawkes_obs["treatment"]["ba"]),
            "control_ab": alpha(hawkes_obs["control"]["ab"]),
            "control_ba": alpha(hawkes_obs["control"]["ba"]),
        },
        "ute_descriptive": ute_obs,
        "verdict": label,
        "utc_evaluated_at": datetime.now(timezone.utc).isoformat(),
        "tests": tests,
        "pair_order": list(PAIR_IDS),
        "metric_order": list(METRIC_IDS),
        "direction_order": list(DIRECTION_IDS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stufe A Hawkes + CTE pipeline")
    parser.add_argument("--bridge-eth", required=True)
    parser.add_argument("--bridge-gnosis", required=True)
    parser.add_argument("--uniswap-eth", required=True)
    parser.add_argument("--uniswap-arb", required=True)
    parser.add_argument("--drivers", required=True)
    parser.add_argument("--output", default="bridge_stufe_a_ergebnis.json")
    parser.add_argument("--n-surrogates", type=int, default=N_SURROGATES)
    parser.add_argument("--allow-smoke", action="store_true")
    args = parser.parse_args()
    result = run_pipeline(
        bridge_eth=args.bridge_eth,
        bridge_gnosis=args.bridge_gnosis,
        uniswap_eth=args.uniswap_eth,
        uniswap_arb=args.uniswap_arb,
        drivers_path=args.drivers,
        n_surrogates=args.n_surrogates,
        allow_smoke=args.allow_smoke,
    )
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
        fh.write("\n")
    print(f"n_events={result['n_events']}")
    print(f"coverage={result['driver_coverage']:.3f}")
    print(f"n_sig={result['n_sig']}")
    print(f"Verdict: {result['verdict']}")
    print(f"Wrote {args.output} ({N_TESTS} tests)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
