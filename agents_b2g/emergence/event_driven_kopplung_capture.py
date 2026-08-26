#!/usr/bin/env python3
"""Event-driven coupling capture — EVENT_DRIVEN_KOPPLUNG_v0 (BINDEND).

F1 no continuous ℓ(t) · F5 Inter-Arrival κ·h · F6 Snapshot Δt=64
docs/EVENT_DRIVEN_KOPPLUNG_v0_PREREG.md
"""
from __future__ import annotations

import math
import zlib
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from partner_select import permute_sticky_map
from measure import SwarmTrace
from response_rij import assign_p, r_ij, FORMULA_V02

EPS = 1e-9
N_AGENTS = 9
WARMUP_EVENTS = 16
MIN_MEASURE_EVENTS = 64
SNAPSHOT_DT = 64.0  # F6
MIN_SNAPSHOTS = 48
S_LOW = 0.5
S_HIGH = 2.0
RHO_MAX = 0.90
MAE_NORM_MIN = 0.05
DELTA_R_MIN = 0.05
MAX_SIM_DEFAULT = 50000.0


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


def _h_from_r(r: float) -> float:
    return float(max(0.0, min(1.0, abs(r) / (abs(r) + 1.0))))


def capture_event_driven_coupling(
    *,
    run_seed: int = 20262001,
    kappa: float = 0.0,
    arm: str = "B",
    max_sim_time: float = MAX_SIM_DEFAULT,
) -> Dict[str, Any]:
    """Return {trace, precondition, battery, arm, kappa}."""
    arm = str(arm).upper()
    if arm not in {"A", "B", "C"}:
        raise ValueError(arm)
    kappa_run = 0.0 if arm == "A" else float(kappa)
    interval_on = kappa_run > 0.0

    agent_ids = [f"E{i:02d}" for i in range(1, N_AGENTS + 1)]
    p_of = assign_p(agent_ids)
    idx = {aid: i for i, aid in enumerate(agent_ids)}

    # Sticky ring partners (role=partner) — degree 1 out
    frozen_map: Dict[Tuple[str, str], str] = {}
    for i, aid in enumerate(agent_ids):
        pid = agent_ids[(i + 1) % N_AGENTS]
        frozen_map[(aid, "partner")] = pid
    map_c = permute_sticky_map(frozen_map, seed=int(run_seed))
    signal_map = map_c if arm == "C" else frozen_map
    signal_partner = {s: p for (s, _r), p in signal_map.items()}
    true_partner = {s: p for (s, _r), p in frozen_map.items()}
    pi_partner = {s: p for (s, _r), p in map_c.items()}

    # State
    gamma = {a: 0.05 for a in agent_ids}
    R = {a: 0.0 for a in agent_ids}
    T_period = {a: 1.0 for a in agent_ids}
    t_last = {a: 0.0 for a in agent_ids}
    n_events = {a: 0 for a in agent_ids}
    event_k = {a: 0 for a in agent_ids}

    def base_gap(aid: str) -> float:
        k = event_k[aid]
        return 0.4 + 1.6 * _crc_u01(f"{run_seed}|{aid}|gap|{k}")

    def payload(aid: str) -> float:
        k = event_k[aid]
        u = _crc_u01(f"{run_seed}|{aid}|S|{k}")
        s = S_HIGH if u > 0.45 else S_LOW
        s *= 0.85 + 0.30 * _crc_u01(f"{run_seed}|{aid}|Sj|{k}")
        return float(s)

    # Pre-draw sigma from a dry run of payloads (deterministic)
    dry_s: List[float] = []
    for aid in agent_ids:
        for k in range(WARMUP_EVENTS + MIN_MEASURE_EVENTS + 8):
            u = _crc_u01(f"{run_seed}|{aid}|S|{k}")
            s = S_HIGH if u > 0.45 else S_LOW
            s *= 0.85 + 0.30 * _crc_u01(f"{run_seed}|{aid}|Sj|{k}")
            dry_s.append(s)
    mean_s = sum(dry_s) / len(dry_s)
    sigma = math.sqrt(sum((x - mean_s) ** 2 for x in dry_s) / (len(dry_s) - 1))
    if sigma < EPS:
        sigma = 1.0

    next_t = {a: base_gap(a) * _crc_u01(f"{run_seed}|{a}|t0") for a in agent_ids}

    # Measure buffers
    r_series: Dict[str, List[float]] = {a: [] for a in agent_ids}
    r_edge_b: Dict[Tuple[str, str], List[float]] = {
        (s, true_partner[s]): [] for s in agent_ids
    }
    r_edge_c: Dict[Tuple[str, str], List[float]] = {
        (s, signal_partner[s]): [] for s in agent_ids
    }
    r_low: Dict[str, List[float]] = {a: [] for a in agent_ids}
    r_high: Dict[str, List[float]] = {a: [] for a in agent_ids}
    msg_log: List[Tuple[int, str, str]] = []
    snapshots: List[List[Dict[str, float]]] = []
    snap_idx = 0
    next_snap_t = SNAPSHOT_DT
    measure_on = False

    def phase_of(aid: str) -> float:
        T = max(T_period[aid], EPS)
        return float((2.0 * math.pi * (t_last[aid] / T)) % (2.0 * math.pi))

    def numeric_state(aid: str) -> Dict[str, float]:
        return {
            "phase": phase_of(aid),
            "R": float(R[aid]),
            "T": float(T_period[aid]),
            "n_events": float(n_events[aid]),
        }

    t = 0.0
    while t < max_sim_time:
        # next event agent
        aid = min(agent_ids, key=lambda a: next_t[a])
        t = float(next_t[aid])
        if t > max_sim_time:
            break

        # emit any due snapshots up to t
        while next_snap_t <= t + 1e-12:
            if measure_on:
                snapshots.append([numeric_state(a) for a in agent_ids])
                snap_idx += 1
            next_snap_t += SNAPSHOT_DT

        # fire event
        s = payload(aid)
        p = p_of[aid]
        gamma[aid] = math.tanh(gamma[aid] + 0.08 * (s - mean_s) / sigma)
        r = r_ij(s, gamma[aid], p, sigma, formula=FORMULA_V02)
        R[aid] = r
        t_last[aid] = t
        n_events[aid] += 1
        pid_true = true_partner[aid]
        pid_sig = signal_partner[aid]
        msg_log.append((int(t), aid, pid_true))

        if measure_on:
            r_series[aid].append(r)
            r_edge_b[(aid, pid_true)].append(r)
            r_edge_c.setdefault((aid, pid_sig), []).append(r)
            if s < (S_LOW + S_HIGH) / 2:
                r_low[aid].append(r)
            else:
                r_high[aid].append(r)

        # F5 Inter-Arrival
        gap0 = base_gap(aid)
        if interval_on:
            r_partner = R.get(pid_sig, 0.0)
            h = _h_from_r(r_partner)
            gap = gap0 * (1.0 + kappa_run * h)
        else:
            gap = gap0
        T_period[aid] = max(gap, EPS)
        event_k[aid] += 1
        next_t[aid] = t + gap

        # warmup → measure
        if not measure_on and all(n_events[a] >= WARMUP_EVENTS for a in agent_ids):
            measure_on = True
            # reset measure counters conceptually: keep R/gamma/T, clear series
            for a in agent_ids:
                r_series[a].clear()
                r_low[a].clear()
                r_high[a].clear()
            for k in r_edge_b:
                r_edge_b[k].clear()
            for k in list(r_edge_c.keys()):
                r_edge_c[k].clear()
            msg_log.clear()
            snapshots.clear()
            # align next snapshot
            next_snap_t = t + SNAPSHOT_DT

        if (
            measure_on
            and all(len(r_series[a]) >= MIN_MEASURE_EVENTS for a in agent_ids)
            and len(snapshots) >= MIN_SNAPSHOTS
        ):
            break

    # Ensure minimal snapshot history
    while len(snapshots) < 2:
        snapshots.append([numeric_state(a) for a in agent_ids])

    # Build SwarmTrace
    keys = ["phase", "R", "T", "n_events"]
    Tsnap = len(snapshots)
    if Tsnap < 2:
        # force minimal history
        while len(snapshots) < 2:
            snapshots.append([numeric_state(a) for a in agent_ids])
        Tsnap = len(snapshots)
    states = np.zeros((Tsnap, N_AGENTS, len(keys)))
    for ti, snap in enumerate(snapshots):
        for ai, st in enumerate(snap):
            for di, k in enumerate(keys):
                states[ti, ai, di] = float(st.get(k, 0.0))

    tr = SwarmTrace(list(agent_ids), states, list(msg_log))
    tr.state_keys = keys
    tr.kappa = kappa_run
    tr.arm = arm
    tr.run_seed = int(run_seed)
    tr.frozen_map = frozen_map
    tr.shuffled_map = map_c

    # --- Battery A ---
    # Align by min length ordinal
    L = min(len(r_series[a]) for a in agent_ids)
    if L < 2:
        L = 2
        for a in agent_ids:
            while len(r_series[a]) < L:
                r_series[a].append(R[a])
    ebar = [
        sum(r_series[a][t] for a in agent_ids) / N_AGENTS for t in range(L)
    ]
    corrs: List[float] = []
    for a in agent_ids:
        c = _corr_abs(r_series[a][:L], ebar)
        if c is not None:
            corrs.append(c)
    med_rho = sorted(corrs)[len(corrs) // 2] if corrs else 1.0
    flag_a = bool(med_rho <= RHO_MAX and len(corrs) >= N_AGENTS)

    # --- Battery B: mae of partner-R trajectories true vs π ---
    maes = []
    for s in agent_ids:
        p_true = true_partner[s]
        p_pi = pi_partner[s]
        pb = r_series[p_true]
        pc = r_series[p_pi]
        Lp = min(len(pb), len(pc), L)
        if Lp < 2:
            continue
        maes.append(sum(abs(pb[t] - pc[t]) for t in range(Lp)) / Lp)
    if not maes:
        mae_norm = 0.0
        flag_b = False
    else:
        mae_raw = sum(maes) / len(maes)
        last_vals = [r_series[a][L - 1] for a in agent_ids]
        mean_r = sum(last_vals) / len(last_vals)
        sigma_r = (
            math.sqrt(
                sum((x - mean_r) ** 2 for x in last_vals) / (len(last_vals) - 1)
            )
            if len(last_vals) > 1
            else 1.0
        )
        mae_norm = mae_raw / (sigma_r + EPS)
        flag_b = bool(mae_norm >= MAE_NORM_MIN)

    # --- Battery C ---
    deltas = []
    for a in agent_ids:
        if r_low[a] and r_high[a]:
            deltas.append(
                abs(sum(r_high[a]) / len(r_high[a]) - sum(r_low[a]) / len(r_low[a]))
            )
    mean_abs_diff = sum(deltas) / len(deltas) if deltas else 0.0
    flag_c = bool(mean_abs_diff >= DELTA_R_MIN and len(deltas) >= N_AGENTS)

    intact = bool(flag_a and flag_b and flag_c)
    precon_label = "INTACT" if intact else "PRECONDITION_LOST"

    battery = {
        "A": {
            "pass": flag_a,
            "median_abs_rho": round(med_rho, 6),
            "n_corr": len(corrs),
        },
        "B": {
            "pass": flag_b,
            "mae_norm": round(mae_norm, 6),
        },
        "C": {
            "pass": flag_c,
            "mean_abs_diff": round(mean_abs_diff, 6),
        },
    }

    return {
        "trace": tr,
        "arm": arm,
        "kappa": float(kappa),
        "kappa_run": kappa_run,
        "run_seed": int(run_seed),
        "snapshot_dt": SNAPSHOT_DT,
        "n_snapshots": Tsnap,
        "formula": FORMULA_V02,
        "f5": "inter_arrival",
        "precondition": {
            "label": precon_label,
            "intact": intact,
            "battery": battery,
        },
        "battery": battery,
    }
