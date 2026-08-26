#!/usr/bin/env python3
"""
Async verification screen — sync vs pipeline throughput (SCREEN only)

Sandbox: prototypes/v2_stateful_graph/

Frage: Kann asynchrone Verifikation (Pipeline-Tiefe D) den Durchsatz erhöhen,
ohne STRUCTURE_RELATIONAL auf dem sparse Ring zu brechen?

Hypothese:
  · sparse Ring bleibt STRUCTURE_RELATIONAL unter sync und async
  · async (D>1) hat höheren accounted tps als sync (D=1)
  · Topologie bleibt Ring (einzig stabile aus topology-Screen)

Freeze:
  |Q|=4 · sparse Ring · Warmup=32 · Measure=80
  Seeds: 20270901–06
  Verify: O(|Q|²×INNER) Mock-Z3/BHO (INNER=64), always-ok für Zustands-Pfad
  Pipeline: sync D=1 vs async D=4 (accounted Parallel-Worker-Makespan)
  Gate: ΔQ≥0.5 ∧ H≥2.0 ∧ Margin>0.1  (≥4/6 → STRUCTURE_RELATIONAL)

Wahrheit vor Optik: tps aus Makespan-Modell über gemessene per-Txn-Kosten
(nicht Thread-Pool); Zustandsreihenfolge = Event-Order in beiden Modi.

Usage:
  python3 prototypes/v2_stateful_graph/async_verify_screen.py
"""
from __future__ import annotations

import heapq
import json
import math
import sys
import time
import zlib
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import stateful_graph_study as sg  # noqa: E402

Q_SIZE = 4
SEEDS = [20270901, 20270902, 20270903, 20270904, 20270905, 20270906]
MODES = ("sync", "async")
ASYNC_DEPTH = 4
INNER = 64
DELTA_Q_FLOOR = 0.5
EPS_H = 2.0
MARGIN_SCREEN = 0.1
PASSES_NEEDED = 4


def _crc_u01(material: str) -> float:
    return (zlib.crc32(material.encode()) & 0xFFFFFFFF) / 0xFFFFFFFF


def _ring(agent_ids: List[str]) -> Dict[str, str]:
    n = len(agent_ids)
    return {agent_ids[i]: agent_ids[(i + 1) % n] for i in range(n)}


def _derange(run_seed: int, agent_ids: List[str]) -> Dict[str, str]:
    order = sorted(agent_ids, key=lambda a: _crc_u01(f"{run_seed}|async_pi|{a}"))
    n = len(order)
    return {order[i]: order[(i + 1) % n] for i in range(n)}


def mock_verify_ms(
    *,
    run_seed: int,
    aid: str,
    k: int,
    q: int,
    sigma: int,
) -> Tuple[bool, float]:
    """Always-ok mock Z3/BHO; returns (ok, wall_ms). CPU work O(|Q|²×INNER)."""
    t0 = time.perf_counter()
    dig = zlib.crc32(
        f"{run_seed}|{aid}|k{k}|q{q}|σ{sigma}|async_v".encode()
    ) & 0xFFFFFFFF
    for i in range(Q_SIZE):
        for j in range(Q_SIZE):
            for inner in range(INNER):
                dig = (
                    zlib.crc32(f"{dig:08x}|{i}|{j}|{inner}".encode())
                    & 0xFFFFFFFF
                )
    ms = (time.perf_counter() - t0) * 1000.0
    return True, ms


def pipeline_makespan_ms(costs_ms: List[float], depth: int) -> float:
    """Accounted parallel workers: D verify slots, jobs in order."""
    if not costs_ms:
        return 0.0
    d = max(1, int(depth))
    free = [0.0] * d
    heapq.heapify(free)
    done = 0.0
    for c in costs_ms:
        t = heapq.heappop(free)
        finish = t + float(c)
        heapq.heappush(free, finish)
        done = max(done, finish)
    return done


