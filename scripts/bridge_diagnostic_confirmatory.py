#!/usr/bin/env python3
"""Confirmatory Bridge Diagnostic run (Pre-Reg bindend).

Requires: bridge_diagnostic_informativity_gate.json with status=PASS
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents_b2g.diagnostic.confirmatory import run_confirmatory


def main() -> int:
    parser = argparse.ArgumentParser(description="Bridge Diagnostic confirmatory pipeline")
    parser.add_argument("--input-dir", type=Path, default=ROOT)
    parser.add_argument(
        "--informativity-gate",
        type=Path,
        default=ROOT / "bridge_diagnostic_informativity_gate.json",
    )
    parser.add_argument(
        "--integrity-gate",
        type=Path,
        default=ROOT / "bridge_stufe_a_v3_integrity_gate.json",
    )
    parser.add_argument(
        "--v3-ergebnis",
        type=Path,
        default=ROOT / "bridge_stufe_a_v3_ergebnis.json",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT)
    parser.add_argument("--skip-ex-post", action="store_true", default=True)
    args = parser.parse_args()

    print("Confirmatory diagnostic — Ablation + Permutation (observed CTE only)", flush=True)
    result = run_confirmatory(
        input_dir=args.input_dir,
        informativity_gate_path=args.informativity_gate,
        integrity_gate_path=args.integrity_gate,
        v3_ergebnis_path=args.v3_ergebnis,
        skip_ex_post=args.skip_ex_post,
        output_dir=args.output_dir,
    )
    print(f"perm_fragment={result['phase1']['perm_fragment']}", flush=True)
    print(f"roles={result['roles']}", flush=True)
    print(f"n_unclassified={result['n_unclassified']}", flush=True)
    print(f"final_verdict={result['final_verdict']}", flush=True)
    print(json.dumps({"final_verdict": result["final_verdict"], "roles": result["roles"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
