#!/usr/bin/env python3
"""KOPPLUNG_EIJ_v1 — I1-Edge only (BINDEND). No κ-sweep. No historical data reuse."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "agents_b2g" / "emergence"))
sys.path.insert(0, str(REPO))

from edge_capture import capture_edge_i1  # noqa: E402


def main() -> int:
    out_dir = Path(os.environ.get("EIJ_I1_OUT", "/tmp/emergence_eij_i1"))
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    result = capture_edge_i1(warmup_ticks=32, cycles=64, run_seed=20261001)
    result["elapsed_s"] = round(time.time() - t0, 2)

    json_path = out_dir / "KOPPLUNG_EIJ_I1.json"
    md_path = out_dir / "KOPPLUNG_EIJ_I1.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")

    crit = result.get("criteria", {})
    lines = [
        "# KOPPLUNG_EIJ_v1 — I1-Edge Ergebnis",
        "",
        "**Pre-Reg:** `docs/KOPPLUNG_EIJ_v1_PREREG.md` (BINDEND)",
        f"**Verdict:** `{result.get('verdict')}` · i1_pass={result.get('i1_pass')}",
        f"**Seed:** {result.get('run_seed')} · warmup=32 · cycles=64 · κ=0 · "
        f"{result['elapsed_s']}s",
        "",
        "| Kriterium | Wert | Schwelle | Pass |",
        "|-----------|-----:|---------:|:----:|",
    ]
    for key in ("I1E-V", "I1E-S", "I1E-U", "I1E-G"):
        c = crit.get(key, {})
        lines.append(
            f"| {key} | {c.get('value')} | {c.get('threshold')} | "
            f"{'YES' if c.get('pass') else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Regel",
            "",
            "I1 PASS → κ-Sweep freigegeben. I1 FAIL → `SIGNAL_BLIND`, kein Sweep.",
            "HARKing: state_screen / kopplung_full / reputation_i1 gesperrt.",
            "",
        ]
    )
    md_path.write_text("\n".join(lines))

    repo_out = REPO / "agents_b2g" / "emergence" / "eij_i1"
    try:
        repo_out.mkdir(parents=True, exist_ok=True)
        (repo_out / json_path.name).write_text(json_path.read_text())
        (repo_out / md_path.name).write_text(md_path.read_text())
    except OSError as e:
        print(f"WARN repo copy: {e}", file=sys.stderr)

    print(
        json.dumps(
            {
                k: result[k]
                for k in ("verdict", "i1_pass", "criteria", "elapsed_s", "n_sticky_edges")
                if k in result
            },
            indent=2,
        )
    )
    print(f"wrote {md_path}")
    return 0 if result.get("i1_pass") else 2


if __name__ == "__main__":
    raise SystemExit(main())
