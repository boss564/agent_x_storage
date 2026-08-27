#!/usr/bin/env python3
"""Phase 4A — synthetic datagen smoke (PREFILTER_DATAGEN_PASS).

Usage:
  PYTHONPATH=. python3 scripts/test_prefilter_datagen.py
  make raas-prefilter-datagen
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.generate_prefilter_synthetic_data import (  # noqa: E402
    FEATURE_COLS,
    generate_rows,
    write_outputs,
)


def main() -> int:
    print("Phase 4A prefilter datagen smoke")
    print("=" * 60)
    failed = 0
    out = _ROOT / "data" / "raas" / "sandbox" / "prefilter_synth" / "smoke"

    a = generate_rows(12, seed=20260827, label_mode="severity_proxy")
    b = generate_rows(12, seed=20260827, label_mode="severity_proxy")
    if [r["sample_id"] for r in a] != [r["sample_id"] for r in b]:
        print("  FAIL  determinism sample_id")
        failed += 1
    else:
        print("  PASS  determinism (same seed → same sample_ids)")

    if any(r.get("live_execution") is not False for r in a):
        print("  FAIL  live_execution must be false")
        failed += 1
    else:
        print("  PASS  live_execution=false")

    kinds = {r["scenario_kind"] for r in a}
    if not kinds.intersection({"LATENCY_SPIKE", "STALE_PRICE"}):
        print("  FAIL  expected MEV+Oracle kinds")
        failed += 1
    else:
        print(f"  PASS  kinds present ({len(kinds)})")

    paths = write_outputs(a, out)
    with open(paths["csv"], encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        if list(cols) != FEATURE_COLS:
            print("  FAIL  CSV columns mismatch")
            failed += 1
        else:
            print("  PASS  CSV feature columns")

    # Generator must not claim to be a signing prefilter service
    for r in a:
        if "envelope_id" in r or "egress_seal" in r:
            print("  FAIL  decision/signing fields in training row")
            failed += 1
            break
    else:
        print("  PASS  no envelope/seal fields in rows")

    # Path under sandbox
    if "sandbox/prefilter_synth" not in paths["jsonl"].replace("\\", "/"):
        print("  FAIL  output not under sandbox")
        failed += 1
    else:
        print("  PASS  output under D2 sandbox path")

    manifest = json.loads(Path(paths["manifest"]).read_text(encoding="utf-8"))
    if manifest.get("n") != 12:
        print("  FAIL  manifest n")
        failed += 1
    else:
        print("  PASS  manifest")

    verdict = "PREFILTER_DATAGEN_PASS" if failed == 0 else "PREFILTER_DATAGEN_FAIL"
    print("=" * 60)
    print(f"VERDICT: {verdict}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
