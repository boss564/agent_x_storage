#!/usr/bin/env python3
"""16s screen — Continuous Dissensus Gegenprobe.

Primary gate (matched to discrete): ΔS≥0.5 ∧ Arm-C-Bruch on anti vs TRUE partner.
Secondary report: global pairwise anti (topology-blind) — often B≈C.

Seeds 20270301–03. No Pre-Reg from this screen alone.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from continuous_dissensus_proto import run_cell  # noqa: E402

SEEDS = (20270301, 20270302, 20270303)
BUDGET_S = 16.0


def main() -> int:
    print("=" * 64)
    print("CONTINUOUS-DISSENSUS Gegenprobe · ≤16s · matched protocol")
    print(f"seeds={SEEDS}")
    print("PRIMARY gate: ΔS≥0.5 ∧ anti_true B−C ≥ 0.15")
    print("SECONDARY: global anti (not a gate)")
    print("=" * 64)

    t0 = time.monotonic()
    rows_v1 = []
    rows_v2 = []

    print("--- v1 unbounded (sync) ---")
    for seed in SEEDS:
        cell = run_cell(run_seed=seed, bounded=False, mode="sync")
        rows_v1.append(cell)
        print(f"  seed={seed} DIVERGENCE={cell.get('exploded')} · FAIL")

    print("--- v2 tanh-bounded (sync) ---")
    for seed in SEEDS:
        cell = run_cell(run_seed=seed, bounded=True, mode="sync")
        rows_v2.append(cell)
        print(
            f"  seed={seed} ΔS {cell['delta_s_b']:.3f}/{cell['delta_s_c']:.3f} "
            f"anti_true {cell['anti_true_b']:.3f}/{cell['anti_true_c']:.3f} "
            f"m_true={cell['margin_true']:.3f} | "
            f"anti_g {cell['anti_global_b']:.3f}/{cell['anti_global_c']:.3f} "
            f"m_g={cell['margin_global']:.3f} · "
            f"{'PASS' if cell['pass_relational'] else 'FAIL'}"
        )

    elapsed = time.monotonic() - t0
    v1_div = all(r.get("exploded") for r in rows_v1)
    n_pass = sum(1 for r in rows_v2 if r.get("pass_relational"))
    # majority ≥2/3 for proto screen
    if elapsed > BUDGET_S:
        gate = "DISCARD_TIMEOUT"
    elif n_pass >= 2:
        gate = "PROTO_PASS"
    else:
        gate = "PROTO_FAIL"

    payload = {
        "schema": "continuous_dissensus_proto_v1",
        "sandbox": "prototypes/v3_continuous_dissensus",
        "not_a_pre_reg": True,
        "question": "Does STRUCTURE_RELATIONAL generalize to continuous |S_i-S_j|?",
        "primary_gate": "delta_S >= 0.5 AND anti_true_B - anti_true_C >= 0.15",
        "secondary_note": (
            "global pairwise anti is nearly identical on B vs C; "
            "must not replace the relational (true-partner) gate"
        ),
        "seeds": list(SEEDS),
        "elapsed_s": round(elapsed, 3),
        "budget_ok": elapsed <= BUDGET_S,
        "v1_unbounded": {"all_diverged": v1_div, "per_seed": rows_v1},
        "v2_bounded_tanh": {
            "n_pass_relational": n_pass,
            "per_seed": rows_v2,
        },
        "gate": gate,
        "interpretation": (
            "PROTO_PASS under matched true-partner protocol means continuous "
            "repulsion can still break under π(M) on anti_true — "
            "do not seal a negative from global-swarm stats alone. "
            "PROTO_FAIL would mean no relational Arm-C break under matched protocol."
        ),
        "next": (
            "if PROTO_PASS: DRAFT/Pre-Reg decision by user — not auto-opened; "
            "if PROTO_FAIL: document negative Gegenprobe, no Pre-Reg"
        ),
    }
    (HERE / "DISSENSUS_PROTO.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    (HERE / "DISSENSUS_PROTO_GATE.txt").write_text(
        f"gate={gate} elapsed={elapsed:.2f}s v1_diverge={v1_div} "
        f"v2_relational_pass={n_pass}/3\n",
        encoding="utf-8",
    )

    analysis = f"""# Continuous Dissensus Gegenprobe — Analyse

**Gate (matched protocol):** `{gate}` · {elapsed:.2f}s / 16s · relational pass {n_pass}/3

## Zwei Metrik-Ebenen

| Ebene | Definition | Rolle |
|-------|------------|-------|
| **Primary (relational)** | anti vs **true** Sticky-Partner · Margin B−C | Gate — analog diskret |
| **Secondary (global)** | Gegenzeichen über **alle** Paare | Bericht — topologie-blind |

v1 (unbounded): divergiert (alle Seeds).

v2 (tanh): Primary kann PASS oder FAIL sein; Secondary sieht oft B≈C
(anti_global ≈ 0.5, kleine Margin) — das erklärt Berichte der Form
„beide Arme identisch“, ist aber **kein** Ersatz für den relationalen Gate.

## Root Cause (präzisiert)

`S_i += α·(S_i − S_j)` ist auf der **Signal-Kante** symmetrisch. Ob daraus
**keine** relationale Struktur vs. true Partner folgt, ist empirisch:
gemessen wird anti_true, nicht anti_signal und nicht nur die globale Paarstatistik.

## Serie

- Stateful Graph v0: `STRUCTURE_RELATIONAL` (diskret) — versiegelt Sweep
- Dissens-Gegenprobe: `{gate}` unter matched protocol — siehe Gate-Datei

Kein Pre-Reg ohne User-Freigabe.
"""
    (HERE / "ANALYSIS.md").write_text(analysis, encoding="utf-8")

    print("=" * 64)
    print(f"GATE: {gate}  ({elapsed:.2f}s / {BUDGET_S}s)  relational {n_pass}/3")
    print("=" * 64)
    return 0 if gate in ("PROTO_PASS", "PROTO_FAIL") else 1


if __name__ == "__main__":
    raise SystemExit(main())
