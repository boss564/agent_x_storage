"""Stufe-A lock tests: frozen pre-reg constants, nulls, BH-FDR, verdict."""
from __future__ import annotations

import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bridge_stufe_a_config import (
    EVENT_TOKENS_BRIDGED,
    EVENT_TOKENS_BRIDGING_INITIATED,
    N_TESTS,
    OMNIBRIDGE_ETH,
    OMNIBRIDGE_GNOSIS,
    TOPIC_TOKENS_BRIDGED,
    TOPIC_TOKENS_BRIDGING_INITIATED,
    UNISWAP_UR_ARBITRUM,
    UNISWAP_UR_ETH,
    XDAI_BRIDGE_ETH,
    XDAI_BRIDGE_GNOSIS,
    assert_frozen_addresses,
    calendar_days_inclusive,
)
from bridge_stufe_a_stats import (
    benjamini_hochberg,
    hawkes_gamma_histogram,
    jitter_timestamps,
    plus_one_p,
    transfer_entropy_binary,
    verdict,
)


def test_n_tests_is_248():
    assert N_TESTS == 2 * 31 * 2 * 2 == 248


def test_window_is_90_calendar_days():
    assert calendar_days_inclusive() == 90


def test_xdai_bridge_excluded():
    locked = {OMNIBRIDGE_ETH.lower(), OMNIBRIDGE_GNOSIS.lower()}
    locked |= {a.lower() for a in UNISWAP_UR_ETH}
    locked |= {a.lower() for a in UNISWAP_UR_ARBITRUM}
    assert XDAI_BRIDGE_ETH.lower() not in locked
    assert XDAI_BRIDGE_GNOSIS.lower() not in locked


def test_topic0_matches_keccak():
    from eth_hash.auto import keccak

    def topic(sig: str) -> str:
        return "0x" + keccak(sig.encode()).hex()

    assert topic(EVENT_TOKENS_BRIDGING_INITIATED) == TOPIC_TOKENS_BRIDGING_INITIATED
    assert topic(EVENT_TOKENS_BRIDGED) == TOPIC_TOKENS_BRIDGED


def test_assert_frozen_addresses_accepts_lock():
    assert_frozen_addresses(
        {
            "omnibridge_eth": OMNIBRIDGE_ETH,
            "omnibridge_gnosis": OMNIBRIDGE_GNOSIS.lower(),
            "uniswap_ur_eth": list(UNISWAP_UR_ETH),
            "uniswap_ur_arbitrum": list(UNISWAP_UR_ARBITRUM),
            "topic0": [TOPIC_TOKENS_BRIDGING_INITIATED, TOPIC_TOKENS_BRIDGED],
        }
    )


def test_assert_frozen_addresses_rejects_drift():
    try:
        assert_frozen_addresses(
            {
                "omnibridge_eth": XDAI_BRIDGE_ETH,
                "omnibridge_gnosis": OMNIBRIDGE_GNOSIS,
                "uniswap_ur_eth": list(UNISWAP_UR_ETH),
                "uniswap_ur_arbitrum": list(UNISWAP_UR_ARBITRUM),
                "topic0": [TOPIC_TOKENS_BRIDGING_INITIATED, TOPIC_TOKENS_BRIDGED],
            }
        )
    except AssertionError:
        return
    raise AssertionError("drift should have been rejected")


def test_jitter_preserves_n_and_window():
    rng = random.Random(20260817)
    window_start, window_end = 1_000.0, 10_000.0
    times = [2000.0, 3500.0, 8000.0, 9990.0]
    out = jitter_timestamps(
        times, rng, window_start=window_start, window_end=window_end, jitter=300.0
    )
    assert len(out) == len(times)
    assert all(window_start <= t <= window_end for t in out)
    assert out == sorted(out)


