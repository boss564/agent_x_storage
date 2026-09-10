#!/usr/bin/env python3
"""Regime-swarm image smoke — AstroCore hook worm ingest (P3, read-only).

Runs inside the regime-swarm container after image build or helm rollout.
Charter: diagnostic_only · live_execution=false · no Neo4j writes
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agents_b2g.astrocore_hook import AstrocoreHookClient, parse_gap_logs  # noqa: E402


def main() -> int:
    quiet = "--quiet" in sys.argv or os.getenv("ASTROCORE_SMOKE_QUIET", "").lower() in (
        "1",
        "true",
        "yes",
    )
    audit_dir = Path(os.getenv("RAAS_AUDIT_DIR", "/data/audit"))
    lookback = int(os.getenv("ASTROCORE_NEO4J_LOOKBACK_DAYS", "7"))
    data_source = os.getenv("ASTROCORE_DATA_SOURCE", "worm")

    timestamps, meta = parse_gap_logs(audit_dir, lookback_days=lookback)
    client = AstrocoreHookClient(
        data_source=data_source,
        audit_dir=str(audit_dir),
        strict=False,
    )
    env = client.analyze_liquidations()

    summary = {
        "status": "PASS",
        "audit_dir": str(audit_dir),
        "data_provenance": env["data_provenance"],
        "verdict": env["verdict"],
        "raw_verdict": env["stats"].get("raw_verdict"),
        "events_read": env["stats"]["events_read"],
        "source_files": meta.get("source_files", []),
        "warnings": env.get("warnings", []),
    }
    if env["data_provenance"] not in ("worm", "gap_synthetic", "synthetic", "neo4j"):
        summary["status"] = "FAIL"
        print(json.dumps(summary, separators=(",", ":") if quiet else None, indent=None if quiet else 2))
        print("FAIL: unexpected provenance", file=sys.stderr)
        return 1
    if env["data_provenance"] == "worm" and env["verdict"] == "CLUSTER_DETECTED":
        summary["status"] = "FAIL"
        print(json.dumps(summary, separators=(",", ":") if quiet else None, indent=None if quiet else 2))
        print("FAIL: D1b cap missing for worm provenance", file=sys.stderr)
        return 1
    print(json.dumps(summary, separators=(",", ":") if quiet else None, indent=None if quiet else 2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