def _run_arm(
    *,
    run_seed: int,
    arm: str,
    agent_ids: List[str],
    true_partner: Dict[str, str],
    signal_partner: Optional[Dict[str, str]],
    pipeline_depth: int,
    collect_verify: bool,
) -> Dict[str, Any]:
    n_states = sg.N_STATES
    q = {
        a: int(_crc_u01(f"{run_seed}|{a}|q0") * n_states) % n_states
        for a in agent_ids
    }
    n_ev = {a: 0 for a in agent_ids}
    k_ev = {a: 0 for a in agent_ids}
    series: Dict[str, List[int]] = {a: [] for a in agent_ids}
    edge_pairs: Counter = Counter()
    anti_hits = 0
    anti_tot = 0
    costs: List[float] = []
    n_txn = 0

    heap: List[Tuple[float, int, str]] = []
    seq = 0

    def push(t: float, aid: str) -> None:
        nonlocal seq
        seq += 1
        heapq.heappush(heap, (t, seq, aid))

    for a in agent_ids:
        push(0.01 + _crc_u01(f"{run_seed}|{a}|t0") * 0.2, a)

    while heap and min(n_ev.values()) < sg.TOTAL_EVENTS:
        t, _s, aid = heapq.heappop(heap)
        if n_ev[aid] >= sg.TOTAL_EVENTS:
            continue
        k = k_ev[aid]
        if arm == "A" or signal_partner is None:
            sigma = sg._private_sigma(run_seed, aid, k)
        else:
            sigma = q[signal_partner[aid]]

        if collect_verify:
            _ok, ms = mock_verify_ms(
                run_seed=run_seed, aid=aid, k=k, q=q[aid], sigma=sigma
            )
            costs.append(ms)
        # Transition after verify acknowledgment (order = event order; both modes)
        q[aid] = sg._transition(q[aid], sigma)
        n_txn += 1
        n_ev[aid] += 1
        k_ev[aid] += 1

        if n_ev[aid] > sg.WARMUP_EVENTS:
            series[aid].append(q[aid])
            true_id = true_partner[aid]
            edge_pairs[(q[aid], q[true_id])] += 1
            anti_tot += 1
            if q[aid] == (q[true_id] + 1) % n_states or q[aid] == (
                q[true_id] + 2
            ) % n_states:
                anti_hits += 1

        if n_ev[aid] < sg.TOTAL_EVENTS:
            push(t + sg._base_gap(run_seed, aid, k_ev[aid]), aid)

    L = min((len(series[a]) for a in agent_ids), default=0)
    if L < 2:
        delta_q = 0.0
    else:
        dists = []
        for i, a in enumerate(agent_ids):
            for b in agent_ids[i + 1 :]:
                d = sum(
                    abs(series[a][tt] - series[b][tt]) for tt in range(L)
                ) / float(L)
                dists.append(d)
        delta_q = sum(dists) / len(dists) if dists else 0.0

    makespan = pipeline_makespan_ms(costs, pipeline_depth) if costs else 0.0
    tps = (1000.0 * n_txn / makespan) if makespan > 0 else float("inf")

    return {
        "arm": arm,
        "delta_q": round(delta_q, 6),
        "h_edge": round(sg._shannon_bits(edge_pairs), 6),
        "anti_frac_vs_true": round(
            anti_hits / anti_tot if anti_tot else 0.0, 6
        ),
        "n_txn": n_txn,
        "verify_sum_ms": round(sum(costs), 3) if costs else 0.0,
        "makespan_ms": round(makespan, 3),
        "tps": round(tps, 3),
        "pipeline_depth": pipeline_depth,
        "mean_verify_ms": round(sum(costs) / len(costs), 6) if costs else 0.0,
    }


