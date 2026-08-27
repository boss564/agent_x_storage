#!/usr/bin/env python3
"""Phase 4A — quality gate for synthetic prefilter batches.

Fails if gateway labels are mixed into a training corpus, or provenance missing.

Usage:
  PYTHONPATH=. python3 scripts/check_prefilter_synth_quality.py data/synthetic/prefilter/extremes
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: check_prefilter_synth_quality.py <batch_dir>")
        return 2
    batch = Path(sys.argv[1])
    jsonl = batch / "features.jsonl"
    manifest_path = batch / "manifest.json"
    print("Phase 4A synth quality check")
    print("=" * 60)
    print(f"batch={batch}")
    if not jsonl.is_file():
        print("VERDICT: PREFILTER_SYNTH_QUALITY_FAIL")
        print("  missing features.jsonl")
        return 1

    modes: Counter[str] = Counter()
    provenances: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    n = 0
    bad = 0
    with jsonl.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            n += 1
            lm = row.get("label_mode")
            modes[str(lm)] += 1
            provenances[str(row.get("label_provenance", ""))] += 1
            kinds[str(row.get("scenario_kind", ""))] += 1
            if not row.get("label_provenance"):
                bad += 1
            if lm == "gateway":
                bad += 1  # training corpus must not include circular gate labels
            if row.get("live_execution") is not False:
                bad += 1

    manifest = {}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    training_ok = modes.keys() == {"severity_proxy"} and bad == 0
    if manifest:
        if manifest.get("training_allowed") is True and not training_ok:
            print("  FAIL  manifest.training_allowed=true but gateway/bad rows present")
            bad += 1
        if manifest.get("n") != n:
            print(f"  FAIL  manifest.n={manifest.get('n')} != jsonl n={n}")
            bad += 1

    print(f"  n={n}")
    print(f"  label_modes={dict(modes)}")
    print(f"  kinds={dict(kinds)}")
    print(f"  training_allowed_effective={training_ok}")

    verdict = (
        "PREFILTER_SYNTH_QUALITY_PASS" if training_ok and n > 0 else "PREFILTER_SYNTH_QUALITY_FAIL"
    )
    print("=" * 60)
    print(f"VERDICT: {verdict}")
    return 0 if verdict.endswith("_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
