#!/usr/bin/env python3
"""
Topology screen — STRUCTURE_RELATIONAL across communication graphs (SCREEN only)

Sandbox: prototypes/v2_stateful_graph/

Frage: Bleibt Margin B↔C > 0.1, wenn die Signal-Topologie wechselt
(vollständig / spärlich / skalenfrei Hub-Spoke), bei fixem |Q|=4?

Hypothese: Relationale Trennung bleibt stabil; Topologie ändert
Ausbreitungsgeschwindigkeit, nicht die Struktur selbst.

Freeze:
  |Q|=4 · N=9 · Warmup=32 · Measure=80 · BINDEND-Übergang
  Seeds: 20270801–06
  Gate: ΔQ≥0.5 ∧ H≥2.0 ∧ Margin>0.1  (≥4/6 → STRUCTURE_RELATIONAL)
  Metrik-Partner: immer Ring (true sticky M) — Topologie steuert nur σ-Quelle

Topologien (Signalgraph Arm B):
  complete  — jeder Tick: crc-Peer unter allen anderen (K_{9} dynamisch)
  sparse    — Ring-Nachbar (Referenz = Studie-1 true_p)
  hub       — Hub G01; Speichen ← Hub; Hub ← G02

Arm C: σ von π(Peer_B), π = Seed-Derangement der Agent-IDs.

Spread-Proxy: onset = erstes Measure-Event mit rolling anti≥0.25 (Fenster 16).

Usage:
  python3 prototypes/v2_stateful_graph/topology_screen.py
"""
from __future__ import annotations

import heapq
import json
import math
import sys
import time
import zlib
from collections import Counter, deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import stateful_graph_study as sg  # noqa: E402

Q_SIZE = 4
SEEDS = [20270801, 20270802, 20270803, 20270804, 20270805, 20270806]
TOPOLOGIES = ("complete", "sparse", "hub")
DELTA_Q_FLOOR = 0.5
EPS_H = 2.0
MARGIN_SCREEN = 0.1
PASSES_NEEDED = 4
ONSET_THRESHOLD = 0.25
ONSET_WINDOW = 16
HUB_ID = "G01"
HUB_FEED = "G02"


def _crc_u01(material: str) -> float:
    return (zlib.crc32(material.encode()) & 0xFFFFFFFF) / 0xFFFFFFFF


def _derange_ids(run_seed: int, agent_ids: List[str]) -> Dict[str, str]:
    order = sorted(agent_ids, key=lambda a: _crc_u01(f"{run_seed}|topo_pi|{a}"))
    n = len(order)
    return {order[i]: order[(i + 1) % n] for i in range(n)}


def _ring_partners(agent_ids: List[str]) -> Dict[str, str]:
    n = len(agent_ids)
    return {agent_ids[i]: agent_ids[(i + 1) % n] for i in range(n)}


def _select_peer_b(
    *,
    topology: str,
    run_seed: int,
    aid: str,
    k: int,
    agent_ids: List[str],
    ring: Dict[str, str],
) -> str:
    if topology == "sparse":
        return ring[aid]
    if topology == "hub":
        if aid == HUB_ID:
            return HUB_FEED
        return HUB_ID
    if topology == "complete":
        others = [a for a in agent_ids if a != aid]
        idx = int(_crc_u01(f"{run_seed}|{aid}|k{k}|peer") * len(others)) % len(
            others
        )
        return others[idx]
    raise ValueError(topology)


def _mean_degree(topology: str, n: int) -> float:
    if topology == "complete":
        return float(n - 1)  # potential peers per tick
    if topology == "sparse":
        return 1.0
    if topology == "hub":
        # hub degree n-1 outbound-of-spokes inbound; spokes degree 1
        return (2.0 * (n - 1)) / n
    return float("nan")


