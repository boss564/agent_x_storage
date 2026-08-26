#!/usr/bin/env python3
"""M7 filter spike: median vs upper-trim vs ewma_gate (post-ACK reciprocity).

Engineering only — no Pre-Reg.
Canonical candidate: trimmed_m7 (MAD + upper 10% trim).
Gate: ell-selective ≥2/3 seeds AND battery ≥2/3 on the candidate mode.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "agents_b2g" / "emergence"))

from closed_loop_capture import capture_closed_loop  # noqa: E402
from kanten_ledger import (  # noqa: E402
    LATENCY_MODE_EWMA,
    LATENCY_MODE_EWMA_GATE,
    LATENCY_MODE_M7,
    LATENCY_MODE_M7_TRIM,
)

SEEDS = (20261731, 20261732, 20261733)
CANDIDATE = LATENCY_MODE_M7_TRIM
MODES = (
    LATENCY_MODE_EWMA,
    LATENCY_MODE_M7,
    LATENCY_MODE_M7_TRIM,
    LATENCY_MODE_EWMA_GATE,
)


def summarize(cell: dict) -> dict:
    a, b, c = cell["layer_a"], cell["layer_b"], cell["layer_c"]
    ell = cell.get("phi_L_ell_screen") or {}
    return {
        "run_seed": cell["run_seed"],
        "latency_mode": cell.get("latency_mode"),
        "ell_rho": ell.get("median_abs_rho"),
        "ell_pass": ell.get("pass"),
        "ell_mae": ell.get("mae"),
        "A": a["pass"],
        "rho": a.get("median_abs_rho"),
        "B": b["pass"],
        "mae_n": b.get("mae_norm"),
        "C": c.get("pass"),
        "dR": c.get("mean_abs_diff"),
        "battery": bool(a["pass"] and b["pass"] and c.get("pass")),
        "latency_evaluable_edges": cell.get("latency_evaluable_edges"),
        "latency_thin_edges": cell.get("latency_thin_edges"),
        "reciprocity": cell.get("reciprocity"),
        "elapsed_s": cell.get("elapsed_s"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=256)
    ap.add_argument("--warmup", type=int, default=32)
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_PROJECT_ROOT
        / "agents_b2g"
        / "emergence"
        / "m7_filter_v0",
    )
    args = ap.parse_args()
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("M7 filter · median vs trimmed_m7 vs ewma_gate (no Pre-Reg)")
    print(f"seeds={SEEDS} candidate={CANDIDATE}")
    print("=" * 60)

    by_mode: dict = {m: [] for m in MODES}
    t0 = time.monotonic()

    for mode in MODES:
        print(f"\n--- latency_mode={mode} ---")
        for seed in SEEDS:
            print(f"  seed={seed} ...", flush=True)
            t1 = time.monotonic()
            cell = capture_closed_loop(
                cycles=args.cycles,
                warmup_ticks=args.warmup,
                run_seed=seed,
                latency_mode=mode,
            )
            cell["elapsed_s"] = round(time.monotonic() - t1, 2)
            s = summarize(cell)
            by_mode[mode].append(s)
            rec = s["reciprocity"] or {}
            print(
                f"    ell_ρ={s['ell_rho']} ell_pass={s['ell_pass']} · "
                f"A={s['A']} B={s['B']} C={s['C']} · "
                f"recip_via={rec.get('frac_sticky_via_ledger')} · "
                f"{s['elapsed_s']}s"
            )

    def maj_ell(rows):
        return sum(1 for r in rows if r["ell_pass"]) >= 2

    def maj_bat(rows):
        return sum(1 for r in rows if r["battery"]) >= 2

    elapsed = time.monotonic() - t0
    cand = by_mode[CANDIDATE]
    ell_ok = maj_ell(cand)
    bat_ok = maj_bat(cand)
    recip_fracs = [
        (r.get("reciprocity") or {}).get("frac_sticky_via_ledger")
        for r in cand
    ]
    recip_fracs = [x for x in recip_fracs if x is not None]
    recip_med = (
        sorted(recip_fracs)[len(recip_fracs) // 2] if recip_fracs else None
    )

    if ell_ok and bat_ok and recip_med is not None and recip_med >= 0.3:
        gate = "M7_PRESERVES_FIT"
    elif not ell_ok:
        gate = "M7_LOSES_ELL_SELECTIVITY"
    elif not bat_ok:
        gate = "M7_BREAKS_FIT"
    else:
        gate = "M7_INCONCLUSIVE"

    table = {}
    for mode, rows in by_mode.items():
        rhos = [r["ell_rho"] for r in rows if r["ell_rho"] is not None]
        med_rho = sorted(rhos)[len(rhos) // 2] if rhos else None
        table[mode] = {
            "ell_selective_majority": maj_ell(rows),
            "battery_majority": maj_bat(rows),
            "median_ell_rho": med_rho,
            "per_seed": rows,
        }

    payload = {
        "schema": "m7_filter_v0",
        "not_a_pre_reg": True,
        "threat_ref": "docs/THREAT_MODEL_POST_QUANTUM_v0.md §3.5",
        "candidate": CANDIDATE,
        "estimator": "MAD + upper_trim 10%",
        "params": {
            "seeds": list(SEEDS),
            "warmup": args.warmup,
            "cycles": args.cycles,
        },
        "elapsed_s": round(elapsed, 1),
        "modes": table,
        "gate": gate,
        "reciprocity_median_frac_sticky_via_ledger": recip_med,
        "note": (
            "Post-ACK traffic (b9da5efe). Median_m7 remains comparison; "
            "canonical M7 candidate is trimmed_m7."
        ),
    }
    (out_dir / "M7_FILTER.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )

    lines = [
        "# M7 Filter — Ergebnis",
        "",
        "**Charakter:** Engineering · keine Pre-Reg",
        f"**Gate:** `{gate}` · {elapsed:.1f}s",
        f"**Candidate:** `{CANDIDATE}` (MAD + upper 10% trim)",
        f"**Seeds:** `{SEEDS[0]}…{SEEDS[-1]}`",
        f"**Reziprozität (Median via_led):** {recip_med}",
        "",
        "## sticky-ℓ Selektivität + Batterie",
        "",
        "| Mode | median ell_ρ | ell-selektiv (≥2/3) | Batterie (≥2/3) |",
        "|:-----|-------------:|:-------------------:|:---------------:|",
    ]
    for mode in MODES:
        t = table[mode]
        mark_e = "✓" if t["ell_selective_majority"] else "✗"
        mark_b = "✓" if t["battery_majority"] else "✗"
        lines.append(
            f"| {mode} | {t['median_ell_rho']} | {mark_e} | {mark_b} |"
        )
    lines += [
        "",
        f"## Per seed ({CANDIDATE})",
        "",
        "| Seed | ell_ρ | ell_pass | A | B | C | via_led |",
        "|-----:|------:|:--------:|:-:|:-:|:-:|--------:|",
    ]
    for s in cand:
        rec = s.get("reciprocity") or {}
        lines.append(
            f"| {s['run_seed']} | {s['ell_rho']} | {s['ell_pass']} | "
            f"{s['A']} | {s['B']} | {s['C']} | "
            f"{rec.get('frac_sticky_via_ledger')} |"
        )
    lines += [
        "",
        "## Konsequenz",
        "",
        "- `M7_PRESERVES_FIT` → Engpass 2 behoben; Edge-Local Pre-Reg freigegeben.",
        "- Sonst → Intake weiter justieren (frac / MAD_K / ewma_gate).",
        "",
        "Versiegeltes `ARCHITECTURE_FIT` (EWMA) bleibt Vorher-Zustand (§3.5.1).",
        "",
    ]
    md = out_dir / "M7_FILTER_ERGEBNIS.md"
    md.write_text("\n".join(lines), encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"GATE: {gate}  candidate={CANDIDATE}")
    for mode in MODES:
        t = table[mode]
        print(
            f"  {mode}: ell_ρ_med={t['median_ell_rho']} "
            f"ell={t['ell_selective_majority']} bat={t['battery_majority']}"
        )
    print(f"wrote: {md}")
    print("=" * 60)
    return 0 if gate == "M7_PRESERVES_FIT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
