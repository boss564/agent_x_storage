#!/usr/bin/env python3
"""κ-Sweep — RECIPROCAL_EVENT_KOPPLUNG_v0 (BINDEND).

F5 Inter-Arrival · F6 Snapshot Δt=64 · F7 Receipt Gate.
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

from measure import divergence, kuramoto  # noqa: E402
from reciprocal_event_kopplung_capture import capture_reciprocal_event_coupling  # noqa: E402

KAPPAS = [0.0, 0.2, 0.4, 0.6, 0.8, 1.2]
RUN_SEEDS = [20262201, 20262202, 20262203, 20262204, 20262205, 20262206]
SPOT_SEED = 20262201
LOCKED_MAX_SEED = 20262199
ALPHA = 0.05
N_SURROGATES = 200
DELTA_R_MIN = 0.10
R_FLOOR = 0.34
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


def run_cell(arm: str, kappa: float, run_seed: int) -> dict:
    if int(run_seed) <= LOCKED_MAX_SEED:
        raise RuntimeError(f"HARKing: seed {run_seed} ≤ {LOCKED_MAX_SEED}")
    pack = capture_reciprocal_event_coupling(run_seed=run_seed, kappa=kappa, arm=arm)
    tr = pack["trace"]
    precon = pack["precondition"]
    bat = pack["battery"]
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
    assess = precon.get("label") if not intact else coupling_assess

    return {
        "arm": arm,
        "kappa": kappa,
        "run_seed": run_seed,
        "r": kur.get("r_observed"),
        "p": kur.get("p_value"),
        "d_dyn": div.get("divergence_dynamic"),
        "assess_verdict": assess,
        "coupling_assess": coupling_assess,
        "precondition_intact": intact,
        "precondition_label": precon.get("label"),
        "battery_A": bat["A"]["pass"],
        "battery_B": bat["B"]["pass"],
        "battery_C": bat["C"]["pass"],
        "mae_norm": bat["B"].get("mae_norm"),
        "median_abs_rho": bat["A"].get("median_abs_rho"),
        "n_corr": bat["A"].get("n_corr"),
        "mean_abs_diff": bat["C"].get("mean_abs_diff"),
        "frac_coupling_on": pack.get("frac_coupling_on"),
        "n_snapshots": pack.get("n_snapshots"),
        "n_ticks": int(tr.states.shape[0]),
        "n_msg": len(tr.messages),
    }


def evaluate(cells: list[dict]) -> dict:
    def by(arm: str, kappa: float) -> list[dict]:
        return [c for c in cells if c["arm"] == arm and abs(c["kappa"] - kappa) < 1e-12]

    kappa_meta: dict[float, dict] = {}
    for kappa in KAPPAS:
        intact_n = gate_passes = c_coupled_intact = 0
        seed_detail = []
        for seed in RUN_SEEDS:
            b = next((c for c in by("B", kappa) if c["run_seed"] == seed), None)
            c = next((c for c in by("C", kappa) if c["run_seed"] == seed), None)
            b_ok = bool(b and b.get("precondition_intact"))
            if b_ok:
                intact_n += 1
            gate = bool(b_ok and c and gate_seed(b["r"], b["p"], b["d_dyn"], c["r"]))
            if gate:
                gate_passes += 1
            c_coup = bool(
                b_ok and c and c.get("coupling_assess") == "COUPLED" and (c.get("d_dyn") or 0) > 0
            )
            if c_coup:
                c_coupled_intact += 1
            seed_detail.append(
                {
                    "run_seed": seed,
                    "b_intact": b_ok,
                    "gate": gate,
                    "c_coupled": c_coup,
                    "r_b": None if not b else b["r"],
                    "r_c": None if not c else c["r"],
                    "p_b": None if not b else b["p"],
                    "d_dyn_b": None if not b else b["d_dyn"],
                    "frac_on_b": None if not b else b.get("frac_coupling_on"),
                    "frac_on_c": None if not c else c.get("frac_coupling_on"),
                }
            )
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

    r_bar_b, r_rows_b = [], []
    for kappa in KAPPAS:
        if kappa not in intact_kappas:
            r_bar_b.append(float("nan"))
            r_rows_b.append([])
            continue
        rs = [c["r"] for c in by("B", kappa) if c.get("precondition_intact") and c["r"] is not None]
        r_rows_b.append(rs)
        r_bar_b.append(sum(rs) / len(rs) if rs else float("nan"))

    form_kappas = [k for k in KAPPAS if k in intact_kappas]
    form_r = [r_bar_b[KAPPAS.index(k)] for k in form_kappas]
    form_rows = [r_rows_b[KAPPAS.index(k)] for k in form_kappas]
    sd_pool = pooled_sd(form_rows) if form_rows else 0.0
    form_ok, form_meta = (
        form_criterion(form_r, sd_pool) if len(form_r) >= 2 else (False, {"note": "need ≥2 intact κ"})
    )

    d_a = [c["d_dyn"] for c in by("A", 0.0) if c["d_dyn"] is not None]
    d_a_mean = sum(d_a) / len(d_a) if d_a else float("nan")
    coupled_kappas = [k for k, g in kappa_meta.items() if g["coupled"]]
    kappa_star = min(coupled_kappas) if coupled_kappas else None

    if c_coupled_any:
        verdict = "KOPPLUNG_INVALID"
        reason = "Arm C COUPLED (Mehrheit) on precondition-intact κ — §1.1 falsified"
    elif kappa_star is not None:
        d_b_star = [c["d_dyn"] for c in by("B", kappa_star) if c.get("precondition_intact") and c["d_dyn"] is not None]
        d_b_mean = sum(d_b_star) / len(d_b_star) if d_b_star else float("nan")
        if d_b_mean < d_a_mean:
            verdict = "HOMOGENIZED"
            reason = f"D_dyn(B,κ*)={d_b_mean:.4f} < D_dyn(A)={d_a_mean:.4f}"
        elif form_ok:
            verdict = "COUPLED_EMERGENT"
            reason = "Gate on intact κ + form criterion"
        else:
            verdict = "COUPLED_FORCED"
            reason = "Gate on intact κ but form criterion failed"
    elif not intact_kappas:
        verdict = "PRECONDITION_LOST"
        reason = "no κ-stage with ≥4/6 intact battery"
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


def write_md(path: Path, eval_res: dict, elapsed: float, spot: dict, signal_blind: bool, json_path: Path) -> None:
    lines = [
        "# RECIPROCAL_EVENT_KOPPLUNG_v0 — κ-Sweep Ergebnis",
        "",
        "**Pre-Reg:** `docs/RECIPROCAL_EVENT_KOPPLUNG_v0_PREREG.md` (BINDEND)",
        f"**Lauf:** FULL · {elapsed:.0f}s",
        f"**JSON:** `{json_path}`",
        "**F5:** Inter-Arrival · **F6:** Snapshot Δt=64 · **F7:** Receipt Gate",
        f"**Seeds:** `{RUN_SEEDS[0]}…{RUN_SEEDS[-1]}`",
        "",
        f"## κ=0 Spot (Seed {SPOT_SEED})",
        "",
        f"- Intact: **{spot.get('precondition_intact')}** ({spot.get('precondition_label')})",
        f"- A ρ={spot.get('median_abs_rho')} · B mae_n={spot.get('mae_norm')} · C |ΔΔR|={spot.get('mean_abs_diff')}",
        f"- SIGNAL_BLIND: **{'JA' if signal_blind else 'NEIN'}**",
        "",
        "## Verdict",
        "",
        f"**`{eval_res['verdict']}`** — {eval_res['reason']}",
        "",
        "| κ | Intact | Label | Gate-OK | ≥4/6 Gate | C-COUPLED |",
        "|--:|-------:|:------|--------:|:---------:|----------:|",
    ]
    meta = eval_res["kappa_meta"]
    for k in KAPPAS:
        g = meta[str(k)]
        lines.append(
            f"| {k} | {g['intact_seeds']}/6 | {g['label']} | {g['gate_passes']}/6 | "
            f"{'YES' if g['coupled'] else 'no'} | {g['c_coupled_seeds']}/6 |"
        )
    lines += [
        "",
        f"§1.1 gehalten: **{'JA' if not eval_res['c_coupled_any'] else 'NEIN'}**",
        f"κ*={eval_res['kappa_star']} · Form-OK={eval_res['form_ok']}",
        "",
        "Tick-Serie versiegelt · Hybrid Tick/Event verboten · keine Schwellen-Nachjustierung.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spot-only", action="store_true")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_PROJECT_ROOT / "agents_b2g" / "emergence" / "reciprocal_event_kopplung_v0",
    )
    args = ap.parse_args()
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("RECIPROCAL_EVENT_KOPPLUNG_v0 (BINDEND · F7 receipt gate)")
    print(f"seeds={RUN_SEEDS}")
    print("=" * 60)

    t0 = time.monotonic()
    print(f"\n--- Spot κ=0 seed={SPOT_SEED} ---")
    spot_cell = run_cell("B", 0.0, SPOT_SEED)
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
        "frac_coupling_on": spot_cell["frac_coupling_on"],
        "n_snapshots": spot_cell["n_snapshots"],
    }
    print(
        f"  intact={spot['precondition_intact']} A={spot['battery_A']} B={spot['battery_B']} "
        f"C={spot['battery_C']} ρ={spot['median_abs_rho']} mae_n={spot['mae_norm']} "
        f"|ΔΔR|={spot['mean_abs_diff']} frac_on={spot['frac_coupling_on']}"
    )
    (out_dir / "SPOT_CHECK.json").write_text(json.dumps(spot, indent=2), encoding="utf-8")

    signal_blind = not bool(spot.get("precondition_intact"))
    if signal_blind:
        print("SIGNAL_BLIND — Sweep gesperrt")
        (out_dir / "RECIPROCAL_EVENT_KOPPLUNG_ERGEBNIS.md").write_text(
            f"# SIGNAL_BLIND\n\nSpot {SPOT_SEED} Batterie FAIL\n",
            encoding="utf-8",
        )
        return 1
    if args.spot_only:
        return 0

    cells: list[dict] = []
    print("\n--- Arm A ---")
    for seed in RUN_SEEDS:
        print(f"  A κ=0 seed={seed} ...", flush=True)
        cells.append(run_cell("A", 0.0, seed))
        print(f"    r={cells[-1]['r']} precon={cells[-1]['precondition_label']}")

    for arm in ("B", "C"):
        print(f"\n--- Arm {arm} ---")
        for kappa in KAPPAS:
            for seed in RUN_SEEDS:
                print(f"  {arm} κ={kappa} seed={seed} ...", flush=True)
                cells.append(run_cell(arm, kappa, seed))
                c = cells[-1]
                print(
                    f"    r={c['r']} p={c['p']} precon={c['precondition_label']} "
                    f"assess={c['assess_verdict']} frac_on={c['frac_coupling_on']}"
                )

    eval_res = evaluate(cells)
    elapsed = time.monotonic() - t0

    def _san(o):
        if isinstance(o, float) and math.isnan(o):
            return None
        if isinstance(o, dict):
            return {k: _san(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_san(x) for x in o]
        return o

    json_path = out_dir / "RECIPROCAL_EVENT_KOPPLUNG_FULL.json"
    payload = {
        "pre_reg": "docs/RECIPROCAL_EVENT_KOPPLUNG_v0_PREREG.md",
        "status": "BINDEND",
        "f5": "inter_arrival",
        "f6_snapshot_dt": 64,
        "f7": "receipt_equals_signal_partner",
        "spot_check": spot,
        "constants": {
            "kappas": KAPPAS,
            "run_seeds": RUN_SEEDS,
            "locked_max_seed": LOCKED_MAX_SEED,
            "alpha": ALPHA,
            "delta_r_min": DELTA_R_MIN,
            "r_floor": R_FLOOR,
            "majority": MAJORITY,
            "n_surrogates": N_SURROGATES,
        },
        "cells": cells,
        "evaluation": eval_res,
        "elapsed_s": round(elapsed, 1),
    }
    json_path.write_text(json.dumps(_san(payload), indent=2, default=str), encoding="utf-8")
    md_path = out_dir / "RECIPROCAL_EVENT_KOPPLUNG_ERGEBNIS.md"
    write_md(md_path, eval_res, elapsed, spot, signal_blind, json_path)

    print("\n" + "=" * 60)
    print(f"VERDICT: {eval_res['verdict']}")
    print(f"  {eval_res['reason']}")
    print(f"wrote: {md_path}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

