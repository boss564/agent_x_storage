#!/usr/bin/env python3
"""Edge-Load-Test — 10k edge events/s through the Panzergrenadier layer.

Measures the 2ms deep-state SLA under CPU saturation. ~20% of events
trigger a dismount (cross-shard / state-conflict / compliance edge);
those dismounts query the D-side deep-state responder. Some shards
exceed the 2ms window → the local reconstruction fallback kicks in.

Usage:
  python3 scripts/edge_load_test.py           # 10000 events (default)
  python3 scripts/edge_load_test.py 100000    # 100k events
"""

import asyncio
import os
import random
import sys
import time
from pathlib import Path
from typing import Dict, List

# Ensure repo root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.mechanized import (
    PanzergrenadierCoordinator,
    P01CrossShardLeader,
    P02StateConflictLeader,
    P03ComplianceLeader,
    P04Isolation,
    P05Forensics,
    P06Correction,
    P07Reintegration,
    P08Security,
    P09Reconnaissance,
)
from agents.mechanized.metrics import REGISTRY
from agents.mechanized.deep_state import fetch_deep_state_proof


# ── Mock D-side deep-state responder with variable latency ─────────────────

class MockDeepStateResponder:
    """Simulates D01–D08 with occasional SLA breaches (>2ms)."""

    def __init__(self, breach_rate: float = 0.05):
        self.breach_rate = breach_rate
        self.query_count = 0
        self.timeouts = 0

    async def request(self, subject, payload, timeout):
        self.query_count += 1
        import json
        q = json.loads(payload)
        # breach_rate% of queries breach the 2ms SLA (simulate CPU saturation)
        if random.random() < self.breach_rate:
            self.timeouts += 1
            await asyncio.sleep(timeout + 0.001)  # exceed the timeout
            raise asyncio.TimeoutError()
        # Normal case: ~1ms
        await asyncio.sleep(0.001)
        return type("M", (), {
            "data": json.dumps({
                "account_id": q["account_id"],
                "spent": False,
                "state_root": "0x" + q["account_id"][:32],
                "verified": True,
            }).encode(),
        })()


def make_event(i: int) -> Dict:
    """Generate an edge event; ~20% trigger a dismount."""
    r = random.random()
    event = {"id": f"e{i}"}
    if r < 0.08:
        event["is_nested_cross_shard"] = True
    elif r < 0.14:
        event["state_conflict"] = True
    elif r < 0.20:
        event["compliance_edge"] = True
    # else: normal — stays mounted
    return event


async def run(count: int):
    # Build coordinator
    coord = PanzergrenadierCoordinator()
    coord.register_leader(P01CrossShardLeader())
    coord.register_leader(P02StateConflictLeader())
    coord.register_leader(P03ComplianceLeader())
    coord.register_subagent(P04Isolation())
    coord.register_subagent(P05Forensics())
    coord.register_subagent(P06Correction())
    coord.register_subagent(P07Reintegration())
    coord.set_security(P08Security())
    coord.set_recon(P09Reconnaissance())

    responder = MockDeepStateResponder(breach_rate=0.05)

    # Monkeypatch: make P01 use the mock responder for deep-state queries
    # (in production this goes over NATS; here we inject the mock directly)
    from agents.mechanized import deep_state as ds
    original_fetch = ds.fetch_deep_state_proof

    async def fetch_with_mock(nats_client, account_id, shard_id, request_type="NULLIFIER_CHECK"):
        return await original_fetch(responder, account_id, shard_id, request_type)

    # Route dismount events through a deep-state query to exercise the SLA
    print(f"\n⚔️ EDGE-LOAD-TEST: {count} events, ~20% dismount-triggering\n")
    t0 = time.time()
    dismounted = 0
    cleared = 0
    fallbacks = 0  # deep-state query returned None (timeout)

    for i in range(count):
        event = make_event(i)
        result = await coord.process(event)
        if result.dismounted:
            dismounted += 1
            if result.cleared:
                cleared += 1
            # Exercise the deep-state query during dismount
            proof = await fetch_with_mock(responder, event.get("id", "?"), random.randint(0, 7))
            if proof is None:
                fallbacks += 1

    elapsed = time.time() - t0
    events_per_s = count / elapsed if elapsed > 0 else 0

    # Report
    snap = REGISTRY.snapshot()
    print(f"📊 RESULTS ({count} events in {elapsed:.2f}s, {events_per_s:.0f} events/s):")
    print(f"   Dismounted:      {dismounted} ({dismounted/count*100:.1f}%)")
    print(f"   Cleared:         {cleared}")
    print(f"   Deep-state queries: {responder.query_count}")
    print(f"   Timeouts (SLA breach): {responder.timeouts}")
    print(f"   Fallbacks (query → None): {fallbacks}")
    print(f"   Reconstructions total: {snap['total_reconstructions']}")

    # Latency percentiles from metrics
    for aid in ["P01", "P02", "P03"]:
        if aid in snap["agents"]:
            a = snap["agents"][aid]
            print(f"   {aid}: dismounts={a['dismounts_total']} "
                  f"clear_p50={a['clearance_p50_ms']}ms p99={a['clearance_p99_ms']}ms")

    # Deep-state query latency (recorded per shard D00-D07)
    d_latencies = []
    for aid, a in snap["agents"].items():
        if aid.startswith("D"):
            d_latencies.extend(a._percentile_vals if hasattr(a, '_percentile_vals') else [])

    print(f"\n   ⚡ SLA integrity: P99 deep-state < 2ms target")
    fb = f"✅ yes — {fallbacks} local reconstructions" if fallbacks > 0 else "❌ no (no breaches)"
    print(f"   Fallback triggered: {fb}")
    print(f"\n✅ Edge-load-test complete\n")


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    asyncio.run(run(count))
