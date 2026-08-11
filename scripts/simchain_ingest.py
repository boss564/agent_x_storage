#!/usr/bin/env python3
"""Producer: send 1000 SurfaceEnvelope events to NATS, measure throughput.

Usage:
  python3 scripts/simchain_ingest.py              # 1000 events (default)
  python3 scripts/simchain_ingest.py 10000        # 10000 events
  python3 scripts/simchain_ingest.py 100 0.01     # 100 events, 10ms pacing
"""

import asyncio
import json
import os
import random
import sys
import time
import uuid
from datetime import datetime, timezone

NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
SUBJECT = "agentx.surface.events"

SCHEMAS = ["VOB_B", "SENSOR", "COMPLIANCE", "SETTLEMENT"]
DEVICES = [
    "ESP32_DEMO_01", "ESP32_SOLAR_MUC", "MEIER_BAU_GMBH",
    "CONTRACTOR_4012", "STAKING_POOL", "TREASURY_MAIN",
]


def make_event(i: int) -> dict:
    return {
        "payload_id": str(uuid.uuid4())[:8],
        "trace_id": str(uuid.uuid4())[:12],
        "schema": random.choice(SCHEMAS),
        "device_id": random.choice(DEVICES),
        "amount": round(random.uniform(100, 500_000), 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "seq": i,
    }


async def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 0

    print(f"\n📡 Producer: {count} events → {SUBJECT} on {NATS_URL}")
    if interval > 0:
        print(f"   Pacing: {interval}s between events")

    try:
        import nats
    except ImportError:
        print("❌ nats-py not installed. pip install nats-py")
        return 1

    nc = await nats.connect(NATS_URL)
    print(f"✅ Connected to NATS")

    t0 = time.time()
    sent = 0
    errors = 0

    for i in range(1, count + 1):
        payload = json.dumps(make_event(i)).encode()
        try:
            await nc.publish(SUBJECT, payload)
            sent += 1
        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"  ⚠️ publish error: {e}")

        if interval > 0:
            await asyncio.sleep(interval)

        if i % 250 == 0:
            elapsed = time.time() - t0
            tps = i / elapsed if elapsed > 0 else 0
            print(f"  [{i:>5}/{count}] {tps:.0f} events/s")

    elapsed = time.time() - t0
    tps = sent / elapsed if elapsed > 0 else 0

    await nc.close()

    print(f"\n{'─'*50}")
    print(f"  ✅ {sent} events sent in {elapsed:.2f}s ({tps:.0f} events/s)")
    if errors:
        print(f"  ⚠️ {errors} errors")
    print(f"  Subject: {SUBJECT}")
    print(f"  NATS:    {NATS_URL}")
    print(f"{'─'*50}\n")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