def _run_arm_topo(
    *,
    run_seed: int,
    arm: str,
    topology: str,
    agent_ids: List[str],
    true_partner: Dict[str, str],
    ring: Dict[str, str],
    pi_ids: Dict[str, str],
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
    rolling: Deque[int] = deque(maxlen=ONSET_WINDOW)
    onset_event: Optional[int] = None
    measure_idx = 0

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
        if arm == "A":
            sigma = sg._private_sigma(run_seed, aid, k)
        else:
            peer = _select_peer_b(
                topology=topology,
                run_seed=run_seed,
                aid=aid,
                k=k,
                agent_ids=agent_ids,
                ring=ring,
            )
            if arm == "C":
                peer = pi_ids[peer]
            sigma = q[peer]

        q[aid] = sg._transition(q[aid], sigma)
        n_ev[aid] += 1
        k_ev[aid] += 1

        if n_ev[aid] > sg.WARMUP_EVENTS:
            series[aid].append(q[aid])
            true_id = true_partner[aid]
            edge_pairs[(q[aid], q[true_id])] += 1
            anti_tot += 1
            hit = int(
                q[aid] == (q[true_id] + 1) % n_states
                or q[aid] == (q[true_id] + 2) % n_states
            )
            anti_hits += hit
            if arm == "B":
                rolling.append(hit)
                measure_idx += 1
                if (
                    onset_event is None
                    and len(rolling) == ONSET_WINDOW
                    and (sum(rolling) / ONSET_WINDOW) >= ONSET_THRESHOLD
                ):
                    onset_event = measure_idx

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
                    abs(series[a][t] - series[b][t]) for t in range(L)
                ) / float(L)
                dists.append(d)
        delta_q = sum(dists) / len(dists) if dists else 0.0

    return {
        "arm": arm,
        "delta_q": round(delta_q, 6),
        "h_edge": round(sg._shannon_bits(edge_pairs), 6),
        "anti_frac_vs_true": round(
            anti_hits / anti_tot if anti_tot else 0.0, 6
        ),
        "onset_event": onset_event,
        "onset_or_inf": onset_event if onset_event is not None else sg.MEASURE_EVENTS
        * sg.N_AGENTS,
    }


def run_cell(*, run_seed: int, topology: str) -> Dict[str, Any]:
    if run_seed <= 20270199:
        return {"run_seed": run_seed, "contamination": True, "pass": False}

    agent_ids = [f"G{i:02d}" for i in range(1, sg.N_AGENTS + 1)]
    ring = _ring_partners(agent_ids)
    true_p = ring  # sticky metric partner — always ring
    pi_ids = _derange_ids(run_seed, agent_ids)

    arm_a = _run_arm_topo(
        run_seed=run_seed,
        arm="A",
        topology=topology,
        agent_ids=agent_ids,
        true_partner=true_p,
        ring=ring,
        pi_ids=pi_ids,
    )
    arm_b = _run_arm_topo(
        run_seed=run_seed,
        arm="B",
        topology=topology,
        agent_ids=agent_ids,
        true_partner=true_p,
        ring=ring,
        pi_ids=pi_ids,
    )
    arm_c = _run_arm_topo(
        run_seed=run_seed,
        arm="C",
        topology=topology,
        agent_ids=agent_ids,
        true_partner=true_p,
        ring=ring,
        pi_ids=pi_ids,
    )
    margin = arm_b["anti_frac_vs_true"] - arm_c["anti_frac_vs_true"]
    triad = bool(
        arm_b["delta_q"] >= DELTA_Q_FLOOR
        and arm_b["h_edge"] >= EPS_H
        and margin > MARGIN_SCREEN
    )
    return {
        "run_seed": run_seed,
        "topology": topology,
        "contamination": False,
        "mean_degree": _mean_degree(topology, sg.N_AGENTS),
        "delta_q": arm_b["delta_q"],
        "h_edge": arm_b["h_edge"],
        "anti_b": arm_b["anti_frac_vs_true"],
        "anti_c": arm_c["anti_frac_vs_true"],
        "anti_margin": round(margin, 6),
        "onset_b": arm_b["onset_event"],
        "onset_proxy": arm_b["onset_or_inf"],
        "pass": triad,
        "arm_a_delta_q": arm_a["delta_q"],
    }


