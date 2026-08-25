#!/usr/bin/env python3
"""Probe: is S_i globally synchronized before any R transform?

docs/R_IJ_SCREEN_v0_DRAFT.md — topology/common-input check (not a Pre-Reg).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "agents_b2g" / "emergence"))

from kanten_ledger import _corr_abs  # noqa: E402
from s_i_probe_capture import capture_ell_for_s_probe  # noqa: E402

SEEDS = (20261401, 20261402, 20261403)
EdgeKey = Tuple[str, str]


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


def probe_s_commonality(
    *,
    sticky_map_b: dict,
    ell_hist: List[Dict[EdgeKey, float]],
) -> dict:
    s_series = _sender_mean_series(ell_hist)
    agents = sorted(s_series.keys())
    T = len(ell_hist)
    if T < 2 or len(agents) < 2:
        return {"error": "too_short", "n_agents": len(agents), "T": T}

    sbar = [
        sum(s_series[a][t] for a in agents) / len(agents) for t in range(T)
    ]
    rho_vs_bar: List[float] = []
    for a in agents:
        c = _corr_abs(s_series[a], sbar)
        if c is not None:
            rho_vs_bar.append(c)

    pair_rhos: List[float] = []
    for i, a in enumerate(agents):
        for b in agents[i + 1 :]:
            c = _corr_abs(s_series[a], s_series[b])
            if c is not None:
                pair_rhos.append(c)

    sticky_s: Dict[tuple, List[float]] = {}
    for sk_role, pid in sticky_map_b.items():
        sid = sk_role[0].split(":")[0]
        sticky_s[sk_role] = list(s_series.get(sid, [0.0] * T))

    keys = list(sticky_s.keys())
    ebar = [
        sum(sticky_s[k][t] for k in keys) / len(keys) for t in range(T)
    ] if keys else []
    sticky_rhos: List[float] = []
    for k in keys:
        c = _corr_abs(sticky_s[k], ebar)
        if c is not None:
            sticky_rhos.append(c)

    edge_series: Dict[tuple, List[float]] = {k: [] for k in keys}
    for snap in ell_hist:
        for sk_role, pid in sticky_map_b.items():
            sid = sk_role[0].split(":")[0]
            edge_series[sk_role].append(float(snap.get((sid, pid), 0.0)))
    ell_bar = [
        sum(edge_series[k][t] for k in keys) / len(keys) for t in range(T)
    ] if keys else []
    ell_rhos: List[float] = []
    for k in keys:
        c = _corr_abs(edge_series[k], ell_bar)
        if c is not None:
            ell_rhos.append(c)

    med_s = _median(rho_vs_bar)
    med_pair = _median(pair_rhos)
    med_sticky_s = _median(sticky_rhos)
    med_ell = _median(ell_rhos)
    common = bool(med_sticky_s is not None and med_sticky_s >= 0.95)

    return {
        "n_agents": len(agents),
        "n_sticky": len(keys),
        "T": T,
        "median_abs_rho_S_vs_Sbar": None if med_s is None else round(med_s, 6),
        "median_abs_rho_S_pairwise": (
            None if med_pair is None else round(med_pair, 6)
        ),
        "median_abs_rho_sticky_S_vs_ebar": (
            None if med_sticky_s is None else round(med_sticky_s, 6)
        ),
        "median_abs_rho_sticky_ell_vs_ebar": (
            None if med_ell is None else round(med_ell, 6)
        ),
        "n_corr_S": len(rho_vs_bar),
        "n_corr_pair": len(pair_rhos),
        "n_corr_sticky_S": len(sticky_rhos),
        "n_corr_ell": len(ell_rhos),
        "common_input": common,
        "label": "S_COMMON" if common else "S_DIFFERENTIATED",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_PROJECT_ROOT / "agents_b2g" / "emergence" / "r_ij_screen_v0",
    )
    args = ap.parse_args()
    warmup = 8 if args.fast else 32
    cycles = 64 if args.fast else 512
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("S_i commonality probe (vor R-Transform · kein Pre-Reg)")
    print(f"seeds={SEEDS} warmup={warmup} cycles={cycles}")
    print("=" * 60)

    per_seed = []
    t0 = time.monotonic()
    for seed in SEEDS:
        print(f"\n=== seed {seed} ===", flush=True)
        t1 = time.monotonic()
        pack = capture_ell_for_s_probe(
            cycles=cycles, warmup_ticks=warmup, run_seed=seed,
        )
        probe = probe_s_commonality(
            sticky_map_b=pack["sticky_map_b"],
            ell_hist=pack["ell_hist"],
        )
        probe["run_seed"] = seed
        probe["elapsed_s"] = round(time.monotonic() - t1, 2)
        per_seed.append(probe)
        print(
            f"  S vs S̄ |ρ|={probe['median_abs_rho_S_vs_Sbar']} · "
            f"pairwise={probe['median_abs_rho_S_pairwise']}"
        )
        print(
            f"  sticky-S |ρ|={probe['median_abs_rho_sticky_S_vs_ebar']} · "
            f"sticky-ℓ |ρ|={probe['median_abs_rho_sticky_ell_vs_ebar']} → "
            f"{probe['label']} ({probe['elapsed_s']}s)"
        )

    maj = Counter(p["label"] for p in per_seed).most_common(1)[0][0]
    elapsed = time.monotonic() - t0
    implication = (
        "If S_COMMON: bottleneck = shared input / star fan-out; "
        "no reaction f_i can pass Schicht A. Next strand = topology, "
        "not another R-screen."
    )
    payload = {
        "schema": "s_i_commonality_probe",
        "draft": "docs/R_IJ_SCREEN_v0_DRAFT.md",
        "not_a_pre_reg": True,
        "params": {"seeds": list(SEEDS), "warmup": warmup, "cycles": cycles},
        "elapsed_s": round(elapsed, 1),
        "per_seed": per_seed,
        "majority_label": maj,
        "implication": implication,
    }
    tag = "FAST" if args.fast else "FULL"
    jp = out_dir / f"S_I_COMMONALITY_{tag}.json"
    jp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    mp = out_dir / f"S_I_COMMONALITY_{tag}_ERGEBNIS.md"
    lines = [
        f"# S_i-Commonality Probe ({tag})",
        "",
        "**Kein Pre-Reg.** `|ρ|` von `S_i` *vor* jeder R-Transformation.",
        f"**Majority:** `{maj}` · {elapsed:.0f}s",
        "",
        "| Seed | S vs S̄ | pairwise | sticky-S | sticky-ℓ | Label |",
        "|-----:|--------:|---------:|---------:|---------:|:------|",
    ]
    for p in per_seed:
        lines.append(
            f"| {p['run_seed']} | {p['median_abs_rho_S_vs_Sbar']} | "
            f"{p['median_abs_rho_S_pairwise']} | "
            f"{p['median_abs_rho_sticky_S_vs_ebar']} | "
            f"{p['median_abs_rho_sticky_ell_vs_ebar']} | `{p['label']}` |"
        )
    lines += ["", "## Lesart", "", implication, ""]
    mp.write_text("\n".join(lines), encoding="utf-8")
    print("\n" + "=" * 60)
    print(f"MAJORITY: {maj}")
    print(f"wrote: {mp}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
