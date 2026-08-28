#!/usr/bin/env python3
"""G1 — Chaos Engineering offline harness (P6-Trading / gate_core)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.chaos_engineering.harness_common import (  # noqa: E402
    MATRIX_PATH,
    REPORT_DIR,
    capture_probe_offline,
    run_matrix,
)

REPORT_PATH = REPORT_DIR / "g1_latest.json"


def main() -> int:
    if not MATRIX_PATH.is_file():
        print(f"CHAOS_G1_FAIL missing config: {MATRIX_PATH}", file=sys.stderr)
        return 1
    report = run_matrix(
        gate_label="G1",
        mode="offline_gate_core",
        capture_fn=capture_probe_offline,
        report_path=REPORT_PATH,
        pass_verdict="CHAOS_G1_PASS",
        fail_verdict="CHAOS_G1_FAIL",
    )
    print(
        json.dumps(
            {
                "verdict": report["verdict"],
                "passed": report["passed"],
                "total": report["total_tests"],
                "report": str(REPORT_PATH),
            }
        )
    )
    return 0 if report["verdict"] == "CHAOS_G1_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