def test_hawkes_kernel_peaks_at_injected_lag():
    window_start, window_end = 0.0, 20_000.0
    src = [float(i * 300) for i in range(1, 40)]
    lag_sec = 180.0  # 3 minutes
    tgt = [s + lag_sec for s in src if s + lag_sec <= window_end]
    gammas = hawkes_gamma_histogram(
        src,
        tgt,
        lags_min=range(0, 11),
        window_start=window_start,
        window_end=window_end,
    )
    peak = max(range(len(gammas)), key=lambda i: gammas[i])
    assert peak == 3, f"peak lag={peak} gammas={gammas}"
    assert gammas[3] > 0


def test_hawkes_one_pass_matches_per_lag_bisect():
    from bisect import bisect_left
    from bridge_stufe_a_config import DELTA_TAU_SEC

    rng = random.Random(20260817)
    window_start, window_end = 0.0, 50_000.0
    src = sorted(rng.uniform(window_start, window_end - 120.0) for _ in range(80))
    tgt = sorted(rng.uniform(window_start, window_end) for _ in range(90))
    lags = list(range(0, 11))
    fast = hawkes_gamma_histogram(
        src, tgt, lags_min=lags, window_start=window_start, window_end=window_end
    )
    t_len = window_end - window_start
    lam = len(tgt) / t_len
    tgt_sorted = sorted(tgt)
    slow = []
    for lag in lags:
        tau = lag * DELTA_TAU_SEC
        count = n_complete = 0
        for s in src:
            lo = s + tau
            hi = s + tau + DELTA_TAU_SEC
            if hi > window_end:
                continue
            n_complete += 1
            count += bisect_left(tgt_sorted, hi) - bisect_left(tgt_sorted, lo)
        slow.append(0.0 if n_complete == 0 else (count / (n_complete * DELTA_TAU_SEC)) - lam)
    assert all(abs(a - b) < 1e-12 for a, b in zip(fast, slow)), (fast, slow)


def test_plus_one_p_bounds():
    p = plus_one_p(10.0, [0.0] * 1000)
    assert abs(p - 1 / 1001) < 1e-12
    p_hi = plus_one_p(0.0, [1.0] * 1000)
    assert abs(p_hi - 1.0) < 1e-12


def test_benjamini_hochberg_all_small():
    p = [0.01, 0.02, 0.03, 0.04]
    mask = benjamini_hochberg(p, q=0.05)
    assert mask == [True, True, True, True]


def test_benjamini_hochberg_only_smallest():
    p = [0.01, 0.04, 0.03, 0.50]
    mask = benjamini_hochberg(p, q=0.05)
    assert mask[0] is True
    assert mask[3] is False


def test_te_identical_series_positive_at_lag0():
    x = [0, 1, 0, 1, 1, 0, 1, 0, 0, 1, 1, 0] * 8
    te = transfer_entropy_binary(x, x, drivers=None, tau=0)
    assert te > 0


def test_interpolate_short_gaps_fills_at_most_5():
    from bridge_stufe_a_stats import interpolate_short_gaps

    series = [1.0, None, None, 4.0, None, None, None, None, None, None, 11.0]
    out = interpolate_short_gaps(series, max_gap=5)
    assert out[1] is not None and out[2] is not None
    assert out[4] is None  # run of 6


def test_n_minute_bins_90_days():
    from bridge_stufe_a_config import n_minute_bins

    assert n_minute_bins() == 90 * 24 * 60


def test_parse_omnibridge_log_topics():
    from bridge_stufe_a_capture import parse_omnibridge_log
    from bridge_stufe_a_config import OMNIBRIDGE_ETH, TOPIC_TOKENS_BRIDGING_INITIATED

    token = "0x" + "11" * 20
    sender = "0x" + "22" * 20
    log = {
        "transactionHash": "0xabc",
        "logIndex": "0x1",
        "blockNumber": "0x10",
        "topics": [
            TOPIC_TOKENS_BRIDGING_INITIATED,
            "0x" + "00" * 12 + token[2:],
            "0x" + "00" * 12 + sender[2:],
            "0x" + "33" * 32,
        ],
        "data": "0x",
    }
    ev = parse_omnibridge_log("ethereum", OMNIBRIDGE_ETH, log, 1_700_000_000)
    assert ev["event_type"] == "TokensBridgingInitiated"
    assert ev["token"] == token
    assert ev["counterparty"] == sender
    assert ev["logIndex"] == 1


