#!/usr/bin/env python3
"""κ-Sweep — EDGE_LOCAL_KOPPLUNG_v0 (BINDEND).

docs/EDGE_LOCAL_KOPPLUNG_v0_PREREG.md
η=1.0 · trimmed_m7 · h↔ · Batterie A∧B∧C ∧ Reziprozität ≥0.3
Seeds 20261801…06 · Spot 20261801.
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

from edge_local_kopplung_capture import capture_edge_local_coupling  # noqa: E402
from measure import divergence, kuramoto  # noqa: E402

KAPPAS = [0.0, 0.2, 0.4, 0.6, 0.8, 1.2]
RUN_SEEDS = [20261801, 20261802, 20261803, 20261804, 20261805, 20261806]
SPOT_SEED = 20261801
LOCKED_MAX_SEED = 20261799  # HARKing: all seeds ≤ this locked
ALPHA = 0.05
N_SURROGATES = 200
DELTA_R_MIN = 0.10
R_FLOOR = 0.34
RECIP_MIN = 0.3
WARMUP = 32
CYCLES = 512
MAJORITY = 4
ETA = 1.0


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
    cycles: int,
    warmup: int,
) -> dict:
    if int(run_seed) <= LOCKED_MAX_SEED:
        raise RuntimeError(f"HARKing: seed {run_seed} ≤ {LOCKED_MAX_SEED} gesperrt")
    pack = capture_edge_local_coupling(
        cycles=cycles,
        warmup_ticks=warmup,
        run_seed=run_seed,
        kappa=kappa,
        arm=arm,
    )
    tr = pack["trace"]
    precon = pack["precondition"]
    bat = pack["battery"]
    recip = pack.get("reciprocity") or {}
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
    assess_verdict = precon.get("label") if not intact else coupling_assess

    return {
        "arm": arm,
        "kappa": kappa,
        "run_seed": run_seed,
        "r": kur.get("r_observed"),
        "p": kur.get("p_value"),
        "d_dyn": div.get("divergence_dynamic"),
        "assess_verdict": assess_verdict,
        "coupling_assess": coupling_assess,
        "precondition_intact": intact,
        "precondition_label": precon.get("label"),
        "battery_ok": precon.get("battery_ok"),
        "reciprocity_ok": precon.get("reciprocity_ok"),
        "frac_sticky_via_ledger": recip.get("frac_sticky_via_ledger"),
        "battery_A": bat["A"]["pass"],
        "battery_B": bat["B"]["pass"],
        "battery_C": bat["C"]["pass"],
        "mae_norm": bat["B"].get("mae_norm"),
        "median_abs_rho": bat["A"].get("median_abs_rho"),
        "n_corr": bat["A"].get("n_corr"),
        "mean_abs_diff": bat["C"].get("mean_abs_diff"),
        "eta": pack.get("eta"),
        "sigma_ell": pack.get("sigma_ell"),
        "latency_mode": pack.get("latency_mode"),
        "dimension_used": kur.get("dimension_used"),
        "n_ticks": int(tr.states.shape[0]),
        "n_msg": len(tr.messages),
        "battery": bat,
        "reciprocity": recip,
    }


def evaluate(cells: list[dict]) -> dict:
    def by(arm: str, kappa: float) -> list[dict]:
        return [
            c
            for c in cells
            if c["arm"] == arm and abs(c["kappa"] - kappa) < 1e-12
        ]

    kappa_meta: dict[float, dict] = {}
    for kappa in KAPPAS:
        seed_detail = []
        intact_n = 0
        gate_passes = 0
        c_coupled_intact = 0
        recip_lost_n = 0
        for seed in RUN_SEEDS:
            b = next((c for c in by("B", kappa) if c["run_seed"] == seed), None)
            c = next((c for c in by("C", kappa) if c["run_seed"] == seed), None)
            b_ok = bool(b and b.get("precondition_intact"))
            if b_ok:
                intact_n += 1
            if b and b.get("precondition_label") == "RECIPROCITY_LOST":
                recip_lost_n += 1
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
                "delta_r_c": None if not b else b.get("mean_abs_diff"),
                "frac_via_led": None if not b else b.get("frac_sticky_via_ledger"),
                "precon_label": None if not b else b.get("precondition_label"),
            })
        stage_intact = intact_n >= MAJORITY
        kappa_meta[kappa] = {
            "intact_seeds": intact_n,
            "stage_intact": stage_intact,
            "gate_passes": gate_passes,
            "coupled": bool(stage_intact and gate_passes >= MAJORITY),
            "c_coupled_seeds": c_coupled_intact,
            "c_majority": bool(stage_intact and c_coupled_intact >= MAJORITY),
            "reciprocity_lost_seeds": recip_lost_n,
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
            recip_dom = all(
                kappa_meta[k]["reciprocity_lost_seeds"] >= MAJORITY for k in KAPPAS
            )
            if recip_dom:
                verdict = "RECIPROCITY_LOST"
                reason = "majority seeds RECIPROCITY_LOST across κ stages"
            else:
                verdict = "PRECONDITION_LOST"
                reason = "no κ-stage with ≥4/6 intact (battery ∧ reciprocity)"
        else:
            verdict = "NO_COUPLING"
            reason = "Gate unmet on all precondition-intact κ"

    return {
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
    eval_res: dict,
    elapsed: float,
    smoke: bool,
    json_path: Path,
    spot: dict | None,
    signal_blind: bool,
    recip_lost_spot: bool,
) -> None:
    lines = [
        "# EDGE_LOCAL_KOPPLUNG_v0 — κ-Sweep Ergebnis",
        "",
        "**Pre-Reg:** `docs/EDGE_LOCAL_KOPPLUNG_v0_PREREG.md` (BINDEND)",
        f"**Lauf:** {'SMOKE' if smoke else 'FULL'} · {elapsed:.0f}s · EXIT 0",
        f"**JSON:** `{json_path}`",
        f"**η:** {ETA} (F1) · ℓ=`trimmed_m7` (F4) · Seeds `{RUN_SEEDS[0]}…{RUN_SEEDS[-1]}`",
        "",
    ]
    if spot is not None:
        lines += [
            f"## κ=0 Spot-Check (Seed {SPOT_SEED})",
            "",
            f"- Intact: **{spot.get('precondition_intact')}** "
            f"({spot.get('precondition_label')})",
            f"- A ρ={spot.get('median_abs_rho')} · B mae_n={spot.get('mae_norm')} · "
            f"C |ΔΔR|={spot.get('mean_abs_diff')}",
            f"- Reziprozität via_led={spot.get('frac_sticky_via_ledger')} "
            f"(Gate ≥ {RECIP_MIN})",
            f"- SIGNAL_BLIND: **{'JA' if signal_blind else 'NEIN'}** · "
            f"RECIPROCITY_LOST: **{'JA' if recip_lost_spot else 'NEIN'}**",
            "",
        ]
    lines += [
        "## Verdict",
        "",
        f"**`{eval_res['verdict']}`** — {eval_res['reason']}",
        "",
        "## Per-κ Batterie∧Reziprozität + Gate (Arm B vs C)",
        "",
        "| κ | Intact | Label | Gate-OK | ≥4/6 Gate | C-COUPLED | RecipLost |",
        "|--:|-------:|:------|--------:|:---------:|----------:|----------:|",
    ]
    meta = eval_res["kappa_meta"]
    for k in KAPPAS:
        g = meta[str(k)]
        lines.append(
            f"| {k} | {g['intact_seeds']}/6 | {g['label']} | "
            f"{g['gate_passes']}/6 | {'YES' if g['coupled'] else 'no'} | "
            f"{g['c_coupled_seeds']}/6 | {g['reciprocity_lost_seeds']}/6 |"
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
        "Keine Schwellen-Nachjustierung. Seeds ≤20261799 gesperrt. HARKing-Sperre aktiv.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--spot-only", action="store_true")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_PROJECT_ROOT / "agents_b2g" / "emergence" / "edge_local_kopplung_v0",
    )
    args = ap.parse_args()

    cycles = 64 if args.smoke else CYCLES
    warmup = 8 if args.smoke else WARMUP
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("EDGE_LOCAL_KOPPLUNG_v0 κ-Sweep (BINDEND · h↔ · trimmed_m7)")
    print(f"kappas={KAPPAS} seeds={RUN_SEEDS}")
    print(f"warmup={warmup} cycles={cycles} out={out_dir}")
    print("=" * 60)

    t0 = time.monotonic()

    print(f"\n--- κ=0 Spot-Check seed={SPOT_SEED} ---")
    spot_cell = run_cell("B", 0.0, SPOT_SEED, cycles, warmup)
    spot = {
        "precondition_intact": spot_cell["precondition_intact"],
        "precondition_label": spot_cell["precondition_label"],
        "mae_norm": spot_cell["mae_norm"],
        "median_abs_rho": spot_cell["median_abs_rho"],
        "n_corr": spot_cell["n_corr"],
        "mean_abs_diff": spot_cell["mean_abs_diff"],
        "battery_A": spot_cell["battery_A"],
        "battery_B": spot_cell["battery_B"],
        "battery_C": spot_cell["battery_C"],
        "frac_sticky_via_ledger": spot_cell["frac_sticky_via_ledger"],
        "reciprocity_ok": spot_cell["reciprocity_ok"],
        "latency_mode": spot_cell["latency_mode"],
        "sigma_ell": spot_cell["sigma_ell"],
    }
    print(
        f"  intact={spot['precondition_intact']} label={spot['precondition_label']} "
        f"A={spot['battery_A']} B={spot['battery_B']} C={spot['battery_C']} "
        f"ρ={spot['median_abs_rho']} mae_n={spot['mae_norm']} "
        f"|ΔΔR|={spot['mean_abs_diff']} via_led={spot['frac_sticky_via_ledger']}"
    )
    spot_path = out_dir / ("SPOT_CHECK_SMOKE.json" if args.smoke else "SPOT_CHECK.json")
    spot_path.write_text(json.dumps(spot, indent=2), encoding="utf-8")

    signal_blind = not bool(spot.get("battery_A") and spot.get("battery_B") and spot.get("battery_C"))
    recip_lost_spot = (
        spot.get("frac_sticky_via_ledger") is None
        or float(spot.get("frac_sticky_via_ledger") or 0) < RECIP_MIN
    )

    if signal_blind or recip_lost_spot:
        label = "SIGNAL_BLIND" if signal_blind else "RECIPROCITY_LOST"
        print(f"{label}: Spot-Check failed — Sweep gesperrt.")
        md = out_dir / (
            "EDGE_LOCAL_KOPPLUNG_ERGEBNIS_SMOKE.md"
            if args.smoke
            else "EDGE_LOCAL_KOPPLUNG_ERGEBNIS.md"
        )
        md.write_text(
            "\n".join([
                f"# EDGE_LOCAL_KOPPLUNG_v0 — {label}",
                "",
                f"**Spot κ=0 Seed {SPOT_SEED}:** FAIL",
                f"- A={spot['battery_A']} ρ={spot['median_abs_rho']}",
                f"- B={spot['battery_B']} mae_n={spot['mae_norm']}",
                f"- C={spot['battery_C']} |ΔΔR|={spot['mean_abs_diff']}",
                f"- via_led={spot['frac_sticky_via_ledger']} (need ≥ {RECIP_MIN})",
                "",
                f"Verdict: `{label}` — Sweep nicht ausgeführt.",
                "",
            ]),
            encoding="utf-8",
        )
        print(f"wrote: {md}")
        return 1

    if args.spot_only:
        print(f"Spot-only PASS → {spot_path}")
        return 0

    cells: list[dict] = []
    print("\n--- Arm A (κ=0) ---")
    for seed in RUN_SEEDS:
        print(f"  A  κ=0  seed={seed} ...", flush=True)
        cells.append(run_cell("A", 0.0, seed, cycles, warmup))
        c = cells[-1]
        print(
            f"    r={c['r']} precon={c['precondition_label']} "
            f"via_led={c['frac_sticky_via_ledger']}"
        )

    for arm in ("B", "C"):
        print(f"\n--- Arm {arm} ---")
        for kappa in KAPPAS:
            for seed in RUN_SEEDS:
                print(f"  {arm}  κ={kappa}  seed={seed} ...", flush=True)
                cells.append(run_cell(arm, kappa, seed, cycles, warmup))
                c = cells[-1]
                print(
                    f"    r={c['r']} p={c['p']} "
                    f"precon={c['precondition_label']} "
                    f"assess={c['assess_verdict']}"
                )

    eval_res = evaluate(cells)
    elapsed = time.monotonic() - t0
    tag = "SMOKE" if args.smoke else "FULL"
    json_path = out_dir / f"EDGE_LOCAL_KOPPLUNG_{tag}.json"
    md_path = out_dir / (
        "EDGE_LOCAL_KOPPLUNG_ERGEBNIS_SMOKE.md"
        if args.smoke
        else "EDGE_LOCAL_KOPPLUNG_ERGEBNIS.md"
    )

    payload = {
        "pre_reg": "docs/EDGE_LOCAL_KOPPLUNG_v0_PREREG.md",
        "status": "BINDEND",
        "eta": ETA,
        "latency_mode": "trimmed_m7",
        "coupling": "h_mutual=0.5*(hij+hji)",
        "smoke": bool(args.smoke),
        "spot_check": spot,
        "signal_blind_spot": signal_blind,
        "reciprocity_lost_spot": recip_lost_spot,
        "constants": {
            "kappas": KAPPAS,
            "run_seeds": RUN_SEEDS,
            "locked_max_seed": LOCKED_MAX_SEED,
            "warmup": warmup,
            "cycles": cycles,
            "alpha": ALPHA,
            "delta_r_min": DELTA_R_MIN,
            "r_floor": R_FLOOR,
            "recip_min": RECIP_MIN,
            "majority": MAJORITY,
            "n_surrogates": N_SURROGATES,
            "eta": ETA,
        },
        "cells": [
            {k: v for k, v in c.items() if k not in ("battery", "reciprocity")}
            for c in cells
        ],
        "evaluation": eval_res,
        "elapsed_s": round(elapsed, 1),
    }
    # Serialize evaluation with nan-safe
    def _san(obj):
        if isinstance(obj, float) and math.isnan(obj):
            return None
        if isinstance(obj, dict):
            return {k: _san(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_san(x) for x in obj]
        return obj

    json_path.write_text(
        json.dumps(_san(payload), indent=2, default=str), encoding="utf-8"
    )
    write_md(
        md_path, eval_res, elapsed, args.smoke, json_path, spot,
        signal_blind, recip_lost_spot,
    )
    print("\n" + "=" * 60)
    print(f"VERDICT: {eval_res['verdict']}")
    print(f"  {eval_res['reason']}")
    print(f"wrote: {md_path}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
