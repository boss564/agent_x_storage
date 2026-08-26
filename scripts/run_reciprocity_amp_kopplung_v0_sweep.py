#!/usr/bin/env python3
"""κ/α-Sweep — RECIPROCITY_AMP_KOPPLUNG_v0 (BINDEND).

Vierarm A/B/C/D · P1 κ-Trennung · P2 Gate B↔D · §1.1d auf D.
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
from reciprocity_amp_kopplung_capture import (  # noqa: E402
    capture_reciprocity_amp_coupling,
)

ALPHAS = [0.0, 0.10, 0.25, 0.40, 0.60, 1.00]
RUN_SEEDS = [20262401, 20262402, 20262403, 20262404, 20262405, 20262406]
SPOT_SEED = 20262401
LOCKED_MAX_SEED = 20262399
ALPHA_STAT = 0.05
N_SURROGATES = 200
DELTA_R_MIN = 0.10
N_AGENTS = 9
R_FLOOR = 1.0 / math.sqrt(N_AGENTS) + 0.15  # 0.483...
DELTA_KAPPA_MIN = 0.50
DELTA_AMP_MIN = 0.50
MAJORITY = 4


def gate_p2(r_b, p_b, d_dyn_b, r_d) -> bool:
    if not (p_b is not None and p_b < ALPHA_STAT):
        return False
    if not (d_dyn_b is not None and d_dyn_b > 0):
        return False
    if r_b is None or r_d is None:
        return False
    if (r_b - r_d) < DELTA_R_MIN:
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


def pooled_sd(values_by_alpha: list[list[float]]) -> float:
    flat = [v for row in values_by_alpha for v in row if v is not None]
    if len(flat) < 2:
        return 0.0
    mean = sum(flat) / len(flat)
    return math.sqrt(sum((x - mean) ** 2 for x in flat) / (len(flat) - 1))


def run_arm(arm: str, amp_step: float, run_seed: int, kappa_fixed=None) -> dict:
    if int(run_seed) <= LOCKED_MAX_SEED:
        raise RuntimeError(f"HARKing: seed {run_seed} ≤ {LOCKED_MAX_SEED}")
    pack = capture_reciprocity_amp_coupling(
        run_seed=run_seed,
        amp_step=amp_step,
        arm=arm,
        kappa_fixed=kappa_fixed,
    )
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
        "amp_step": amp_step,
        "run_seed": run_seed,
        "kappa_fixed": kappa_fixed,
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
        "mean_abs_diff": bat["C"].get("mean_abs_diff"),
        "frac_amp": pack.get("frac_amp"),
        "final_kappa_mean": pack.get("final_kappa_mean"),
        "n_snapshots": pack.get("n_snapshots"),
        "n_ticks": int(tr.states.shape[0]),
        "n_msg": len(tr.messages),
    }


def run_seed_bundle(amp_step: float, run_seed: int) -> list[dict]:
    """A (only α=0 meaningful), B, C endogenous; D matched to κ̄_B."""
    out = []
    if abs(amp_step) < 1e-12:
        out.append(run_arm("A", 0.0, run_seed))
    b = run_arm("B", amp_step, run_seed)
    out.append(b)
    out.append(run_arm("C", amp_step, run_seed))
    kappa_b = float(b["final_kappa_mean"])
    d = run_arm("D", amp_step, run_seed, kappa_fixed=kappa_b)
    # Match check
    d["match_ok"] = abs(float(d["final_kappa_mean"]) - kappa_b) < 1e-9
    d["kappa_b_source"] = kappa_b
    out.append(d)
    return out


def evaluate(cells: list[dict]) -> dict:
    def by(arm: str, amp: float) -> list[dict]:
        return [
            c
            for c in cells
            if c["arm"] == arm and abs(c["amp_step"] - amp) < 1e-12
        ]

    alpha_meta: dict[float, dict] = {}
    for amp in ALPHAS:
        intact_n = p1_passes = p2_passes = d_coupled_intact = 0
        match_fails = 0
        seed_detail = []
        for seed in RUN_SEEDS:
            b = next((c for c in by("B", amp) if c["run_seed"] == seed), None)
            c = next((c for c in by("C", amp) if c["run_seed"] == seed), None)
            d = next((c for c in by("D", amp) if c["run_seed"] == seed), None)
            b_ok = bool(b and b.get("precondition_intact"))
            if b_ok:
                intact_n += 1
            p1 = bool(
                b_ok
                and c
                and (b["final_kappa_mean"] - c["final_kappa_mean"]) >= DELTA_KAPPA_MIN
                and (b["frac_amp"] - c["frac_amp"]) >= DELTA_AMP_MIN
            )
            if p1:
                p1_passes += 1
            if d and d.get("match_ok") is False:
                match_fails += 1
            p2 = bool(b_ok and d and gate_p2(b["r"], b["p"], b["d_dyn"], d["r"]))
            if p2:
                p2_passes += 1
            d_coup = bool(
                b_ok
                and d
                and d.get("coupling_assess") == "COUPLED"
                and (d.get("d_dyn") or 0) > 0
            )
            if d_coup:
                d_coupled_intact += 1
            seed_detail.append(
                {
                    "run_seed": seed,
                    "b_intact": b_ok,
                    "p1": p1,
                    "p2": p2,
                    "d_coupled": d_coup,
                    "match_ok": None if not d else d.get("match_ok"),
                    "r_b": None if not b else b["r"],
                    "r_d": None if not d else d["r"],
                    "p_b": None if not b else b["p"],
                    "d_dyn_b": None if not b else b["d_dyn"],
                    "kappa_b": None if not b else b["final_kappa_mean"],
                    "kappa_c": None if not c else c["final_kappa_mean"],
                    "kappa_d": None if not d else d["final_kappa_mean"],
                    "frac_amp_b": None if not b else b["frac_amp"],
                    "frac_amp_c": None if not c else c["frac_amp"],
                }
            )
        stage_intact = intact_n >= MAJORITY
        alpha_meta[amp] = {
            "intact_seeds": intact_n,
            "stage_intact": stage_intact,
            "p1_passes": p1_passes,
            "p2_passes": p2_passes,
            "p1_majority": bool(stage_intact and p1_passes >= MAJORITY),
            "p2_majority": bool(stage_intact and p2_passes >= MAJORITY),
            "d_coupled_seeds": d_coupled_intact,
            "d_majority": bool(stage_intact and d_coupled_intact >= MAJORITY),
            "match_fails": match_fails,
            "seeds": seed_detail,
            "label": "INTACT" if stage_intact else "PRECONDITION_LOST",
        }

    intact_alphas = [a for a, m in alpha_meta.items() if m["stage_intact"]]
    d_coupled_any = any(m["d_majority"] for m in alpha_meta.values())
    p1_any = any(m["p1_majority"] for a, m in alpha_meta.items() if a > 0)
    p2_alphas = [a for a, m in alpha_meta.items() if m["p2_majority"]]
    alpha_star = min(p2_alphas) if p2_alphas else None

    if any(m["match_fails"] > 0 for m in alpha_meta.values()):
        verdict = "MATCH_FAIL"
        reason = "Arm D κ match failed on ≥1 cell"
    elif d_coupled_any:
        verdict = "KOPPLUNG_INVALID"
        reason = "Arm D COUPLED (Mehrheit) on intact α — §1.1d falsified"
    elif alpha_star is not None and p1_any:
        # form on B r across intact alphas
        r_bar_b, r_rows = [], []
        for amp in ALPHAS:
            if amp not in intact_alphas:
                r_bar_b.append(float("nan"))
                r_rows.append([])
                continue
            rs = [
                c["r"]
                for c in by("B", amp)
                if c.get("precondition_intact") and c["r"] is not None
            ]
            r_rows.append(rs)
            r_bar_b.append(sum(rs) / len(rs) if rs else float("nan"))
        form_a = [a for a in ALPHAS if a in intact_alphas]
        form_r = [r_bar_b[ALPHAS.index(a)] for a in form_a]
        form_rows = [r_rows[ALPHAS.index(a)] for a in form_a]
        sd_pool = pooled_sd(form_rows) if form_rows else 0.0
        form_ok, form_meta = (
            form_criterion(form_r, sd_pool)
            if len(form_r) >= 2
            else (False, {"note": "need ≥2 intact α"})
        )
        d_a = [c["d_dyn"] for c in by("A", 0.0) if c["d_dyn"] is not None]
        d_a_mean = sum(d_a) / len(d_a) if d_a else float("nan")
        d_b_star = [
            c["d_dyn"]
            for c in by("B", alpha_star)
            if c.get("precondition_intact") and c["d_dyn"] is not None
        ]
        d_b_mean = sum(d_b_star) / len(d_b_star) if d_b_star else float("nan")
        if d_b_mean < d_a_mean:
            verdict = "HOMOGENIZED"
            reason = f"D_dyn(B,α*)={d_b_mean:.4f} < D_dyn(A)={d_a_mean:.4f}"
        elif form_ok:
            verdict = "COUPLED_EMERGENT"
            reason = "P1+P2 on intact α + form criterion"
        else:
            verdict = "COUPLED_FORCED"
            reason = "P1+P2 on intact α but form criterion failed"
        return {
            "alpha_meta": {str(k): v for k, v in alpha_meta.items()},
            "intact_alphas": intact_alphas,
            "p1_any": p1_any,
            "p2_any": True,
            "form": form_meta,
            "form_ok": form_ok,
            "d_dyn_a_mean": d_a_mean,
            "alpha_star": alpha_star,
            "verdict": verdict,
            "reason": reason,
            "d_coupled_any": d_coupled_any,
        }
    elif alpha_star is not None and not p1_any:
        verdict = "P2_ONLY"
        reason = "P2 Gate B↔D positiv, P1 κ-Trennung nicht mehrheitlich"
    elif p1_any and alpha_star is None:
        verdict = "P1_ONLY"
        reason = "P1 κ relational positiv, P2 Gate B↔D negativ — gültiger Abschluss"
    elif not intact_alphas:
        verdict = "PRECONDITION_LOST"
        reason = "no α-stage with ≥4/6 intact battery"
    else:
        verdict = "NO_COUPLING"
        reason = "P1 and P2 unmet on all precondition-intact α; §1.1d held"

    return {
        "alpha_meta": {str(k): v for k, v in alpha_meta.items()},
        "intact_alphas": intact_alphas,
        "p1_any": p1_any,
        "p2_any": alpha_star is not None,
        "form": {},
        "form_ok": False,
        "d_dyn_a_mean": None,
        "alpha_star": alpha_star,
        "verdict": verdict,
        "reason": reason,
        "d_coupled_any": d_coupled_any,
    }


def write_md(path, eval_res, elapsed, spot, signal_blind, json_path):
    lines = [
        "# RECIPROCITY_AMP_KOPPLUNG_v0 — Sweep Ergebnis",
        "",
        "**Pre-Reg:** `docs/RECIPROCITY_AMP_KOPPLUNG_v0_PREREG.md` (BINDEND)",
        f"**Lauf:** FULL · {elapsed:.0f}s",
        f"**JSON:** `{json_path}`",
        "**Vierarm** A/B/C/D · P1 κ · P2 Gate B↔D · §1.1d auf D",
        f"**N={N_AGENTS}** · **r_floor={R_FLOOR:.4f}** · Seeds `{RUN_SEEDS[0]}…{RUN_SEEDS[-1]}`",
        "",
        f"## Spot α=0 (Seed {SPOT_SEED})",
        "",
        f"- Intact: **{spot.get('precondition_intact')}** ({spot.get('precondition_label')})",
        f"- A ρ={spot.get('median_abs_rho')} · B mae_n={spot.get('mae_norm')} · "
        f"C |ΔΔR|={spot.get('mean_abs_diff')}",
        f"- SIGNAL_BLIND: **{'JA' if signal_blind else 'NEIN'}**",
        "",
        "## Verdict",
        "",
        f"**`{eval_res['verdict']}`** — {eval_res['reason']}",
        "",
        "| α | Intact | P1≥4/6 | P2≥4/6 | D-COUPLED |",
        "|--:|-------:|:------:|:------:|----------:|",
    ]
    meta = eval_res["alpha_meta"]
    for a in ALPHAS:
        g = meta[str(a)]
        lines.append(
            f"| {a} | {g['intact_seeds']}/6 | "
            f"{'YES' if g['p1_majority'] else 'no'} ({g['p1_passes']}/6) | "
            f"{'YES' if g['p2_majority'] else 'no'} ({g['p2_passes']}/6) | "
            f"{g['d_coupled_seeds']}/6 |"
        )
    lines += [
        "",
        f"§1.1d gehalten: **{'JA' if not eval_res['d_coupled_any'] else 'NEIN'}**",
        f"P1_any={eval_res['p1_any']} · P2_any={eval_res['p2_any']} · α*={eval_res['alpha_star']}",
        "",
        "Tick-Serie versiegelt · Hybrid verboten · keine Schwellen-Nachjustierung.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spot-only", action="store_true")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_PROJECT_ROOT
        / "agents_b2g"
        / "emergence"
        / "reciprocity_amp_kopplung_v0",
    )
    args = ap.parse_args()
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("RECIPROCITY_AMP_KOPPLUNG_v0 (BINDEND · Vierarm · P1/P2)")
    print(f"seeds={RUN_SEEDS} r_floor={R_FLOOR:.4f}")
    print("=" * 60)

    t0 = time.monotonic()
    print(f"\n--- Spot α=0 seed={SPOT_SEED} ---")
    spot_cell = run_arm("B", 0.0, SPOT_SEED)
    spot = {
        "precondition_intact": spot_cell["precondition_intact"],
        "precondition_label": spot_cell["precondition_label"],
        "mae_norm": spot_cell["mae_norm"],
        "median_abs_rho": spot_cell["median_abs_rho"],
        "mean_abs_diff": spot_cell["mean_abs_diff"],
        "battery_A": spot_cell["battery_A"],
        "battery_B": spot_cell["battery_B"],
        "battery_C": spot_cell["battery_C"],
        "frac_amp": spot_cell["frac_amp"],
        "final_kappa_mean": spot_cell["final_kappa_mean"],
        "n_snapshots": spot_cell["n_snapshots"],
    }
    print(
        f"  intact={spot['precondition_intact']} A={spot['battery_A']} "
        f"B={spot['battery_B']} C={spot['battery_C']} ρ={spot['median_abs_rho']} "
        f"mae_n={spot['mae_norm']} |ΔΔR|={spot['mean_abs_diff']}"
    )
    (out_dir / "SPOT_CHECK.json").write_text(
        json.dumps(spot, indent=2), encoding="utf-8"
    )

    signal_blind = not bool(spot.get("precondition_intact"))
    if signal_blind:
        print("SIGNAL_BLIND — Sweep gesperrt")
        (out_dir / "RECIPROCITY_AMP_KOPPLUNG_ERGEBNIS.md").write_text(
            f"# SIGNAL_BLIND\n\nSpot {SPOT_SEED} Batterie FAIL\n",
            encoding="utf-8",
        )
        return 1
    if args.spot_only:
        return 0

    cells: list[dict] = []
    for amp in ALPHAS:
        print(f"\n--- α={amp} ---")
        for seed in RUN_SEEDS:
            print(f"  seed={seed} A/B/C/D ...", flush=True)
            bundle = run_seed_bundle(amp, seed)
            cells.extend(bundle)
            b = next(c for c in bundle if c["arm"] == "B")
            c = next(x for x in bundle if x["arm"] == "C")
            d = next(x for x in bundle if x["arm"] == "D")
            print(
                f"    B r={b['r']} κ={b['final_kappa_mean']} amp={b['frac_amp']} "
                f"| C κ={c['final_kappa_mean']} amp={c['frac_amp']} "
                f"| D r={d['r']} κ={d['final_kappa_mean']} match={d.get('match_ok')} "
                f"precon={b['precondition_label']}"
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

    json_path = out_dir / "RECIPROCITY_AMP_KOPPLUNG_FULL.json"
    payload = {
        "pre_reg": "docs/RECIPROCITY_AMP_KOPPLUNG_v0_PREREG.md",
        "status": "BINDEND",
        "n_agents": N_AGENTS,
        "r_floor": R_FLOOR,
        "spot_check": spot,
        "constants": {
            "alphas": ALPHAS,
            "run_seeds": RUN_SEEDS,
            "locked_max_seed": LOCKED_MAX_SEED,
            "alpha_stat": ALPHA_STAT,
            "delta_r_min": DELTA_R_MIN,
            "delta_kappa_min": DELTA_KAPPA_MIN,
            "delta_amp_min": DELTA_AMP_MIN,
            "majority": MAJORITY,
            "n_surrogates": N_SURROGATES,
        },
        "cells": cells,
        "evaluation": eval_res,
        "elapsed_s": round(elapsed, 1),
    }
    json_path.write_text(
        json.dumps(_san(payload), indent=2, default=str), encoding="utf-8"
    )
    md_path = out_dir / "RECIPROCITY_AMP_KOPPLUNG_ERGEBNIS.md"
    write_md(md_path, eval_res, elapsed, spot, signal_blind, json_path)

    print("\n" + "=" * 60)
    print(f"VERDICT: {eval_res['verdict']}")
    print(f"  {eval_res['reason']}")
    print(f"wrote: {md_path}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
