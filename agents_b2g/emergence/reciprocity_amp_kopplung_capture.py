#!/usr/bin/env python3
"""Reciprocity-amplification capture — RECIPROCITY_AMP_KOPPLUNG_v0 (BINDEND).

Vierarm A/B/C/D. F8 endogenous amp on B/C. F9 Arm D: κ exogen = κ̄_B.
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
SNAPSHOT_DT = 64
RHO_MAX = 0.90
MAE_NORM_MIN = 0.05
DELTA_R_MIN = 0.05
KAPPA0 = 0.15
KAPPA_MAX = 2.0
DECAY = 0.98
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
    amp_step: float,
    agent_ids: List[str],
    p_of,
    true_partner: Dict[str, str],
    signal_partner: Dict[str, str],
    mean_s: float,
    sigma: float,
    kappa_fixed: Optional[float] = None,
) -> Dict[str, Any]:
    """Arm A: κ=0. B/C: endogenous F8. D: exogenous kappa_fixed, no F8 growth."""
    endogenous = arm in {"B", "C"} and amp_step > 0 and kappa_fixed is None
    fixed = float(kappa_fixed) if kappa_fixed is not None else None
    if arm == "A":
        endogenous = False
        fixed = 0.0

    gamma = {a: 0.05 for a in agent_ids}
    R = {a: 0.0 for a in agent_ids}
    t_last = {a: 0.0 for a in agent_ids}
    T_period = {a: 1.0 for a in agent_ids}
    kappa_edge = {a: (fixed if fixed is not None else KAPPA0) for a in agent_ids}
    n_req = {a: 0 for a in agent_ids}
    k_req = {a: 0 for a in agent_ids}
    series: Dict[str, List[float]] = {a: [] for a in agent_ids}
    r_low: Dict[str, List[float]] = {a: [] for a in agent_ids}
    r_high: Dict[str, List[float]] = {a: [] for a in agent_ids}
    msg_log: List[Tuple[int, str, str]] = []
    n_amp = 0
    n_decay = 0
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
        snapshots.append(
            [
                {
                    "phase": phase_of(a),
                    "R": float(R[a]),
                    "T": float(T_period[a]),
                    "kappa": float(kappa_edge[a]),
                    "n_req": float(n_req[a]),
                }
                for a in agent_ids
            ]
        )

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

            if arm == "A" or (fixed is not None and not endogenous):
                # A or D: fixed κ (0 or κ̄_B); D still uses signal for h()
                k_use = 0.0 if arm == "A" else float(fixed)
                kappa_edge[requester] = k_use
                if arm == "D" and reciprocal:
                    # D does not amplify; count reciprocity only for diagnostics
                    n_amp += 1
                elif arm == "D":
                    n_decay += 1
                if arm == "A" or k_use <= 0:
                    gap = gap0
                else:
                    gap = gap0 / (1.0 + k_use * _h(R.get(sig, 0.0)))
            elif endogenous:
                if reciprocal:
                    kappa_edge[requester] = min(
                        KAPPA_MAX,
                        kappa_edge[requester] + amp_step * _h(R.get(sig, 0.0)),
                    )
                    n_amp += 1
                    gap = gap0 / (
                        1.0 + kappa_edge[requester] * _h(R.get(sig, 0.0))
                    )
                else:
                    kappa_edge[requester] = max(
                        KAPPA0 * 0.5, kappa_edge[requester] * DECAY
                    )
                    n_decay += 1
                    gap = gap0
            else:
                # B/C with amp_step=0: no growth, no coupling
                gap = gap0
                n_decay += 1

            T_period[requester] = max(gap, EPS)
            if n_req[requester] < N_REQUESTS:
                push(t + gap, "REQUEST", requester, true_partner[requester])

    if len(snapshots) < 2:
        take_snapshot()
        take_snapshot()

    n_dec = n_amp + n_decay
    final_k = sum(kappa_edge.values()) / len(kappa_edge)
    return {
        "series": series,
        "r_low": r_low,
        "r_high": r_high,
        "msg_log": msg_log,
        "snapshots": snapshots,
        "frac_amp": (n_amp / n_dec) if n_dec else 0.0,
        "n_amp": n_amp,
        "n_decay": n_decay,
        "final_kappa_mean": final_k,
        "kappa_edge": dict(kappa_edge),
    }


def capture_reciprocity_amp_coupling(
    *,
    run_seed: int = 20262401,
    amp_step: float = 0.0,
    arm: str = "B",
    kappa_fixed: Optional[float] = None,
) -> Dict[str, Any]:
    arm = str(arm).upper()
    if arm not in {"A", "B", "C", "D"}:
        raise ValueError(arm)
    if arm == "D" and kappa_fixed is None:
        raise ValueError("Arm D requires kappa_fixed (= κ̄_B)")

    agent_ids = [f"E{i:02d}" for i in range(1, N_AGENTS + 1)]
    p_of = assign_p(agent_ids)
    frozen = {
        (aid, "partner"): agent_ids[(i + 1) % N_AGENTS]
        for i, aid in enumerate(agent_ids)
    }
    map_c = permute_sticky_map(frozen, seed=int(run_seed))
    true_p = {s: p for (s, _r), p in frozen.items()}
    pi_p = {s: p for (s, _r), p in map_c.items()}
    if arm in {"C", "D"}:
        sig_p = pi_p
    else:
        sig_p = true_p

    dry = [
        _payload(run_seed, aid, k)
        for aid in agent_ids
        for k in range(N_REQUESTS)
    ]
    mean_s = sum(dry) / len(dry)
    sigma = math.sqrt(sum((x - mean_s) ** 2 for x in dry) / (len(dry) - 1))
    if sigma < EPS:
        sigma = 1.0

    step = 0.0 if arm == "A" else float(amp_step)
    arm_out = _run_arm(
        run_seed=run_seed,
        arm=arm,
        amp_step=step,
        agent_ids=agent_ids,
        p_of=p_of,
        true_partner=true_p,
        signal_partner=sig_p,
        mean_s=mean_s,
        sigma=sigma,
        kappa_fixed=0.0 if arm == "A" else kappa_fixed,
    )

    series = arm_out["series"]
    L = min(len(series[a]) for a in agent_ids)
    if L < 2:
        L = 2
        for a in agent_ids:
            while len(series[a]) < L:
                series[a].append(0.0)

    ebar = [sum(series[a][t] for a in agent_ids) / N_AGENTS for t in range(L)]
    corrs = [
        c
        for c in (_corr_abs(series[a][:L], ebar) for a in agent_ids)
        if c is not None
    ]
    med_rho = sorted(corrs)[len(corrs) // 2] if corrs else 1.0
    flag_a = bool(med_rho <= RHO_MAX and len(corrs) >= N_AGENTS)

    maes = []
    for s in agent_ids:
        pb, pc = series[true_p[s]], series[pi_p[s]]
        Lp = min(len(pb), len(pc), L)
        if Lp >= 2:
            maes.append(sum(abs(pb[t] - pc[t]) for t in range(Lp)) / Lp)
    if maes:
        mae_raw = sum(maes) / len(maes)
        last_vals = [series[a][L - 1] for a in agent_ids]
        mean_r = sum(last_vals) / len(last_vals)
        sigma_r = (
            math.sqrt(
                sum((x - mean_r) ** 2 for x in last_vals) / (len(last_vals) - 1)
            )
            if len(last_vals) > 1
            else 1.0
        )
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
    keys = ["phase", "R", "T", "kappa", "n_req"]
    states = np.zeros((len(snaps), N_AGENTS, len(keys)))
    for ti, snap in enumerate(snaps):
        for ai, st in enumerate(snap):
            for di, k in enumerate(keys):
                states[ti, ai, di] = float(st.get(k, 0.0))
    tr = SwarmTrace(agent_ids, states, arm_out["msg_log"])
    tr.state_keys = keys
    tr.kappa = float(arm_out["final_kappa_mean"])
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
        "amp_step": float(amp_step),
        "kappa_fixed": kappa_fixed,
        "run_seed": int(run_seed),
        "n_agents": N_AGENTS,
        "snapshot_dt": SNAPSHOT_DT,
        "n_snapshots": len(snaps),
        "formula": FORMULA_V02,
        "f8": "endogenous_amp" if arm in {"B", "C"} else None,
        "f9": "exogenous_match" if arm == "D" else None,
        "frac_amp": round(float(arm_out["frac_amp"]), 6),
        "final_kappa_mean": round(float(arm_out["final_kappa_mean"]), 6),
        "n_amp": int(arm_out["n_amp"]),
        "n_decay": int(arm_out["n_decay"]),
        "precondition": {"label": precon_label, "intact": intact, "battery": battery},
        "battery": battery,
    }
