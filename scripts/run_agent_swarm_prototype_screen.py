#!/usr/bin/env python3
"""9-Agent swarm prototype screen — Batterie A∧B∧C (Pass/Fail gate).

docs/AGENT_SWARM_P9_MAP_v0.md
Not a Pre-Reg. Not a hypothesis test. Architecture fitness only.
Rules: no type-pair matrix · S_ij = ℓ_ij · P_i from Gas A1…A9.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "agents_b2g" / "emergence"))

from closed_loop_capture import capture_closed_loop  # noqa: E402
from response_rij import derive_p_bank  # noqa: E402

# Distinct from coupling screening (202615xx) and sweep (202616xx)
SEEDS = (20261701, 20261702, 20261703)

# Static map — paths relative to repo root (existence check only)
ROLE_MAP = {
    1: {
        "role": "Ingestion & Invarianten",
        "artifacts": [
            "agent_x_klasse_a_1_ingestion.py",
            "api_agents/agent_1_gatekeeper.py",
            "contracts/HandwerkAnchor.sol",
        ],
    },
    2: {
        "role": "Telematic & Relay",
        "artifacts": [
            "api_agents/agent_9_telemetry.py",
            "api_agents/agent_17_supply_chain.py",
            "agents_b2g/telemetry",
        ],
    },
    3: {
        "role": "Pressure & Execution",
        "artifacts": [
            "agent_x_klasse_b_pressure_b1_ingestion.py",
            "agent_x_klasse_b_pressure_b2_analytics.py",
            "api_agents/agent_5_sync_exec.py",
        ],
    },
    4: {
        "role": "Arbitrage & Market State",
        "artifacts": [
            "agent_x_klasse_c_3_arbitrage.py",
            "agent_x_klasse_f_sentiment_whale.py",
            "out/ResourceTrader.sol",
        ],
    },
    5: {
        "role": "Analytics & Oracle Feeds",
        "artifacts": [
            "agent_x_klasse_d_2_analytics.py",
            "agent_x_klasse_d_oracle_models.py",
            "agent_x_pyth_client.py",
        ],
    },
    6: {
        "role": "Risk & Compliance Audit",
        "artifacts": [
            "agent_x_lending_b2_risk.py",
            "api_agents/agent_14_audit_compliance.py",
            "services/z3_solver",
        ],
    },
    7: {
        "role": "Strategy & Off-Chain Scout",
        "artifacts": [
            "agent_x_klasse_a_3_strategie.py",
            "agent_x_offchain_scout.py",
            "agent_x_jito_client.py",
        ],
    },
    8: {
        "role": "Liquidation & Force",
        "artifacts": [
            "agent_x_klasse_c_2_flashloans.py",
            "agent_x_lending_b3_liquidation.py",
            "agent_x_flashbots_client.py",
        ],
    },
    9: {
        "role": "Storage & State Anchor",
        "artifacts": [
            "agent_x_storage_guardian.py",
            "agent_x_orchestrator.py",
            "core/state_store.py",
            "api_agents/agent_10_blockchain_anchor.py",
        ],
    },
}


def check_static_map(root: Path) -> dict:
    """Existence check for mapped artifacts — not the dynamic battery."""
    missing = []
    present = []
    for idx, meta in ROLE_MAP.items():
        for rel in meta["artifacts"]:
            p = root / rel
            ok = p.exists()
            entry = {"P": idx, "path": rel, "exists": ok}
            (present if ok else missing).append(entry)
    return {
        "n_present": len(present),
        "n_missing": len(missing),
        "missing": missing,
        "present": present,
        "map_ok": len(missing) == 0,
    }


def check_edge_path_contract(cell: dict) -> dict:
    """Architecture contract: S=ℓ, R-formula, no type-pair (P from Gas only)."""
    formula_ok = cell.get("formula") == "R=a(1+γ)(ℓ-b)"
    s_ok = cell.get("S_ij") == "avg_latency"
    p_assign = cell.get("P_assignment") or {}
    indices = sorted({int(v["P_index"]) for v in p_assign.values()}) if p_assign else []
    # All P_1…P_9 appear (27 agents → each index used thrice)
    p_ok = indices == list(range(1, 10))
    return {
        "formula_ok": formula_ok,
        "S_is_ell": s_ok,
        "P_indices_1_to_9": p_ok,
        "P_indices_seen": indices,
        "pass": bool(formula_ok and s_ok and p_ok),
        "note": "no type-pair matrix; P_i from Gas A1…A9 via assign_p",
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="9-agent swarm prototype screen (A∧B∧C Pass/Fail)"
    )
    ap.add_argument(
        "--full",
        action="store_true",
        help="warmup=32 cycles=512 (default is ~16s prototype: 32/256)",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_PROJECT_ROOT
        / "agents_b2g"
        / "emergence"
        / "agent_swarm_prototype_v0",
    )
    args = ap.parse_args()

    # Default tuned for ~16s wall time (3 seeds); --full ≈ closed-loop step2
    warmup = 32
    cycles = 512 if args.full else 256
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("AGENT_SWARM prototype screen (A∧B∧C · Pass/Fail · no Pre-Reg)")
    print(f"map=docs/AGENT_SWARM_P9_MAP_v0.md")
    print(f"seeds={SEEDS} warmup={warmup} cycles={cycles}")
    print("=" * 60)

    bank = derive_p_bank()
    p_bank = {i: bank[i].as_dict() for i in range(1, 10)}
    static = check_static_map(_PROJECT_ROOT)
    print(
        f"\nStatic map: present={static['n_present']} "
        f"missing={static['n_missing']} → "
        f"{'OK' if static['map_ok'] else 'GAPS'}"
    )
    for m in static["missing"][:12]:
        print(f"  MISSING P{m['P']}: {m['path']}")

    per_seed = []
    t0 = time.monotonic()
    for seed in SEEDS:
        print(f"\n=== seed {seed} ===", flush=True)
        t1 = time.monotonic()
        cell = capture_closed_loop(
            cycles=cycles, warmup_ticks=warmup, run_seed=seed,
        )
        edge = check_edge_path_contract(cell)
        cell["elapsed_s"] = round(time.monotonic() - t1, 2)
        cell["edge_path_contract"] = edge
        per_seed.append(cell)
        a, b, c = cell["layer_a"], cell["layer_b"], cell["layer_c"]
        print(
            f"  A={a['pass']} ρ={a.get('median_abs_rho')} · "
            f"B={b['pass']} mae_n={b.get('mae_norm')} · "
            f"C={c.get('pass')} |ΔΔR|={c.get('mean_abs_diff')}"
        )
        print(
            f"  edge_path={edge['pass']} · φ_L ρ={cell.get('phi_L_ell_median_abs_rho')} · "
            f"{cell['verdict']['label']} ({cell['elapsed_s']}s)"
        )

    elapsed = time.monotonic() - t0
    a_ok = sum(1 for c in per_seed if c["layer_a"]["pass"]) >= 2
    b_ok = sum(1 for c in per_seed if c["layer_b"]["pass"]) >= 2
    c_ok = sum(1 for c in per_seed if c["layer_c"].get("pass")) >= 2
    edge_ok = all(c["edge_path_contract"]["pass"] for c in per_seed)
    battery_pass = bool(a_ok and b_ok and c_ok and edge_ok)
    # Static gaps warn but do not fail dynamic battery (map may use optional paths)
    label = "ARCHITECTURE_FIT" if battery_pass else "ARCHITECTURE_UNFIT"
    if not static["map_ok"]:
        label = label + "_MAP_GAPS"

    tag = "FULL" if args.full else "PROTO"
    payload = {
        "schema": "agent_swarm_prototype_screen_v0",
        "map_doc": "docs/AGENT_SWARM_P9_MAP_v0.md",
        "not_a_pre_reg": True,
        "not_a_hypothesis_test": True,
        "rules": {
            "no_type_pair_matrix": True,
            "S_ij": "avg_latency",
            "P_source": "Gas A1…A9 → derive_p_bank",
        },
        "P_bank": p_bank,
        "ROLE_MAP": ROLE_MAP,
        "static_map_check": static,
        "params": {"seeds": list(SEEDS), "warmup": warmup, "cycles": cycles},
        "elapsed_s": round(elapsed, 1),
        "per_seed": [
            {
                "run_seed": c["run_seed"],
                "layer_a": c["layer_a"],
                "layer_b": c["layer_b"],
                "layer_c": {
                    k: c["layer_c"].get(k)
                    for k in ("pass", "mean_abs_diff", "S1", "S2", "n_agents")
                },
                "edge_path_contract": c["edge_path_contract"],
                "phi_L_ell_median_abs_rho": c.get("phi_L_ell_median_abs_rho"),
                "verdict_label": c["verdict"]["label"],
                "elapsed_s": c["elapsed_s"],
            }
            for c in per_seed
        ],
        "majority": {
            "A_pass_seeds": sum(1 for c in per_seed if c["layer_a"]["pass"]),
            "B_pass_seeds": sum(1 for c in per_seed if c["layer_b"]["pass"]),
            "C_pass_seeds": sum(
                1 for c in per_seed if c["layer_c"].get("pass")
            ),
            "edge_path_all": edge_ok,
            "battery_pass": battery_pass,
            "label": label,
        },
    }
    jp = out_dir / f"AGENT_SWARM_PROTO_{tag}.json"
    jp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    md = out_dir / f"AGENT_SWARM_PROTO_{tag}_ERGEBNIS.md"
    lines = [
        f"# Agent-Swarm Prototyp-Screen ({tag})",
        "",
        "**Map:** `docs/AGENT_SWARM_P9_MAP_v0.md` · **keine** Pre-Reg",
        f"**Verdict:** `{label}` · Batterie A∧B∧C+edge: "
        f"**{'PASS' if battery_pass else 'FAIL'}** · {elapsed:.1f}s",
        f"**Static map:** present={static['n_present']} missing={static['n_missing']}",
        "",
        "| Seed | A | ρ | B | mae_n | C | |ΔΔR| | edge | Label |",
        "|-----:|:-:|--:|:-:|------:|:-:|-------:|:----:|:------|",
    ]
    for c in per_seed:
        a, b, cc = c["layer_a"], c["layer_b"], c["layer_c"]
        lines.append(
            f"| {c['run_seed']} | {'✓' if a['pass'] else '✗'} | "
            f"{a.get('median_abs_rho')} | {'✓' if b['pass'] else '✗'} | "
            f"{b.get('mae_norm')} | {'✓' if cc.get('pass') else '✗'} | "
            f"{cc.get('mean_abs_diff')} | "
            f"{'✓' if c['edge_path_contract']['pass'] else '✗'} | "
            f"`{c['verdict']['label']}` |"
        )
    lines += [
        "",
        "## Regeln",
        "",
        "- Keine Typ-Paar-Matrix · S_ij = avg_latency · P_i aus Gas A1…A9",
        "- PASS → Architektur für Experimente geeignet",
        "- FAIL → Quelle / Reaktion / Kanten-Pfad anpassen",
        "",
    ]
    md.write_text("\n".join(lines), encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"VERDICT: {label} · battery={'PASS' if battery_pass else 'FAIL'}")
    print(f"elapsed: {elapsed:.1f}s → {md}")
    print("=" * 60)
    return 0 if battery_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