def run_topology_screen() -> Dict[str, Any]:
    t0 = time.perf_counter()
    sg.N_STATES = Q_SIZE
    sg.H_MAX = math.log2(float(Q_SIZE * Q_SIZE))
    sg.DELTA_Q_FLOOR = DELTA_Q_FLOOR
    sg.EPS_H = EPS_H

    print("Topology screen (|Q|=4 · complete / sparse / hub)")
    print("=" * 96)
    print(
        f"Gate: ΔQ≥{DELTA_Q_FLOOR} ∧ H≥{EPS_H} ∧ Margin>{MARGIN_SCREEN}  "
        f"Seeds={SEEDS}"
    )
    print("-" * 96)

    by_topo: Dict[str, List[Dict[str, Any]]] = {t: [] for t in TOPOLOGIES}

    for topology in TOPOLOGIES:
        print(f"\n### topology={topology}  ⟨k⟩≈{_mean_degree(topology, sg.N_AGENTS):.2f}")
        print(
            f"{'Seed':<12} {'ΔQ':<8} {'H':<8} {'Margin':<8} "
            f"{'onset':<8} {'PASS':<6}"
        )
        for seed in SEEDS:
            cell = run_cell(run_seed=seed, topology=topology)
            by_topo[topology].append(cell)
            onset = cell["onset_b"]
            onset_s = str(onset) if onset is not None else "—"
            print(
                f"{seed:<12} {cell['delta_q']:<8.3f} {cell['h_edge']:<8.3f} "
                f"{cell['anti_margin']:<8.3f} {onset_s:<8} "
                f"{'PASS' if cell['pass'] else 'FAIL':<6}"
            )

    print("\n" + "=" * 96)
    print(
        f"{'Topo':<12} {'Passes':<10} {'Avg Margin':<12} "
        f"{'Avg onset':<12} {'⟨k⟩':<8} {'Verdict'}"
    )
    print("-" * 96)

    summary: Dict[str, Any] = {}
    for topology in TOPOLOGIES:
        rows = by_topo[topology]
        n_pass = sum(1 for c in rows if c["pass"])
        avg_m = sum(c["anti_margin"] for c in rows) / len(rows)
        onsets = [c["onset_proxy"] for c in rows]
        avg_onset = sum(onsets) / len(onsets)
        verdict = (
            "STRUCTURE_RELATIONAL"
            if n_pass >= PASSES_NEEDED
            else "STRUCTURE_BREAKS"
        )
        summary[topology] = {
            "n_pass": n_pass,
            "n": len(rows),
            "avg_margin": round(avg_m, 6),
            "avg_onset_proxy": round(avg_onset, 3),
            "mean_degree": _mean_degree(topology, sg.N_AGENTS),
            "verdict": verdict,
        }
        print(
            f"{topology:<12} {n_pass}/6{'':<6} {avg_m:<12.3f} "
            f"{avg_onset:<12.1f} {_mean_degree(topology, sg.N_AGENTS):<8.2f} "
            f"{verdict}"
        )

    structure_ok = all(
        summary[t]["verdict"] == "STRUCTURE_RELATIONAL" for t in TOPOLOGIES
    )
    # Spread differs: onset not identical across topologies (allow ties)
    onset_vals = [summary[t]["avg_onset_proxy"] for t in TOPOLOGIES]
    spread_differs = max(onset_vals) - min(onset_vals) > 1.0
    hyp_ok = structure_ok  # primary; spread is descriptive
    hyp = "HYPOTHESIS_CONFIRMED" if hyp_ok else "HYPOTHESIS_FALSIFIED"

    elapsed = time.perf_counter() - t0
    payload = {
        "screen": "topology_v0",
        "hypothesis": (
            "STRUCTURE_RELATIONAL for complete/sparse/hub at |Q|=4; "
            "topology may change onset/spread, not relational margin gate"
        ),
        "hypothesis_result": hyp,
        "hypothesis_parts": {
            "structure_all_topologies": structure_ok,
            "spread_onset_range": round(max(onset_vals) - min(onset_vals), 3),
            "spread_differs_descriptive": spread_differs,
        },
        "Q_size": Q_SIZE,
        "seeds": SEEDS,
        "topologies": list(TOPOLOGIES),
        "gate": {
            "delta_q": DELTA_Q_FLOOR,
            "h_edge": EPS_H,
            "margin": MARGIN_SCREEN,
        },
        "note": (
            "Metric partner = ring sticky M; signal topology varies. "
            "Arm C = π(peer_B). Hub = G01 / feed G02."
        ),
        "summary": summary,
        "elapsed_s": round(elapsed, 3),
        "results": {
            t: [
                {
                    "seed": c["run_seed"],
                    "pass": c["pass"],
                    "delta_q": c["delta_q"],
                    "h_edge": c["h_edge"],
                    "anti_margin": c["anti_margin"],
                    "onset_b": c["onset_b"],
                }
                for c in by_topo[t]
            ]
            for t in TOPOLOGIES
        },
    }

    out = _HERE / "topology_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print("-" * 96)
    print(f"Hypothesis: {hyp}  (structure_all={structure_ok})")
    print(f"elapsed={elapsed:.3f}s → {out}")
    return payload


if __name__ == "__main__":
    run_topology_screen()