def test_eth_rpc_candidates_include_fallbacks():
    from bridge_stufe_a_capture import pick_rpc

    urls = pick_rpc("ethereum", None)
    assert len(urls) >= 2


def test_gnosis_rpc_prefers_public_over_alchemy():
    from bridge_stufe_a_capture import pick_rpc

    urls = pick_rpc("gnosis", None)
    assert urls[0].startswith("https://rpc.gnosischain.com")
    assert "alchemy.com" not in urls[0]


def test_ethereum_requires_source():
    from bridge_stufe_a_capture import resolve_stream

    try:
        resolve_stream("ethereum", None, None)
    except SystemExit:
        return
    raise AssertionError("ethereum without source must exit")


def test_resolve_stream_aliases():
    from bridge_stufe_a_capture import resolve_stream

    assert resolve_stream("gnosis", None, None) == "treat_gnosis"
    assert resolve_stream("arbitrum", None, None) == "ctrl_arbitrum"
    assert resolve_stream("ethereum", "uniswap", None) == "ctrl_eth"
    assert resolve_stream(None, None, "treat_eth") == "treat_eth"


def test_no_uniswap_v2_swap_topic_in_capture():
    import inspect
    import bridge_stufe_a_capture as cap

    src = inspect.getsource(cap)
    assert "d78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822" not in src


def test_pipeline_inconclusive_on_sparse_files(tmp_path=None):
    import tempfile
    from bridge_stufe_a_config import WINDOW_START_UTC
    from bridge_stufe_a_pipeline import run_pipeline

    start = int(WINDOW_START_UTC.timestamp())
    d = tempfile.mkdtemp()

    def write_events(name, n):
        path = os.path.join(d, name)
        with open(path, "w", encoding="utf-8") as fh:
            for i in range(n):
                fh.write(json.dumps({"blockTime": start + 120 + i * 10, "txHash": f"0x{i}"}) + "\n")
        return path

    def write_drivers(name):
        path = os.path.join(d, name)
        with open(path, "w", encoding="utf-8") as fh:
            for i in range(10):
                fh.write(
                    json.dumps(
                        {
                            "timestamp": start + i * 60,
                            "gas_price_gwei": 1.0,
                            "btc_price_usd": 100.0,
                            "cex_volume_usd": 1.0,
                        }
                    )
                    + "\n"
                )
        return path

    result = run_pipeline(
        bridge_eth=write_events("be.jsonl", 10),
        bridge_gnosis=write_events("bg.jsonl", 10),
        uniswap_eth=write_events("ue.jsonl", 10),
        uniswap_arb=write_events("ua.jsonl", 10),
        drivers_path=write_drivers("drv.jsonl"),
        n_surrogates=2,
        allow_smoke=True,
    )
    assert result["n_tests"] == 248
    assert result["verdict"] == "INCONCLUSIVE"
    assert len(result["tests"]) == 248


def test_verdict_inconclusive_on_small_n():
    label = verdict(
        n_events={"treat_eth": 10, "treat_gnosis": 200, "ctrl_eth": 200, "ctrl_arbitrum": 200},
        driver_coverage=0.99,
        n_sig_hawkes_treat=5,
        n_sig_cte_treat=5,
        n_sig_hawkes_ctrl=0,
        n_sig_cte_ctrl=0,
    )
    assert label == "INCONCLUSIVE"


