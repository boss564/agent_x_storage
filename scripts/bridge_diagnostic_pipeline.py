#!/usr/bin/env python3
"""CLI stub for Bridge Diagnostic (Wave 38).

Confirmatory runs (CTE, permutation verdict) are blocked until informativity gate
(Pre-reg §4) is implemented. Skeleton accepts --help and structural dry-run only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents_b2g.diagnostic.diagnostic_orchestrator import DiagnosticPipelineOrchestrator


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bridge Filter Diagnostic pipeline (Wave 38 skeleton)"
    )
    parser.add_argument(
        "--output",
        default="bridge_diagnostic_ergebnis.json",
        help="Output JSON path (skeleton metadata only)",
    )
    parser.add_argument(
        "--skip-ex-post",
        action="store_true",
        default=True,
        help="Skip ex-post phase (default in skeleton)",
    )
    parser.add_argument(
        "--confirmatory",
        action="store_true",
        help="Blocked in skeleton — requires informativity gate + explicit release",
    )
    parser.add_argument("--user-id", default="diagnostic")
    args = parser.parse_args()

    orch = DiagnosticPipelineOrchestrator(user_id=args.user_id)
    result = orch.run_full_diagnosis(
        {
            "user_id": args.user_id,
            "domain": "bridge_cte",
            "pre_reg": "docs/BRIDGE_DIAGNOSTIC_PREREG.md",
            "options": {
                "skip_ex_post": args.skip_ex_post,
                "confirmatory": args.confirmatory,
            },
        }
    )

    out = Path(args.output)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "job_id": result["job_id"], "output": str(out)}))

    if args.confirmatory:
        return 2
    return 0 if result["status"] in ("completed", "started") else 1


if __name__ == "__main__":
    raise SystemExit(main())
