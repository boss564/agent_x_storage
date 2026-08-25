#!/usr/bin/env python3
"""Run Bridge Diagnostic informativity gate (Pre-Reg §4).

No CTE, no verdict — encoding quality only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents_b2g.diagnostic.informativity_gate import run_informativity_gate


def main() -> int:
    parser = argparse.ArgumentParser(description="Bridge Diagnostic informativity gate")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=ROOT,
        help="Repo root with V3 capture JSONL files",
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
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "bridge_diagnostic_informativity_gate.json",
    )
    args = parser.parse_args()

    result = run_informativity_gate(
        input_dir=args.input_dir,
        integrity_gate_path=args.integrity_gate,
        v3_ergebnis_path=args.v3_ergebnis,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "output": str(args.output),
                "summary": result["summary"],
                "blockers": result["blockers"],
            },
            indent=2,
        )
    )
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
