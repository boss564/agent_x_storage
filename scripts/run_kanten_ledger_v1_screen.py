#!/usr/bin/env python3
"""KANTEN_LEDGER_v1 acceptance screening (ARCH_BINDEND).

Seeds {20261201,20261202,20261203} · warmup=32 · cycles=512 · κ=0
Docs: docs/KANTEN_LEDGER_v1_DRAFT.md
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "agents_b2g" / "emergence"))
sys.path.insert(0, str(REPO))

from kanten_ledger_capture import capture_ledger  # noqa: E402

SEEDS = (20261201, 20261202, 20261203)
WARMUP = 32
CYCLES = 512
MAJORITY = 2


def _aggregate(per_seed: List[Dict[str, Any]]) -> Dict[str, Any]:
    cand_counts: Counter[str] = Counter()
    near_counts: Counter[str] = Counter()
    for s in per_seed:
        for c in s["candidates"]:
            cand_counts[c] += 1
        for c in s["near_miss"]:
            near_counts[c] += 1
    majority_cands = sorted(d for d, n in cand_counts.items() if n >= MAJORITY)
    majority_near = sorted(
        d
        for d, n in near_counts.items()
        if n >= MAJORITY and d not in majority_cands
    )
    if majority_cands:
        outcome = "LEDGER_SCREEN_PASS"
    elif majority_near:
        outcome = "LEDGER_SCREEN_CLOSE"
    else:
        outcome = "LEDGER_SCREEN_FAIL"
    return {
        "majority_threshold": MAJORITY,
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
    out_tmp = Path(os.environ.get("KANTEN_LEDGER_OUT", "/tmp/kanten_ledger_v1"))
    out_repo = REPO / "agents_b2g" / "emergence" / "kanten_ledger_v1"
    out_tmp.mkdir(parents=True, exist_ok=True)
    out_repo.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    per_seed: List[Dict[str, Any]] = []
    for seed in SEEDS:
        print(f"=== seed {seed} ledger capture ===")
        t1 = time.time()
        result = capture_ledger(cycles=CYCLES, warmup_ticks=WARMUP, run_seed=seed)
        result["elapsed_s"] = round(time.time() - t1, 2)
        per_seed.append(result)
        print(
            f"seed {seed}: pass={result['seed_pass']} "
            f"cand={result['candidates']} near={result['near_miss']} "
            f"({result['elapsed_s']}s, edges={result['n_edges']})"
        )

    agg = _aggregate(per_seed)
    payload = {
        "schema": "kanten_ledger_v1",
        "draft": "docs/KANTEN_LEDGER_v1_DRAFT.md",
        "status": "ARCH_BINDEND",
        "not_a_study_sweep": True,
        "harking_guard": (
            "PASS candidates must not be κ-tested on this dataset. "
            "Follow-up = new Pre-Reg + new seeds. "
            "Sealed E_ij / partnerselect artifacts remain locked."
        ),
        "params": {
            "seeds": list(SEEDS),
            "warmup": WARMUP,
            "cycles": CYCLES,
            "kappa": 0.0,
            "gamma": 0.05,
            "majority": MAJORITY,
            "mae_min": 0.05,
            "rho_max": 0.90,
        },
        "aggregation": agg,
        "outcome": agg["outcome"],
        "candidates": agg["candidates_majority"],
        "near_miss": agg["near_miss_majority"],
        "per_seed": per_seed,
        "elapsed_s_total": round(time.time() - t0, 2),
    }

    json_path = out_tmp / "KANTEN_LEDGER_v1.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    lines = [
        "# KANTEN_LEDGER_v1 — Abnahme-Screening",
        "",
        "**Status:** ARCH_BINDEND · kein κ-Sweep",
        f"**DRAFT:** `docs/KANTEN_LEDGER_v1_DRAFT.md`",
        f"**Lauf:** seeds={list(SEEDS)} · warmup={WARMUP} · cycles={CYCLES} · κ=0 · "
        f"{payload['elapsed_s_total']}s",
        f"**Outcome:** `{payload['outcome']}`",
        "",
        f"**Kandidaten (≥2/3):** `{payload['candidates'] or '(keine)'}`",
        f"**Near-Miss (≥2/3):** `{payload['near_miss'] or '(keine)'}`",
        "",
        "## Pro Seed / Komponente",
        "",
    ]
    for s in per_seed:
        lines.append(f"### Seed {s['run_seed']} ({s['elapsed_s']}s)")
        lines.append("")
        lines.append("| Komponente | MAE | |ρ| | S-S | S-G | Pass | Near |")
        lines.append("|------------|----:|----:|:--:|:--:|:----:|:----:|")
        for c in s["components"]:
            rho = c.get("median_abs_rho")
            fl = c.get("flags", {})
            lines.append(
                f"| `{c['component']}` | {c.get('mae')} | "
                f"{rho if rho is not None else '—'} | "
                f"{'Y' if fl.get('S_S') else 'n'} | "
                f"{'Y' if fl.get('S_G') else 'n'} | "
                f"{'YES' if c.get('pass') else 'no'} | "
                f"{'yes' if fl.get('near_miss') else ''} |"
            )
        lines.append("")

    md_path = out_tmp / "KANTEN_LEDGER_v1.md"
    md_path.write_text("\n".join(lines))

    close = [
        "# KANTEN_LEDGER_v1 — Abschluss",
        "",
        f"**Status:** abgeschlossen · **Label:** `{payload['outcome']}`",
        f"**DRAFT / Bindung:** `docs/KANTEN_LEDGER_v1_DRAFT.md` (ARCH_BINDEND)",
        f"**Parameter:** seeds={list(SEEDS)} · warmup={WARMUP} · cycles={CYCLES} · κ=0 · γ=0.05",
        f"**Laufzeit:** {payload['elapsed_s_total']}s",
        "",
        f"**Kandidaten (≥2/3):** {payload['candidates'] or '(keine)'}",
        f"**Near-Miss (≥2/3):** {payload['near_miss'] or '(keine)'}",
        "",
        "## HARKing-Sperre",
        "",
        "- Kein κ-Sweep auf diesem Datensatz.",
        "- Folgestudie = neue Pre-Reg + neue Seeds.",
        "- `eij_*`, `partnerselect_screen_v1/` bleiben gesperrt.",
        "",
    ]
    if payload["outcome"] == "LEDGER_SCREEN_FAIL":
        close.extend(
            [
                "## Konsequenz FAIL → C",
                "",
                "Gebautes Ledger allein reicht unter S-S/S-G nicht. "
                "Nächster DRAFT: Router/Fan-out, nicht Schwellen-Senkung.",
                "",
            ]
        )
    close_path = out_tmp / "SCREENING_ABSCHLUSS.md"
    close_path.write_text("\n".join(close))

    for src in (json_path, md_path, close_path):
        (out_repo / src.name).write_text(src.read_text())

    sums = []
    for name in ("KANTEN_LEDGER_v1.json", "KANTEN_LEDGER_v1.md", "SCREENING_ABSCHLUSS.md"):
        sums.append(f"{_sha256(out_repo / name)}  {name}")
    (out_repo / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n")

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
