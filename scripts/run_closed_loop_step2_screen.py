#!/usr/bin/env python3
"""Schritt-2 screen: closed-loop φ_L + R A∧B∧C (BAU_FREIGEGEBEN).

docs/CLOSED_LOOP_RESPONSE_v0_DRAFT.md
No κ-sweep. Freeze F1–F3 documented in artifacts.
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

SEEDS = (20261501, 20261502, 20261503)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_PROJECT_ROOT / "agents_b2g" / "emergence" / "closed_loop_v0",
    )
    args = ap.parse_args()
    warmup = 8 if args.fast else 32
    cycles = 64 if args.fast else 512
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("CLOSED_LOOP Step-2 screen (A∧B∧C · φ_L · BAU_FREIGEGEBEN)")
    print(f"seeds={SEEDS} warmup={warmup} cycles={cycles}")
    print("=" * 60)

    per_seed = []
    t0 = time.monotonic()
    for seed in SEEDS:
        print(f"\n=== seed {seed} ===", flush=True)
        t1 = time.monotonic()
        cell = capture_closed_loop(
            cycles=cycles, warmup_ticks=warmup, run_seed=seed,
        )
        cell["elapsed_s"] = round(time.monotonic() - t1, 2)
        per_seed.append(cell)
        v = cell["verdict"]
        print(
            f"  A={cell['layer_a']['pass']} ρ={cell['layer_a'].get('median_abs_rho')} · "
            f"B={cell['layer_b']['pass']} mae_n={cell['layer_b'].get('mae_norm')} · "
            f"C={cell['layer_c'].get('pass')} |ΔΔR|={cell['layer_c'].get('mean_abs_diff')}"
        )
        print(
            f"  η={cell['freeze']['F1_eta']:.4f} · "
            f"φ_L ρ={cell.get('phi_L_ell_median_abs_rho')} · "
            f"→ {v['label']} ({cell['elapsed_s']}s)"
        )

    elapsed = time.monotonic() - t0
    labels = [c["verdict"]["label"] for c in per_seed]
    maj = Counter(labels).most_common(1)[0][0]
    a_ok = sum(1 for c in per_seed if c["layer_a"]["pass"]) >= 2
    b_ok = sum(1 for c in per_seed if c["layer_b"]["pass"]) >= 2
    c_ok = sum(1 for c in per_seed if c["layer_c"].get("pass")) >= 2
    pre_reg = a_ok and b_ok and c_ok

    tag = "FAST" if args.fast else "FULL"
    payload = {
        "schema": "closed_loop_step2_v0",
        "draft": "docs/CLOSED_LOOP_RESPONSE_v0_DRAFT.md",
        "status": "BAU_FREIGEGEBEN",
        "not_a_pre_reg": True,
        "no_kappa_sweep": True,
        "params": {
            "seeds": list(SEEDS),
            "warmup": warmup,
            "cycles": cycles,
        },
        "elapsed_s": round(elapsed, 1),
        "per_seed": per_seed,
        "majority": {
            "label": maj,
            "A_pass_seeds": sum(1 for c in per_seed if c["layer_a"]["pass"]),
            "B_pass_seeds": sum(1 for c in per_seed if c["layer_b"]["pass"]),
            "C_pass_seeds": sum(
                1 for c in per_seed if c["layer_c"].get("pass")
            ),
            "pre_reg_allowed": pre_reg,
            "step2_label": (
                "RESPONSE_HETEROGENEOUS" if pre_reg else maj
            ),
        },
    }
    jp = out_dir / f"CLOSED_LOOP_STEP2_{tag}.json"
    jp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    mp = out_dir / f"CLOSED_LOOP_STEP2_{tag}_ERGEBNIS.md"
    lines = [
        f"# Closed-Loop Schritt 2 ({tag})",
        "",
        "**Protokoll:** `docs/CLOSED_LOOP_RESPONSE_v0_DRAFT.md` (BAU_FREIGEGEBEN)",
        f"**Majority:** `{payload['majority']['step2_label']}` · "
        f"Pre-Reg erlaubt: **{'JA' if pre_reg else 'NEIN'}** · {elapsed:.0f}s",
        "",
        r"| Seed | A | ρ | B | mae_n | C | |ΔΔR| | η | Label |",
        "|-----:|:-:|--:|:-:|------:|:-:|-------:|--:|:------|",
    ]
    for c in per_seed:
        a, b, cc, v = c["layer_a"], c["layer_b"], c["layer_c"], c["verdict"]
        lines.append(
            f"| {c['run_seed']} | {'✓' if a['pass'] else '✗'} | "
            f"{a.get('median_abs_rho')} | {'✓' if b['pass'] else '✗'} | "
            f"{b.get('mae_norm')} | {'✓' if cc.get('pass') else '✗'} | "
            f"{cc.get('mean_abs_diff')} | {c['freeze']['F1_eta']:.4f} | "
            f"`{v['label']}` |"
        )
    lines += [
        "",
        "## Freeze (Bau-Default)",
        "",
        "- F1 η: pro Seed im JSON `freeze.F1_eta`",
        "- F2 ℓ: nur LedgerBook.update",
        "- F3 B: MAE unter Partnerpermutation",
        "",
        "Vor Pre-Reg §2.2 schließen. Kein κ-Sweep.",
        "",
    ]
    mp.write_text("\n".join(lines), encoding="utf-8")
    print("\n" + "=" * 60)
    print(f"STEP2: {payload['majority']['step2_label']} · pre_reg={pre_reg}")
    print(f"wrote: {mp}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
