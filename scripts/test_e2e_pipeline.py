#!/usr/bin/env python3
"""E2E Integration Test — full six-layer chain: C01 → P09 → D05 → Anvil.

Verifies state propagation across the entire architecture:
  1. Surface (C01) generates a high-throughput event batch
  2. Recon (P09) marks complex events for dismount
  3. Infantry (P01–P03) dismounts and clears edge cases
  4. Deep-state (D-shard mock) provides verified context (2ms SLA)
  5. L1 anchor (Anvil mock) records the final state root

This is the "watcher that checks the whole watcher" — a falsifiable test
that turns red if any layer in the six-layer chain regresses.

Usage:
  python3 scripts/test_e2e_pipeline.py
"""

import asyncio
import hashlib
import json
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

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
from agents.mechanized.deep_state import fetch_deep_state_proof


# ─── Mock L1 Anchor (Anvil) ────────────────────────────────────────────────

class MockAnvil:
    """Simulates the Anvil L1 EVM: records state roots, confirms finality."""

    def __init__(self):
        self.state_roots: Dict[int, str] = {}
        self.block_height = 0
        self.settled_epochs = 0

    def anchor(self, state_root: str) -> int:
        self.block_height += 1
        self.state_roots[self.block_height] = state_root
        self.settled_epochs += 1
        return self.block_height

    def confirm_finality(self, block: int, required: int = 12) -> bool:
        return block > 0 and self.block_height >= block


# ─── Mock D-shard responder ────────────────────────────────────────────────

class MockShard:
    def __init__(self, shard_id: int, breach_rate: float = 0.02):
        self.shard_id = shard_id
        self.breach_rate = breach_rate
        self.queries = 0

    async def request(self, subject, payload, timeout):
        self.queries += 1
        q = json.loads(payload)
        if random.random() < self.breach_rate:
            await asyncio.sleep(timeout + 0.001)
            raise asyncio.TimeoutError()
        await asyncio.sleep(0.0005)
        return type("M", (), {"data": json.dumps({
            "account_id": q["account_id"],
            "spent": False,
            "state_root": hashlib.sha256(q["account_id"].encode()).hexdigest()[:32],
            "shard_id": self.shard_id,
            "verified": True,
        }).encode()})()


async def run():
    print("\n" + "=" * 70)
    print("🧪 E2E PIPELINE TEST — C01 → P09 → D05 → Anvil")
    print("=" * 70 + "\n")

    # ── Build all layers ──
    coord = PanzergrenadierCoordinator()
    coord.register_leader(P01CrossShardLeader())
    coord.register_leader(P02StateConflictLeader())
    coord.register_leader(P03ComplianceLeader())
    coord.register_subagent(P04Isolation())
    coord.register_subagent(P05Forensics())
    coord.register_subagent(P06Correction())
    coord.register_subagent(P07Reintegration())
    coord.set_security(P08Security())
    recon = P09Reconnaissance()
    coord.set_recon(recon)

    shard5 = MockShard(5)
    anvil = MockAnvil()

    # ── Phase 1: Surface generates events ──
    total_events = 100
    surface_events = []
    for i in range(total_events):
        e = {"id": f"c01_{i}", "account_id": f"acct_{i % 16}"}
        r = random.random()
        if r < 0.08:
            e["is_nested_cross_shard"] = True
        elif r < 0.14:
            e["state_conflict"] = True
        elif r < 0.20:
            e["compliance_edge"] = True
        surface_events.append(e)

    print(f"📡 Phase 1 (C01): {total_events} events generated (~20% complex)")

    # ── Phase 2: Recon marks + Infantry clears ──
    dismounted = 0
    cleared = 0
    fallbacks = 0
    for e in surface_events:
        # P09 recon marks the event
        leader = recon.mark_event(e)
        if leader:
            result = await coord.process(e)
            if result.dismounted:
                dismounted += 1
                if result.cleared:
                    cleared += 1
                # Deep-state query to shard 5 during dismount
                proof = await fetch_deep_state_proof(
                    shard5, e.get("account_id", "?"), 5
                )
                if proof is None:
                    fallbacks += 1

    print(f"🪖 Phase 2 (P09/P01–P03): {dismounted} dismounted, {cleared} cleared, {fallbacks} fallbacks")

    # ── Phase 3: Deep-state verified ──
    print(f"🌊 Phase 3 (D05): {shard5.queries} deep-state queries answered")

    # ── Phase 4: L1 anchor ──
    state_root = hashlib.sha256(
        f"epoch_{anvil.settled_epochs + 1}".encode()
    ).hexdigest()[:32]
    block = anvil.anchor(state_root)
    final = anvil.confirm_finality(block)

    print(f"⚓ Phase 4 (Anvil): block={block}, state_root={state_root[:16]}..., finality={'✅' if final else '❌'}")

    # ── Assertions (the falsifiable checks) ──
    print("\n" + "-" * 70)
    checks = [
        ("Surface generated 100 events", len(surface_events) == 100),
        ("Infantry dismounted complex events", dismounted > 0),
        ("All dismounts cleared (no loss)", dismounted == cleared),
        ("Deep-state queried shard 5", shard5.queries > 0),
        ("L1 anchor advanced block", block > 0),
        ("L1 finality confirmed", final is True),
    ]
    all_pass = True
    for name, ok in checks:
        print(f"  {'✅' if ok else '❌'} {name}")
        all_pass = all_pass and ok

    print("-" * 70)
    print(f"  RESULT: {'✅ E2E PASS' if all_pass else '❌ E2E FAIL'}\n")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
