#!/usr/bin/env python3
"""Mock D01 ZK Responder — replies to subsurface ZK requests with a simulated proof.

Subscribes to agentx.subsurface.zk_request, generates a mocked Groth16
proof payload (Base64-encoded JSON), and replies with the proof.

Usage:
  python3 scripts/mock_d01_responder.py
  python3 scripts/mock_d01_responder.py --latency 5  # 5ms simulated latency
"""

import asyncio
import hashlib
import json
import os
import sys
import time
import uuid

import nats

NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
SUBJECT = "agentx.subsurface.zk_request"


def make_proof(payload: dict) -> dict:
    """Generate a simulated Groth16 proof response."""
    payload_id = payload.get("payload_id", "unknown")
    amount = payload.get("amount", 0)
    device_id = payload.get("device_id", "unknown")

    return {
        "status": "SAT",
        "z3_proof": hashlib.sha256(f"Z3_{payload_id}_{amount}".encode()).hexdigest()[:32],
        "nullifier_hash": hashlib.sha256(f"NULL_{payload_id}".encode()).hexdigest(),
        "commitment_hash": hashlib.sha256(f"COMMIT_{device_id}_{amount}".encode()).hexdigest(),
        "settlement_net_eur_cents": int(float(amount) * 100),
        "proof": {
            "pi_a": ["0x" + hashlib.sha256(b"a").hexdigest()[:64]],
            "pi_b": [["0x" + hashlib.sha256(b"b1").hexdigest()[:64],
                      "0x" + hashlib.sha256(b"b2").hexdigest()[:64]]],
            "pi_c": ["0x" + hashlib.sha256(b"c").hexdigest()[:64]],
        },
        "valhalla_stamp": f"did:valhalla:{hashlib.sha256(device_id.encode()).hexdigest()[:8]}",
        "latency_ms": 4.2,
        "responder_id": str(uuid.uuid4())[:8],
    }


async def main():
    latency_ms = 0.0
    if len(sys.argv) > 1 and sys.argv[1] == "--latency":
        latency_ms = float(sys.argv[2]) / 1000.0 if len(sys.argv) > 2 else 0.0

    nc = await nats.connect(NATS_URL)
    count = 0
    t0 = time.time()

    async def handler(msg):
        nonlocal count
        count += 1
        if latency_ms > 0:
            await asyncio.sleep(latency_ms)
        payload = json.loads(msg.data.decode())
        proof = make_proof(payload)
        await nc.publish(msg.reply, json.dumps(proof).encode())

        if count % 100 == 0:
            elapsed = time.time() - t0
            tps = count / elapsed if elapsed > 0 else 0
            print(f"  [D01 Mock] {count} proofs | {tps:.0f}/s")

    await nc.subscribe(SUBJECT, cb=handler, queue="d01-workers")
    print(f"🧮 D01 Mock ZK Responder ready on {SUBJECT} ({NATS_URL})")
    if latency_ms > 0:
        print(f"   Simulated latency: {latency_ms*1000:.0f}ms")

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 D01 Mock stopped")
        sys.exit(0)
