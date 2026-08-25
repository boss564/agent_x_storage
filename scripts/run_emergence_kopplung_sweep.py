#!/usr/bin/env python3
"""κ-Sweep — Emergenz-Kopplungs-Umbau (Pre-Reg BINDEND 2026-08-24).

docs/EMERGENZ_KOPPLUNG_PREREG.md

Usage:
    python3 scripts/run_emergence_kopplung_sweep.py
    python3 scripts/run_emergence_kopplung_sweep.py --smoke   # shorter cycles
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "agents_b2g" / "emergence"))

from agents_b2g.emergence.adapter_agentx import capture  # noqa: E402
from agents_b2g.emergence.measure import assess  # noqa: E402

# Bound constants (§3 / §5.1) — do not edit after binding
KAPPAS = [0.0, 0.2, 0.4, 0.6, 0.8, 1.2]
RUN_SEEDS = [20260824, 20260825, 20260826, 20260827, 20260828, 20260829]
ALPHA = 0.05
N_SURROGATES = 200
DELTA_R_MIN = 0.10
R_FLOOR = 0.34
WARMUP = 32
CYCLES = 512
MAJORITY = 4  # ≥ 4 of 6 seeds


def gate_seed(r_b: float, p_b: float, d_dyn_b: float, r_c: float) -> bool:
    """§3.1 all four criteria for one seed at one κ."""
    if not (p_b is not None and p_b < ALPHA):
        return False
    if not (d_dyn_b is not None and d_dyn_b > 0):
        return False
    if r_b is None or r_c is None:
        return False
    if (r_b - r_c) < DELTA_R_MIN:
        return False
    if r_b < R_FLOOR:
        return False
    return True


def form_criterion(r_bar: list[float], sd_pool: float) -> tuple[bool, dict]:
    """§3.2 transition shape on seed-mean r̄(κ)."""
    deltas = [r_bar[k + 1] - r_bar[k] for k in range(len(r_bar) - 1)]
    if not deltas:
        return False, {"deltas": [], "max_delta": 0.0}
    max_k = max(range(len(deltas)), key=lambda k: deltas[k])
    max_delta = deltas[max_k]
    below = deltas[:max_k]
    mean_below = sum(below) / len(below) if below else 0.0
    cond1 = max_delta >= 3.0 * mean_below if below else False
    cond2 = max_delta >= 2.0 * sd_pool if sd_pool > 0 else max_delta > 0
    return bool(cond1 and cond2), {
        "deltas": deltas,
        "max_delta": max_delta,
        "max_k": max_k,
        "mean_below": mean_below,
        "sd_pool": sd_pool,
        "cond_3x_mean": cond1,
        "cond_2x_sd": cond2,
    }


def pooled_sd(values_by_kappa: list[list[float]]) -> float:
    """Pooled SD of r across all seeds and κ stages."""
    flat = [v for row in values_by_kappa for v in row if v is not None]
    if len(flat) < 2:
        return 0.0
    mean = sum(flat) / len(flat)
    var = sum((x - mean) ** 2 for x in flat) / (len(flat) - 1)
    return math.sqrt(var)


def run_cell(arm: str, kappa: float, run_seed: int, cycles: int, warmup: int) -> dict:
    from agents_b2g.emergence.measure import divergence, kuramoto

    tr = capture(
        cycles=cycles,
        full=True,
        kappa=kappa,
        run_seed=run_seed,
        warmup_ticks=warmup,
        arm=arm,
    )
    div = divergence(tr)
    keys = list(getattr(tr, "state_keys", []))
    # Pre-Reg interval path: measure sync on the phase we seed/modulate — not auto-dim.
    if "phase" in keys:
        dim = keys.index("phase")
        kur = kuramoto(tr, dim=dim, n_surrogates=N_SURROGATES, seed=run_seed)
    else:
        kur = kuramoto(tr, dim="auto", n_surrogates=N_SURROGATES, seed=run_seed)
    if kur.get("error"):
        assess_verdict = "ERROR"
    elif div.get("identical_agents"):
        assess_verdict = "TRIVIAL_SYNC"
    elif kur.get("significant"):
        assess_verdict = "COUPLED"
    else:
        assess_verdict = "NO_COUPLING"
    return {
        "arm": arm,
        "kappa": kappa,
        "run_seed": run_seed,
        "r": kur.get("r_observed"),
        "p": kur.get("p_value"),
        "d_dyn": div.get("divergence_dynamic"),
        "assess_verdict": assess_verdict,
        "dimension_used": kur.get("dimension_used"),
        "n_ticks": int(tr.states.shape[0]),
        "n_msg": len(tr.messages),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="cycles=64 warmup=8 (dev only)")
    ap.add_argument(
        "--out",
        type=Path,
        default=_PROJECT_ROOT / "docs" / "EMERGENZ_KOPPLUNG_ERGEBNIS.md",
    )
    ap.add_argument(
        "--json",
        type=Path,
        default=_PROJECT_ROOT / "docs" / "EMERGENZ_KOPPLUNG_SWEEP.json",
    )
    args = ap.parse_args()

    cycles = 64 if args.smoke else CYCLES
    warmup = 8 if args.smoke else WARMUP
    kappas = KAPPAS
    seeds = RUN_SEEDS

    print("=" * 60)
    print("Emergenz-Kopplung κ-Sweep (Pre-Reg BINDEND)")
    print(f"kappas={kappas}  seeds={len(seeds)}  warmup={warmup}  cycles={cycles}")
    print("=" * 60)

    t0 = time.monotonic()
    cells: list[dict] = []

    # Arm A: baseline κ=0 only (6 seeds)
    print("\n--- Arm A (baseline κ=0) ---")
    for seed in seeds:
        print(f"  A  κ=0  seed={seed} ...", flush=True)
        cells.append(run_cell("A", 0.0, seed, cycles, warmup))
        print(f"    r={cells[-1]['r']} p={cells[-1]['p']} D={cells[-1]['d_dyn']}")

    # Arms B and C: full κ × seed grid
    for arm in ("B", "C"):
        print(f"\n--- Arm {arm} ---")
        for kappa in kappas:
            for seed in seeds:
                print(f"  {arm}  κ={kappa}  seed={seed} ...", flush=True)
                cells.append(run_cell(arm, kappa, seed, cycles, warmup))
                c = cells[-1]
                print(f"    r={c['r']} p={c['p']} D={c['d_dyn']}")

    elapsed = time.monotonic() - t0

    def by(arm: str, kappa: float) -> list[dict]:
        return [c for c in cells if c["arm"] == arm and abs(c["kappa"] - kappa) < 1e-12]

    # Per-κ majority gate §3.3
    kappa_gate: dict[float, dict] = {}
    for kappa in kappas:
        passes = 0
        seed_detail = []
        for seed in seeds:
            b = next((c for c in by("B", kappa) if c["run_seed"] == seed), None)
            c = next((c for c in by("C", kappa) if c["run_seed"] == seed), None)
            ok = False
            if b and c:
                ok = gate_seed(b["r"], b["p"], b["d_dyn"], c["r"])
            if ok:
                passes += 1
            seed_detail.append({
                "run_seed": seed,
                "gate": ok,
                "r_b": None if not b else b["r"],
                "r_c": None if not c else c["r"],
                "p_b": None if not b else b["p"],
                "d_dyn_b": None if not b else b["d_dyn"],
            })
        kappa_gate[kappa] = {
            "passes": passes,
            "coupled": passes >= MAJORITY,
            "seeds": seed_detail,
        }

    # Arm C risk prediction §1.1: any κ with C coupled under §3.3?
    # C is "COUPLED" if ≥4/6 seeds meet assess significant + D_dyn>0 + r≥floor
    # Pre-Reg: Arm C COUPLED = Gate §3.1 after majority — but Gate needs r_B-r_C.
    # For Arm C alone, "COUPLED" in §1.1 means assess would call it coupled.
    # Strict reading of §4 KOPPLUNG_INVALID: Arm C at any κ COUPLED after Gate §3.1+§3.3.
    # Gate §3.1 requires r_B - r_C — that's a B-vs-C gate, not C alone.
    # §1.1: "Arm C bleibt NO_COUPLING" — use measure.assess verdict majority:
    c_coupled_any = False
    c_majority: dict[float, dict] = {}
    for kappa in kappas:
        n_sig = 0
        for seed in seeds:
            c = next((x for x in by("C", kappa) if x["run_seed"] == seed), None)
            if c and c["assess_verdict"] == "COUPLED" and (c["d_dyn"] or 0) > 0:
                n_sig += 1
        c_majority[kappa] = {"passes": n_sig, "coupled": n_sig >= MAJORITY}
        if n_sig >= MAJORITY:
            c_coupled_any = True

    # Form criterion on B seed-mean r
    r_bar_b = []
    r_rows_b = []
    for kappa in kappas:
        rs = [c["r"] for c in by("B", kappa) if c["r"] is not None]
        r_rows_b.append(rs)
        r_bar_b.append(sum(rs) / len(rs) if rs else float("nan"))
    sd_pool = pooled_sd(r_rows_b)
    form_ok, form_meta = form_criterion(r_bar_b, sd_pool)

    # D_dyn Arm A baseline (seed mean)
    d_a = [c["d_dyn"] for c in by("A", 0.0) if c["d_dyn"] is not None]
    d_a_mean = sum(d_a) / len(d_a) if d_a else float("nan")

    coupled_kappas = [k for k, g in kappa_gate.items() if g["coupled"]]
    kappa_star = min(coupled_kappas) if coupled_kappas else None

    # Verdict §4 (priority top-down)
    if c_coupled_any:
        verdict = "KOPPLUNG_INVALID"
        reason = "Arm C COUPLED (Mehrheit) at some κ — §1.1 falsified"
    elif kappa_star is not None:
        d_b_star = [
            c["d_dyn"] for c in by("B", kappa_star) if c["d_dyn"] is not None
        ]
        d_b_mean = sum(d_b_star) / len(d_b_star) if d_b_star else float("nan")
        if d_b_mean < d_a_mean:
            verdict = "HOMOGENIZED"
            reason = f"mean D_dyn(B,κ*={kappa_star})={d_b_mean:.4f} < D_dyn(A)={d_a_mean:.4f}"
        elif form_ok:
            verdict = "COUPLED_EMERGENT"
            reason = "Gate §3.3 at ≥1 κ and form criterion §3.2"
        else:
            verdict = "COUPLED_FORCED"
            reason = "Gate §3.3 met but form criterion §3.2 failed"
    else:
        verdict = "NO_COUPLING"
        reason = "Gate §3.1 after §3.3 unmet at every κ"

    result = {
        "pre_reg": "docs/EMERGENZ_KOPPLUNG_PREREG.md",
        "status": "BINDEND",
        "smoke": bool(args.smoke),
        "elapsed_s": round(elapsed, 1),
        "constants": {
            "kappas": kappas,
            "run_seeds": seeds,
            "warmup": warmup,
            "cycles": cycles,
            "alpha": ALPHA,
            "delta_r_min": DELTA_R_MIN,
            "r_floor": R_FLOOR,
            "majority": MAJORITY,
            "n_surrogates": N_SURROGATES,
        },
        "cells": cells,
        "kappa_gate": {str(k): v for k, v in kappa_gate.items()},
        "arm_c_majority": {str(k): v for k, v in c_majority.items()},
        "r_bar_b": r_bar_b,
        "sd_pool": sd_pool,
        "form": form_meta,
        "form_ok": form_ok,
        "d_dyn_a_mean": d_a_mean,
        "kappa_star": kappa_star,
        "verdict": verdict,
        "reason": reason,
    }

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    # Markdown Ergebnis (append-only style report)
    lines = [
        "# Emergenz — Kopplungs-Umbau: Ergebnis",
        "",
        f"**Pre-Reg:** `docs/EMERGENZ_KOPPLUNG_PREREG.md` (BINDEND 2026-08-24)",
        f"**Lauf:** {'SMOKE' if args.smoke else 'FULL'} · warmup={warmup} · cycles={cycles} · "
        f"{elapsed:.0f}s",
        f"**JSON:** `{args.json}`",
        "",
        "## Verdict",
        "",
        f"**`{verdict}`** — {reason}",
        "",
        "## Gate §3.3 je κ (Arm B vs C)",
        "",
        "| κ | Seeds Gate-OK | ≥4/6 |",
        "|--:|-------------:|:----:|",
    ]
    for k in kappas:
        g = kappa_gate[k]
        lines.append(
            f"| {k} | {g['passes']}/6 | {'YES' if g['coupled'] else 'no'} |"
        )
    lines += [
        "",
        "## Arm C (§1.1 riskante Vorhersage)",
        "",
        "| κ | assess COUPLED Seeds | ≥4/6 |",
        "|--:|---------------------:|:----:|",
    ]
    for k in kappas:
        g = c_majority[k]
        lines.append(
            f"| {k} | {g['passes']}/6 | {'YES' if g['coupled'] else 'no'} |"
        )
    lines += [
        "",
        f"Vorhersage gehalten: **{'JA' if not c_coupled_any else 'NEIN'}**",
        "",
        "## Form §3.2",
        "",
        f"r̄_B(κ) = {[round(x, 4) for x in r_bar_b]}",
        f"SD_pool = {sd_pool:.4f}",
        f"Form-OK = {form_ok} · meta = `{json.dumps(form_meta, default=str)}`",
        "",
        f"D_dyn(A) mean = {d_a_mean:.4f}",
        f"κ* = {kappa_star}",
        "",
        "## Regel",
        "",
        "Keine Schwellen-Nachjustierung. Bereichserweiterung = neue Pre-Reg.",
        "",
    ]
    args.out.write_text("\n".join(lines), encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"VERDICT: {verdict}")
    print(f"reason:  {reason}")
    print(f"wrote:   {args.out}")
    print(f"json:    {args.json}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
