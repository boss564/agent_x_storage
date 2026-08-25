#!/usr/bin/env python3
"""R_ij Screen v0 — Layers A/B/C (NOT a Pre-Reg).

docs/R_IJ_SCREEN_v0_DRAFT.md
--formula threshold_gamma_v01 | sensitivity_gamma_v02
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

from r_ij_capture import capture_r_ij  # noqa: E402
from response_rij import FORMULA_V01, FORMULA_V02, FORMULA_VERSION  # noqa: E402

SEEDS = (20261401, 20261402, 20261403)


def run_one(formula: str, warmup: int, cycles: int, out_dir: Path, fast: bool) -> dict:
    print("=" * 60)
    print("R_IJ_SCREEN_v0 (DRAFT · kein Pre-Reg · kein κ)")
    print(f"formula={formula} seeds={SEEDS} warmup={warmup} cycles={cycles}")
    print("=" * 60)

    t0 = time.monotonic()
    per_seed = []
    for seed in SEEDS:
        print(f"\n=== seed {seed} ===", flush=True)
        t1 = time.monotonic()
        cell = capture_r_ij(
            cycles=cycles, warmup_ticks=warmup, run_seed=seed, formula=formula,
        )
        cell["elapsed_s"] = round(time.monotonic() - t1, 2)
        per_seed.append(cell)
        v = cell["verdict"]["label"]
        a, b, c = cell["layer_a"], cell["layer_b"], cell["layer_c"]
        print(
            f"  A={a['pass']} mae_n={a['mae_norm']} ρ={a['median_abs_rho']}"
        )
        print(f"  B={b['pass']} mean_ΔR={b['mean_delta_r']}")
        print(
            f"  C={c['pass']} |ΔR(S1)−ΔR(S2)|={c['mean_abs_diff']} "
            f"S1={c.get('S1')} S2={c.get('S2')} → {v} ({cell['elapsed_s']}s)"
        )

    labels = [c["verdict"]["label"] for c in per_seed]
    cnt = Counter(labels)
    majority_label = cnt.most_common(1)[0][0]
    a_maj = sum(1 for x in per_seed if x["layer_a"]["pass"]) >= 2
    b_maj = sum(1 for x in per_seed if x["layer_b"]["pass"]) >= 2
    c_maj = sum(1 for x in per_seed if x["layer_c"]["pass"]) >= 2
    pre_reg_ok = a_maj and b_maj and c_maj

    elapsed = time.monotonic() - t0
    tag = "FAST" if fast else "FULL"
    payload = {
        "schema": "r_ij_screen_v0",
        "formula": formula,
        "draft": "docs/R_IJ_SCREEN_v0_DRAFT.md",
        "not_a_pre_reg": True,
        "no_kappa_sweep": True,
        "harking_guard": (
            "Sealed kopplung_* locked. Pre-Reg only if RESPONSE_HETEROGENEOUS "
            "(A∧B∧C)."
        ),
        "params": {
            "seeds": list(SEEDS),
            "warmup": warmup,
            "cycles": cycles,
            "fast": fast,
            "ell_component": "avg_latency",
        },
        "elapsed_s": round(elapsed, 1),
        "per_seed": per_seed,
        "majority": {
            "layer_a_pass_seeds": sum(1 for x in per_seed if x["layer_a"]["pass"]),
            "layer_b_pass_seeds": sum(1 for x in per_seed if x["layer_b"]["pass"]),
            "layer_c_pass_seeds": sum(1 for x in per_seed if x["layer_c"]["pass"]),
            "label_counts": dict(cnt),
            "majority_label": majority_label,
            "pre_reg_allowed": pre_reg_ok,
        },
    }

    json_path = out_dir / f"R_IJ_SCREEN_{formula}_{tag}.json"
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    md_path = out_dir / f"R_IJ_SCREEN_{formula}_{tag}_ERGEBNIS.md"
    lines = [
        f"# R_ij Screen — `{formula}`",
        "",
        "**Protokoll:** `docs/R_IJ_SCREEN_v0_DRAFT.md` (kein Pre-Reg)",
        f"**Lauf:** {tag} · {elapsed:.0f}s · warmup={warmup} · cycles={cycles}",
        f"**JSON:** `{json_path}`",
        "",
        "## Majority",
        "",
        f"**`{majority_label}`** · Pre-Reg erlaubt: **{'JA' if pre_reg_ok else 'NEIN'}**",
        f"A {payload['majority']['layer_a_pass_seeds']}/3 · "
        f"B {payload['majority']['layer_b_pass_seeds']}/3 · "
        f"C {payload['majority']['layer_c_pass_seeds']}/3",
        "",
        "| Seed | A | B | mean ΔR | C | |ΔΔR| | Label |",
        "|-----:|:-:|:-:|--------:|:-:|------:|:------|",
    ]
    for x in per_seed:
        a, b, c = x["layer_a"], x["layer_b"], x["layer_c"]
        lines.append(
            f"| {x['run_seed']} | {'✓' if a['pass'] else '✗'} | "
            f"{'✓' if b['pass'] else '✗'} | {b['mean_delta_r']} | "
            f"{'✓' if c['pass'] else '✗'} | {c['mean_abs_diff']} | "
            f"`{x['verdict']['label']}` |"
        )
    lines += [
        "",
        "## Lesart",
        "",
        "- `OFFSET_ONLY`: A∧B, C fail — konstanter Kantenversatz (v0.1).",
        "- `RESPONSE_HETEROGENEOUS`: A∧B∧C — Empfindlichkeit (v0.2-Kandidat).",
        "- Pre-Reg nur bei A∧B∧C.",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print("\n" + "=" * 60)
    print(f"MAJORITY: {majority_label} · pre_reg={pre_reg_ok}")
    print(f"wrote: {md_path}")
    print("=" * 60)
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    ap.add_argument(
        "--formula",
        choices=(FORMULA_V01, FORMULA_V02, "both"),
        default="both",
        help="default: both (v0.1 then v0.2)",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_PROJECT_ROOT / "agents_b2g" / "emergence" / "r_ij_screen_v0",
    )
    args = ap.parse_args()

    warmup = 8 if args.fast else 32
    cycles = 64 if args.fast else 512
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    formulas = (
        [FORMULA_V01, FORMULA_V02]
        if args.formula == "both"
        else [args.formula]
    )
    results = {}
    for fml in formulas:
        results[fml] = run_one(fml, warmup, cycles, out_dir, args.fast)

    if len(results) > 1:
        cmp_path = out_dir / (
            "R_IJ_SCREEN_COMPARE_FAST.json" if args.fast else "R_IJ_SCREEN_COMPARE.json"
        )
        summary = {
            f: {
                "majority_label": results[f]["majority"]["majority_label"],
                "pre_reg_allowed": results[f]["majority"]["pre_reg_allowed"],
                "A": results[f]["majority"]["layer_a_pass_seeds"],
                "B": results[f]["majority"]["layer_b_pass_seeds"],
                "C": results[f]["majority"]["layer_c_pass_seeds"],
            }
            for f in results
        }
        cmp_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print("\nCOMPARE:", json.dumps(summary, indent=2))
        print(f"wrote: {cmp_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
