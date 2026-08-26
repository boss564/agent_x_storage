#!/usr/bin/env python3
"""Stateful Graph Automata — isolated sandbox prototype (Serie v2).

NO imports from agents_b2g/emergence coupling family.
Gate: ΔQ > 0  ∧  H_Kante > ε  ∧  Arm-C-Bruch
Engineering screen only — no Pre-Reg.
"""
from __future__ import annotations

import heapq
import math
import zlib
from collections import Counter
from typing import Any, Dict, List, Sequence, Tuple

N_AGENTS = 9
N_STATES = 4  # Q = {0,1,2,3}
N_EVENTS = 80
EPS_H = 0.15
ARM_C_MARGIN = 0.15
DELTA_Q_MIN = 1e-6


def _crc_u01(material: str) -> float:
    return (zlib.crc32(material.encode()) & 0xFFFFFFFF) / 0xFFFFFFFF


def _shannon(counts: Counter) -> float:
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    h = 0.0
    for c in counts.values():
        if c <= 0:
            continue
        p = c / total
        h -= p * math.log(p + 1e-15, 2)
    return float(h)


def _base_gap(run_seed: int, aid: str, k: int) -> float:
    return 0.4 + 1.6 * _crc_u01(f"{run_seed}|{aid}|gap|{k}")


def _transition(q: int, sigma: int) -> int:
    """Discrete repulsion: next state is niche offset from input symbol."""
    # Input symbol = observed signal-partner state; move to complementary niche.
    return int((sigma + 1 + (q % 2)) % N_STATES)


def _run_arm(
    *,
    run_seed: int,
    arm: str,
    agent_ids: List[str],
    true_partner: Dict[str, str],
    signal_partner: Dict[str, str],
) -> Dict[str, Any]:
    q = {
        a: int(_crc_u01(f"{run_seed}|{a}|q0") * N_STATES) % N_STATES
        for a in agent_ids
    }
    n_ev = {a: 0 for a in agent_ids}
    k_ev = {a: 0 for a in agent_ids}
    series: Dict[str, List[int]] = {a: [] for a in agent_ids}
    edge_pairs: Counter = Counter()  # (q_i, q_true_partner) on sticky M
    anti_hits = 0
    anti_tot = 0

    heap: List[Tuple[float, int, str]] = []
    seq = 0

    def push(t: float, aid: str) -> None:
        nonlocal seq
        seq += 1
        heapq.heappush(heap, (t, seq, aid))

    for a in agent_ids:
        push(0.01 + _crc_u01(f"{run_seed}|{a}|t0") * 0.2, a)

    while heap and min(n_ev.values()) < N_EVENTS:
        t, _s, aid = heapq.heappop(heap)
        if n_ev[aid] >= N_EVENTS:
            continue
        sig_id = signal_partner[aid]
        true_id = true_partner[aid]
        sigma = q[sig_id]
        q[aid] = _transition(q[aid], sigma)
        series[aid].append(q[aid])
        # Metrics always against TRUE sticky edge (relational structure test)
        edge_pairs[(q[aid], q[true_id])] += 1
        anti_tot += 1
        if q[aid] == (q[true_id] + 1) % N_STATES or q[aid] == (
            q[true_id] + 2
        ) % N_STATES:
            anti_hits += 1
        n_ev[aid] += 1
        k_ev[aid] += 1
        if n_ev[aid] < N_EVENTS:
            push(t + _base_gap(run_seed, aid, k_ev[aid]), aid)

    # ΔQ: mean pairwise L1 of aligned trajectories
    L = min(len(series[a]) for a in agent_ids)
    if L < 2:
        delta_q = 0.0
    else:
        dists = []
        for i, a in enumerate(agent_ids):
            for b in agent_ids[i + 1 :]:
                d = sum(
                    abs(series[a][t] - series[b][t]) for t in range(L)
                ) / float(L)
                dists.append(d)
        delta_q = sum(dists) / len(dists) if dists else 0.0

    h_edge = _shannon(edge_pairs)
    anti_frac = anti_hits / anti_tot if anti_tot else 0.0

    return {
        "arm": arm,
        "delta_q": round(delta_q, 6),
        "h_edge": round(h_edge, 6),
        "anti_frac_vs_true": round(anti_frac, 6),
        "n_edge_obs": sum(edge_pairs.values()),
        "series_len": L,
    }


def run_stateful_graph_cell(*, run_seed: int) -> Dict[str, Any]:
    agent_ids = [f"G{i:02d}" for i in range(1, N_AGENTS + 1)]
    # Sticky ring
    true_p = {
        agent_ids[i]: agent_ids[(i + 1) % N_AGENTS] for i in range(N_AGENTS)
    }
    # Deterministic permutation of partners (derangement-ish via offset+2)
    pi_p = {
        agent_ids[i]: agent_ids[(i + 2) % N_AGENTS] for i in range(N_AGENTS)
    }
    # Seed-dependent shuffle of π values to avoid fixed structure bias
    order = sorted(
        agent_ids,
        key=lambda a: _crc_u01(f"{run_seed}|perm|{a}"),
    )
    vals = [true_p[a] for a in order]
    # rotate values
    vals = vals[1:] + vals[:1]
    pi_p = {order[i]: vals[i] for i in range(N_AGENTS)}

    arm_b = _run_arm(
        run_seed=run_seed,
        arm="B",
        agent_ids=agent_ids,
        true_partner=true_p,
        signal_partner=true_p,
    )
    arm_c = _run_arm(
        run_seed=run_seed,
        arm="C",
        agent_ids=agent_ids,
        true_partner=true_p,
        signal_partner=pi_p,
    )

    delta_q_ok = bool(arm_b["delta_q"] > DELTA_Q_MIN)
    h_ok = bool(arm_b["h_edge"] > EPS_H)
    # Arm-C-Bruch: relational anti-alignment vs TRUE partner holds on B, breaks on C
    c_break = bool(
        (arm_b["anti_frac_vs_true"] - arm_c["anti_frac_vs_true"]) >= ARM_C_MARGIN
    )
    passed = bool(delta_q_ok and h_ok and c_break)

    return {
        "run_seed": run_seed,
        "strand": "stateful_graph_v2",
        "n_agents": N_AGENTS,
        "n_states": N_STATES,
        "n_events": N_EVENTS,
        "eps_h": EPS_H,
        "arm_c_margin": ARM_C_MARGIN,
        "delta_q": arm_b["delta_q"],
        "h_edge": arm_b["h_edge"],
        "anti_b": arm_b["anti_frac_vs_true"],
        "anti_c": arm_c["anti_frac_vs_true"],
        "delta_q_pass": delta_q_ok,
        "h_pass": h_ok,
        "arm_c_break": c_break,
        "pass": passed,
        "arm_b": arm_b,
        "arm_c": arm_c,
        "note": "sandbox-only; no coupling-family imports",
    }
