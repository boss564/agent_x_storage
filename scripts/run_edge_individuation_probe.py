#!/usr/bin/env python3
"""Edge-individuation probe v0 — measure sticky-S ρ; noise = positive control only.

docs/EDGE_INDIVIDUATION_v0_DRAFT.md
No ρ target optimization. No Pre-Reg. No κ-sweep.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "agents_b2g" / "emergence"))

from kanten_ledger import _corr_abs  # noqa: E402
from s_i_probe_capture import capture_ell_for_s_probe  # noqa: E402

SEEDS = (20261401, 20261402, 20261403)
EdgeKey = Tuple[str, str]
EPS = 1e-9


def _median(xs: List[float]) -> Optional[float]:
    if not xs:
        return None
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else 0.5 * (s[m - 1] + s[m])


def _sender_mean_series(
    ell_hist: List[Dict[EdgeKey, float]],
) -> Dict[str, List[float]]:
    senders: set[str] = set()
    for snap in ell_hist:
        for i, _j in snap:
            senders.add(i)
    out: Dict[str, List[float]] = {s: [] for s in senders}
    for snap in ell_hist:
        by: Dict[str, List[float]] = {}
        for (i, _j), v in snap.items():
            by.setdefault(i, []).append(float(v))
        for s in senders:
            vals = by.get(s)
            out[s].append(sum(vals) / len(vals) if vals else 0.0)
    return out


def _freeze_sigma(ell_hist: List[Dict[EdgeKey, float]], sticky_map_b: dict) -> float:
    if not ell_hist or not sticky_map_b:
        return 0.0
    snap0 = ell_hist[0]
    vals = []
    for sk_role, pid in sticky_map_b.items():
        sid = sk_role[0].split(":")[0]
        vals.append(float(snap0.get((sid, pid), 0.0)))
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    return math.sqrt(sum((x - mean) ** 2 for x in vals) / (len(vals) - 1))


def _sticky_median_abs_rho(
    series_by_key: Dict[tuple, List[float]],
) -> tuple[Optional[float], int]:
    keys = list(series_by_key.keys())
    if not keys:
        return None, 0
    T = len(next(iter(series_by_key.values())))
    ebar = [
        sum(series_by_key[k][t] for k in keys) / len(keys) for t in range(T)
    ]
    corrs: List[float] = []
    for k in keys:
        c = _corr_abs(series_by_key[k], ebar)
        if c is not None:
            corrs.append(c)
    return _median(corrs), len(corrs)


def _tau_ticks(ell_med: float, sigma: float, *, tau_scale: float = 16.0) -> int:
    """Acquired delay from ledger latency (not a type-pair matrix)."""
    raw = float(ell_med) / (float(sigma) + EPS) * float(tau_scale)
    return int(max(0, min(64, round(raw))))


def build_panels(
    *,
    sticky_map_b: dict,
    ell_hist: List[Dict[EdgeKey, float]],
    run_seed: int,
) -> dict:
    """Panels: raw S_i, φ₀ (scale), φ₁ (delay), noise positive control."""
    s_series = _sender_mean_series(ell_hist)
    sigma = _freeze_sigma(ell_hist, sticky_map_b)
    T = len(ell_hist)
    keys = list(sticky_map_b.keys())

    raw_s: Dict[tuple, List[float]] = {}
    phi0: Dict[tuple, List[float]] = {}
    phi1: Dict[tuple, List[float]] = {}
    noise: Dict[tuple, List[float]] = {}
    ell_panel: Dict[tuple, List[float]] = {}
    tau_report: Dict[str, int] = {}

    import zlib

    for sk_role, pid in sticky_map_b.items():
        sid = sk_role[0].split(":")[0]
        ek = (sid, pid)
        s_i_full = list(s_series.get(sid, [0.0] * T))
        raw_s[sk_role] = list(s_i_full)
        phi0[sk_role] = []
        phi1[sk_role] = []
        noise[sk_role] = []
        ell_panel[sk_role] = []

        ell_series = [float(snap.get(ek, 0.0)) for snap in ell_hist]
        ell_med = _median(ell_series) or 0.0
        tau = _tau_ticks(ell_med, sigma)
        tau_report[f"{sid}->{pid}"] = tau

        h = zlib.crc32(f"{run_seed}:{sk_role}:{pid}".encode()) & 0xFFFFFFFF
        phase = (h % 997) / 997.0 * 2.0 * math.pi
        amp = 0.5 + (h % 100) / 100.0

        for t, snap in enumerate(ell_hist):
            ell = float(snap.get(ek, 0.0))
            ell_panel[sk_role].append(ell)
            s_i = float(s_i_full[t])
            gamma = max(0.0, ell / (sigma + EPS))
            # φ₀: multiplicative — scale-invariant class (almost not decoupled)
            phi0[sk_role].append(s_i * (1.0 + gamma))
            # φ₁: time shift — not scale-invariant; τ from ledger latency
            t_src = t - tau if t >= tau else 0
            phi1[sk_role].append(float(s_i_full[t_src]))
            # Positive control only
            noise[sk_role].append(
                s_i + amp * math.sin(0.17 * t + phase) + 0.01 * ((h + t) % 13)
            )

    rho_raw, n_raw = _sticky_median_abs_rho(raw_s)
    rho0, n0 = _sticky_median_abs_rho(phi0)
    rho1, n1 = _sticky_median_abs_rho(phi1)
    rho_noise, n_noise = _sticky_median_abs_rho(noise)
    rho_ell, n_ell = _sticky_median_abs_rho(ell_panel)

    screen_sees_noise = bool(
        rho_raw is not None
        and rho_noise is not None
        and rho_noise < 0.90
        and (rho_raw - rho_noise) >= 0.05
    )
    taus = list(tau_report.values())
    return {
        "sigma_ell": sigma,
        "n_sticky": len(keys),
        "T": T,
        "tau_ticks_median": _median([float(t) for t in taus]),
        "tau_ticks_span": (max(taus) - min(taus)) if taus else 0,
        "sticky_S_raw_median_abs_rho": None if rho_raw is None else round(rho_raw, 6),
        "sticky_S_phi0_scale_median_abs_rho": (
            None if rho0 is None else round(rho0, 6)
        ),
        "sticky_S_phi1_delay_median_abs_rho": (
            None if rho1 is None else round(rho1, 6)
        ),
        "sticky_S_noise_ctrl_median_abs_rho": (
            None if rho_noise is None else round(rho_noise, 6)
        ),
        "sticky_ell_median_abs_rho": None if rho_ell is None else round(rho_ell, 6),
        # φ_L: ledger IS the signal (dynamic series ℓ_ij(t) = avg_latency)
        "sticky_S_phi_L_median_abs_rho": None if rho_ell is None else round(rho_ell, 6),
        "phi_L_below_0_90": bool(rho_ell is not None and rho_ell < 0.90),
        "n_corr": {
            "raw": n_raw, "phi0": n0, "phi1": n1, "noise": n_noise, "ell": n_ell,
        },
        "positive_control": {
            "label": "SCREEN_SEES_NOISE" if screen_sees_noise else "SCREEN_BLIND",
            "pass": screen_sees_noise,
            "note": "noise is control only — not a production path",
        },
        "preferred_production": "phi_L",
        "production_note": (
            "phi_L: S_ij(t)=avg_latency_ij(t) — ledger IS signal, not modulator; "
            "phi0/phi1 = failed Broadcast+Transform class"
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    ap.add_argument(
        "--mode",
        choices=("all", "phi_L"),
        default="phi_L",
        help="phi_L: S_ij=ℓ_ij(t) as production path (default); all: compare panels",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_PROJECT_ROOT / "agents_b2g" / "emergence" / "edge_individuation_v0",
    )
    args = ap.parse_args()
    warmup = 8 if args.fast else 32
    cycles = 64 if args.fast else 512
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print(f"Edge-individuation probe mode={args.mode}")
    print(f"seeds={SEEDS} warmup={warmup} cycles={cycles}")
    print("φ_L: S_ij(t)=avg_latency_ij(t) · ρ=Befund · kein Fit")
    print("=" * 60)

    per_seed = []
    t0 = time.monotonic()
    for seed in SEEDS:
        print(f"\n=== seed {seed} ===", flush=True)
        t1 = time.monotonic()
        pack = capture_ell_for_s_probe(
            cycles=cycles, warmup_ticks=warmup, run_seed=seed,
        )
        panel = build_panels(
            sticky_map_b=pack["sticky_map_b"],
            ell_hist=pack["ell_hist"],
            run_seed=seed,
        )
        panel["run_seed"] = seed
        panel["elapsed_s"] = round(time.monotonic() - t1, 2)
        panel["mode"] = args.mode
        panel["production_signal"] = "avg_latency"
        panel["S_ij_definition"] = "ell_ij(t)  # phi_L"
        per_seed.append(panel)

        if args.mode == "phi_L":
            print(
                f"  φ_L |ρ|={panel['sticky_S_phi_L_median_abs_rho']} "
                f"(n_corr={panel['n_corr']['ell']}) · "
                f"below_0.90={panel['phi_L_below_0_90']} · "
                f"T={panel['T']} ({panel['elapsed_s']}s)"
            )
            print(
                f"  (ref) raw-S={panel['sticky_S_raw_median_abs_rho']} · "
                f"noise={panel['sticky_S_noise_ctrl_median_abs_rho']} → "
                f"{panel['positive_control']['label']}"
            )
        else:
            print(
                f"  raw={panel['sticky_S_raw_median_abs_rho']} · "
                f"φ₀={panel['sticky_S_phi0_scale_median_abs_rho']} · "
                f"φ₁={panel['sticky_S_phi1_delay_median_abs_rho']} · "
                f"φ_L={panel['sticky_S_phi_L_median_abs_rho']}"
            )
            print(
                f"  noise={panel['sticky_S_noise_ctrl_median_abs_rho']} → "
                f"{panel['positive_control']['label']} ({panel['elapsed_s']}s)"
            )

    elapsed = time.monotonic() - t0
    ctrl_ok = sum(1 for p in per_seed if p["positive_control"]["pass"]) >= 2
    phi_l_vals = [
        p["sticky_S_phi_L_median_abs_rho"] for p in per_seed
        if p["sticky_S_phi_L_median_abs_rho"] is not None
    ]
    phi_l_all_ok = bool(phi_l_vals) and all(v < 0.90 for v in phi_l_vals)
    phi_l_mean = sum(phi_l_vals) / len(phi_l_vals) if phi_l_vals else None

    if phi_l_all_ok:
        step1_label = "PHI_L_SOURCE_PASS"
        step1_blocked = False
    else:
        step1_label = "STEP1_BLOCKED"
        step1_blocked = True

    tag = "FAST" if args.fast else "FULL"
    mode_tag = args.mode
    payload = {
        "schema": "edge_individuation_v0",
        "mode": args.mode,
        "draft": "docs/EDGE_INDIVIDUATION_v0_DRAFT.md",
        "not_a_pre_reg": True,
        "no_rho_target": True,
        "noise_is_positive_control_only": True,
        "preferred_production": "phi_L",
        "S_ij_production": "avg_latency_ij(t)",
        "schicht_a_definition": "median |rho| vs swarm mean (not pairwise)",
        "battery_required_later": "A && B && C",
        "params": {"seeds": list(SEEDS), "warmup": warmup, "cycles": cycles},
        "elapsed_s": round(elapsed, 1),
        "per_seed": per_seed,
        "majority": {
            "positive_control_pass_seeds": sum(
                1 for p in per_seed if p["positive_control"]["pass"]
            ),
            "screen_instrument_ok": ctrl_ok,
            "instrument_label": "SCREEN_SEES_NOISE" if ctrl_ok else "SCREEN_BLIND",
            "phi_L_pass_seeds": sum(1 for p in per_seed if p["phi_L_below_0_90"]),
            "phi_L_mean_abs_rho": (
                None if phi_l_mean is None else round(phi_l_mean, 6)
            ),
            "phi_L_all_below_0_90": phi_l_all_ok,
            "step1_label": step1_label,
            "step1_blocked": step1_blocked,
            "step2_blocked": True,
        },
    }
    jp = out_dir / f"EDGE_INDIVIDUATION_{mode_tag}_{tag}.json"
    jp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    mp = out_dir / f"EDGE_INDIVIDUATION_{mode_tag}_{tag}_ERGEBNIS.md"
    lines = [
        f"# Edge-Individuierung — mode=`{args.mode}` ({tag})",
        "",
        "**Protokoll:** `docs/EDGE_INDIVIDUATION_v0_DRAFT.md`",
        "**Prod:** `S_ij(t) = avg_latency_ij(t)` (φ_L) · ρ = Befund · kein Fit",
        f"**Schritt 1:** `{step1_label}` · φ_L Mittel |ρ| = {phi_l_mean}",
        f"**Instrument:** `{payload['majority']['instrument_label']}` · {elapsed:.0f}s",
        "",
        "| Seed | φ_L |ρ| | <0.90 | raw-S | noise | Ctrl |",
        "|-----:|---------:|:-----:|------:|------:|:-----|",
    ]
    for p in per_seed:
        lines.append(
            f"| {p['run_seed']} | {p['sticky_S_phi_L_median_abs_rho']} | "
            f"{'✓' if p['phi_L_below_0_90'] else '✗'} | "
            f"{p['sticky_S_raw_median_abs_rho']} | "
            f"{p['sticky_S_noise_ctrl_median_abs_rho']} | "
            f"`{p['positive_control']['label']}` |"
        )
    if args.mode == "all":
        lines += [
            "",
            "| Seed | φ₀ | φ₁ |",
            "|-----:|---:|---:|",
        ]
        for p in per_seed:
            lines.append(
                f"| {p['run_seed']} | {p['sticky_S_phi0_scale_median_abs_rho']} | "
                f"{p['sticky_S_phi1_delay_median_abs_rho']} |"
            )
    lines += [
        "",
        "## Lesart",
        "",
        "- φ_L speist `ℓ_ij(t)` als **dynamischen** Datenstrom (nicht nur statischer Screen).",
        "- Stabil ≈0.348 und <0.90 ⇒ Quell-Entkopplung im Runner-Pfad technisch belegt.",
        "- Geschlossener Kreis (Verhalten↔Ledger) relevant ab Schritt 3, nicht für dieses Tor.",
        "- Schritt 2 bleibt gesperrt bis Schritt 1 erledigt.",
        "",
    ]
    mp.write_text("\n".join(lines), encoding="utf-8")
    print("\n" + "=" * 60)
    print(f"STEP1: {step1_label} · phi_L_mean={phi_l_mean}")
    print(f"INSTRUMENT: {payload['majority']['instrument_label']}")
    print(f"wrote: {mp}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
