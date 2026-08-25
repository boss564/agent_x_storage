#!/usr/bin/env python3
"""κ-Sweep — KOPPLUNG_LEDGER_v1 (BINDEND).

docs/KOPPLUNG_LEDGER_v1_PREREG.md
σ-normalization · Per-κ S-S/S-G · PRECONDITION_LOST
No reuse of kanten_ledger_v1 / eij / partnerselect sealed dirs.
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

from kanten_ledger_sweep_capture import capture_ledger_coupling  # noqa: E402
from measure import divergence, kuramoto  # noqa: E402

KAPPAS = [0.0, 0.2, 0.4, 0.6, 0.8, 1.2]
RUN_SEEDS = [20261301, 20261302, 20261303, 20261304, 20261305, 20261306]
SPOT_SEED = 20261301
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


def run_cell(
    arm: str,
    kappa: float,
    run_seed: int,
    component: str,
    cycles: int,
    warmup: int,
) -> dict:
    pack = capture_ledger_coupling(
        component=component,
        cycles=cycles,
        warmup_ticks=warmup,
        run_seed=run_seed,
        kappa=kappa,
        arm=arm,
    )
    tr = pack["trace"]
    precon = pack["precondition"]
    div = divergence(tr)
    keys = list(getattr(tr, "state_keys", []))
    if "phase" in keys:
        dim = keys.index("phase")
        kur = kuramoto(tr, dim=dim, n_surrogates=N_SURROGATES, seed=run_seed)
    else:
        kur = kuramoto(tr, dim="auto", n_surrogates=N_SURROGATES, seed=run_seed)

    intact = bool(precon.get("intact"))
    if kur.get("error"):
        coupling_assess = "ERROR"
    elif div.get("identical_agents"):
        coupling_assess = "TRIVIAL_SYNC"
    elif kur.get("significant"):
        coupling_assess = "COUPLED"
    else:
        coupling_assess = "NO_COUPLING"
    # Cell label: PRECONDITION_LOST overrides coupling for reporting,
    # but coupling_assess is kept for §1.1 on Arm C when B is intact.
    assess_verdict = "PRECONDITION_LOST" if not intact else coupling_assess

    return {
        "arm": arm,
        "kappa": kappa,
        "run_seed": run_seed,
        "component": component,
        "r": kur.get("r_observed"),
        "p": kur.get("p_value"),
        "d_dyn": div.get("divergence_dynamic"),
        "assess_verdict": assess_verdict,
        "coupling_assess": coupling_assess,
        "precondition_intact": intact,
        "precondition_label": precon.get("label"),
        "mae_norm": precon.get("mae_norm"),
        "median_abs_rho": precon.get("median_abs_rho"),
        "n_corr": precon.get("n_corr"),
        "sigma": pack.get("sigma"),
        "dimension_used": kur.get("dimension_used"),
        "n_ticks": int(tr.states.shape[0]),
        "n_msg": len(tr.messages),
        "precondition": precon,
    }


def evaluate_component(cells: list[dict], component: str) -> dict:
    def by(arm: str, kappa: float) -> list[dict]:
        return [
            c
            for c in cells
            if c["arm"] == arm
            and abs(c["kappa"] - kappa) < 1e-12
            and c["component"] == component
        ]

    kappa_meta: dict[float, dict] = {}
    for kappa in KAPPAS:
        seed_detail = []
        intact_n = 0
        gate_passes = 0
        c_coupled_intact = 0
        for seed in RUN_SEEDS:
            b = next((c for c in by("B", kappa) if c["run_seed"] == seed), None)
            c = next((c for c in by("C", kappa) if c["run_seed"] == seed), None)
            b_ok = bool(b and b.get("precondition_intact"))
            if b_ok:
                intact_n += 1
            gate = bool(
                b_ok
                and c
                and gate_seed(b["r"], b["p"], b["d_dyn"], c["r"])
            )
            if gate:
                gate_passes += 1
            c_coup = bool(
                b_ok
                and c
                and c.get("coupling_assess") == "COUPLED"
                and (c.get("d_dyn") or 0) > 0
            )
            if c_coup:
                c_coupled_intact += 1
            seed_detail.append({
                "run_seed": seed,
                "b_intact": b_ok,
                "gate": gate,
                "c_coupled": c_coup,
                "r_b": None if not b else b["r"],
                "r_c": None if not c else c["r"],
                "p_b": None if not b else b["p"],
                "d_dyn_b": None if not b else b["d_dyn"],
                "mae_norm_b": None if not b else b.get("mae_norm"),
                "rho_b": None if not b else b.get("median_abs_rho"),
            })
        stage_intact = intact_n >= MAJORITY
        kappa_meta[kappa] = {
            "intact_seeds": intact_n,
            "stage_intact": stage_intact,
            "gate_passes": gate_passes,
            "coupled": bool(stage_intact and gate_passes >= MAJORITY),
            "c_coupled_seeds": c_coupled_intact,
            "c_majority": bool(stage_intact and c_coupled_intact >= MAJORITY),
            "seeds": seed_detail,
            "label": "INTACT" if stage_intact else "PRECONDITION_LOST",
        }

    intact_kappas = [k for k, m in kappa_meta.items() if m["stage_intact"]]
    c_coupled_any = any(m["c_majority"] for m in kappa_meta.values())

    r_bar_b = []
    r_rows_b = []
    for kappa in KAPPAS:
        if kappa not in intact_kappas:
            r_bar_b.append(float("nan"))
            r_rows_b.append([])
            continue
        rs = [
            c["r"]
            for c in by("B", kappa)
            if c.get("precondition_intact") and c["r"] is not None
        ]
        r_rows_b.append(rs)
        r_bar_b.append(sum(rs) / len(rs) if rs else float("nan"))

    # Form only on contiguous intact κ sequence (skip NaNs in deltas)
    form_kappas = [k for k in KAPPAS if k in intact_kappas]
    form_r = []
    form_rows = []
    for k in form_kappas:
        idx = KAPPAS.index(k)
        form_r.append(r_bar_b[idx])
        form_rows.append(r_rows_b[idx])
    sd_pool = pooled_sd(form_rows) if form_rows else 0.0
    form_ok, form_meta = form_criterion(form_r, sd_pool) if len(form_r) >= 2 else (
        False,
        {"deltas": [], "note": "need ≥2 intact κ"},
    )

    d_a = [c["d_dyn"] for c in by("A", 0.0) if c["d_dyn"] is not None]
    d_a_mean = sum(d_a) / len(d_a) if d_a else float("nan")
    coupled_kappas = [k for k, g in kappa_meta.items() if g["coupled"]]
    kappa_star = min(coupled_kappas) if coupled_kappas else None

    if c_coupled_any:
        verdict = "KOPPLUNG_INVALID"
        reason = "Arm C COUPLED (Mehrheit) on precondition-intact κ — §1.1 falsified"
    elif kappa_star is not None:
        d_b_star = [
            c["d_dyn"]
            for c in by("B", kappa_star)
            if c.get("precondition_intact") and c["d_dyn"] is not None
        ]
        d_b_mean = sum(d_b_star) / len(d_b_star) if d_b_star else float("nan")
        if d_b_mean < d_a_mean:
            verdict = "HOMOGENIZED"
            reason = (
                f"mean D_dyn(B,κ*={kappa_star})={d_b_mean:.4f} < D_dyn(A)={d_a_mean:.4f}"
            )
        elif form_ok:
            verdict = "COUPLED_EMERGENT"
            reason = "Gate on intact κ + form criterion"
        else:
            verdict = "COUPLED_FORCED"
            reason = "Gate on intact κ but form criterion failed"
    else:
        lost_all = len(intact_kappas) == 0
        if lost_all:
            verdict = "PRECONDITION_LOST"
            reason = "no κ-stage with ≥4/6 intact precondition"
        else:
            verdict = "NO_COUPLING"
            reason = "Gate unmet on all precondition-intact κ"

    return {
        "component": component,
        "kappa_meta": {str(k): v for k, v in kappa_meta.items()},
        "intact_kappas": intact_kappas,
        "r_bar_b": r_bar_b,
        "sd_pool": sd_pool,
        "form": form_meta,
        "form_ok": form_ok,
        "d_dyn_a_mean": d_a_mean,
        "kappa_star": kappa_star,
        "verdict": verdict,
        "reason": reason,
        "c_coupled_any": c_coupled_any,
    }


def write_md(
    path: Path,
    component: str,
    eval_res: dict,
    elapsed: float,
    smoke: bool,
    json_path: Path,
    spot: dict | None,
) -> None:
    lines = [
        f"# KOPPLUNG_LEDGER_v1 — κ-Sweep Ergebnis ({component})",
        "",
        "**Pre-Reg:** `docs/KOPPLUNG_LEDGER_v1_PREREG.md` (BINDEND)",
        f"**Größe:** `{component}` · Lauf: {'SMOKE' if smoke else 'FULL'} · "
        f"{elapsed:.0f}s · EXIT 0",
        f"**JSON:** `{json_path}`",
        "",
    ]
    if spot is not None:
        lines += [
            "## κ=0 Spot-Check (Seed 20261301)",
            "",
            f"- L1 avg_latency intact: **{spot['L1'].get('precondition_intact')}** "
            f"(mae_norm={spot['L1'].get('mae_norm')}, ρ={spot['L1'].get('median_abs_rho')})",
            f"- L2 interaction_count intact: **{spot['L2'].get('precondition_intact')}** "
            f"(mae_norm={spot['L2'].get('mae_norm')}, ρ={spot['L2'].get('median_abs_rho')})",
            "",
        ]
    lines += [
        "## Verdict",
        "",
        f"**`{eval_res['verdict']}`** — {eval_res['reason']}",
        "",
        "## Per-κ Vorbedingung + Gate (Arm B vs C)",
        "",
        "| κ | Intact | Label | Gate-OK | ≥4/6 Gate | C-COUPLED |",
        "|--:|-------:|:------|--------:|:---------:|----------:|",
    ]
    meta = eval_res["kappa_meta"]
    for k in KAPPAS:
        g = meta[str(k)]
        lines.append(
            f"| {k} | {g['intact_seeds']}/6 | {g['label']} | "
            f"{g['gate_passes']}/6 | {'YES' if g['coupled'] else 'no'} | "
            f"{g['c_coupled_seeds']}/6 |"
        )
    lines += [
        "",
        f"§1.1 gehalten: **{'JA' if not eval_res['c_coupled_any'] else 'NEIN'}**",
        f"κ* = {eval_res['kappa_star']} · Form-OK = {eval_res['form_ok']} · "
        f"SD_pool = {eval_res['sd_pool']:.4f}",
        f"r̄_B (NaN = PRECONDITION_LOST stage) = "
        f"{[None if (isinstance(x, float) and math.isnan(x)) else round(x, 4) for x in eval_res['r_bar_b']]}",
        "",
        "## Regel",
        "",
        "Keine Schwellen-Nachjustierung. HARKing auf Abnahme-Datensatz gesperrt.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--spot-only", action="store_true", help="κ=0 spot-check only")
    ap.add_argument(
        "--component",
        choices=("avg_latency", "interaction_count", "both"),
        default="both",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_PROJECT_ROOT / "agents_b2g" / "emergence" / "kopplung_ledger_v1",
    )
    args = ap.parse_args()

    cycles = 64 if args.smoke else CYCLES
    warmup = 8 if args.smoke else WARMUP
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    components = (
        ["avg_latency", "interaction_count"]
        if args.component == "both"
        else [args.component]
    )

    print("=" * 60)
    print("KOPPLUNG_LEDGER_v1 κ-Sweep (BINDEND · σ · PRECONDITION_LOST)")
    print(f"components={components} kappas={KAPPAS} seeds={len(RUN_SEEDS)}")
    print(f"warmup={warmup} cycles={cycles} out={out_dir}")
    print("=" * 60)

    t0 = time.monotonic()

    # --- Spot-check κ=0 ---
    spot: dict = {"L1": {}, "L2": {}}
    print("\n--- κ=0 Spot-Check seed=20261301 ---")
    for comp, key in (("avg_latency", "L1"), ("interaction_count", "L2")):
        print(f"  spot {comp} ...", flush=True)
        cell = run_cell("B", 0.0, SPOT_SEED, comp, cycles, warmup)
        spot[key] = {
            "precondition_intact": cell["precondition_intact"],
            "precondition_label": cell["precondition_label"],
            "mae_norm": cell["mae_norm"],
            "median_abs_rho": cell["median_abs_rho"],
            "n_corr": cell["n_corr"],
            "sigma": cell["sigma"],
        }
        print(
            f"    intact={cell['precondition_intact']} "
            f"mae_norm={cell['mae_norm']} ρ={cell['median_abs_rho']}"
        )

    spot_path = out_dir / (
        "SPOT_CHECK_SMOKE.json" if args.smoke else "SPOT_CHECK.json"
    )
    spot_path.write_text(json.dumps(spot, indent=2), encoding="utf-8")

    if args.spot_only:
        print(f"\nSpot-only done → {spot_path}")
        return 0

    signal_blind = not (
        spot["L1"].get("precondition_intact")
        and spot["L2"].get("precondition_intact")
    )
    if signal_blind:
        print("WARNING: Spot-Check failed → SIGNAL_BLIND risk; continuing sweep.")

    all_cells: list[dict] = []
    results_by_comp: dict = {}

    for component in components:
        cells: list[dict] = []
        print(f"\n=== Component {component} ===")
        print("--- Arm A (κ=0) ---")
        for seed in RUN_SEEDS:
            print(f"  A  κ=0  seed={seed} ...", flush=True)
            cells.append(run_cell("A", 0.0, seed, component, cycles, warmup))
            c = cells[-1]
            print(
                f"    r={c['r']} precon={c['precondition_label']} "
                f"mae_n={c['mae_norm']}"
            )

        for arm in ("B", "C"):
            print(f"\n--- Arm {arm} ---")
            for kappa in KAPPAS:
                for seed in RUN_SEEDS:
                    print(f"  {arm}  κ={kappa}  seed={seed} ...", flush=True)
                    cells.append(
                        run_cell(arm, kappa, seed, component, cycles, warmup)
                    )
                    c = cells[-1]
                    print(
                        f"    r={c['r']} p={c['p']} "
                        f"precon={c['precondition_label']} "
                        f"assess={c['assess_verdict']}"
                    )

        eval_res = evaluate_component(cells, component)
        if signal_blind and eval_res["verdict"] == "NO_COUPLING":
            # Optional Pre-Reg label when spot fails
            pass
        all_cells.extend(cells)
        results_by_comp[component] = eval_res

        tag = "SMOKE" if args.smoke else "FULL"
        short = "L1" if component == "avg_latency" else "L2"
        json_path = out_dir / f"KOPPLUNG_LEDGER_{short}_{tag}.json"
        md_path = out_dir / (
            f"KOPPLUNG_LEDGER_{short}_ERGEBNIS_SMOKE.md"
            if args.smoke
            else f"KOPPLUNG_LEDGER_{short}_ERGEBNIS.md"
        )

        payload = {
            "pre_reg": "docs/KOPPLUNG_LEDGER_v1_PREREG.md",
            "status": "BINDEND",
            "normalization": "sigma",
            "component": component,
            "smoke": bool(args.smoke),
            "spot_check": spot,
            "signal_blind_spot": signal_blind,
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
            **eval_res,
        }
        json_path.write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
        write_md(
            md_path,
            component,
            eval_res,
            time.monotonic() - t0,
            args.smoke,
            json_path,
            spot,
        )
        print(f"\nVERDICT {component}: {eval_res['verdict']}")
        print(f"  → {md_path}")

    elapsed = time.monotonic() - t0
    summary = {
        "pre_reg": "docs/KOPPLUNG_LEDGER_v1_PREREG.md",
        "status": "BINDEND",
        "elapsed_s": round(elapsed, 1),
        "spot_check": spot,
        "verdicts": {
            c: results_by_comp[c]["verdict"] for c in results_by_comp
        },
        "reasons": {
            c: results_by_comp[c]["reason"] for c in results_by_comp
        },
    }
    sum_path = out_dir / (
        "KOPPLUNG_LEDGER_SUMMARY_SMOKE.json"
        if args.smoke
        else "KOPPLUNG_LEDGER_SUMMARY.json"
    )
    sum_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"elapsed: {elapsed:.0f}s")
    for c, v in summary["verdicts"].items():
        print(f"  {c}: {v}")
    print(f"summary: {sum_path}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
