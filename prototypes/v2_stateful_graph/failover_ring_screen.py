#!/usr/bin/env python3
"""
Failover-ring screen — sparse ring reforms after one agent dies (SCREEN only)

Sandbox: prototypes/v2_stateful_graph/

Frage (nicht vorhersehbar): Wenn ein Agent im sparse Ring ausfällt und der
Ring sich unter den Überlebenden neu formiert — erholt sich die relationale
Trennung (STRUCTURE_RECOVERS) oder bricht sie dauerhaft
(STRUCTURE_BREAKS_PERMANENT)?

Hypothese: offen — ⟨k⟩=1 ist kritisch; Reform könnte reichen oder nicht.

Freeze:
  |Q|=4 · N=9 · sparse Ring · Warmup=32 · Pre-measure=40 · Post-measure=80
  Seeds: 20271101–06
  Failover: ein Agent (seed-bestimmt) fällt aus · Ring = Cycle auf Survivors
  Gate (pre & post): ΔQ≥0.5 ∧ H≥2.0 ∧ Margin>0.1
  ≥4/6 seeds mit post-Pass → STRUCTURE_RECOVERS
  ≥4/6 seeds mit pre-Pass ∧ post-Fail → STRUCTURE_BREAKS_PERMANENT

Usage:
  python3 prototypes/v2_stateful_graph/failover_ring_screen.py
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
from typing import Any, Dict, List, Optional, Set, Tuple

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import stateful_graph_study as sg  # noqa: E402

Q_SIZE = 4
N_AGENTS = 9
SEEDS = [20271101, 20271102, 20271103, 20271104, 20271105, 20271106]
WARMUP = 32
PRE_MEASURE = 40
POST_MEASURE = 80
DELTA_Q_FLOOR = 0.5
EPS_H = 2.0
MARGIN_SCREEN = 0.1
PASSES_NEEDED = 4
RECOVERY_WINDOW = 16


def _crc_u01(material: str) -> float:
    return (zlib.crc32(material.encode()) & 0xFFFFFFFF) / 0xFFFFFFFF


def _ring(agent_ids: List[str]) -> Dict[str, str]:
    n = len(agent_ids)
    return {agent_ids[i]: agent_ids[(i + 1) % n] for i in range(n)}


def _derange(run_seed: int, agent_ids: List[str], tag: str) -> Dict[str, str]:
    order = sorted(
        agent_ids, key=lambda a: _crc_u01(f"{run_seed}|{tag}|{a}")
    )
    n = len(order)
    return {order[i]: order[(i + 1) % n] for i in range(n)}


def _pick_victim(run_seed: int, agent_ids: List[str]) -> str:
    # Avoid killing "first" only — crc among all
    order = sorted(
        agent_ids, key=lambda a: _crc_u01(f"{run_seed}|victim|{a}")
    )
    return order[0]


def _phase_metrics(
    series: Dict[str, List[int]],
    edge_pairs: Counter,
    anti_hits: int,
    anti_tot: int,
    alive: List[str],
) -> Dict[str, Any]:
    n_states = sg.N_STATES
    L = min((len(series[a]) for a in alive if a in series), default=0)
    if L < 2:
        delta_q = 0.0
    else:
        dists = []
        for i, a in enumerate(alive):
            for b in alive[i + 1 :]:
                if a not in series or b not in series:
                    continue
                la = len(series[a])
                lb = len(series[b])
                m = min(la, lb, L)
                if m < 1:
                    continue
                d = sum(abs(series[a][t] - series[b][t]) for t in range(m)) / float(
                    m
                )
                dists.append(d)
        delta_q = sum(dists) / len(dists) if dists else 0.0
    h = sg._shannon_bits(edge_pairs)
    anti = anti_hits / anti_tot if anti_tot else 0.0
    return {
        "delta_q": round(delta_q, 6),
        "h_edge": round(h, 6),
        "anti_frac": round(anti, 6),
        "n_obs": anti_tot,
        "series_len": L,
    }


def _run_arm_failover(
    *,
    run_seed: int,
    arm: str,
    agent_ids: List[str],
    victim: str,
) -> Dict[str, Any]:
    """Sparse ring with mid-run kill + ring reform among survivors."""
    n_states = sg.N_STATES
    alive: List[str] = list(agent_ids)
    true_p = _ring(alive)
    pi_p = _derange(run_seed, alive, "pi_pre")

    q = {
        a: int(_crc_u01(f"{run_seed}|{a}|q0") * n_states) % n_states
        for a in alive
    }
    n_ev = {a: 0 for a in alive}
    k_ev = {a: 0 for a in alive}

    # Phase buffers
    series_pre: Dict[str, List[int]] = {a: [] for a in alive}
    series_post: Dict[str, List[int]] = {a: [] for a in alive}
    edge_pre: Counter = Counter()
    edge_post: Counter = Counter()
    anti_pre_h = anti_pre_t = 0
    anti_post_h = anti_post_t = 0

    failed = False
    failover_sim_t: Optional[float] = None
    recovery_event: Optional[int] = None
    post_hits_roll: List[int] = []
    post_measure_events = 0

    heap: List[Tuple[float, int, str]] = []
    seq = 0

    def push(t: float, aid: str) -> None:
        nonlocal seq
        seq += 1
        heapq.heappush(heap, (t, seq, aid))

    for a in alive:
        push(0.01 + _crc_u01(f"{run_seed}|{a}|t0") * 0.2, a)

    def signal_partner_of(aid: str) -> Optional[str]:
        if arm == "A":
            return None
        if arm == "B":
            return true_p[aid]
        return pi_p[aid]

    def maybe_failover(t: float) -> None:
        nonlocal failed, alive, true_p, pi_p, failover_sim_t, series_post
        nonlocal edge_post, anti_post_h, anti_post_t
        if failed:
            return
        # Trigger when every still-alive agent finished warmup+pre
        if min(n_ev[a] for a in alive) < WARMUP + PRE_MEASURE:
            return
        failed = True
        failover_sim_t = t
        alive = [a for a in alive if a != victim]
        true_p = _ring(alive)
        pi_p = _derange(run_seed, alive, "pi_post")
        series_post = {a: [] for a in alive}
        edge_post = Counter()
        anti_post_h = 0
        anti_post_t = 0
        # Re-seed survivors into the event heap for the post window
        for a in alive:
            push(t + 0.01 + _crc_u01(f"{run_seed}|{a}|post0") * 0.05, a)
    while heap:
        t, _s, aid = heapq.heappop(heap)
        if failed and aid == victim:
            continue
        if aid not in n_ev:
            continue
        if failed and min(n_ev[a] for a in alive) >= (
            WARMUP + PRE_MEASURE + POST_MEASURE
        ):
            break

        k = k_ev[aid]
        sp = signal_partner_of(aid)
        if sp is None:
            sigma = sg._private_sigma(run_seed, aid, k)
        else:
            if sp not in q or (failed and sp == victim):
                # should not happen after reform
                continue
            sigma = q[sp]

        q[aid] = sg._transition(q[aid], sigma)
        n_ev[aid] += 1
        k_ev[aid] += 1

        in_pre = (not failed) and n_ev[aid] > WARMUP
        in_post = failed and n_ev[aid] > WARMUP + PRE_MEASURE

        if in_pre and aid in series_pre:
            true_id = true_p[aid]
            if true_id in q:
                series_pre[aid].append(q[aid])
                edge_pre[(q[aid], q[true_id])] += 1
                anti_pre_t += 1
                hit = int(
                    q[aid] == (q[true_id] + 1) % n_states
                    or q[aid] == (q[true_id] + 2) % n_states
                )
                anti_pre_h += hit

        if in_post and aid in series_post:
            true_id = true_p[aid]
            if true_id in q:
                series_post[aid].append(q[aid])
                edge_post[(q[aid], q[true_id])] += 1
                anti_post_t += 1
                hit = int(
                    q[aid] == (q[true_id] + 1) % n_states
                    or q[aid] == (q[true_id] + 2) % n_states
                )
                anti_post_h += hit
                if arm == "B":
                    post_measure_events += 1
                    post_hits_roll.append(hit)
                    if (
                        recovery_event is None
                        and len(post_hits_roll) >= RECOVERY_WINDOW
                    ):
                        window = post_hits_roll[-RECOVERY_WINDOW:]
                        if sum(window) / RECOVERY_WINDOW >= 0.25:
                            recovery_event = post_measure_events

        maybe_failover(t)

        if failed:
            if aid in alive and n_ev[aid] < (
                WARMUP + PRE_MEASURE + POST_MEASURE
            ):
                push(t + sg._base_gap(run_seed, aid, k_ev[aid]), aid)
        else:
            if n_ev[aid] < WARMUP + PRE_MEASURE:
                push(t + sg._base_gap(run_seed, aid, k_ev[aid]), aid)

    pre = _phase_metrics(
        series_pre, edge_pre, anti_pre_h, anti_pre_t, list(series_pre.keys())
    )
    post_alive = [a for a in alive if a != victim]
    post = _phase_metrics(
        series_post, edge_post, anti_post_h, anti_post_t, post_alive
    )
    return {
        "arm": arm,
        "victim": victim,
        "n_survivors": len(post_alive),
        "failover_sim_t": failover_sim_t,
        "pre": pre,
        "post": post,
        "recovery_onset_proxy": recovery_event,
        "anti_pre": pre["anti_frac"],
        "anti_post": post["anti_frac"],
    }


def run_cell(*, run_seed: int) -> Dict[str, Any]:
    if run_seed <= 20270199:
        return {"run_seed": run_seed, "contamination": True, "pass": False}

    agent_ids = [f"G{i:02d}" for i in range(1, N_AGENTS + 1)]
    victim = _pick_victim(run_seed, agent_ids)

    arm_b = _run_arm_failover(
        run_seed=run_seed, arm="B", agent_ids=agent_ids, victim=victim
    )
    arm_c = _run_arm_failover(
        run_seed=run_seed, arm="C", agent_ids=agent_ids, victim=victim
    )

    margin_pre = arm_b["anti_pre"] - arm_c["anti_pre"]
    margin_post = arm_b["anti_post"] - arm_c["anti_post"]
    pre_ok = bool(
        arm_b["pre"]["delta_q"] >= DELTA_Q_FLOOR
        and arm_b["pre"]["h_edge"] >= EPS_H
        and margin_pre > MARGIN_SCREEN
    )
    post_ok = bool(
        arm_b["post"]["delta_q"] >= DELTA_Q_FLOOR
        and arm_b["post"]["h_edge"] >= EPS_H
        and margin_post > MARGIN_SCREEN
    )

    if pre_ok and post_ok:
        outcome = "RECOVERS"
    elif pre_ok and not post_ok:
        outcome = "BREAKS_PERMANENT"
    elif not pre_ok:
        outcome = "PRE_FAIL"
    else:
        outcome = "INCONCLUSIVE"

    return {
        "run_seed": run_seed,
        "victim": victim,
        "n_survivors": arm_b["n_survivors"],
        "margin_pre": round(margin_pre, 6),
        "margin_post": round(margin_post, 6),
        "delta_q_pre": arm_b["pre"]["delta_q"],
        "delta_q_post": arm_b["post"]["delta_q"],
        "h_pre": arm_b["pre"]["h_edge"],
        "h_post": arm_b["post"]["h_edge"],
        "pre_ok": pre_ok,
        "post_ok": post_ok,
        "outcome": outcome,
        "recovery_onset_proxy": arm_b["recovery_onset_proxy"],
        "failover_sim_t": arm_b["failover_sim_t"],
    }


def run_failover_ring_screen() -> Dict[str, Any]:
    t0 = time.perf_counter()
    sg.N_STATES = Q_SIZE
    sg.H_MAX = math.log2(float(Q_SIZE * Q_SIZE))

    print("Failover-ring screen (|Q|=4 · kill-1 · reform survivors)")
    print("=" * 96)
    print(
        f"Pre/Post gate: ΔQ≥{DELTA_Q_FLOOR} ∧ H≥{EPS_H} ∧ Margin>{MARGIN_SCREEN}  "
        f"Seeds={SEEDS}"
    )
    print("-" * 96)
    print(
        f"{'Seed':<12} {'Victim':<8} {'m_pre':<8} {'m_post':<8} "
        f"{'pre':<6} {'post':<6} {'Outcome'}"
    )

    cells: List[Dict[str, Any]] = []
    for seed in SEEDS:
        cell = run_cell(run_seed=seed)
        cells.append(cell)
        print(
            f"{seed:<12} {cell['victim']:<8} "
            f"{cell['margin_pre']:<8.3f} {cell['margin_post']:<8.3f} "
            f"{'Y' if cell['pre_ok'] else 'N':<6} "
            f"{'Y' if cell['post_ok'] else 'N':<6} "
            f"{cell['outcome']}"
        )

    n_rec = sum(1 for c in cells if c["outcome"] == "RECOVERS")
    n_brk = sum(1 for c in cells if c["outcome"] == "BREAKS_PERMANENT")
    n_prefail = sum(1 for c in cells if c["outcome"] == "PRE_FAIL")
    avg_pre = sum(c["margin_pre"] for c in cells) / len(cells)
    avg_post = sum(c["margin_post"] for c in cells) / len(cells)
    onsets = [
        c["recovery_onset_proxy"]
        for c in cells
        if c["recovery_onset_proxy"] is not None
    ]
    avg_onset = sum(onsets) / len(onsets) if onsets else None

    if n_rec >= PASSES_NEEDED:
        verdict = "STRUCTURE_RECOVERS"
    elif n_brk >= PASSES_NEEDED:
        verdict = "STRUCTURE_BREAKS_PERMANENT"
    else:
        verdict = "INCONCLUSIVE"

    # Open hyp: either recovers or breaks is a result; inconclusive is weak
    hyp = (
        "HYPOTHESIS_RESOLVED"
        if verdict in ("STRUCTURE_RECOVERS", "STRUCTURE_BREAKS_PERMANENT")
        else "HYPOTHESIS_UNRESOLVED"
    )

    elapsed = time.perf_counter() - t0
    payload = {
        "screen": "failover_ring_v0",
        "question": (
            "After one agent dies on sparse ring and survivors reform the ring, "
            "does relational margin recover or break permanently?"
        ),
        "hypothesis": "open — not predictable a priori",
        "hypothesis_result": hyp,
        "verdict": verdict,
        "counts": {
            "RECOVERS": n_rec,
            "BREAKS_PERMANENT": n_brk,
            "PRE_FAIL": n_prefail,
            "n": len(cells),
        },
        "avg_margin_pre": round(avg_pre, 6),
        "avg_margin_post": round(avg_post, 6),
        "avg_recovery_onset_proxy": (
            round(avg_onset, 3) if avg_onset is not None else None
        ),
        "freeze": {
            "Q_size": Q_SIZE,
            "N": N_AGENTS,
            "warmup": WARMUP,
            "pre_measure": PRE_MEASURE,
            "post_measure": POST_MEASURE,
            "seeds": SEEDS,
            "reform": "cycle on survivors",
        },
        "gate": {
            "delta_q": DELTA_Q_FLOOR,
            "h_edge": EPS_H,
            "margin": MARGIN_SCREEN,
        },
        "elapsed_s": round(elapsed, 3),
        "results": cells,
    }

    out = _HERE / "failover_ring_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print("-" * 96)
    print(
        f"Verdict: {verdict}  ({hyp})  "
        f"RECOVERS={n_rec}/6  BREAKS={n_brk}/6  PRE_FAIL={n_prefail}"
    )
    print(
        f"avg margin pre={avg_pre:.3f} post={avg_post:.3f}  "
        f"onset≈{avg_onset}"
    )
    print(f"elapsed={elapsed:.3f}s → {out}")
    return payload


if __name__ == "__main__":
    run_failover_ring_screen()
