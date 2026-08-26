#!/usr/bin/env python3
"""
completion_proof Screen — State-Transition Verifiability (SCREEN only)

Strang: Arbeitsnachweis als *completion_proof* (kein kryptographisches PoW).
Sandbox: prototypes/v2_stateful_graph/

Frage: Bleibt STRUCTURE_RELATIONAL bei |Q|=4, wenn q→q' nur nach
deterministisch verifizierbarem Receipt (Mock-Z3 / Mock-BHO) greift?

Hypothese: Margin > 0.1 bleibt stabil, wenn der Nachweis deterministisch
und verifizierbar ist (auch unter Bremsung / Verlustanteil).

Freeze (Screen):
  |Q|=4 · BINDEND-Mechanik (Warmup=32 · Measure=80 · H Paare · F10)
  Seeds: 20270601–06
  Gate: ΔQ≥0.5 ∧ H≥2.0 ∧ Margin>0.1  (≥4/6 → STRUCTURE_RELATIONAL)

Arme:
  baseline — unveränderte Studie
  always   — Receipt immer ok (Verifikation ohne Verlust)
  lossy    — ~25% Übergänge gebremst (crc%4==0 → kein Wechsel)

Usage:
  python3 prototypes/v2_stateful_graph/completion_proof_screen.py
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
SEEDS = [20270601, 20270602, 20270603, 20270604, 20270605, 20270606]
DELTA_Q_FLOOR = 0.5
EPS_H = 2.0
MARGIN_SCREEN = 0.1
PASSES_NEEDED = 4
MODES = ("baseline", "always", "lossy")


def _crc_u01(material: str) -> float:
    return (zlib.crc32(material.encode()) & 0xFFFFFFFF) / 0xFFFFFFFF


def completion_receipt(
    *,
    run_seed: int,
    aid: str,
    k: int,
    q: int,
    sigma: int,
    mode: str,
) -> Dict[str, Any]:
    """Deterministic mock of Z3-SAT / BHO Δ=0 gate — not crypto PoW.

    always: receipt always ok (verifiable, zero brake).
    lossy:  brake when crc ≡ 0 (mod 4) ≈ 25% skip.
    """
    material = f"{run_seed}|{aid}|k{k}|q{q}|σ{sigma}|completion"
    digest = zlib.crc32(material.encode()) & 0xFFFFFFFF
    if mode == "always":
        ok = True
        kind = "mock_z3_always"
    elif mode == "lossy":
        ok = (digest % 4) != 0
        kind = "mock_z3_lossy_25"
    else:
        raise ValueError(mode)
    # Mock BHO twin: zero-sum tag derived from same digest (audit trail only)
    bho_delta = 0.0 if ok else 0.01
    return {
        "ok": ok,
        "kind": kind,
        "digest": f"{digest:08x}",
        "bho_delta": bho_delta,
    }


def _run_arm_gated(
    *,
    run_seed: int,
    arm: str,
    agent_ids: List[str],
    true_partner: Dict[str, str],
    signal_partner: Optional[Dict[str, str]],
    mode: str,
) -> Dict[str, Any]:
    """BINDEND arm loop with optional completion_proof brake on transition."""
    n_states = sg.N_STATES
    q = {
        a: int(sg._crc_u01(f"{run_seed}|{a}|q0") * n_states) % n_states
        for a in agent_ids
    }
    n_ev = {a: 0 for a in agent_ids}
    k_ev = {a: 0 for a in agent_ids}
    series: Dict[str, List[int]] = {a: [] for a in agent_ids}
    edge_pairs: Counter = Counter()
    anti_hits = 0
    anti_tot = 0
    receipts_ok = 0
    receipts_brake = 0

    heap: List[Tuple[float, int, str]] = []
    seq = 0

    def push(t: float, aid: str) -> None:
        nonlocal seq
        seq += 1
        heapq.heappush(heap, (t, seq, aid))

    for a in agent_ids:
        push(0.01 + sg._crc_u01(f"{run_seed}|{a}|t0") * 0.2, a)

    while heap and min(n_ev.values()) < sg.TOTAL_EVENTS:
        t, _s, aid = heapq.heappop(heap)
        if n_ev[aid] >= sg.TOTAL_EVENTS:
            continue
        k = k_ev[aid]
        if arm == "A" or signal_partner is None:
            sigma = sg._private_sigma(run_seed, aid, k)
        else:
            sigma = q[signal_partner[aid]]

        if mode == "baseline":
            q[aid] = sg._transition(q[aid], sigma)
        else:
            rec = completion_receipt(
                run_seed=run_seed,
                aid=aid,
                k=k,
                q=q[aid],
                sigma=sigma,
                mode=mode,
            )
            if rec["ok"]:
                q[aid] = sg._transition(q[aid], sigma)
                receipts_ok += 1
            else:
                receipts_brake += 1

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
        "receipts_ok": receipts_ok,
        "receipts_brake": receipts_brake,
        "brake_rate": round(
            receipts_brake / max(receipts_ok + receipts_brake, 1), 6
        ),
    }


def run_cell(*, run_seed: int, mode: str) -> Dict[str, Any]:
    if run_seed <= 20270199:
        return {"run_seed": run_seed, "contamination": True, "pass": False}
    agent_ids = [f"G{i:02d}" for i in range(1, sg.N_AGENTS + 1)]
    true_p, pi_p = sg._build_partners(run_seed, agent_ids)

    if mode == "baseline":
        # Unmodified BINDEND path
        cell = sg.run_stateful_graph_study_cell(run_seed=run_seed)
        cell["mode"] = "baseline"
        cell["brake_rate"] = 0.0
        return cell

    arm_a = _run_arm_gated(
        run_seed=run_seed,
        arm="A",
        agent_ids=agent_ids,
        true_partner=true_p,
        signal_partner=None,
        mode=mode,
    )
    arm_b = _run_arm_gated(
        run_seed=run_seed,
        arm="B",
        agent_ids=agent_ids,
        true_partner=true_p,
        signal_partner=true_p,
        mode=mode,
    )
    arm_c = _run_arm_gated(
        run_seed=run_seed,
        arm="C",
        agent_ids=agent_ids,
        true_partner=true_p,
        signal_partner=pi_p,
        mode=mode,
    )
    margin = arm_b["anti_frac_vs_true"] - arm_c["anti_frac_vs_true"]
    triad = bool(
        arm_b["delta_q"] >= DELTA_Q_FLOOR
        and arm_b["h_edge"] >= EPS_H
        and margin > MARGIN_SCREEN
    )
    return {
        "run_seed": run_seed,
        "mode": mode,
        "contamination": False,
        "n_states": sg.N_STATES,
        "delta_q": arm_b["delta_q"],
        "h_edge": arm_b["h_edge"],
        "anti_b": arm_b["anti_frac_vs_true"],
        "anti_c": arm_c["anti_frac_vs_true"],
        "anti_margin": round(margin, 6),
        "brake_rate": arm_b["brake_rate"],
        "receipts_ok": arm_b["receipts_ok"],
        "receipts_brake": arm_b["receipts_brake"],
        "pass": triad,
        "triad": triad,
        "arm_a": arm_a,
        "arm_b": arm_b,
        "arm_c": arm_c,
    }


def _screen_pass(cell: Dict[str, Any]) -> bool:
    if cell.get("contamination"):
        return False
    return bool(
        cell["delta_q"] >= DELTA_Q_FLOOR
        and cell["h_edge"] >= EPS_H
        and cell["anti_margin"] > MARGIN_SCREEN
    )


def run_completion_proof_screen() -> Dict[str, Any]:
    t0 = time.perf_counter()
    sg.N_STATES = Q_SIZE
    sg.H_MAX = math.log2(float(Q_SIZE * Q_SIZE))
    sg.DELTA_Q_FLOOR = DELTA_Q_FLOOR
    sg.EPS_H = EPS_H
    sg.ARM_C_MARGIN = 0.15

    print("completion_proof Screen (|Q|=4 · State-Transition Verifiability)")
    print("=" * 88)
    print(
        f"Gate: ΔQ≥{DELTA_Q_FLOOR} ∧ H≥{EPS_H} ∧ Margin>{MARGIN_SCREEN}  "
        f"Seeds={SEEDS}"
    )
    print("-" * 88)

    by_mode: Dict[str, List[Dict[str, Any]]] = {m: [] for m in MODES}

    for mode in MODES:
        print(f"\n### mode={mode}")
        print(
            f"{'Seed':<12} {'ΔQ':<8} {'H':<8} {'Margin':<8} "
            f"{'brake':<8} {'PASS':<6}"
        )
        for seed in SEEDS:
            cell = run_cell(run_seed=seed, mode=mode)
            # normalize margin field for baseline
            if mode == "baseline":
                cell["anti_margin"] = cell.get("anti_margin", 0.0)
                cell["pass"] = _screen_pass(cell)
            passed = bool(cell.get("pass"))
            by_mode[mode].append(cell)
            print(
                f"{seed:<12} {cell.get('delta_q', float('nan')):<8.3f} "
                f"{cell.get('h_edge', float('nan')):<8.3f} "
                f"{cell.get('anti_margin', float('nan')):<8.3f} "
                f"{cell.get('brake_rate', 0.0):<8.3f} "
                f"{'PASS' if passed else 'FAIL':<6}"
            )

    summary = {}
    print("\n" + "=" * 88)
    print(f"{'Mode':<12} {'Passes':<10} {'Avg Margin':<12} {'Avg brake':<10} {'Verdict'}")
    print("-" * 88)
    for mode in MODES:
        rows = by_mode[mode]
        n_pass = sum(1 for c in rows if c.get("pass"))
        avg_m = sum(c["anti_margin"] for c in rows) / len(rows)
        avg_b = sum(float(c.get("brake_rate") or 0.0) for c in rows) / len(rows)
        verdict = (
            "STRUCTURE_RELATIONAL"
            if n_pass >= PASSES_NEEDED
            else "STRUCTURE_BREAKS"
        )
        summary[mode] = {
            "n_pass": n_pass,
            "n": len(rows),
            "avg_margin": round(avg_m, 6),
            "avg_brake_rate": round(avg_b, 6),
            "verdict": verdict,
        }
        print(
            f"{mode:<12} {n_pass}/6{'':<6} {avg_m:<12.3f} {avg_b:<10.3f} {verdict}"
        )

    # Hypothesis: always + lossy remain STRUCTURE_RELATIONAL
    hyp_ok = (
        summary["always"]["verdict"] == "STRUCTURE_RELATIONAL"
        and summary["lossy"]["verdict"] == "STRUCTURE_RELATIONAL"
    )
    hyp = "HYPOTHESIS_CONFIRMED" if hyp_ok else "HYPOTHESIS_FALSIFIED"

    elapsed = time.perf_counter() - t0
    payload = {
        "screen": "completion_proof_v0",
        "terminology": (
            "completion_proof — verifiable transition receipt "
            "(mock Z3/BHO); not cryptographic Proof-of-Work"
        ),
        "Q_size": Q_SIZE,
        "seeds": SEEDS,
        "gate": {
            "delta_q": DELTA_Q_FLOOR,
            "h_edge": EPS_H,
            "margin": MARGIN_SCREEN,
        },
        "hypothesis": (
            "Relational margin stays >0.1 when q→q' requires a deterministic "
            "verifiable completion_proof (always or lossy~25%)."
        ),
        "hypothesis_result": hyp,
        "summary": summary,
        "elapsed_s": round(elapsed, 3),
        "budget_ok": elapsed < 16.0,
        "results": {
            m: [
                {
                    "seed": c["run_seed"],
                    "pass": c.get("pass"),
                    "delta_q": c.get("delta_q"),
                    "h_edge": c.get("h_edge"),
                    "anti_margin": c.get("anti_margin"),
                    "brake_rate": c.get("brake_rate"),
                }
                for c in by_mode[m]
            ]
            for m in MODES
        },
    }

    out = _HERE / "completion_proof_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print("-" * 88)
    print(f"Hypothesis: {hyp}")
    print(f"elapsed={elapsed:.3f}s  budget_ok={payload['budget_ok']}")
    print(f"Results: {out}")

    # restore defaults
    sg.N_STATES = 4
    sg.H_MAX = 4.0
    return payload


if __name__ == "__main__":
    run_completion_proof_screen()
