#!/usr/bin/env python3
"""Stage-1 pilot — single edge P1→P2 over NATS Queue-Group.

Requires NATS (e.g. docker run -d --name nats-gate0 -p 4222:4222 nats:2.10-alpine).

Checks:
  - Queue-Group hop works (adapter)
  - Determinism: same payload → same echo_sha256 twice
  - No broadcast subjects
  - live_execution=false on wire

Usage:
  PYTHONPATH=. python3 scripts/test_stage1_edge_bus_pilot.py
  make raas-stage1-edge-pilot
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_hybrid_shell.edge_bus import (  # noqa: E402
    edge_queue,
    edge_subject,
    forbid_broadcast,
    run_pilot_roundtrip,
)


def main() -> int:
    print("Stage-1 edge bus pilot (P1→P2 Queue-Group)")
    print("=" * 60)
    print(f"NATS_URL={os.environ.get('NATS_URL', 'nats://127.0.0.1:4222')}")
    print(f"subject={edge_subject('P1','P2')}  queue={edge_queue('P1','P2')}")

    try:
        forbid_broadcast("edge.broadcast.all")
        print("  FAIL  broadcast subject should raise")
        return 1
    except ValueError:
        print("  PASS  broadcast subject rejected")

    payload = {
        "proposal_id": "stage1-pilot",
        "max_slippage_pct": 0.5,
        "label": "SYNTHETIC_MILD",
    }
    try:
        a = run_pilot_roundtrip(payload)
        b = run_pilot_roundtrip(payload)
    except Exception as exc:
        print(f"VERDICT: STAGE1_EDGE_PILOT_FAIL")
        print(f"  NATS/error: {exc}")
        return 1

    echo_a = a["response"].get("echo_sha256")
    echo_b = b["response"].get("echo_sha256")
    ok = all(
        [
            a["request_hash"] == b["request_hash"],
            echo_a == echo_b,
            a["response"].get("hop") == "P1->P2",
            a["response"].get("live_execution") is False,
            a["via"] == "nats_queue_group",
        ]
    )
    print(f"  roundtrip1 echo={echo_a}")
    print(f"  roundtrip2 echo={echo_b}")
    print(f"  determinism={'PASS' if echo_a == echo_b else 'FAIL'}")
    verdict = "STAGE1_EDGE_PILOT_PASS" if ok else "STAGE1_EDGE_PILOT_FAIL"
    print("=" * 60)
    print(f"VERDICT: {verdict}")

    out = _ROOT / "data" / "raas" / "stage1_edge_pilot_last.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"verdict": verdict, "a": a, "b": b}, indent=2),
        encoding="utf-8",
    )
    print(f"artifact: {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
