"""Capture-layer consistency checks for Stufe A (does not change the pre-reg).

Hard FAIL: N<100, missing topic, (txHash, logIndex) dupes, joint driver coverage < 80%.
Descriptive NOTES (no abort): type-cross correspondence, timestamp-edge shortfall.
Also prints per-driver coverage (gas/btc/cex); frozen gate remains the joint AND.

Usage:
  python3 scripts/check_bridge_stufe_a_capture.py \\
    --bridge-eth bridge_eth.jsonl --bridge-gnosis bridge_gnosis.jsonl \\
    --uniswap-eth uniswap_eth.jsonl --uniswap-arb uniswap_arb.jsonl \\
    --drivers drivers_90d.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bridge_stufe_a_config import (
    DRIVER_COVERAGE_MIN,
    N_MIN_EVENTS,
    TOPIC_TOKENS_BRIDGED,
    TOPIC_TOKENS_BRIDGING_INITIATED,
    WINDOW_END_UTC,
    WINDOW_START_UTC,
    calendar_days_inclusive,
    n_minute_bins,
)
from bridge_stufe_a_stats import driver_coverage, interpolate_short_gaps

START = int(WINDOW_START_UTC.timestamp())
END = int(WINDOW_END_UTC.timestamp())
WINDOW_SEC = END - START + 1
EDGE_SLACK_S = 24 * 3600
GNOSIS_BLOCK_S = 5.0
ETH_BLOCK_S = 12.0
# Correspondence: hang/fail/window-edge diffs expected. Only note if ratio is wild.
CORR_NOTE_RATIO = 5.0


def load_events(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_manifest(jsonl_path: str) -> dict | None:
    man = jsonl_path + ".manifest.json"
    if not os.path.isfile(man):
        return None
    with open(man, encoding="utf-8") as fh:
        return json.load(fh)


def load_drivers(path: str) -> tuple[list, list, list]:
    n = n_minute_bins()
    gas: list = [None] * n
    btc: list = [None] * n
    cex: list = [None] * n
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            idx = int((int(rec["timestamp"]) - START) // 60)
            if 0 <= idx < n:
                gas[idx] = rec.get("gas_price_gwei")
                btc[idx] = rec.get("btc_price_usd")
                cex[idx] = rec.get("cex_volume_usd")
    return (
        interpolate_short_gaps(gas, max_gap=5),
        interpolate_short_gaps(btc, max_gap=5),
        interpolate_short_gaps(cex, max_gap=5),
    )


def type_counts(rows: list[dict]) -> Counter:
    c: Counter = Counter()
    for r in rows:
        key = r.get("event_type") or r.get("topic0") or "?"
        c[key] += 1
    return c


def iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def check_stream(name: str, rows: list[dict], *, expect_both_topics: bool) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    notes: list[str] = []
    if len(rows) < N_MIN_EVENTS:
        problems.append(f"{name}: N={len(rows)} < {N_MIN_EVENTS}")
    keys = [(r.get("txHash"), r.get("logIndex")) for r in rows]
    if len(keys) != len(set(keys)):
        problems.append(f"{name}: duplicate (txHash, logIndex) — chunk overlap")
    ts = [int(r["blockTime"]) for r in rows if r.get("blockTime") is not None]
    if not ts:
        problems.append(f"{name}: no timestamps")
        return problems, notes
    lead = min(ts) - START
    tail = END - max(ts)
    if lead > EDGE_SLACK_S:
        notes.append(
            f"{name}: first event {iso(min(ts))} is {lead / 86400:.2f}d after window start"
        )
    if tail > EDGE_SLACK_S:
        notes.append(
            f"{name}: last event {iso(max(ts))} is {tail / 86400:.2f}d before window end"
        )
    span_d = (max(ts) - min(ts)) / 86400
    span_frac = (max(ts) - min(ts)) / WINDOW_SEC
    notes.append(
        f"{name}: event span {span_d:.2f}d "
        f"({iso(min(ts))} → {iso(max(ts))}); pre-reg window {calendar_days_inclusive()}d"
    )
    if span_frac < 0.80:
        problems.append(
            f"{name}: timestamp span {span_d:.2f}d is {span_frac:.0%} of the "
            f"{calendar_days_inclusive()}d window — incomplete capture"
        )
    if expect_both_topics:
        types = type_counts(rows)
        n_init = types.get("TokensBridgingInitiated", 0)
        n_bridged = types.get("TokensBridged", 0)
        if n_init == 0 or n_bridged == 0:
            problems.append(f"{name}: missing topic (Initiated={n_init} Bridged={n_bridged})")
    return problems, notes


def series_coverage(xs: list) -> float:
    if not xs:
        return 0.0
    return sum(v is not None for v in xs) / len(xs)


def correspondence_note(a: int, b: int, label: str) -> str:
    lo, hi = (a, b) if a <= b else (b, a)
    if lo == 0 and hi == 0:
        return f"{label}: both 0"
    if lo == 0:
        return f"{label}: {a} vs {b} — one side empty (capture gap?)"
    ratio = hi / lo
    delta = hi - lo
    rel = delta / max(hi, 1)
    flag = "  [order-of-magnitude mismatch]" if ratio >= CORR_NOTE_RATIO else ""
    return f"{label}: {a} ≈ {b}  Δ={delta}  rel={rel:.1%}  ratio={ratio:.2f}{flag}"


def type_cross_notes(eth: list[dict], gno: list[dict]) -> list[str]:
    eth_types = type_counts(eth)
    gno_types = type_counts(gno)
    eth_init = eth_types.get("TokensBridgingInitiated", 0)
    eth_bridged = eth_types.get("TokensBridged", 0)
    gno_init = gno_types.get("TokensBridgingInitiated", 0)
    gno_bridged = gno_types.get("TokensBridged", 0)
    notes = [
        correspondence_note(eth_init, gno_bridged, "ETH Initiated ↔ Gnosis Bridged"),
        correspondence_note(gno_init, eth_bridged, "Gnosis Initiated ↔ ETH Bridged"),
    ]
    total_delta = abs(len(eth) - len(gno))
    remainder = abs(gno_init - eth_bridged)
    notes.append(
        f"treatment N ETH={len(eth)} ({eth_init} Initiated + {eth_bridged} Bridged) "
        f"vs Gnosis={len(gno)} ({gno_init} Initiated + {gno_bridged} Bridged); "
        f"total Δ={total_delta} equals the Initiated/Bridged remainder {remainder}"
    )
    return notes


def timestamp_coverage_notes(named: dict[str, list[dict]]) -> list[str]:
    """Primary window check: event timestamps, not implied block-range × slot time."""
    notes: list[str] = []
    spans: dict[str, tuple[int, int]] = {}
    for name, rows in named.items():
        ts = [int(r["blockTime"]) for r in rows if r.get("blockTime") is not None]
        if not ts:
            notes.append(f"{name}: no timestamps")
            continue
        spans[name] = (min(ts), max(ts))
        notes.append(
            f"{name}: timestamp coverage {iso(min(ts))} → {iso(max(ts))} "
            f"({(max(ts) - min(ts)) / 86400:.2f}d); "
            f"lead={(min(ts) - START) / 86400:.2f}d tail={(END - max(ts)) / 86400:.2f}d"
        )
    if len(spans) < 2:
        return notes
    lo = max(a for a, _ in spans.values())
    hi = min(b for _, b in spans.values())
    common_d = (hi - lo) / 86400 if hi > lo else 0.0
    target = calendar_days_inclusive()
    line = (
        f"common timestamp intersection {iso(lo)} → {iso(hi)} "
        f"({common_d:.2f}d) vs pre-reg {target}d"
    )
    short = target - common_d
    if short > 0.5:
        line += f"  — common event basis short by ~{short:.2f}d (document, do not retune window)"
    notes.append(line)
    return notes


def window_from_manifest(name: str, man: dict | None, block_s: float) -> list[str]:
    if not man:
        return [f"{name}: no manifest — cannot check block-range vs 90d"]
    fb, tb = man.get("from_block"), man.get("to_block")
    if fb is None or tb is None:
        return [f"{name}: manifest missing from_block/to_block"]
    n_blocks = int(tb) - int(fb) + 1
    implied_d = n_blocks * block_s / 86400
    target_d = calendar_days_inclusive()
    short = target_d - implied_d
    line = (
        f"{name}: blocks {fb}–{tb} ({n_blocks:,} × {block_s:.0f}s ≈ {implied_d:.2f}d) "
        f"vs pre-reg {target_d}d"
    )
    if short > 0.5:
        line += f"  — short by ~{short:.2f}d at the edges (document, do not retune window)"
    return [line]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--bridge-eth", required=True)
    p.add_argument("--bridge-gnosis", required=True)
    p.add_argument("--uniswap-eth", required=True)
    p.add_argument("--uniswap-arb", required=True)
    p.add_argument("--drivers", required=True)
    args = p.parse_args()

    eth = load_events(args.bridge_eth)
    gno = load_events(args.bridge_gnosis)
    ueth = load_events(args.uniswap_eth)
    uarb = load_events(args.uniswap_arb)
    gas, btc, cex = load_drivers(args.drivers)
    eth_man = load_manifest(args.bridge_eth)
    gno_man = load_manifest(args.bridge_gnosis)

    problems: list[str] = []
    notes: list[str] = []
    p1, n1 = check_stream("treat_eth", eth, expect_both_topics=True)
    p2, n2 = check_stream("treat_gnosis", gno, expect_both_topics=True)
    p3, n3 = check_stream("ctrl_eth", ueth, expect_both_topics=False)
    p4, n4 = check_stream("ctrl_arbitrum", uarb, expect_both_topics=False)
    problems += p1 + p2 + p3 + p4
    notes += n1 + n2 + n3 + n4
    notes += window_from_manifest("treat_eth", eth_man, ETH_BLOCK_S)
    notes += window_from_manifest("treat_gnosis", gno_man, GNOSIS_BLOCK_S)
    notes += timestamp_coverage_notes(
        {
            "treat_eth": eth,
            "treat_gnosis": gno,
            "ctrl_eth": ueth,
            "ctrl_arbitrum": uarb,
        }
    )

    eth_types = type_counts(eth)
    gno_types = type_counts(gno)

    print("event counts")
    print(f"  treat_eth     N={len(eth)} {dict(eth_types)}")
    print(f"  treat_gnosis  N={len(gno)} {dict(gno_types)}")
    print(f"  ctrl_eth      N={len(ueth)}")
    print(f"  ctrl_arbitrum N={len(uarb)}")
    print("treatment type cross (descriptive, not a gate)")
    for line in type_cross_notes(eth, gno):
        print(f"  {line}")
        notes.append(line)

    cov_gas = series_coverage(gas)
    cov_btc = series_coverage(btc)
    cov_cex = series_coverage(cex)
    cov = driver_coverage(gas, btc, cex)
    print("driver coverage")
    print(f"  gas {cov_gas:.3f}  btc {cov_btc:.3f}  cex {cov_cex:.3f}")
    print(f"  joint AND {cov:.3f} (frozen gate min {DRIVER_COVERAGE_MIN})")
    for name, value in (("gas", cov_gas), ("btc", cov_btc), ("cex", cov_cex)):
        if value < DRIVER_COVERAGE_MIN:
            notes.append(
                f"{name} coverage {value:.3f} < {DRIVER_COVERAGE_MIN} "
                "(individual; frozen gate is joint AND)"
            )
    if cov < DRIVER_COVERAGE_MIN:
        problems.append(f"driver coverage {cov:.3f} < {DRIVER_COVERAGE_MIN}")

    print("notes (not abort)")
    for item in notes:
        print(f"  · {item}")

    if problems:
        print("CONSISTENCY FAIL")
        for item in problems:
            print(f"  - {item}")
        return 1
    print("CONSISTENCY PASS")
    print(
        f"topics locked Initiated={TOPIC_TOKENS_BRIDGING_INITIATED[:10]}… "
        f"Bridged={TOPIC_TOKENS_BRIDGED[:10]}…"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
