#!/usr/bin/env python3
"""Stateful Graph v0 — BINDEND capture (sandbox only).

NO imports from agents_b2g/emergence coupling family.
Freeze F0–F10 · Pre-Reg docs/STATEFUL_GRAPH_v0_PREREG.md
"""
from __future__ import annotations

import heapq
import math
import zlib
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

N_AGENTS = 9
N_STATES = 4
WARMUP_EVENTS = 32
MEASURE_EVENTS = 80
TOTAL_EVENTS = WARMUP_EVENTS + MEASURE_EVENTS
EPS_H = 2.0
DELTA_Q_FLOOR = 0.5
ARM_C_MARGIN = 0.15
H_MAX = math.log2(float(N_STATES * N_STATES))  # 4.0


def _crc_u01(material: str) -> float:
    return (zlib.crc32(material.encode()) & 0xFFFFFFFF) / 0xFFFFFFFF


def _shannon_bits(counts: Counter) -> float:
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
    return int((sigma + 1 + (q % 2)) % N_STATES)


def _private_sigma(run_seed: int, aid: str, k: int) -> int:
    """F10: Arm-A σ is an independent crc draw — never σ = q_i."""
    return int(_crc_u01(f"{run_seed}|{aid}|sigma|{k}") * N_STATES) % N_STATES


def _run_arm(
    *,
    run_seed: int,
    arm: str,
    agent_ids: List[str],
    true_partner: Dict[str, str],
    signal_partner: Optional[Dict[str, str]],
) -> Dict[str, Any]:
    q = {
        a: int(_crc_u01(f"{run_seed}|{a}|q0") * N_STATES) % N_STATES
        for a in agent_ids
    }
    n_ev = {a: 0 for a in agent_ids}
    k_ev = {a: 0 for a in agent_ids}
    series: Dict[str, List[int]] = {a: [] for a in agent_ids}
    edge_pairs: Counter = Counter()
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

    while heap and min(n_ev.values()) < TOTAL_EVENTS:
        t, _s, aid = heapq.heappop(heap)
        if n_ev[aid] >= TOTAL_EVENTS:
            continue
        k = k_ev[aid]
        if arm == "A" or signal_partner is None:
            sigma = _private_sigma(run_seed, aid, k)
        else:
            sigma = q[signal_partner[aid]]
        q[aid] = _transition(q[aid], sigma)
        n_ev[aid] += 1
        k_ev[aid] += 1

        # Metrics only in measure window (after warmup)
        if n_ev[aid] > WARMUP_EVENTS:
            series[aid].append(q[aid])
            true_id = true_partner[aid]
            edge_pairs[(q[aid], q[true_id])] += 1
            anti_tot += 1
            if q[aid] == (q[true_id] + 1) % N_STATES or q[aid] == (
                q[true_id] + 2
            ) % N_STATES:
                anti_hits += 1

        if n_ev[aid] < TOTAL_EVENTS:
            push(t + _base_gap(run_seed, aid, k_ev[aid]), aid)

    L = min((len(series[a]) for a in agent_ids), default=0)
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

    return {
        "arm": arm,
        "delta_q": round(delta_q, 6),
        "h_edge": round(_shannon_bits(edge_pairs), 6),
        "anti_frac_vs_true": round(
            anti_hits / anti_tot if anti_tot else 0.0, 6
        ),
        "n_edge_obs": sum(edge_pairs.values()),
        "series_len": L,
        "warmup": WARMUP_EVENTS,
        "measure": MEASURE_EVENTS,
    }


def _build_partners(
    run_seed: int, agent_ids: List[str]
) -> Tuple[Dict[str, str], Dict[str, str]]:
    true_p = {
        agent_ids[i]: agent_ids[(i + 1) % N_AGENTS] for i in range(N_AGENTS)
    }
    order = sorted(
        agent_ids, key=lambda a: _crc_u01(f"{run_seed}|perm|{a}")
    )
    vals = [true_p[a] for a in order]
    vals = vals[1:] + vals[:1]
    pi_p = {order[i]: vals[i] for i in range(N_AGENTS)}
    return true_p, pi_p


def run_stateful_graph_study_cell(*, run_seed: int) -> Dict[str, Any]:
    if run_seed <= 20270199:
        return {
            "run_seed": run_seed,
            "pass": False,
            "contamination": True,
            "verdict": "CONTAMINATION",
            "error": "seed ≤ 20270199 locked (proto / HARKing)",
        }

    agent_ids = [f"G{i:02d}" for i in range(1, N_AGENTS + 1)]
    true_p, pi_p = _build_partners(run_seed, agent_ids)

    arm_a = _run_arm(
        run_seed=run_seed,
        arm="A",
        agent_ids=agent_ids,
        true_partner=true_p,
        signal_partner=None,
    )
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

    delta_q_ok = bool(arm_b["delta_q"] >= DELTA_Q_FLOOR)
    h_ok = bool(arm_b["h_edge"] >= EPS_H)
    c_break = bool(
        (arm_b["anti_frac_vs_true"] - arm_c["anti_frac_vs_true"])
        >= ARM_C_MARGIN
    )
    triad = bool(delta_q_ok and h_ok and c_break)

    arm_a_delta_ok = bool(arm_a["delta_q"] >= DELTA_Q_FLOOR)
    arm_a_h_ok = bool(arm_a["h_edge"] >= EPS_H)
    arm_a_sanity = bool(arm_a_delta_ok and arm_a_h_ok)

    return {
        "run_seed": run_seed,
        "strand": "stateful_graph_v0",
        "contamination": False,
        "n_agents": N_AGENTS,
        "n_states": N_STATES,
        "h_max": H_MAX,
        "warmup": WARMUP_EVENTS,
        "measure": MEASURE_EVENTS,
        "delta_q_floor": DELTA_Q_FLOOR,
        "eps_h": EPS_H,
        "arm_c_margin": ARM_C_MARGIN,
        "delta_q": arm_b["delta_q"],
        "h_edge": arm_b["h_edge"],
        "anti_a": arm_a["anti_frac_vs_true"],
        "anti_b": arm_b["anti_frac_vs_true"],
        "anti_c": arm_c["anti_frac_vs_true"],
        "anti_margin": round(
            arm_b["anti_frac_vs_true"] - arm_c["anti_frac_vs_true"], 6
        ),
        "delta_q_pass": delta_q_ok,
        "h_pass": h_ok,
        "arm_c_break": c_break,
        "triad": triad,
        "arm_a_sanity": arm_a_sanity,
        "arm_a_delta_ok": arm_a_delta_ok,
        "arm_a_h_ok": arm_a_h_ok,
        "pass": triad,
        "arm_a": arm_a,
        "arm_b": arm_b,
        "arm_c": arm_c,
    }


def majority_verdict(cells: List[Dict[str, Any]]) -> Dict[str, Any]:
    if any(c.get("contamination") for c in cells):
        return {"verdict": "CONTAMINATION", "n_triad": 0, "n": len(cells)}
    n = len(cells)
    n_triad = sum(1 for c in cells if c.get("triad"))
    n_break = sum(1 for c in cells if c.get("arm_c_break"))
    maj = n_triad >= 4
    s11 = n_break >= 4
    if not maj:
        verdict = "NO_STRUCTURE"
    elif not s11:
        verdict = "RELATION_INVALID"
    else:
        verdict = "STRUCTURE_RELATIONAL"
    return {
        "verdict": verdict,
        "n": n,
        "n_triad": n_triad,
        "n_arm_c_break": n_break,
        "majority_triad": maj,
        "section_1_1_replication": s11,
    }
