#!/usr/bin/env python3
"""Continuous Dissensus Gegenprobe — isolated sandbox (Serie v3).

NO imports from agents_b2g/emergence or v2 stateful-graph runners.

Matched protocol (same as discrete STRUCTURE_RELATIONAL):
  metrics always vs TRUE sticky partner → Arm-C-Bruch = anti_B − anti_C.

Also reports topology-blind GLOBAL pairwise stats (swarm ΔS / anti), which
look nearly identical on B vs C — that is NOT the relational gate.

v1 unbounded: diverges.
v2 tanh-bounded: relational gate is an empirical question (run screen).
"""
from __future__ import annotations

import heapq
import math
import zlib
from typing import Any, Dict, List, Optional, Tuple

N_AGENTS = 9
WARMUP = 32
MEASURE = 80
TOTAL = WARMUP + MEASURE
ALPHA = 0.35
BOUND_SCALE = 1.0  # tanh bound; mean global ΔS ≈ 1.0 under sync
DELTA_S_FLOOR = 0.5
ARM_C_MARGIN = 0.15


def _crc_u01(material: str) -> float:
    return (zlib.crc32(material.encode()) & 0xFFFFFFFF) / 0xFFFFFFFF


def _base_gap(run_seed: int, aid: str, k: int) -> float:
    return 0.4 + 1.6 * _crc_u01(f"{run_seed}|{aid}|gap|{k}")


def _partners(
    run_seed: int, agent_ids: List[str]
) -> Tuple[Dict[str, str], Dict[str, str]]:
    true_p = {
        agent_ids[i]: agent_ids[(i + 1) % N_AGENTS] for i in range(N_AGENTS)
    }
    order = sorted(agent_ids, key=lambda a: _crc_u01(f"{run_seed}|perm|{a}"))
    vals = [true_p[a] for a in order]
    vals = vals[1:] + vals[:1]
    pi_p = {order[i]: vals[i] for i in range(N_AGENTS)}
    return true_p, pi_p


def _run_arm_async(
    *,
    run_seed: int,
    arm: str,
    agent_ids: List[str],
    true_partner: Dict[str, str],
    signal_partner: Dict[str, str],
    bounded: bool,
) -> Dict[str, Any]:
    s = {
        a: (_crc_u01(f"{run_seed}|{a}|s0") - 0.5) * 2.0 for a in agent_ids
    }
    n_ev = {a: 0 for a in agent_ids}
    k_ev = {a: 0 for a in agent_ids}
    series: Dict[str, List[float]] = {a: [] for a in agent_ids}
    anti_true_hits = 0
    anti_true_tot = 0
    exploded = False
    max_abs = 0.0

    heap: List[Tuple[float, int, str]] = []
    seq = 0

    def push(t: float, aid: str) -> None:
        nonlocal seq
        seq += 1
        heapq.heappush(heap, (t, seq, aid))

    for a in agent_ids:
        push(0.01 + _crc_u01(f"{run_seed}|{a}|t0") * 0.2, a)

    while heap and min(n_ev.values()) < TOTAL and not exploded:
        t, _s, aid = heapq.heappop(heap)
        if n_ev[aid] >= TOTAL:
            continue
        sigma = s[signal_partner[aid]]
        raw = s[aid] + ALPHA * (s[aid] - sigma)
        if bounded:
            s[aid] = BOUND_SCALE * math.tanh(raw / BOUND_SCALE)
        else:
            s[aid] = raw
            if abs(s[aid]) > 1e12 or math.isnan(s[aid]) or math.isinf(s[aid]):
                exploded = True
        max_abs = max(max_abs, abs(s[aid]))
        n_ev[aid] += 1
        k_ev[aid] += 1

        if n_ev[aid] > WARMUP and not exploded:
            series[aid].append(s[aid])
            true_id = true_partner[aid]
            anti_true_tot += 1
            if s[aid] * s[true_id] < 0.0:
                anti_true_hits += 1

        if n_ev[aid] < TOTAL and not exploded:
            push(t + _base_gap(run_seed, aid, k_ev[aid]), aid)

    return _summarize(
        arm=arm,
        agent_ids=agent_ids,
        series=series,
        anti_true_hits=anti_true_hits,
        anti_true_tot=anti_true_tot,
        exploded=exploded,
        max_abs=max_abs,
        bounded=bounded,
    )


def _run_arm_sync(
    *,
    run_seed: int,
    arm: str,
    agent_ids: List[str],
    true_partner: Dict[str, str],
    signal_partner: Dict[str, str],
    bounded: bool,
) -> Dict[str, Any]:
    """Synchronous rounds — closer to 'both arms → same equilibrium' narrative."""
    s = {
        a: (_crc_u01(f"{run_seed}|{a}|s0") - 0.5) * 2.0 for a in agent_ids
    }
    series: Dict[str, List[float]] = {a: [] for a in agent_ids}
    anti_true_hits = 0
    anti_true_tot = 0
    exploded = False
    max_abs = 0.0

    for k in range(TOTAL):
        news = {}
        for a in agent_ids:
            sigma = s[signal_partner[a]]
            raw = s[a] + ALPHA * (s[a] - sigma)
            if bounded:
                news[a] = BOUND_SCALE * math.tanh(raw / BOUND_SCALE)
            else:
                news[a] = raw
                if abs(news[a]) > 1e12:
                    exploded = True
            max_abs = max(max_abs, abs(news[a]))
        s = news
        if exploded:
            break
        if k >= WARMUP:
            for a in agent_ids:
                series[a].append(s[a])
                true_id = true_partner[a]
                anti_true_tot += 1
                if s[a] * s[true_id] < 0.0:
                    anti_true_hits += 1

    return _summarize(
        arm=arm,
        agent_ids=agent_ids,
        series=series,
        anti_true_hits=anti_true_hits,
        anti_true_tot=anti_true_tot,
        exploded=exploded,
        max_abs=max_abs,
        bounded=bounded,
    )


