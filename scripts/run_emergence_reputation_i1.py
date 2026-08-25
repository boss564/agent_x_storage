#!/usr/bin/env python3
"""KOPPLUNG_REPUTATION_v1 — I1 instrumentationscheck only (BINDEND).

No κ-sweep. No queue-sweep reuse.
Pre-Reg: docs/KOPPLUNG_REPUTATION_v1_PREREG.md §4
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


def main() -> int:
    out_dir = Path(os.environ.get("REPUTATION_I1_OUT", "/tmp/emergence_reputation_i1"))
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    result = capture(
        cycles=64,
        full=True,
        kappa=0.0,
        warmup_ticks=32,
        arm="B",
        run_seed=20260901,
        honor_track=True,
        honor_coupling=False,
        collect_i1=True,
    )
    elapsed = time.time() - t0
    result["elapsed_s"] = round(elapsed, 2)

    json_path = out_dir / "KOPPLUNG_REPUTATION_I1.json"
    md_path = out_dir / "KOPPLUNG_REPUTATION_I1.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")

    crit = result.get("criteria", {})
    lines = [
        "# KOPPLUNG_REPUTATION_v1 — I1 Ergebnis",
        "",
        "**Pre-Reg:** `docs/KOPPLUNG_REPUTATION_v1_PREREG.md` (BINDEND)",
        f"**Verdict:** `{result.get('verdict')}` · i1_pass={result.get('i1_pass')}",
        f"**Seed:** {result.get('run_seed')} · warmup=32 · cycles=64 · κ=0 · {elapsed:.1f}s",
        "",
        "| Kriterium | Wert | Schwelle | Pass |",
        "|-----------|-----:|---------:|:----:|",
    ]
    for key in ("I1-V", "I1-S", "I1-U", "I1-G"):
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
            "Kein Queue-Sweep, keine Nachjustierung der Schwellen.",
            "",
        ]
    )
    md_path.write_text("\n".join(lines))

    # Durable copy into repo if possible
    repo_out = REPO / "agents_b2g" / "emergence" / "reputation_i1"
    try:
        repo_out.mkdir(parents=True, exist_ok=True)
        (repo_out / "KOPPLUNG_REPUTATION_I1.json").write_text(json_path.read_text())
        (repo_out / "KOPPLUNG_REPUTATION_I1.md").write_text(md_path.read_text())
    except OSError as e:
        print(f"WARN repo copy: {e}", file=sys.stderr)

    print(json.dumps({k: result[k] for k in ("verdict", "i1_pass", "criteria", "elapsed_s") if k in result}, indent=2))
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    return 0 if result.get("i1_pass") else 2


if __name__ == "__main__":
    raise SystemExit(main())