def test_verdict_positiv_negativ_dissoziiert_unspezifisch():
    n = {"treat_eth": 200, "treat_gnosis": 200, "ctrl_eth": 200, "ctrl_arbitrum": 200}
    assert (
        verdict(
            n_events=n,
            driver_coverage=0.9,
            n_sig_hawkes_treat=3,
            n_sig_cte_treat=2,
            n_sig_hawkes_ctrl=0,
            n_sig_cte_ctrl=0,
        )
        == "POSITIVBEFUND"
    )
    assert (
        verdict(
            n_events=n,
            driver_coverage=0.9,
            n_sig_hawkes_treat=0,
            n_sig_cte_treat=0,
            n_sig_hawkes_ctrl=0,
            n_sig_cte_ctrl=0,
        )
        == "NEGATIVBEFUND"
    )
    assert (
        verdict(
            n_events=n,
            driver_coverage=0.9,
            n_sig_hawkes_treat=4,
            n_sig_cte_treat=0,
            n_sig_hawkes_ctrl=0,
            n_sig_cte_ctrl=0,
        )
        == "DISSOZIIERT"
    )
    assert (
        verdict(
            n_events=n,
            driver_coverage=0.9,
            n_sig_hawkes_treat=4,
            n_sig_cte_treat=2,
            n_sig_hawkes_ctrl=1,
            n_sig_cte_ctrl=0,
        )
        == "UNSPEZIFISCH"
    )


def test_correspondence_note_is_descriptive_not_abort():
    from check_bridge_stufe_a_capture import correspondence_note

    typical = correspondence_note(3167, 3100, "ETH Initiated ↔ Gnosis Bridged")
    assert "3167 ≈ 3100" in typical
    assert "order-of-magnitude mismatch" not in typical
    wild = correspondence_note(3167, 10, "ETH Initiated ↔ Gnosis Bridged")
    assert "[order-of-magnitude mismatch]" in wild
    empty = correspondence_note(3167, 0, "ETH Initiated ↔ Gnosis Bridged")
    assert "one side empty" in empty


def test_window_from_manifest_notes_gnosis_edge_shortfall():
    from check_bridge_stufe_a_capture import GNOSIS_BLOCK_S, window_from_manifest

    notes = window_from_manifest(
        "treat_gnosis",
        {"from_block": 46262707, "to_block": 47775608},
        GNOSIS_BLOCK_S,
    )
    assert len(notes) == 1
    assert "≈ 87.56d" in notes[0] or "87.5" in notes[0]
    assert "short by" in notes[0]
    assert "do not retune window" in notes[0]


def test_txlist_does_not_stop_on_short_page():
    """Regression: Etherscan pages of 1_000 used to abort the 90d walk."""
    src = open("scripts/bridge_stufe_a_capture.py", encoding="utf-8").read()
    assert "if len(result) < 10_000:" not in src
    assert "nxt = last_bn + 1" in src


def test_type_cross_resolves_total_n_delta():
    from check_bridge_stufe_a_capture import type_cross_notes

    eth = [{"event_type": "TokensBridgingInitiated"}] * 3167
    eth += [{"event_type": "TokensBridged"}] * 3030
    gno = [{"event_type": "TokensBridged"}] * 3167
    gno += [{"event_type": "TokensBridgingInitiated"}] * 3091
    notes = type_cross_notes(eth, gno)
    assert any("ETH Initiated ↔ Gnosis Bridged: 3167 ≈ 3167" in n for n in notes)
    assert any("Gnosis Initiated ↔ ETH Bridged: 3091 ≈ 3030" in n for n in notes)
    assert any("total Δ=61 equals the Initiated/Bridged remainder 61" in n for n in notes)
    assert not any("order-of-magnitude mismatch" in n for n in notes)


def test_timestamp_coverage_uses_event_times_not_block_range():
    from check_bridge_stufe_a_capture import START, timestamp_coverage_notes

    def rows(t0: int, t1: int) -> list[dict]:
        return [{"blockTime": t0}, {"blockTime": t1}]

    end = START + 90 * 86400 - 1
    notes = timestamp_coverage_notes(
        {
            "treat_eth": rows(START, end),
            "treat_gnosis": rows(START + 3600, end),
            "ctrl_eth": rows(START, end - 7200),
            "ctrl_arbitrum": rows(START, end),
        }
    )
    joined = "\n".join(notes)
    assert "common timestamp intersection" in joined
    assert "timestamp coverage" in joined
    assert "block-range" not in joined


def main() -> int:
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except Exception as exc:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {exc}")
    print(f"RESULT {len(tests) - failed}/{len(tests)}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
