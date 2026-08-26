#!/usr/bin/env python3
"""M7 latency-intake spike + battery re-check + sticky reciprocity.

Engineering only — no Pre-Reg / no hypothesis test.
docs/THREAT_MODEL_POST_QUANTUM_v0.md §3.5–§3.7
Sequence: M7 on → sticky-ℓ screen → A∧B∧C battery → reciprocity frac.
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
from kanten_ledger import LATENCY_MODE_EWMA, LATENCY_MODE_M7  # noqa: E402

SEEDS = (20261711, 20261712, 20261713)  # distinct from ARCHITECTURE_FIT seeds


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
        / "m7_spike_v0",
    )
    args = ap.parse_args()
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("M7 spike · sticky-ℓ · battery · reciprocity (no Pre-Reg)")
    print(f"seeds={SEEDS} warmup={args.warmup} cycles={args.cycles}")
    print("=" * 60)

    rows_ewma = []
    rows_m7 = []
    t0 = time.monotonic()

    for mode, bucket in (
        (LATENCY_MODE_EWMA, rows_ewma),
        (LATENCY_MODE_M7, rows_m7),
    ):
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
            bucket.append({"summary": s, "cell": cell})
            rec = s["reciprocity"] or {}
            print(
                f"    ell_ρ={s['ell_rho']} ell_pass={s['ell_pass']} · "
                f"A={s['A']} ρ={s['rho']} B={s['B']} C={s['C']} · "
                f"eval={s['latency_evaluable_edges']} thin={s['latency_thin_edges']} · "
                f"recip_sticky={rec.get('frac_sticky')} "
                f"recip_via_led={rec.get('frac_sticky_via_ledger')} · "
                f"{s['elapsed_s']}s"
            )

    def maj_battery(rows):
        return sum(1 for r in rows if r["summary"]["battery"]) >= 2

    def maj_ell(rows):
        return sum(1 for r in rows if r["summary"]["ell_pass"]) >= 2

    elapsed = time.monotonic() - t0
    fit_ewma = maj_battery(rows_ewma)
    fit_m7 = maj_battery(rows_m7)
    ell_ewma = maj_ell(rows_ewma)
    ell_m7 = maj_ell(rows_m7)

    # Reciprocity: report from M7 runs (same sticky dynamics as EWMA structurally)
    recip_fracs = [
        (r["summary"]["reciprocity"] or {}).get("frac_sticky_via_ledger")
        for r in rows_m7
    ]
    recip_fracs = [x for x in recip_fracs if x is not None]
    recip_med = sorted(recip_fracs)[len(recip_fracs) // 2] if recip_fracs else None

    if fit_m7 and ell_m7:
        gate = "M7_PRESERVES_FIT"
    elif fit_ewma and not fit_m7:
        gate = "M7_BREAKS_FIT"
    elif not ell_m7:
        gate = "M7_LOSES_ELL_SELECTIVITY"
    else:
        gate = "M7_INCONCLUSIVE"

    payload = {
        "schema": "m7_spike_v0",
        "not_a_pre_reg": True,
        "threat_ref": "docs/THREAT_MODEL_POST_QUANTUM_v0.md §3.5–§3.7",
        "note_continuity": (
            "ARCHITECTURE_FIT (20261701–03, EWMA) is pre-M7; "
            "this spike re-measures under median_m7"
        ),
        "params": {
            "seeds": list(SEEDS),
            "warmup": args.warmup,
            "cycles": args.cycles,
        },
        "elapsed_s": round(elapsed, 1),
        "ewma": {
            "ell_selective_majority": ell_ewma,
            "battery_majority": fit_ewma,
            "per_seed": [r["summary"] for r in rows_ewma],
        },
        "m7": {
            "ell_selective_majority": ell_m7,
            "battery_majority": fit_m7,
            "per_seed": [r["summary"] for r in rows_m7],
            "reciprocity_median_frac_sticky_via_ledger": recip_med,
        },
        "gate": gate,
        "pre_reg_advice": {
            "reciprocity_condition": (
                "Edge-local Pre-Reg needs mutual reaction on (i,j) and (j,i); "
                "measure frac_sticky_via_ledger first"
            ),
            "reciprocity_median": recip_med,
            "sufficient_hint": (
                "if median frac << 0.5, sticky map may lack reciprocal pairs "
                "for two-oscillator coupling"
            ),
        },
    }

    jp = out_dir / "M7_SPIKE.json"
    # Drop heavy nested cell blobs for JSON size — summaries enough
    jp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    md = out_dir / "M7_SPIKE_ERGEBNIS.md"
    lines = [
        "# M7 Spike — Ergebnis",
        "",
        "**Charakter:** Engineering · keine Pre-Reg",
        f"**Gate:** `{gate}` · {elapsed:.1f}s",
        f"**Seeds:** `{SEEDS[0]}…{SEEDS[-1]}`",
        "",
        "## sticky-ℓ Selektivität + Batterie",
        "",
        "| Mode | ell-selektiv (≥2/3) | Batterie A∧B∧C (≥2/3) |",
        "|:-----|:-------------------:|:---------------------:|",
        f"| EWMA (Vorher) | {'✓' if ell_ewma else '✗'} | {'✓' if fit_ewma else '✗'} |",
        f"| M7 median | {'✓' if ell_m7 else '✗'} | {'✓' if fit_m7 else '✗'} |",
        "",
        "## Per seed (M7)",
        "",
        "| Seed | ell_ρ | A ρ | B mae_n | C |ΔΔR| | eval/thin | recip_via_led |",
        "|-----:|------:|----:|--------:|----------:|----------:|--------------:|",
    ]
    for r in rows_m7:
        s = r["summary"]
        rec = s["reciprocity"] or {}
        lines.append(
            f"| {s['run_seed']} | {s['ell_rho']} | {s['rho']} | {s['mae_n']} | "
            f"{s['dR']} | {s['latency_evaluable_edges']}/{s['latency_thin_edges']} | "
            f"{rec.get('frac_sticky_via_ledger')} |"
        )
    lines += [
        "",
        f"**Reziprozität (Median frac sticky→Ledger-Rückkante):** {recip_med}",
        "",
        "## Konsequenz",
        "",
        "- `M7_PRESERVES_FIT` → Edge-Local Pre-Reg darf starten (nach Reziprozitäts-Check).",
        "- `M7_BREAKS_FIT` / `M7_LOSES_ELL_SELECTIVITY` → Intake oder Signalpfad anpassen "
        "bevor Pre-Reg.",
        "- Reziprozität vor Pre-Reg: wechselseitige Reaktion braucht Rückkanten.",
        "",
        "Versiegeltes `ARCHITECTURE_FIT` (EWMA) bleibt Vorher-Zustand (§3.5.1).",
        "",
    ]
    md.write_text("\n".join(lines), encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"GATE: {gate}")
    print(f"reciprocity median (sticky via ledger): {recip_med}")
    print(f"wrote: {md}")
    print("=" * 60)
    return 0 if gate == "M7_PRESERVES_FIT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
