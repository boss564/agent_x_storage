#!/usr/bin/env python3
"""Reciprocal-event coupling capture — RECIPROCAL_EVENT_KOPPLUNG_v0 (BINDEND).

F7 receipt gate: kappa only if receipt_from == signal_partner.
F5 inter-arrival modulation only. F6 snapshot windows on event time.
"""
from __future__ import annotations

import heapq
import math
import zlib
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from measure import SwarmTrace
from partner_select import permute_sticky_map
from response_rij import FORMULA_V02, assign_p, r_ij

EPS = 1e-9
N_AGENTS = 9
N_REQUESTS = 128
SNAPSHOT_DT = 64.0
RHO_MAX = 0.90
MAE_NORM_MIN = 0.05
DELTA_R_MIN = 0.05
S_LOW = 0.5
S_HIGH = 2.0


def _crc_u01(material: str) -> float:
    return (zlib.crc32(material.encode()) & 0xFFFFFFFF) / 0xFFFFFFFF


def _corr_abs(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
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


def _run_arm(
    *,
    run_seed: int,
    arm: str,
    kappa: float,
    agent_ids: List[str],
    p_of,
    true_partner: Dict[str, str],
    signal_partner: Dict[str, str],
    mean_s: float,
    sigma: float,
) -> Dict[str, Any]:
    gamma = {a: 0.05 for a in agent_ids}
    R = {a: 0.0 for a in agent_ids}
    t_last = {a: 0.0 for a in agent_ids}
    T_period = {a: 1.0 for a in agent_ids}
    n_req = {a: 0 for a in agent_ids}
    k_req = {a: 0 for a in agent_ids}
    series: Dict[str, List[float]] = {a: [] for a in agent_ids}
    r_low: Dict[str, List[float]] = {a: [] for a in agent_ids}
    r_high: Dict[str, List[float]] = {a: [] for a in agent_ids}
    msg_log: List[Tuple[int, str, str]] = []
    n_couple_on = 0
    n_couple_off = 0
    event_counter = 0
    next_snap_event = int(SNAPSHOT_DT)
    snapshots: List[List[Dict[str, float]]] = []

    heap: List[Tuple[float, int, str, str, str]] = []
    seq = 0

    def push(t: float, kind: str, sender: str, receiver: str) -> None:
        nonlocal seq
        seq += 1
        heapq.heappush(heap, (t, seq, kind, sender, receiver))

    def phase_of(aid: str) -> float:
        T = max(T_period[aid], EPS)
        return float((2.0 * math.pi * (t_last[aid] / T)) % (2.0 * math.pi))

    def take_snapshot() -> None:
        snap = []
        for a in agent_ids:
            snap.append(
                {
                    "phase": phase_of(a),
                    "R": float(R[a]),
                    "T": float(T_period[a]),
                    "n_req": float(n_req[a]),
                }
            )
        snapshots.append(snap)

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
            t_last[sender] = t
            series[sender].append(r)
            msg_log.append((int(t), sender, receiver))
            if s < (S_LOW + S_HIGH) / 2:
                r_low[sender].append(r)
            else:
                r_high[sender].append(r)
            n_req[sender] += 1
            k_req[sender] += 1
            event_counter += 1
            if event_counter >= next_snap_event:
                take_snapshot()
                next_snap_event += int(SNAPSHOT_DT)
            push(t + 0.05, "RECEIPT", receiver, sender)
        else:
            requester = receiver
            receipt_from = sender
            sig = signal_partner[requester]
            reciprocal = receipt_from == sig
            gap0 = _base_gap(run_seed, requester, k_req[requester])
            if reciprocal and kappa > 0:
                gap = gap0 / (1.0 + kappa * _h(R.get(sig, 0.0)))
                n_couple_on += 1
            else:
                gap = gap0
                n_couple_off += 1
            T_period[requester] = max(gap, EPS)
            if n_req[requester] < N_REQUESTS:
                push(t + gap, "REQUEST", requester, true_partner[requester])

    if not snapshots:
        take_snapshot()
        take_snapshot()

    return {
        "series": series,
        "r_low": r_low,
        "r_high": r_high,
        "msg_log": msg_log,
        "snapshots": snapshots,
        "frac_on": (n_couple_on / (n_couple_on + n_couple_off)) if (n_couple_on + n_couple_off) else 0.0,
        "n_couple_on": n_couple_on,
        "n_couple_off": n_couple_off,
    }


def capture_reciprocal_event_coupling(
    *,
    run_seed: int = 20262201,
    kappa: float = 0.0,
    arm: str = "B",
) -> Dict[str, Any]:
    arm = str(arm).upper()
    if arm not in {"A", "B", "C"}:
        raise ValueError(arm)
    kappa_run = 0.0 if arm == "A" else float(kappa)

    agent_ids = [f"E{i:02d}" for i in range(1, N_AGENTS + 1)]
    p_of = assign_p(agent_ids)
    frozen = {(aid, "partner"): agent_ids[(i + 1) % N_AGENTS] for i, aid in enumerate(agent_ids)}
    map_c = permute_sticky_map(frozen, seed=int(run_seed))
    true_p = {s: p for (s, _r), p in frozen.items()}
    pi_p = {s: p for (s, _r), p in map_c.items()}
    sig_p = true_p if arm != "C" else pi_p

    dry = [_payload(run_seed, aid, k) for aid in agent_ids for k in range(N_REQUESTS)]
    mean_s = sum(dry) / len(dry)
    sigma = math.sqrt(sum((x - mean_s) ** 2 for x in dry) / (len(dry) - 1))
    if sigma < EPS:
        sigma = 1.0

    arm_out = _run_arm(
        run_seed=run_seed,
        arm=arm,
        kappa=kappa_run,
        agent_ids=agent_ids,
        p_of=p_of,
        true_partner=true_p,
        signal_partner=sig_p,
        mean_s=mean_s,
        sigma=sigma,
    )

    series = arm_out["series"]
    L = min(len(series[a]) for a in agent_ids)
    if L < 2:
        L = 2
        for a in agent_ids:
            while len(series[a]) < L:
                series[a].append(0.0)

    ebar = [sum(series[a][t] for a in agent_ids) / N_AGENTS for t in range(L)]
    corrs = [c for c in (_corr_abs(series[a][:L], ebar) for a in agent_ids) if c is not None]
    med_rho = sorted(corrs)[len(corrs) // 2] if corrs else 1.0
    flag_a = bool(med_rho <= RHO_MAX and len(corrs) >= N_AGENTS)

    maes = []
    for s in agent_ids:
        p_true = true_p[s]
        p_pi = pi_p[s]
        pb = series[p_true]
        pc = series[p_pi]
        Lp = min(len(pb), len(pc), L)
        if Lp >= 2:
            maes.append(sum(abs(pb[t] - pc[t]) for t in range(Lp)) / Lp)
    if maes:
        mae_raw = sum(maes) / len(maes)
        last_vals = [series[a][L - 1] for a in agent_ids]
        mean_r = sum(last_vals) / len(last_vals)
        sigma_r = math.sqrt(sum((x - mean_r) ** 2 for x in last_vals) / (len(last_vals) - 1)) if len(last_vals) > 1 else 1.0
        mae_norm = mae_raw / (sigma_r + EPS)
    else:
        mae_norm = 0.0
    flag_b = bool(mae_norm >= MAE_NORM_MIN)

    deltas = []
    for a in agent_ids:
        lo, hi = arm_out["r_low"][a], arm_out["r_high"][a]
        if lo and hi:
            deltas.append(abs(sum(hi) / len(hi) - sum(lo) / len(lo)))
    mean_abs_diff = sum(deltas) / len(deltas) if deltas else 0.0
    flag_c = bool(mean_abs_diff >= DELTA_R_MIN and len(deltas) >= N_AGENTS)

    intact = bool(flag_a and flag_b and flag_c)
    precon_label = "INTACT" if intact else "PRECONDITION_LOST"

    snaps = arm_out["snapshots"]
    keys = ["phase", "R", "T", "n_req"]
    states = np.zeros((len(snaps), N_AGENTS, len(keys)))
    for ti, snap in enumerate(snaps):
        for ai, st in enumerate(snap):
            for di, k in enumerate(keys):
                states[ti, ai, di] = float(st.get(k, 0.0))
    tr = SwarmTrace(agent_ids, states, arm_out["msg_log"])
    tr.state_keys = keys
    tr.kappa = kappa_run
    tr.arm = arm
    tr.run_seed = int(run_seed)
    tr.frozen_map = frozen
    tr.shuffled_map = map_c

    battery = {
        "A": {"pass": flag_a, "median_abs_rho": round(med_rho, 6), "n_corr": len(corrs)},
        "B": {"pass": flag_b, "mae_norm": round(mae_norm, 6)},
        "C": {"pass": flag_c, "mean_abs_diff": round(mean_abs_diff, 6)},
    }

    return {
        "trace": tr,
        "arm": arm,
        "kappa": float(kappa),
        "kappa_run": kappa_run,
        "run_seed": int(run_seed),
        "snapshot_dt": SNAPSHOT_DT,
        "n_snapshots": len(snaps),
        "formula": FORMULA_V02,
        "f5": "inter_arrival",
        "f7": "receipt_gate",
        "frac_coupling_on": round(float(arm_out["frac_on"]), 6),
        "n_couple_on": int(arm_out["n_couple_on"]),
        "n_couple_off": int(arm_out["n_couple_off"]),
        "precondition": {"label": precon_label, "intact": intact, "battery": battery},
        "battery": battery,
    }

