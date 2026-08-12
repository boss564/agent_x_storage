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


ANVIL_RPC = os.getenv("ANVIL_RPC", "http://localhost:8545")
ANVIL_ENABLED = os.getenv("ANVIL_ENABLED", "0") == "1"


def anchor_to_l1(state_root: str, nullifier: str) -> str:
    """Send state root hash to Anvil L1. Returns tx hash or '' on failure."""
    try:
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(ANVIL_RPC))
        if not w3.is_connected():
            return ""
        # Use dev account (Anvil default: 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266)
        acct = w3.eth.accounts[0]
        # Anchor: store hash and nullifier as calldata
        data = (
            Web3.keccak(text="anchor(bytes32,bytes32)")[:4]
            + Web3.to_bytes(hexstr=state_root).rjust(32, b'\0')
            + Web3.to_bytes(hexstr=nullifier).rjust(32, b'\0')
        )
        tx_hash = w3.eth.send_transaction({
            "from": acct, "to": acct, "data": data, "gas": 100_000,
        })
        return tx_hash.hex()
    except Exception:
        return ""


async def main():
    latency_ms = 0.0
    if len(sys.argv) > 1 and sys.argv[1] == "--latency":
        latency_ms = float(sys.argv[2]) / 1000.0 if len(sys.argv) > 2 else 0.0

    nc = await nats.connect(NATS_URL)
    count = 0
    l1_count = 0
    t0 = time.time()

    async def handler(msg):
        nonlocal count, l1_count
        count += 1
        if latency_ms > 0:
            await asyncio.sleep(latency_ms)
        payload = json.loads(msg.data.decode())
        proof = make_proof(payload)
        await nc.publish(msg.reply, json.dumps(proof).encode())

    # Batch handler: receives array of payloads, returns array of proofs
    async def batch_handler(msg):
        nonlocal count, l1_count
        batch_data = json.loads(msg.data.decode())
        if isinstance(batch_data, list):
            count += len(batch_data)
            proofs = [make_proof(p) for p in batch_data]
            await nc.publish(msg.reply, json.dumps(proofs).encode())
            if len(batch_data) >= 100:
                l1_count += 1  # One L1 anchor per batch

        # L1 Anchor
        if ANVIL_ENABLED:
            tx = anchor_to_l1(proof["z3_proof"], proof["nullifier_hash"])
            if tx:
                l1_count += 1

        if count % 100 == 0:
            elapsed = time.time() - t0
            tps = count / elapsed if elapsed > 0 else 0
            l1_info = f"| L1: {l1_count} anchored" if ANVIL_ENABLED else ""
            print(f"  [D01 Mock] {count} proofs | {tps:.0f}/s {l1_info}")

    await nc.subscribe(SUBJECT, cb=handler, queue="d01-workers")
    await nc.subscribe(SUBJECT + "_batch", cb=batch_handler, queue="d01-workers")
    print(f"🧮 D01 Mock ZK Responder ready on {SUBJECT} (+ batch) ({NATS_URL})")
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
