#!/usr/bin/env python3
"""Phase 4A — synthetic datagen smoke (PREFILTER_DATAGEN_PASS).

Usage:
  PYTHONPATH=. python3 scripts/test_prefilter_datagen.py
  make raas-prefilter-datagen
"""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load_gen():
    path = _ROOT / "scripts" / "generate_prefilter_synthetic_data.py"
    spec = importlib.util.spec_from_file_location("prefilter_datagen", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("Phase 4A prefilter datagen smoke")
    print("=" * 60)
    failed = 0
    gen = _load_gen()
    out = _ROOT / "data" / "raas" / "sandbox" / "prefilter_synth" / "smoke"

    a = gen.generate_rows(12, seed=20260827, label_mode="severity_proxy", profile="mixed")
    b = gen.generate_rows(12, seed=20260827, label_mode="severity_proxy", profile="mixed")
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

    extremes = gen.generate_rows(
        14, seed=20260827, label_mode="severity_proxy", profile="extremes"
    )
    ek = {r["scenario_kind"] for r in extremes}
    if not {"DEPEG_SIM", "FLASH_CRASH", "LATENCY_SPIKE"}.issubset(ek):
        print(f"  FAIL  extremes kinds incomplete: {ek}")
        failed += 1
    else:
        print("  PASS  extremes profile includes depeg/flash/latency")

    if any("scenario_inputs" not in r or "label_provenance" not in r for r in extremes):
        print("  FAIL  missing scenario_inputs / label_provenance")
        failed += 1
    else:
        print("  PASS  scenario_inputs + label_provenance present")

    paths = gen.write_outputs(a + extremes, out)
    with open(paths["csv"], encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        if list(cols) != gen.FEATURE_COLS:
            print("  FAIL  CSV columns mismatch")
            failed += 1
        else:
            print("  PASS  CSV feature columns")

    for r in a:
        if "envelope_id" in r or "egress_seal" in r:
            print("  FAIL  decision/signing fields in training row")
            failed += 1
            break
    else:
        print("  PASS  no envelope/seal fields in rows")

    if "sandbox/prefilter_synth" not in paths["jsonl"].replace("\\", "/"):
        print("  FAIL  output not under sandbox")
        failed += 1
    else:
        print("  PASS  output under D2 sandbox path")

    manifest = json.loads(Path(paths["manifest"]).read_text(encoding="utf-8"))
    if manifest.get("n") != 26:
        print(f"  FAIL  manifest n={manifest.get('n')}")
        failed += 1
    else:
        print("  PASS  manifest")

    verdict = "PREFILTER_DATAGEN_PASS" if failed == 0 else "PREFILTER_DATAGEN_FAIL"
    print("=" * 60)
    print(f"VERDICT: {verdict}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
