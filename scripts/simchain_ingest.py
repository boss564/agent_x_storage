#!/usr/bin/env python3
"""Producer: realistic BHO events to NATS, measure throughput.

Usage:
  python3 scripts/simchain_ingest.py              # 1000 events (default)
  python3 scripts/simchain_ingest.py 10000        # 10000 events
  python3 scripts/simchain_ingest.py --rate 1000 --duration 60  # 1k/s for 60s
"""

import asyncio
import hashlib
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

BHO_TEMPLATES = [
    {"project_id": "P-1001", "hours": 12.5, "rate": 85.0, "material": "Beton C30/37"},
    {"project_id": "P-2004", "hours": 8.0, "rate": 120.0, "material": "Stahlträger HEB 200"},
    {"project_id": "P-3012", "hours": 24.0, "rate": 65.0, "material": "Erdarbeiten"},
    {"project_id": "P-4007", "hours": 3.5, "rate": 210.0, "material": "Dämmung WLG 035"},
    {"project_id": "P-5019", "hours": 16.0, "rate": 95.0, "material": "Rohbau Mauerwerk"},
]


def make_event(i: int) -> dict:
    tpl = random.choice(BHO_TEMPLATES)
    total = round(tpl["hours"] * tpl["rate"] + random.uniform(-5, 5), 2)
    return {
        "payload_id": str(uuid.uuid4())[:8],
        "trace_id": str(uuid.uuid4())[:12],
        "schema": random.choice(SCHEMAS),
        "device_id": random.choice(DEVICES),
        "amount": total,
        "project_id": tpl["project_id"],
        "material": tpl["material"],
        "hours": tpl["hours"],
        "rate": tpl["rate"],
        "state_hash": hashlib.sha256(
            f"{tpl['project_id']}{total}{i}".encode()
        ).hexdigest()[:16],
        "telemetry": {
            "cpu": round(random.uniform(0.1, 0.8), 2),
            "mem": round(random.uniform(0.2, 0.9), 2),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "seq": i,
    }


async def main():
    # Parse args: count or --rate/--duration
    rate = 0
    duration = 0
    count = 0
    interval = 0

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--rate" and i + 1 < len(args):
            rate = int(args[i + 1]); i += 2
        elif args[i] == "--duration" and i + 1 < len(args):
            duration = int(args[i + 1]); i += 2
        elif args[i].replace(".", "").isdigit() and count == 0:
            count = int(args[i]); i += 1
            if i < len(args) and args[i].replace(".", "").isdigit():
                interval = float(args[i]); i += 1
        else:
            i += 1

    if rate > 0 and duration > 0:
        count = rate * duration
        interval = 1.0 / rate if rate > 0 else 0
        print(f"\n📡 Producer: {count} events ({rate}/s × {duration}s) → {SUBJECT}")
    else:
        count = count or 1000
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
    next_tick = t0 + interval if interval > 0 else 0

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
            now = time.time()
            if now < next_tick:
                await asyncio.sleep(next_tick - now)
            next_tick = time.time() + interval

        if i % 250 == 0 or (rate > 0 and i % 1000 == 0):
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