def _summarize(
    *,
    arm: str,
    agent_ids: List[str],
    series: Dict[str, List[float]],
    anti_true_hits: int,
    anti_true_tot: int,
    exploded: bool,
    max_abs: float,
    bounded: bool,
) -> Dict[str, Any]:
    L = min((len(series[a]) for a in agent_ids), default=0)
    if exploded or L < 2:
        return {
            "arm": arm,
            "exploded": exploded,
            "bounded": bounded,
            "delta_s_pair": None,
            "anti_true": 0.0,
            "anti_global": 0.0,
            "series_len": L,
            "max_abs": max_abs,
        }

    # Relational ΔS: mean pairwise L1 (same spirit as discrete ΔQ)
    dists = []
    for i, a in enumerate(agent_ids):
        for b in agent_ids[i + 1 :]:
            d = sum(abs(series[a][t] - series[b][t]) for t in range(L)) / float(L)
            dists.append(d)
    delta_s_pair = sum(dists) / len(dists)

    # Topology-blind global anti: opposite signs over all pairs, time-averaged
    # via last snapshot of series (and mean over time)
    anti_g_acc = 0.0
    for t in range(L):
        opp = 0
        tot = 0
        for i, a in enumerate(agent_ids):
            for b in agent_ids[i + 1 :]:
                tot += 1
                if series[a][t] * series[b][t] < 0.0:
                    opp += 1
        anti_g_acc += opp / tot
    anti_global = anti_g_acc / L

    return {
        "arm": arm,
        "exploded": False,
        "bounded": bounded,
        "delta_s_pair": round(delta_s_pair, 6),
        "anti_true": round(
            anti_true_hits / anti_true_tot if anti_true_tot else 0.0, 6
        ),
        "anti_global": round(anti_global, 6),
        "series_len": L,
        "max_abs": round(max_abs, 6),
    }


def run_cell(
    *, run_seed: int, bounded: bool, mode: str = "sync"
) -> Dict[str, Any]:
    agent_ids = [f"D{i:02d}" for i in range(1, N_AGENTS + 1)]
    true_p, pi_p = _partners(run_seed, agent_ids)
    runner = _run_arm_sync if mode == "sync" else _run_arm_async
    arm_b = runner(
        run_seed=run_seed,
        arm="B",
        agent_ids=agent_ids,
        true_partner=true_p,
        signal_partner=true_p,
        bounded=bounded,
    )
    arm_c = runner(
        run_seed=run_seed,
        arm="C",
        agent_ids=agent_ids,
        true_partner=true_p,
        signal_partner=pi_p,
        bounded=bounded,
    )

    if arm_b["exploded"] or arm_c["exploded"]:
        return {
            "run_seed": run_seed,
            "mode": mode,
            "variant": "v1_unbounded" if not bounded else "v2_bounded_tanh",
            "exploded": True,
            "pass_relational": False,
            "fail_reason": "DIVERGENCE",
            "arm_b": arm_b,
            "arm_c": arm_c,
        }

    db = float(arm_b["delta_s_pair"])
    dc = float(arm_c["delta_s_pair"])
    margin_true = arm_b["anti_true"] - arm_c["anti_true"]
    margin_global = arm_b["anti_global"] - arm_c["anti_global"]
    delta_ok = db >= DELTA_S_FLOOR
    c_break = margin_true >= ARM_C_MARGIN
    # Global stats: nearly identical → looks like "no structure" if misused as gate
    global_identical = abs(db - dc) < 0.25 and abs(margin_global) < ARM_C_MARGIN

    return {
        "run_seed": run_seed,
        "mode": mode,
        "variant": "v2_bounded_tanh" if bounded else "v1_unbounded",
        "exploded": False,
        "delta_s_b": round(db, 6),
        "delta_s_c": round(dc, 6),
        "anti_true_b": arm_b["anti_true"],
        "anti_true_c": arm_c["anti_true"],
        "margin_true": round(margin_true, 6),
        "anti_global_b": arm_b["anti_global"],
        "anti_global_c": arm_c["anti_global"],
        "margin_global": round(margin_global, 6),
        "delta_s_ok": delta_ok,
        "arm_c_break_relational": c_break,
        "global_looks_identical": global_identical,
        "pass_relational": bool(delta_ok and c_break),
        "fail_reason": (
            None
            if (delta_ok and c_break)
            else ("NO_ARM_C_BREAK" if not c_break else "DELTA_S_FLOOR")
        ),
        "arm_b": arm_b,
        "arm_c": arm_c,
    }
