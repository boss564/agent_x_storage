#!/usr/bin/env python3
"""Stage-1 ring — all P1→…→P9→P1 edges over NATS Queue-Groups.

Requires NATS (e.g. docker run -d --name nats-gate0 -p 4222:4222 nats:2.10-alpine).

Checks:
  - 9 edges with dedicated subject + queue-group
  - RingOrchestrator sequential request/reply (no reorder)
  - Determinism: same payload → same chain_sha256 twice
  - Broadcast subjects still forbidden
  - live_execution=false on wire
  - TrustedCoreGateway not required (bus-only)

Usage:
  PYTHONPATH=. python3 scripts/test_stage1_edge_bus_ring.py
  make raas-stage1-edge-ring
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
    RING_EDGES,
    edge_queue,
    edge_subject,
    forbid_broadcast,
    run_ring_roundtrip,
)


def main() -> int:
    print("Stage-1 edge bus ring (P1→…→P9→P1 Queue-Group)")
    print("=" * 60)
    print(f"NATS_URL={os.environ.get('NATS_URL', 'nats://127.0.0.1:4222')}")
    print(f"edges={len(RING_EDGES)}")

    try:
        forbid_broadcast("edge.broadcast.all")
        print("  FAIL  broadcast subject should raise")
        return 1
    except ValueError:
        print("  PASS  broadcast subject rejected")

    for src, dst in RING_EDGES:
        sub = edge_subject(src, dst)
        q = edge_queue(src, dst)
        forbid_broadcast(sub)
        print(f"  edge  {src}->{dst}  subject={sub}  queue={q}")

    payload = {
        "proposal_id": "stage1-ring",
        "max_slippage_pct": 0.5,
        "label": "SYNTHETIC_MILD",
    }
    try:
        a = run_ring_roundtrip(payload)
        b = run_ring_roundtrip(payload)
    except Exception as exc:
        print("VERDICT: STAGE1_EDGE_RING_FAIL")
        print(f"  NATS/error: {exc}")
        return 1

    expected_edges = [f"{s}->{d}" for s, d in RING_EDGES]
    ok = all(
        [
            a["hop_count"] == 9,
            b["hop_count"] == 9,
            a["edges"] == expected_edges,
            b["edges"] == expected_edges,
            a["chain_sha256"] == b["chain_sha256"],
            bool(a["chain_sha256"]),
            a["live_execution"] is False,
            a["via"] == "nats_queue_group_sequential",
            all(h["via"] == "nats_queue_group" for h in a["hops"]),
            all(h["response"].get("live_execution") is False for h in a["hops"]),
        ]
    )
    print(f"  chain_a={a['chain_sha256']}")
    print(f"  chain_b={b['chain_sha256']}")
    print(f"  determinism={'PASS' if a['chain_sha256'] == b['chain_sha256'] else 'FAIL'}")
    verdict = "STAGE1_EDGE_RING_PASS" if ok else "STAGE1_EDGE_RING_FAIL"
    print("=" * 60)
    print(f"VERDICT: {verdict}")

    out = _ROOT / "data" / "raas" / "stage1_edge_ring_last.json"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({"verdict": verdict, "a": a, "b": b}, indent=2),
            encoding="utf-8",
        )
        print(f"artifact: {out}")
    except OSError as exc:
        print(f"artifact: skipped ({exc})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
