#!/usr/bin/env python3
"""Zustandsraum-Screening (kein Studien-Verdict).

κ=0, Warm-up+Freeze, I1-S/I1-G-Logik über alle Trace-Dimensionen.
Siehe agents_b2g/emergence/state_space_screen.py.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "agents_b2g" / "emergence"))
sys.path.insert(0, str(REPO))

from adapter_agentx import capture  # noqa: E402
from partner_select import permute_sticky_map  # noqa: E402
from state_space_screen import screen_state_matrix  # noqa: E402


def main() -> int:
    out_dir = Path(
        os.environ.get("STATE_SCREEN_OUT", "/tmp/emergence_state_screen")
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    seed = int(os.environ.get("STATE_SCREEN_SEED", "20260901"))
    warmup = 32
    cycles = 64

    t0 = time.time()
    tr = capture(
        cycles=cycles,
        full=True,
        kappa=0.0,
        warmup_ticks=warmup,
        arm="B",
        run_seed=seed,
        honor_track=True,  # include honor / s_honor in state matrix
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
    )
    report["run_seed"] = seed
    report["warmup"] = warmup
    report["cycles"] = cycles
    report["kappa"] = 0.0
    report["elapsed_s"] = round(time.time() - t0, 2)
    report["n_messages"] = len(tr.messages)

    json_path = out_dir / "STATE_SPACE_SCREEN.json"
    md_path = out_dir / "STATE_SPACE_SCREEN.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")

    lines = [
        "# Zustandsraum-Screening (kein Studien-Verdict)",
        "",
        "**Zweck:** Charakterisierung — welche Dimensionen sind unter Partnerpermutation",
        "selektiv und nicht global synchron? Keine Hypothese, keine Pre-Reg.",
        "",
        f"**Lauf:** seed={seed} · warmup={warmup} · cycles={cycles} · κ=0 · "
        f"{report['elapsed_s']}s · D={report['D_screened']}",
        f"**Outcome-Label:** `{report['outcome']}` "
        "(Arbeitsbezeichnung, kein bindendes Verdict)",
        "",
        "**HARKing-Sperre:** Kandidaten aus diesem Lauf nicht im selben Datensatz",
        "als Hypothese testen. Nächste Studie = neuer DRAFT + neue Läufe.",
        "",
        "| Dimension | σ_last | MAE_scaled | |ρ| | static | Candidate |",
        "|-----------|-------:|-----------:|----:|:------:|:---------:|",
    ]
    for r in report["dimensions"]:
        rho = r["median_abs_rho"]
        lines.append(
            f"| `{r['dimension']}` | {r['sigma_last']} | {r['mae_scaled']} | "
            f"{rho if rho is not None else '—'} | "
            f"{'yes' if r.get('static_over_window') else ''} | "
            f"{'YES' if r['flags']['candidate'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            f"**Kandidaten:** {report['candidates'] or '(keine)'}",
            "",
            "## Lesart der drei Ausgänge",
            "",
            "- `SOME_CANDIDATES` — belegte Vorbedingung für eine *neue* Pre-Reg",
            "- `NONE_CLOSE` — evtl. Transformation prüfen (neuer DRAFT), nicht hier nachjustieren",
            "- `NONE_CLEAR` — Hinweis: partnerselektiver Zustand fehlt; Architekturfrage",
            "",
        ]
    )
    md_path.write_text("\n".join(lines))

    repo_out = REPO / "agents_b2g" / "emergence" / "state_screen"
    try:
        repo_out.mkdir(parents=True, exist_ok=True)
        (repo_out / "STATE_SPACE_SCREEN.json").write_text(json_path.read_text())
        (repo_out / "STATE_SPACE_SCREEN.md").write_text(md_path.read_text())
    except OSError as e:
        print(f"WARN repo copy: {e}", file=sys.stderr)

    print(
        json.dumps(
            {
                "outcome": report["outcome"],
                "candidates": report["candidates"],
                "D_screened": report["D_screened"],
                "elapsed_s": report["elapsed_s"],
            },
            indent=2,
        )
    )
    print(f"wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
