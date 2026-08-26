#!/usr/bin/env python3
"""
Agent-scale screen — N ∈ {9,18,27,36} on sparse ring (SCREEN only)

Sandbox: prototypes/v2_stateful_graph/

Frage: Bleibt STRUCTURE_RELATIONAL bei mehr Agenten? Wie skalieren
Makespan (Verifikationszeit) und tps unter async D=4?

Hypothese:
  · Margin>0.1 / STRUCTURE_RELATIONAL für alle N
  · Makespan (accounted async) skaliert ≈ linear mit N
  · tps: erwarteter Drop — unter Pipeline D=4 ggf. flach (separat berichtet)

Freeze:
  |Q|=4 · sparse Ring · Warmup=32 · Measure=80 · async D=4
  Seeds: 20271001–06
  Verify: O(|Q|²×INNER) auf Arm B (INNER=64); Arm C ohne Heavy (always-ok Pfad identisch)
  Gate: ΔQ≥0.5 ∧ H≥2.0 ∧ Margin>0.1  (≥4/6 → STRUCTURE_RELATIONAL)

Usage:
  python3 prototypes/v2_stateful_graph/agent_scale_screen.py
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
N_SIZES = [9, 18, 27, 36]
SEEDS = [20271001, 20271002, 20271003, 20271004, 20271005, 20271006]
ASYNC_DEPTH = 4
INNER = 64
DELTA_Q_FLOOR = 0.5
EPS_H = 2.0
MARGIN_SCREEN = 0.1
PASSES_NEEDED = 4
# Linear: makespan(N)/makespan(9) ≈ N/9 within ±30%
LINEAR_TOL = 0.30


def _crc_u01(material: str) -> float:
    return (zlib.crc32(material.encode()) & 0xFFFFFFFF) / 0xFFFFFFFF


def _ring(agent_ids: List[str]) -> Dict[str, str]:
    n = len(agent_ids)
    return {agent_ids[i]: agent_ids[(i + 1) % n] for i in range(n)}


def _derange(run_seed: int, agent_ids: List[str]) -> Dict[str, str]:
    order = sorted(
        agent_ids, key=lambda a: _crc_u01(f"{run_seed}|scale_pi|{a}")
    )
    n = len(order)
    return {order[i]: order[(i + 1) % n] for i in range(n)}


def mock_verify_ms(
    *,
    run_seed: int,
    aid: str,
    k: int,
    q: int,
    sigma: int,
) -> float:
    t0 = time.perf_counter()
    dig = zlib.crc32(
        f"{run_seed}|{aid}|k{k}|q{q}|σ{sigma}|scale_v".encode()
    ) & 0xFFFFFFFF
    for i in range(Q_SIZE):
        for j in range(Q_SIZE):
            for inner in range(INNER):
                dig = (
                    zlib.crc32(f"{dig:08x}|{i}|{j}|{inner}".encode())
                    & 0xFFFFFFFF
                )
    return (time.perf_counter() - t0) * 1000.0


def pipeline_makespan_ms(costs_ms: List[float], depth: int) -> float:
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
    n_agents: int,
    agent_ids: List[str],
    true_partner: Dict[str, str],
    signal_partner: Optional[Dict[str, str]],
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
            costs.append(
                mock_verify_ms(
                    run_seed=run_seed, aid=aid, k=k, q=q[aid], sigma=sigma
                )
            )
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

    makespan = pipeline_makespan_ms(costs, ASYNC_DEPTH) if costs else 0.0
    tps = (1000.0 * n_txn / makespan) if makespan > 0 else float("inf")
    return {
        "arm": arm,
        "n_agents": n_agents,
        "delta_q": round(delta_q, 6),
        "h_edge": round(sg._shannon_bits(edge_pairs), 6),
        "anti_frac_vs_true": round(
            anti_hits / anti_tot if anti_tot else 0.0, 6
        ),
        "n_txn": n_txn,
        "verify_sum_ms": round(sum(costs), 3) if costs else 0.0,
        "makespan_ms": round(makespan, 3),
        "tps": round(tps, 3),
        "mean_verify_ms": round(sum(costs) / len(costs), 6) if costs else 0.0,
    }


def run_cell(*, run_seed: int, n_agents: int) -> Dict[str, Any]:
    if run_seed <= 20270199:
        return {"run_seed": run_seed, "contamination": True, "pass": False}

    agent_ids = [f"G{i:02d}" for i in range(1, n_agents + 1)]
    true_p = _ring(agent_ids)
    pi_p = _derange(run_seed, agent_ids)

    arm_b = _run_arm(
        run_seed=run_seed,
        arm="B",
        n_agents=n_agents,
        agent_ids=agent_ids,
        true_partner=true_p,
        signal_partner=true_p,
        collect_verify=True,
    )
    arm_c = _run_arm(
        run_seed=run_seed,
        arm="C",
        n_agents=n_agents,
        agent_ids=agent_ids,
        true_partner=true_p,
        signal_partner=pi_p,
        collect_verify=False,
    )
    margin = arm_b["anti_frac_vs_true"] - arm_c["anti_frac_vs_true"]
    triad = bool(
        arm_b["delta_q"] >= DELTA_Q_FLOOR
        and arm_b["h_edge"] >= EPS_H
        and margin > MARGIN_SCREEN
    )
    return {
        "run_seed": run_seed,
        "n_agents": n_agents,
        "topology": "sparse_ring",
        "pipeline_depth": ASYNC_DEPTH,
        "contamination": False,
        "delta_q": arm_b["delta_q"],
        "h_edge": arm_b["h_edge"],
        "anti_b": arm_b["anti_frac_vs_true"],
        "anti_c": arm_c["anti_frac_vs_true"],
        "anti_margin": round(margin, 6),
        "tps": arm_b["tps"],
        "makespan_ms": arm_b["makespan_ms"],
        "verify_sum_ms": arm_b["verify_sum_ms"],
        "mean_verify_ms": arm_b["mean_verify_ms"],
        "n_txn": arm_b["n_txn"],
        "pass": triad,
    }


def run_agent_scale_screen() -> Dict[str, Any]:
    t0 = time.perf_counter()
    sg.N_STATES = Q_SIZE
    sg.H_MAX = math.log2(float(Q_SIZE * Q_SIZE))
    # N_AGENTS in study module unused when we pass explicit ids; keep transition % N_STATES
    sg.DELTA_Q_FLOOR = DELTA_Q_FLOOR
    sg.EPS_H = EPS_H

    print(
        "Agent-scale screen (|Q|=4 · sparse Ring · async D=4 · "
        f"N∈{N_SIZES})"
    )
    print("=" * 100)
    print(
        f"Gate: ΔQ≥{DELTA_Q_FLOOR} ∧ H≥{EPS_H} ∧ Margin>{MARGIN_SCREEN}  "
        f"Seeds={SEEDS}"
    )
    print("-" * 100)

    results: List[Dict[str, Any]] = []
    for n_agents in N_SIZES:
        print(f"\n### N={n_agents}")
        print(
            f"{'Seed':<12} {'ΔQ':<8} {'Margin':<8} {'makespan':<12} "
            f"{'tps':<10} {'PASS':<6}"
        )
        for seed in SEEDS:
            cell = run_cell(run_seed=seed, n_agents=n_agents)
            results.append(cell)
            print(
                f"{seed:<12} {cell['delta_q']:<8.3f} "
                f"{cell['anti_margin']:<8.3f} "
                f"{cell['makespan_ms']:<12.1f} "
                f"{cell['tps']:<10.1f} "
                f"{'PASS' if cell['pass'] else 'FAIL':<6}"
            )

    print("\n" + "=" * 100)
    print(
        f"{'N':<6} {'Passes':<10} {'Avg Margin':<12} {'makespan':<12} "
        f"{'tps':<12} {'ms/txn':<10} {'Verdict'}"
    )
    print("-" * 100)

    summary: List[Dict[str, Any]] = []
    by_n: Dict[int, float] = {}
    tps_by_n: Dict[int, float] = {}
    for n_agents in N_SIZES:
        rows = [r for r in results if r["n_agents"] == n_agents]
        n_pass = sum(1 for r in rows if r["pass"])
        avg_m = sum(r["anti_margin"] for r in rows) / len(rows)
        avg_ms = sum(r["makespan_ms"] for r in rows) / len(rows)
        avg_tps = sum(r["tps"] for r in rows) / len(rows)
        avg_v = sum(r["mean_verify_ms"] for r in rows) / len(rows)
        by_n[n_agents] = avg_ms
        tps_by_n[n_agents] = avg_tps
        verdict = (
            "STRUCTURE_RELATIONAL"
            if n_pass >= PASSES_NEEDED
            else "STRUCTURE_BREAKS"
        )
        summary.append(
            {
                "n_agents": n_agents,
                "n_pass": n_pass,
                "n": len(rows),
                "avg_margin": round(avg_m, 6),
                "avg_makespan_ms": round(avg_ms, 3),
                "avg_tps": round(avg_tps, 3),
                "avg_mean_verify_ms": round(avg_v, 6),
                "verdict": verdict,
            }
        )
        print(
            f"{n_agents:<6} {n_pass}/6{'':<6} {avg_m:<12.3f} "
            f"{avg_ms:<12.1f} {avg_tps:<12.1f} {avg_v:<10.3f} {verdict}"
        )

    structure_ok = all(
        s["verdict"] == "STRUCTURE_RELATIONAL" for s in summary
    )
    base = by_n[9]
    linear_ok = True
    linear_ratios: Dict[str, float] = {}
    for n in N_SIZES:
        expected = n / 9.0
        actual = by_n[n] / base if base > 0 else float("nan")
        linear_ratios[str(n)] = round(actual, 4)
        if abs(actual - expected) > LINEAR_TOL * expected:
            linear_ok = False
    tps_drops = tps_by_n[36] < 0.9 * tps_by_n[9]
    tps_flat = abs(tps_by_n[36] - tps_by_n[9]) / max(tps_by_n[9], 1e-9) < 0.15

    # Primary: structure + linear makespan. tps-drop is secondary under async.
    hyp_ok = structure_ok and linear_ok
    hyp = "HYPOTHESIS_CONFIRMED" if hyp_ok else "HYPOTHESIS_FALSIFIED"

    elapsed = time.perf_counter() - t0
    payload = {
        "screen": "agent_scale_v0",
        "hypothesis": (
            "STRUCTURE_RELATIONAL for N∈{9,18,27,36} on sparse ring; "
            "async makespan ≈ linear in N; tps-drop secondary (may stay flat at D=4)"
        ),
        "hypothesis_result": hyp,
        "hypothesis_parts": {
            "structure_all_N": structure_ok,
            "makespan_scales_linear": linear_ok,
            "makespan_ratio_vs_N9": linear_ratios,
            "tps_drops_N36_vs_N9": tps_drops,
            "tps_flat_under_async": tps_flat,
            "note": (
                "Primary gate = structure ∧ linear makespan. "
                "Txn-tps often ≈ flat under fixed async depth."
            ),
        },
        "freeze": {
            "Q_size": Q_SIZE,
            "topology": "sparse_ring",
            "async_depth": ASYNC_DEPTH,
            "INNER": INNER,
            "N_sizes": N_SIZES,
            "seeds": SEEDS,
            "linear_tol": LINEAR_TOL,
        },
        "gate": {
            "delta_q": DELTA_Q_FLOOR,
            "h_edge": EPS_H,
            "margin": MARGIN_SCREEN,
        },
        "summary": summary,
        "elapsed_s": round(elapsed, 3),
        "results": [
            {
                "seed": r["run_seed"],
                "n_agents": r["n_agents"],
                "pass": r["pass"],
                "delta_q": r["delta_q"],
                "h_edge": r["h_edge"],
                "anti_margin": r["anti_margin"],
                "makespan_ms": r["makespan_ms"],
                "tps": r["tps"],
                "mean_verify_ms": r["mean_verify_ms"],
            }
            for r in results
        ],
    }

    out = _HERE / "agent_scale_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print("-" * 100)
    print(f"Hypothesis: {hyp}")
    print(
        f"  structure={structure_ok}  linear_makespan={linear_ok}  "
        f"tps_drops={tps_drops}  tps_flat={tps_flat}"
    )
    print(f"  ratios vs N=9: {linear_ratios}")
    print(f"elapsed={elapsed:.3f}s → {out}")
    return payload


if __name__ == "__main__":
    run_agent_scale_screen()
