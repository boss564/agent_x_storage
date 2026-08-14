#!/usr/bin/env python3
"""Producer: realistic BHO events to NATS, measure throughput.

Baseline usage (unchanged):
  python3 scripts/simchain_ingest.py                  # 1000 events (default)
  python3 scripts/simchain_ingest.py 10000            # 10000 events
  python3 scripts/simchain_ingest.py --rate 1000 --duration 60  # 1k/s for 60s

1M tsunami usage:
  python3 scripts/simchain_ingest.py \
    --total 1000000 --rate 100000 \
    --poison-rate 0.05 --complex-rate 0.15 \
    --seed 42 --report /tmp/tsunami_report.json

Event kinds (mutually exclusive, one roll per event):
  * poison  — oversized `custom_proof_data` (>1000 chars) → WitnessGen timeout,
              binary-bisect quarantine downstream in D01.
  * complex — one of is_nested_cross_shard / state_conflict / compliance_edge
              → routed to the Panzergrenadier (infantry) edge-clearance layer.
  * simple  — fast path, stays mounted.
"""

import argparse
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

# Default poison payload size: >1000 chars trips the D01 WitnessGen timeout,
# and len*2 + 50 > 10_000 exceeds the surface constraint-weight budget.
DEFAULT_POISON_SIZE = 5000


def _base_event(i: int, rng: random.Random) -> dict:
    tpl = rng.choice(BHO_TEMPLATES)
    total = round(tpl["hours"] * tpl["rate"] + rng.uniform(-5, 5), 2)
    return {
        "payload_id": str(uuid.uuid4())[:8],
        "trace_id": str(uuid.uuid4())[:12],
        "schema": rng.choice(SCHEMAS),
        "device_id": rng.choice(DEVICES),
        "amount": total,
        "project_id": tpl["project_id"],
        "material": tpl["material"],
        "hours": tpl["hours"],
        "rate": tpl["rate"],
        "state_hash": hashlib.sha256(
            f"{tpl['project_id']}{total}{i}".encode()
        ).hexdigest()[:16],
        "telemetry": {
            "cpu": round(rng.uniform(0.1, 0.8), 2),
            "mem": round(rng.uniform(0.2, 0.9), 2),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "seq": i,
    }


def _apply_complex(event: dict, rng: random.Random) -> None:
    """Tag one of the three Panzergrenadier complexity flags (~8/6/6 split)."""
    r = rng.random()
    if r < 0.4:
        event["is_nested_cross_shard"] = True
    elif r < 0.7:
        event["state_conflict"] = True
    else:
        event["compliance_edge"] = True


def make_event(
    i: int,
    rng: random.Random | None = None,
    poison_rate: float = 0.0,
    complex_rate: float = 0.0,
    poison_size: int = DEFAULT_POISON_SIZE,
) -> tuple[dict, str]:
    """Build one event; returns (event, kind) where kind ∈ {simple, complex, poison}."""
    rng = rng or random
    event = _base_event(i, rng)
    roll = rng.random()
    if poison_rate > 0 and roll < poison_rate:
        event["custom_proof_data"] = "x" * poison_size
        event["has_special_exemption"] = True
        return event, "poison"
    if complex_rate > 0 and roll < poison_rate + complex_rate:
        _apply_complex(event, rng)
        return event, "complex"
    return event, "simple"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="BHO event producer with poison/complex generation")
    p.add_argument("count", nargs="?", type=int, default=0,
                   help="positional event count (backward compat)")
    p.add_argument("--total", type=int, default=0, help="exact number of events")
    p.add_argument("--rate", type=int, default=0, help="events per second pacing")
    p.add_argument("--duration", type=int, default=0, help="seconds (with --rate)")
    p.add_argument("--poison-rate", type=float, default=0.0, help="fraction [0..1] poison")
    p.add_argument("--complex-rate", type=float, default=0.0, help="fraction [0..1] complex")
    p.add_argument("--poison-size", type=int, default=DEFAULT_POISON_SIZE,
                   help="custom_proof_data length for poison payloads")
    p.add_argument("--seed", type=int, default=None, help="deterministic RNG seed")
    p.add_argument("--report", type=str, default="", help="write JSON report to this path")
    return p.parse_args(argv)


async def main() -> int:
    args = _parse_args(sys.argv[1:])

    if args.total > 0:
        count = args.total
    elif args.rate > 0 and args.duration > 0:
        count = args.rate * args.duration
    else:
        count = args.count or 1000
    interval = 1.0 / args.rate if args.rate > 0 else 0.0

    rng = random.Random(args.seed)
    poison_rate = max(0.0, min(1.0, args.poison_rate))
    complex_rate = max(0.0, min(1.0, args.complex_rate))

    print(f"\n📡 Producer: {count} events → {SUBJECT} on {NATS_URL}")
    if args.rate > 0:
        print(f"   Rate: {args.rate}/s")
    if poison_rate or complex_rate:
        print(f"   Poison: {poison_rate*100:.1f}% | Complex: {complex_rate*100:.1f}% "
              f"(poison_size={args.poison_size})")

    try:
        import nats
    except ImportError:
        print("❌ nats-py not installed. pip install nats-py")
        return 1

    nc = await nats.connect(NATS_URL)
    print("✅ Connected to NATS")

    t0 = time.time()
    sent = 0
    errors = 0
    poison_count = 0
    complex_count = 0
    simple_count = 0
    next_tick = t0 + interval if interval > 0 else 0
    progress_interval = max(250, count // 20)  # ~20 progress lines regardless of size

    for i in range(1, count + 1):
        event, kind = make_event(i, rng, poison_rate, complex_rate, args.poison_size)
        if kind == "poison":
            poison_count += 1
        elif kind == "complex":
            complex_count += 1
        else:
            simple_count += 1

        payload = json.dumps(event).encode()
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

        if i % progress_interval == 0:
            elapsed = time.time() - t0
            tps = i / elapsed if elapsed > 0 else 0
            print(f"  [{i:>7}/{count}] {tps:.0f} events/s")

    elapsed = time.time() - t0
    tps = sent / elapsed if elapsed > 0 else 0

    await nc.close()

    report = {
        "sent": sent,
        "errors": errors,
        "poison_count": poison_count,
        "complex_count": complex_count,
        "simple_count": simple_count,
        "elapsed_s": round(elapsed, 3),
        "tps": round(tps, 1),
        "total": count,
    }

    print(f"\n{'─' * 50}")
    print(f"  ✅ {sent} events sent in {elapsed:.2f}s ({tps:.0f} events/s)")
    print(f"  🧬 Poison:  {poison_count} ({poison_count/max(1,sent)*100:.1f}%)")
    print(f"  🪖 Complex: {complex_count} ({complex_count/max(1,sent)*100:.1f}%)")
    print(f"  ⚡ Simple:  {simple_count} ({simple_count/max(1,sent)*100:.1f}%)")
    if errors:
        print(f"  ⚠️ {errors} errors")
    print(f"  Subject: {SUBJECT}")
    print(f"  NATS:    {NATS_URL}")
    print(f"{'─' * 50}\n")

    if args.report:
        try:
            with open(args.report, "w") as f:
                json.dump(report, f, indent=2)
            print(f"  📄 Report written: {args.report}")
        except Exception as e:
            print(f"  ⚠️ Could not write report: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