def run_cell(*, run_seed: int, mode: str) -> Dict[str, Any]:
    if run_seed <= 20270199:
        return {"run_seed": run_seed, "contamination": True, "pass": False}

    depth = 1 if mode == "sync" else ASYNC_DEPTH
    agent_ids = [f"G{i:02d}" for i in range(1, sg.N_AGENTS + 1)]
    true_p = _ring(agent_ids)
    pi_p = _derange(run_seed, agent_ids)

    # Arm A: structure only, no heavy verify (private σ)
    arm_a = _run_arm(
        run_seed=run_seed,
        arm="A",
        agent_ids=agent_ids,
        true_partner=true_p,
        signal_partner=None,
        pipeline_depth=depth,
        collect_verify=False,
    )
    # Arm B: verify + throughput
    arm_b = _run_arm(
        run_seed=run_seed,
        arm="B",
        agent_ids=agent_ids,
        true_partner=true_p,
        signal_partner=true_p,
        pipeline_depth=depth,
        collect_verify=True,
    )
    # Arm C: verify for fair cost, structure margin
    arm_c = _run_arm(
        run_seed=run_seed,
        arm="C",
        agent_ids=agent_ids,
        true_partner=true_p,
        signal_partner=pi_p,
        pipeline_depth=depth,
        collect_verify=True,
    )
    margin = arm_b["anti_frac_vs_true"] - arm_c["anti_frac_vs_true"]
    triad = bool(
        arm_b["delta_q"] >= DELTA_Q_FLOOR
        and arm_b["h_edge"] >= EPS_H
        and margin > MARGIN_SCREEN
    )
    return {
        "run_seed": run_seed,
        "mode": mode,
        "pipeline_depth": depth,
        "contamination": False,
        "topology": "sparse_ring",
        "delta_q": arm_b["delta_q"],
        "h_edge": arm_b["h_edge"],
        "anti_b": arm_b["anti_frac_vs_true"],
        "anti_c": arm_c["anti_frac_vs_true"],
        "anti_margin": round(margin, 6),
        "tps": arm_b["tps"],
        "makespan_ms": arm_b["makespan_ms"],
        "mean_verify_ms": arm_b["mean_verify_ms"],
        "n_txn": arm_b["n_txn"],
        "pass": triad,
        "arm_a_delta_q": arm_a["delta_q"],
    }


