#!/usr/bin/env python3
"""Quick reciprocity check after ACK/Receipt traffic (engineering gate).

Target: median frac_sticky_via_ledger ≥ 0.3 on ≥2/3 seeds.
No Pre-Reg. No M7 filter change.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "agents_b2g" / "emergence"))

from closed_loop_capture import capture_closed_loop  # noqa: E402
from kanten_ledger import LATENCY_MODE_EWMA  # noqa: E402

SEEDS = (20261721, 20261722, 20261723)
TARGET = 0.3


def main() -> int:
    out_dir = (
        _PROJECT_ROOT
        / "agents_b2g"
        / "emergence"
        / "reciprocity_ack_v0"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    print("=" * 60)
    print("ACK/Receipt reciprocity check (EWMA, no Pre-Reg)")
    print(f"seeds={SEEDS} target median frac_sticky_via_ledger ≥ {TARGET}")
    print("=" * 60)

    for seed in SEEDS:
        t0 = time.monotonic()
        cell = capture_closed_loop(
            cycles=128,
            warmup_ticks=32,
            run_seed=seed,
            latency_mode=LATENCY_MODE_EWMA,
        )
        rec = cell.get("reciprocity") or {}
        elapsed = round(time.monotonic() - t0, 2)
        frac = float(rec.get("frac_sticky_via_ledger") or 0.0)
        rows.append(
            {
                "run_seed": seed,
                "frac_sticky": rec.get("frac_sticky"),
                "frac_sticky_via_ledger": frac,
                "n_sticky": rec.get("n_sticky"),
                "n_reciprocal_sticky_via_ledger": rec.get(
                    "n_reciprocal_sticky_via_ledger"
                ),
                "frac_ledger_edges_with_reverse": rec.get(
                    "frac_ledger_edges_with_reverse"
                ),
                "elapsed_s": elapsed,
            }
        )
        print(
            f"  seed={seed} frac_sticky={rec.get('frac_sticky')} "
            f"via_led={frac} n_sticky={rec.get('n_sticky')} "
            f"n_rec={rec.get('n_reciprocal_sticky_via_ledger')} ({elapsed}s)"
        )

    fracs = [r["frac_sticky_via_ledger"] for r in rows]
    med = float(statistics.median(fracs))
    n_ge = sum(1 for f in fracs if f >= TARGET)
    gate = "PASS" if med >= TARGET and n_ge >= 2 else "FAIL"
    summary = {
        "gate": gate,
        "target": TARGET,
        "median_frac_sticky_via_ledger": med,
        "n_seeds_ge_target": n_ge,
        "n_seeds": len(rows),
        "rows": rows,
        "note": (
            "ACK/Receipt on OFFER/BHO_PROOF/SETTLEMENT; "
            "sticky role=receipt for reverse edges"
        ),
    }
    out_path = out_dir / "RECIPROCITY_ACK_CHECK.json"
    out_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    md = out_dir / "RECIPROCITY_ACK_CHECK.md"
    md.write_text(
        "\n".join(
            [
                "# ACK/Receipt Reziprozitäts-Check",
                "",
                f"**Gate:** `{gate}` · Median `frac_sticky_via_ledger` = {med}",
                f"**Ziel:** ≥ {TARGET} auf ≥2/3 Seeds (hier {n_ge}/{len(rows)})",
                "",
                "| Seed | frac_sticky | via_ledger | n_sticky | n_rec |",
                "|------|-------------|------------|----------|-------|",
                *[
                    f"| {r['run_seed']} | {r['frac_sticky']} | "
                    f"{r['frac_sticky_via_ledger']} | {r['n_sticky']} | "
                    f"{r['n_reciprocal_sticky_via_ledger']} |"
                    for r in rows
                ],
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print("=" * 60)
    print(f"GATE={gate} median={med} seeds≥{TARGET}: {n_ge}/{len(rows)}")
    print(f"wrote {out_path}")
    return 0 if gate == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
