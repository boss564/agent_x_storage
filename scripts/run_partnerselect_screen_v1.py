#!/usr/bin/env python3
"""PARTNERSELECT_SCREEN_v1 — SCREEN_BINDEND runner.

κ=0 · Seeds {20261101,20261102,20261103} · warmup=32 · cycles=512
Docs: docs/PARTNERSELECT_SCREEN_v1_DRAFT.md

Kein Studien-Verdict. Trennregel: Kandidaten nicht auf diesem Datensatz testen.
Versiegelte state_screen / E_ij-Artefakte werden nicht angefasst.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Set

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "agents_b2g" / "emergence"))
sys.path.insert(0, str(REPO))

from adapter_agentx import capture  # noqa: E402
from partner_select import permute_sticky_map  # noqa: E402
from state_space_screen import screen_state_matrix  # noqa: E402

SEEDS = (20261101, 20261102, 20261103)
WARMUP = 32
CYCLES = 512
KAPPA = 0.0
MAE_MIN = 0.05
RHO_MAX = 0.90
# Near-miss bands (§5 DRAFT)
NEAR_MAE_LO, NEAR_MAE_HI = 0.03, 0.05
NEAR_RHO_LO, NEAR_RHO_HI = 0.90, 0.95
MAJORITY = 2  # ≥2/3 seeds


def _near_miss_dims(rows: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for r in rows:
        if r.get("static_over_window"):
            continue
        if r["flags"].get("candidate"):
            continue
        mae = float(r.get("mae_scaled") or 0.0)
        rho = r.get("median_abs_rho")
        near_s = NEAR_MAE_LO <= mae < NEAR_MAE_HI
        near_g = (
            rho is not None
            and NEAR_RHO_LO < float(rho) <= NEAR_RHO_HI
        )
        if near_s or near_g:
            out.append(r["dimension"])
    return out


def _seed_label(candidates: List[str], near: List[str]) -> str:
    if candidates:
        return "SOME_CANDIDATES"
    if near:
        return "NONE_CLOSE"
    return "NONE_CLEAR"


def _aggregate(per_seed: List[Dict[str, Any]]) -> Dict[str, Any]:
    cand_counts: Counter[str] = Counter()
    near_counts: Counter[str] = Counter()
    for s in per_seed:
        for d in s["candidates"]:
            cand_counts[d] += 1
        for d in s["near_miss"]:
            near_counts[d] += 1

    majority_cands = sorted(
        d for d, n in cand_counts.items() if n >= MAJORITY
    )
    majority_near = sorted(
        d
        for d, n in near_counts.items()
        if n >= MAJORITY and d not in majority_cands
    )

    if majority_cands:
        outcome = "SOME_CANDIDATES"
    elif majority_near:
        outcome = "NONE_CLOSE"
    else:
        outcome = "NONE_CLEAR"

    return {
        "majority_threshold": MAJORITY,
        "n_seeds": len(per_seed),
        "candidate_seed_counts": dict(cand_counts),
        "near_miss_seed_counts": dict(near_counts),
        "candidates_majority": majority_cands,
        "near_miss_majority": majority_near,
        "outcome": outcome,
    }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    out_tmp = Path(
        os.environ.get("PARTNERSELECT_OUT", "/tmp/partnerselect_screen_v1")
    )
    out_repo = REPO / "agents_b2g" / "emergence" / "partnerselect_screen_v1"
    out_tmp.mkdir(parents=True, exist_ok=True)
    out_repo.mkdir(parents=True, exist_ok=True)

    t_all = time.time()
    per_seed: List[Dict[str, Any]] = []

    for seed in SEEDS:
        t0 = time.time()
        print(f"=== seed {seed} capture κ={KAPPA} warmup={WARMUP} cycles={CYCLES} ===")
        tr = capture(
            cycles=CYCLES,
            full=True,
            kappa=KAPPA,
            warmup_ticks=WARMUP,
            arm="B",
            run_seed=seed,
            honor_track=True,
            honor_coupling=False,
        )
        map_b = getattr(tr, "frozen_map", None) or {}
        map_c = permute_sticky_map(map_b, seed=seed)
        report = screen_state_matrix(
            tr.states,
            getattr(tr, "state_keys", []),
            tr.agents,
            map_b,
            map_c,
            mae_min=MAE_MIN,
            rho_max=RHO_MAX,
        )
        near = _near_miss_dims(report["dimensions"])
        label = _seed_label(report["candidates"], near)
        elapsed = round(time.time() - t0, 2)
        entry = {
            "run_seed": seed,
            "warmup": WARMUP,
            "cycles": CYCLES,
            "kappa": KAPPA,
            "elapsed_s": elapsed,
            "n_messages": len(tr.messages),
            "D_screened": report["D_screened"],
            "state_keys": list(getattr(tr, "state_keys", [])),
            "candidates": report["candidates"],
            "near_miss": near,
            "seed_outcome": label,
            "dimensions": report["dimensions"],
            "library_outcome": report["outcome"],
        }
        per_seed.append(entry)
        print(
            f"seed {seed}: {label} candidates={report['candidates']} "
            f"near={near} ({elapsed}s)"
        )

    agg = _aggregate(per_seed)
    payload = {
        "schema": "partnerselect_screen_v1",
        "draft": "docs/PARTNERSELECT_SCREEN_v1_DRAFT.md",
        "status": "SCREEN_BINDEND",
        "not_a_study": True,
        "harking_guard": (
            "Candidates must not be hypothesis-tested on this same dataset. "
            "Follow-up = new Pre-Reg + new seeds/runs. "
            "Sealed state_screen/ and E_ij artifacts remain locked."
        ),
        "params": {
            "seeds": list(SEEDS),
            "warmup": WARMUP,
            "cycles": CYCLES,
            "kappa": KAPPA,
            "mae_min": MAE_MIN,
            "rho_max": RHO_MAX,
            "near_mae": [NEAR_MAE_LO, NEAR_MAE_HI],
            "near_rho": [NEAR_RHO_LO, NEAR_RHO_HI],
            "majority": MAJORITY,
        },
        "aggregation": agg,
        "outcome": agg["outcome"],
        "candidates": agg["candidates_majority"],
        "near_miss": agg["near_miss_majority"],
        "per_seed": per_seed,
        "elapsed_s_total": round(time.time() - t_all, 2),
    }

    json_name = "PARTNERSELECT_SCREEN_v1.json"
    md_name = "PARTNERSELECT_SCREEN_v1.md"
    close_name = "SCREENING_ABSCHLUSS.md"

    json_path = out_tmp / json_name
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    lines = [
        "# PARTNERSELECT_SCREEN_v1 — Ergebnis",
        "",
        "**Status:** SCREEN_BINDEND · kein Studien-Verdict",
        f"**DRAFT:** `docs/PARTNERSELECT_SCREEN_v1_DRAFT.md`",
        f"**Lauf:** seeds={list(SEEDS)} · warmup={WARMUP} · cycles={CYCLES} · κ=0 · "
        f"{payload['elapsed_s_total']}s",
        f"**Outcome-Label:** `{payload['outcome']}`",
        "",
        "**HARKing-Sperre:** Kandidaten nicht auf diesem Datensatz testen. "
        "`state_screen/` und `E_ij`-Artefakte bleiben gesperrt.",
        "",
        "## Aggregation (≥2/3 Seeds)",
        "",
        f"- Kandidaten: `{payload['candidates'] or '(keine)'}`",
        f"- Near-Miss: `{payload['near_miss'] or '(keine)'}`",
        f"- Seed-Counts Kandidaten: `{agg['candidate_seed_counts']}`",
        f"- Seed-Counts Near-Miss: `{agg['near_miss_seed_counts']}`",
        "",
        "## Pro Seed",
        "",
    ]
    for s in per_seed:
        lines.append(
            f"### Seed {s['run_seed']} — `{s['seed_outcome']}` ({s['elapsed_s']}s)"
        )
        lines.append("")
        lines.append(
            "| Dimension | σ_last | MAE_scaled | |ρ| | static | Candidate |"
        )
        lines.append(
            "|-----------|-------:|-----------:|----:|:------:|:---------:|"
        )
        for r in s["dimensions"]:
            rho = r["median_abs_rho"]
            lines.append(
                f"| `{r['dimension']}` | {r['sigma_last']} | {r['mae_scaled']} | "
                f"{rho if rho is not None else '—'} | "
                f"{'yes' if r.get('static_over_window') else ''} | "
                f"{'YES' if r['flags']['candidate'] else 'no'} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Ausgänge (DRAFT §5)",
            "",
            "- `SOME_CANDIDATES` — neue Pre-Reg mit neuer Größe + neuen Läufen",
            "- `NONE_CLOSE` — Transformations-DRAFT möglich, keine Nachjustierung hier",
            "- `NONE_CLEAR` — knotenbasiert keine partnerselektive Größe; Architekturfrage",
            "",
        ]
    )
    md_path = out_tmp / md_name
    md_path.write_text("\n".join(lines))

    close = [
        "# PARTNERSELECT_SCREEN_v1 — Abschluss",
        "",
        f"**Status:** abgeschlossen · **Label:** `{payload['outcome']}` · kein Studien-Verdict",
        f"**DRAFT / Bindung:** `docs/PARTNERSELECT_SCREEN_v1_DRAFT.md` (SCREEN_BINDEND)",
        f"**Parameter:** seeds={list(SEEDS)} · warmup={WARMUP} · cycles={CYCLES} · κ=0",
        f"**Laufzeit gesamt:** {payload['elapsed_s_total']}s",
        "",
        f"**Kandidaten (≥2/3):** {payload['candidates'] or '(keine)'}",
        f"**Near-Miss (≥2/3):** {payload['near_miss'] or '(keine)'}",
        "",
        "## HARKing-Sperre",
        "",
        "- Keine Hypothese auf **diesem** Datensatz testen.",
        "- `state_screen/`, `reputation_i1/`, `eij_*`, `kopplung_full/` bleiben gesperrt.",
        "- Folgestudie = neue Pre-Reg + neue Seeds.",
        "",
    ]
    close_path = out_tmp / close_name
    close_path.write_text("\n".join(close))

    for src in (json_path, md_path, close_path):
        (out_repo / src.name).write_text(src.read_text())

    sums = out_repo / "SHA256SUMS.txt"
    lines_sum = []
    for name in (json_name, md_name, close_name):
        p = out_repo / name
        lines_sum.append(f"{_sha256(p)}  {name}")
    sums.write_text("\n".join(lines_sum) + "\n")

    print(
        json.dumps(
            {
                "outcome": payload["outcome"],
                "candidates": payload["candidates"],
                "near_miss": payload["near_miss"],
                "elapsed_s_total": payload["elapsed_s_total"],
                "out_repo": str(out_repo),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