def run_async_verify_screen() -> Dict[str, Any]:
    t0 = time.perf_counter()
    sg.N_STATES = Q_SIZE
    sg.H_MAX = math.log2(float(Q_SIZE * Q_SIZE))
    sg.DELTA_Q_FLOOR = DELTA_Q_FLOOR
    sg.EPS_H = EPS_H

    print("Async verification screen (sparse Ring · sync D=1 vs async D=4)")
    print("=" * 96)
    print(
        f"Gate: ΔQ≥{DELTA_Q_FLOOR} ∧ H≥{EPS_H} ∧ Margin>{MARGIN_SCREEN}  "
        f"Seeds={SEEDS}  INNER={INNER}"
    )
    print("-" * 96)

    by_mode: Dict[str, List[Dict[str, Any]]] = {m: [] for m in MODES}

    for mode in MODES:
        depth = 1 if mode == "sync" else ASYNC_DEPTH
        print(f"\n### mode={mode}  pipeline_depth={depth}")
        print(
            f"{'Seed':<12} {'ΔQ':<8} {'Margin':<8} {'tps':<12} "
            f"{'ms/txn':<10} {'PASS':<6}"
        )
        for seed in SEEDS:
            cell = run_cell(run_seed=seed, mode=mode)
            by_mode[mode].append(cell)
            print(
                f"{seed:<12} {cell['delta_q']:<8.3f} "
                f"{cell['anti_margin']:<8.3f} {cell['tps']:<12.1f} "
                f"{cell['mean_verify_ms']:<10.3f} "
                f"{'PASS' if cell['pass'] else 'FAIL':<6}"
            )

    print("\n" + "=" * 96)
    print(
        f"{'Mode':<10} {'D':<4} {'Passes':<10} {'Avg Margin':<12} "
        f"{'Avg tps':<12} {'Verdict'}"
    )
    print("-" * 96)

    summary: Dict[str, Any] = {}
    for mode in MODES:
        rows = by_mode[mode]
        n_pass = sum(1 for c in rows if c["pass"])
        avg_m = sum(c["anti_margin"] for c in rows) / len(rows)
        avg_tps = sum(c["tps"] for c in rows) / len(rows)
        depth = 1 if mode == "sync" else ASYNC_DEPTH
        verdict = (
            "STRUCTURE_RELATIONAL"
            if n_pass >= PASSES_NEEDED
            else "STRUCTURE_BREAKS"
        )
        summary[mode] = {
            "pipeline_depth": depth,
            "n_pass": n_pass,
            "n": len(rows),
            "avg_margin": round(avg_m, 6),
            "avg_tps": round(avg_tps, 3),
            "verdict": verdict,
        }
        print(
            f"{mode:<10} {depth:<4} {n_pass}/6{'':<6} {avg_m:<12.3f} "
            f"{avg_tps:<12.1f} {verdict}"
        )

    structure_ok = all(
        summary[m]["verdict"] == "STRUCTURE_RELATIONAL" for m in MODES
    )
    tps_gain = summary["async"]["avg_tps"] > summary["sync"]["avg_tps"]
    speedup = (
        summary["async"]["avg_tps"] / summary["sync"]["avg_tps"]
        if summary["sync"]["avg_tps"] > 0
        else float("inf")
    )
    # Margins should stay close (same event order / always-ok)
    margin_delta = abs(
        summary["async"]["avg_margin"] - summary["sync"]["avg_margin"]
    )
    hyp_ok = structure_ok and tps_gain
    hyp = "HYPOTHESIS_CONFIRMED" if hyp_ok else "HYPOTHESIS_FALSIFIED"

    elapsed = time.perf_counter() - t0
    payload = {
        "screen": "async_verify_v0",
        "hypothesis": (
            "sparse-ring STRUCTURE_RELATIONAL under sync and async; "
            f"async D={ASYNC_DEPTH} tps > sync D=1"
        ),
        "hypothesis_result": hyp,
        "hypothesis_parts": {
            "structure_both_modes": structure_ok,
            "async_tps_gt_sync": tps_gain,
            "tps_speedup": round(speedup, 4),
            "avg_margin_abs_delta": round(margin_delta, 6),
        },
        "freeze": {
            "Q_size": Q_SIZE,
            "topology": "sparse_ring",
            "INNER": INNER,
            "async_depth": ASYNC_DEPTH,
            "seeds": SEEDS,
            "tps_model": (
                "accounted pipeline makespan over measured per-txn verify ms"
            ),
        },
        "gate": {
            "delta_q": DELTA_Q_FLOOR,
            "h_edge": EPS_H,
            "margin": MARGIN_SCREEN,
        },
        "summary": summary,
        "elapsed_s": round(elapsed, 3),
        "results": {
            m: [
                {
                    "seed": c["run_seed"],
                    "pass": c["pass"],
                    "delta_q": c["delta_q"],
                    "h_edge": c["h_edge"],
                    "anti_margin": c["anti_margin"],
                    "tps": c["tps"],
                    "makespan_ms": c["makespan_ms"],
                    "mean_verify_ms": c["mean_verify_ms"],
                }
                for c in by_mode[m]
            ]
            for m in MODES
        },
    }

    out = _HERE / "async_verify_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print("-" * 96)
    print(f"Hypothesis: {hyp}")
    print(
        f"  structure={structure_ok}  tps_gain={tps_gain}  "
        f"speedup={speedup:.2f}×  margin_Δ={margin_delta:.4f}"
    )
    print(f"elapsed={elapsed:.3f}s → {out}")
    return payload


if __name__ == "__main__":
    run_async_verify_screen()
