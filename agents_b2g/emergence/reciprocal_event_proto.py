#!/usr/bin/env python3
"""Reciprocal-event prototype — κ only on Request+Receipt pairs.

Engineering screen only — no Pre-Reg / no sweep.
Gate: ΔR_i > 0  ∧  median |ρ| < 0.90
Delivery stays on true M; coupling reads signal partner (B=M, C=π(M)).
"""
from __future__ import annotations

import heapq
import math
import zlib
from typing import Any, Dict, List, Sequence, Tuple

from partner_select import permute_sticky_map
from response_rij import assign_p, r_ij, FORMULA_V02

EPS = 1e-9
RHO_MAX = 0.90
N_AGENTS = 9
N_REQUESTS = 64
KAPPA_PROTO = 0.6
S_LOW = 0.5
S_HIGH = 2.0


def _crc_u01(material: str) -> float:
    return (zlib.crc32(material.encode()) & 0xFFFFFFFF) / 0xFFFFFFFF


def _corr_abs(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    n = len(xs)
    if n < 2 or len(ys) != n:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((xs[t] - mx) * (ys[t] - my) for t in range(n))
    dx = math.sqrt(sum((xs[t] - mx) ** 2 for t in range(n)))
    dy = math.sqrt(sum((ys[t] - my) ** 2 for t in range(n)))
    if dx < 1e-12 or dy < 1e-12:
        return None
    return abs(num / (dx * dy))


def _h(r: float) -> float:
    return float(max(0.0, min(1.0, abs(r) / (abs(r) + 1.0))))


def _payload(run_seed: int, aid: str, k: int) -> float:
    u = _crc_u01(f"{run_seed}|{aid}|S|{k}")
    s = S_HIGH if u > 0.45 else S_LOW
    return float(s * (0.85 + 0.30 * _crc_u01(f"{run_seed}|{aid}|Sj|{k}")))


def _base_gap(run_seed: int, aid: str, k: int) -> float:
    return 0.4 + 1.6 * _crc_u01(f"{run_seed}|{aid}|gap|{k}")


def _series_stats(series: Dict[str, List[float]]) -> Tuple[float, float, bool, bool]:
    ids = list(series)
    T = min(len(series[a]) for a in ids)
    if T < 2:
        return 1.0, 0.0, False, False
    ebar = [sum(series[a][t] for a in ids) / len(ids) for t in range(T)]
    corrs = []
    for a in ids:
        c = _corr_abs(series[a][:T], ebar)
        if c is not None:
            corrs.append(c)
    med_rho = sorted(corrs)[len(corrs) // 2] if corrs else 1.0
    # ΔR from first vs second half of each series (payload mix already in events)
    deltas = []
    for a in ids:
        xs = series[a][:T]
        mid = T // 2
        lo, hi = xs[:mid], xs[mid:]
        if lo and hi:
            deltas.append(abs(sum(hi) / len(hi) - sum(lo) / len(lo)))
        else:
            deltas.append(0.0)
    mean_d = sum(deltas) / len(deltas) if deltas else 0.0
    flag_a = bool(med_rho < RHO_MAX and len(corrs) >= N_AGENTS)
    flag_b = bool(mean_d > 0.0 and all(d > 0.0 for d in deltas))
    return med_rho, mean_d, flag_a, flag_b


def _run_arm(
    *,
    run_seed: int,
    arm: str,
    agent_ids: List[str],
    p_of,
    true_partner: Dict[str, str],
    signal_partner: Dict[str, str],
    mean_s: float,
    sigma: float,
) -> Dict[str, Any]:
    """Event loop: REQUEST on true M; RECEIPT to sender; κ only if receipt==signal."""
    kappa = KAPPA_PROTO
    gamma = {a: 0.05 for a in agent_ids}
    R = {a: 0.0 for a in agent_ids}
    n_req = {a: 0 for a in agent_ids}
    k_req = {a: 0 for a in agent_ids}
    series: Dict[str, List[float]] = {a: [] for a in agent_ids}
    r_low: Dict[str, List[float]] = {a: [] for a in agent_ids}
    r_high: Dict[str, List[float]] = {a: [] for a in agent_ids}
    n_couple_on = 0
    n_couple_off = 0

    heap: List[Tuple[float, int, str, str, str]] = []
    seq = 0

    def push(t: float, kind: str, sender: str, receiver: str) -> None:
        nonlocal seq
        seq += 1
        heapq.heappush(heap, (t, seq, kind, sender, receiver))

    t0 = 0.01
    for a in agent_ids:
        push(t0 + _crc_u01(f"{run_seed}|{a}|t0") * 0.2, "REQUEST", a, true_partner[a])

    while heap and min(n_req.values()) < N_REQUESTS:
        t, _s, kind, sender, receiver = heapq.heappop(heap)
        if kind == "REQUEST":
            if n_req[sender] >= N_REQUESTS:
                continue
            s = _payload(run_seed, sender, k_req[sender])
            p = p_of[sender]
            gamma[sender] = math.tanh(gamma[sender] + 0.08 * (s - mean_s) / sigma)
            r = r_ij(s, gamma[sender], p, sigma, formula=FORMULA_V02)
            R[sender] = r
            series[sender].append(r)
            if s < (S_LOW + S_HIGH) / 2:
                r_low[sender].append(r)
            else:
                r_high[sender].append(r)
            n_req[sender] += 1
            k_req[sender] += 1
            # Receipt is always from the real delivery partner, immediately after
            push(t + 0.05, "RECEIPT", receiver, sender)
            # Schedule next request using last coupling decision (updated on RECEIPT)
            # First request uses base gap; subsequent use last stored gap via RECEIPT handler
        else:  # RECEIPT: receiver is original requester
            requester = receiver
            receipt_from = sender
            sig = signal_partner[requester]
            reciprocal = receipt_from == sig
            gap0 = _base_gap(run_seed, requester, k_req[requester])
            if reciprocal:
                gap = gap0 / (1.0 + kappa * _h(R.get(sig, 0.0)))
                n_couple_on += 1
            else:
                gap = gap0
                n_couple_off += 1
            if n_req[requester] < N_REQUESTS:
                push(
                    t + gap,
                    "REQUEST",
                    requester,
                    true_partner[requester],
                )

    # ΔR from payload classes (same as first proto)
    deltas = []
    for a in agent_ids:
        if r_low[a] and r_high[a]:
            deltas.append(
                abs(sum(r_high[a]) / len(r_high[a]) - sum(r_low[a]) / len(r_low[a]))
            )
        else:
            deltas.append(0.0)
    med_rho, _half_d, flag_a, _ = _series_stats(series)
    mean_d = sum(deltas) / len(deltas) if deltas else 0.0
    flag_b = bool(mean_d > 0.0 and all(d > 0.0 for d in deltas))
    n_dec = n_couple_on + n_couple_off
    return {
        "arm": arm,
        "median_abs_rho": round(med_rho, 6),
        "mean_delta_r": round(mean_d, 6),
        "layer_a_pass": flag_a,
        "layer_b_pass": flag_b,
        "pass": bool(flag_a and flag_b),
        "frac_coupling_on": round(n_couple_on / n_dec, 6) if n_dec else 0.0,
        "n_couple_on": n_couple_on,
        "n_couple_off": n_couple_off,
    }


def run_reciprocal_event_cell(*, run_seed: int) -> Dict[str, Any]:
    agent_ids = [f"E{i:02d}" for i in range(1, N_AGENTS + 1)]
    p_of = assign_p(agent_ids)
    frozen = {}
    for i, aid in enumerate(agent_ids):
        frozen[(aid, "partner")] = agent_ids[(i + 1) % N_AGENTS]
    map_c = permute_sticky_map(frozen, seed=int(run_seed))
    true_p = {s: p for (s, _r), p in frozen.items()}
    pi_p = {s: p for (s, _r), p in map_c.items()}

    dry = []
    for aid in agent_ids:
        for k in range(N_REQUESTS):
            dry.append(_payload(run_seed, aid, k))
    mean_s = sum(dry) / len(dry)
    sigma = math.sqrt(sum((x - mean_s) ** 2 for x in dry) / (len(dry) - 1))
    if sigma < EPS:
        sigma = 1.0

    common = dict(
        run_seed=run_seed,
        agent_ids=agent_ids,
        p_of=p_of,
        true_partner=true_p,
        mean_s=mean_s,
        sigma=sigma,
    )
    arm_b = _run_arm(arm="B", signal_partner=true_p, **common)
    arm_c = _run_arm(arm="C", signal_partner=pi_p, **common)

    # Gate is architecture fitness of the reciprocal mechanism (Arm B series)
    passed = bool(arm_b["pass"])
    return {
        "run_seed": run_seed,
        "strand": "reciprocal_event",
        "n_agents": N_AGENTS,
        "n_requests": N_REQUESTS,
        "kappa_proto": KAPPA_PROTO,
        "median_abs_rho": arm_b["median_abs_rho"],
        "mean_delta_r": arm_b["mean_delta_r"],
        "layer_a_pass": arm_b["layer_a_pass"],
        "layer_b_pass": arm_b["layer_b_pass"],
        "pass": passed,
        "arm_b": arm_b,
        "arm_c": arm_c,
        "selectivity_hint": {
            "frac_on_B": arm_b["frac_coupling_on"],
            "frac_on_C": arm_c["frac_coupling_on"],
            "note": "κ fires only if receipt sender == signal partner",
        },
        "formula": FORMULA_V02,
        "note": "delivery on M; receipt from true partner; κ iff receipt==signal",
    }
