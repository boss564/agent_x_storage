#!/usr/bin/env python3
"""κ-Sweep — KOPPLUNG_EIJ_v1 (BINDEND, I1_PASS).

docs/KOPPLUNG_EIJ_v1_PREREG.md
No reuse of state_screen / kopplung_full / reputation_i1.
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

from edge_capture import capture_edge  # noqa: E402
from measure import divergence, kuramoto  # noqa: E402

KAPPAS = [0.0, 0.2, 0.4, 0.6, 0.8, 1.2]
RUN_SEEDS = [20261001, 20261002, 20261003, 20261004, 20261005, 20261006]
ALPHA = 0.05
N_SURROGATES = 200
DELTA_R_MIN = 0.10
R_FLOOR = 0.34
WARMUP = 32
CYCLES = 512
MAJORITY = 4


def gate_seed(r_b, p_b, d_dyn_b, r_c) -> bool:
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
    deltas = [r_bar[k + 1] - r_bar[k] for k in range(len(r_bar) - 1)]
    if not deltas:
        return False, {"deltas": []}
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
    flat = [v for row in values_by_kappa for v in row if v is not None]
    if len(flat) < 2:
        return 0.0
    mean = sum(flat) / len(flat)
    return math.sqrt(sum((x - mean) ** 2 for x in flat) / (len(flat) - 1))


def run_cell(arm: str, kappa: float, run_seed: int, cycles: int, warmup: int) -> dict:
    tr = capture_edge(
        cycles=cycles,
        warmup_ticks=warmup,
        run_seed=run_seed,
        kappa=kappa,
        arm=arm,
    )
    div = divergence(tr)
    keys = list(getattr(tr, "state_keys", []))
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
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=Path("/tmp/emergence_eij_sweep"),
    )
    args = ap.parse_args()

    cycles = 64 if args.smoke else CYCLES
    warmup = 8 if args.smoke else WARMUP
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / (
        "KOPPLUNG_EIJ_SWEEP_SMOKE.json" if args.smoke else "KOPPLUNG_EIJ_SWEEP.json"
    )
    md_path = out_dir / (
        "KOPPLUNG_EIJ_ERGEBNIS_SMOKE.md" if args.smoke else "KOPPLUNG_EIJ_ERGEBNIS.md"
    )

    print("=" * 60)
    print("KOPPLUNG_EIJ_v1 κ-Sweep (BINDEND · I1_PASS)")
    print(f"kappas={KAPPAS} seeds={len(RUN_SEEDS)} warmup={warmup} cycles={cycles}")
    print("=" * 60)

    t0 = time.monotonic()
    cells: list[dict] = []

    print("\n--- Arm A (κ=0) ---")
    for seed in RUN_SEEDS:
        print(f"  A  κ=0  seed={seed} ...", flush=True)
        cells.append(run_cell("A", 0.0, seed, cycles, warmup))
        print(f"    r={cells[-1]['r']} p={cells[-1]['p']} D={cells[-1]['d_dyn']}")

    for arm in ("B", "C"):
        print(f"\n--- Arm {arm} ---")
        for kappa in KAPPAS:
            for seed in RUN_SEEDS:
                print(f"  {arm}  κ={kappa}  seed={seed} ...", flush=True)
                cells.append(run_cell(arm, kappa, seed, cycles, warmup))
                c = cells[-1]
                print(f"    r={c['r']} p={c['p']} D={c['d_dyn']}")

    elapsed = time.monotonic() - t0

    def by(arm: str, kappa: float) -> list[dict]:
        return [c for c in cells if c["arm"] == arm and abs(c["kappa"] - kappa) < 1e-12]

    kappa_gate: dict[float, dict] = {}
    for kappa in KAPPAS:
        passes = 0
        seed_detail = []
        for seed in RUN_SEEDS:
            b = next((c for c in by("B", kappa) if c["run_seed"] == seed), None)
            c = next((c for c in by("C", kappa) if c["run_seed"] == seed), None)
            ok = bool(b and c and gate_seed(b["r"], b["p"], b["d_dyn"], c["r"]))
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

    c_coupled_any = False
    c_majority: dict[float, dict] = {}
    for kappa in KAPPAS:
        n_sig = 0
        for seed in RUN_SEEDS:
            c = next((x for x in by("C", kappa) if x["run_seed"] == seed), None)
            if c and c["assess_verdict"] == "COUPLED" and (c["d_dyn"] or 0) > 0:
                n_sig += 1
        c_majority[kappa] = {"passes": n_sig, "coupled": n_sig >= MAJORITY}
        if n_sig >= MAJORITY:
            c_coupled_any = True

    r_bar_b = []
    r_rows_b = []
    for kappa in KAPPAS:
        rs = [c["r"] for c in by("B", kappa) if c["r"] is not None]
        r_rows_b.append(rs)
        r_bar_b.append(sum(rs) / len(rs) if rs else float("nan"))
    sd_pool = pooled_sd(r_rows_b)
    form_ok, form_meta = form_criterion(r_bar_b, sd_pool)

    d_a = [c["d_dyn"] for c in by("A", 0.0) if c["d_dyn"] is not None]
    d_a_mean = sum(d_a) / len(d_a) if d_a else float("nan")
    coupled_kappas = [k for k, g in kappa_gate.items() if g["coupled"]]
    kappa_star = min(coupled_kappas) if coupled_kappas else None

    if c_coupled_any:
        verdict = "KOPPLUNG_INVALID"
        reason = "Arm C COUPLED (Mehrheit) at some κ — §1.1 falsified"
    elif kappa_star is not None:
        d_b_star = [c["d_dyn"] for c in by("B", kappa_star) if c["d_dyn"] is not None]
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
        "pre_reg": "docs/KOPPLUNG_EIJ_v1_PREREG.md",
        "status": "BINDEND",
        "i1": "I1_PASS",
        "smoke": bool(args.smoke),
        "elapsed_s": round(elapsed, 1),
        "constants": {
            "kappas": KAPPAS,
            "run_seeds": RUN_SEEDS,
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
    json_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    lines = [
        "# KOPPLUNG_EIJ_v1 — κ-Sweep Ergebnis",
        "",
        "**Pre-Reg:** `docs/KOPPLUNG_EIJ_v1_PREREG.md` (BINDEND · I1_PASS)",
        f"**Lauf:** {'SMOKE' if args.smoke else 'FULL'} · warmup={warmup} · "
        f"cycles={cycles} · {elapsed:.0f}s · EXIT 0",
        f"**JSON:** `{json_path}`",
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
    for k in KAPPAS:
        g = kappa_gate[k]
        lines.append(f"| {k} | {g['passes']}/6 | {'YES' if g['coupled'] else 'no'} |")
    lines += [
        "",
        "## Arm C (§1.1)",
        "",
        "| κ | assess COUPLED Seeds | ≥4/6 |",
        "|--:|---------------------:|:----:|",
    ]
    for k in KAPPAS:
        g = c_majority[k]
        lines.append(f"| {k} | {g['passes']}/6 | {'YES' if g['coupled'] else 'no'} |")
    lines += [
        "",
        f"Vorhersage gehalten: **{'JA' if not c_coupled_any else 'NEIN'}**",
        "",
        "## Form §3.2",
        "",
        f"r̄_B(κ) = {[round(x, 4) for x in r_bar_b]}",
        f"SD_pool = {sd_pool:.4f} · Form-OK = {form_ok}",
        f"D_dyn(A) mean = {d_a_mean:.4f} · κ* = {kappa_star}",
        "",
        "## Regel",
        "",
        "Keine Schwellen-Nachjustierung. HARKing auf Alt-Daten aktiv.",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"VERDICT: {verdict}")
    print(f"reason:  {reason}")
    print(f"wrote:   {md_path}")
    print(f"json:    {json_path}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
