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

# ─── WitnessGen DoS Defense ────────────────────────────────────────────────

WITNESS_TIMEOUT_MS = 15.0  # Hard ceiling for witness generation
QUARANTINE_SUBJECT = "agentx.surface.quarantine"


class WitnessTimeoutException(Exception):
    """Raised when witness generation exceeds the hard 15ms timeout."""
    def __init__(self, batch_id: str, elapsed_ms: float):
        self.batch_id = batch_id
        self.elapsed_ms = elapsed_ms
        super().__init__(f"WitnessGen timeout: {batch_id} took {elapsed_ms:.1f}ms "
                         f"(limit {WITNESS_TIMEOUT_MS}ms)")


def witness_gen_with_timeout(payload: dict) -> dict:
    """Simulate witness generation with a hard timeout.

    In production, this wraps the native C++/ark-circom WitnessGen.
    Here we simulate a poisoned payload (huge custom_proof_data) causing
    a timeout, and a healthy payload completing instantly.
    """
    # Simulate: oversized custom_proof_data is the algorithmic-complexity trigger
    if payload.get("custom_proof_data") and len(str(payload["custom_proof_data"])) > 1000:
        # Simulate expensive witness gen that exceeds timeout
        raise WitnessTimeoutException(payload.get("payload_id", "unknown"), WITNESS_TIMEOUT_MS + 1)
    return make_proof(payload)


async def binary_bisect_and_quarantine(batch: list, nc) -> tuple:
    """Recursively split a failing batch to isolate poison events.

    Returns (healthy_proofs, quarantine_events).
    """
    healthy = []
    quarantined = []

    async def _process(sub_batch: list):
        # Generate proofs into a temp list — only append if whole batch succeeds
        local_proofs = []
        for payload in sub_batch:
            try:
                proof = witness_gen_with_timeout(payload)
                local_proofs.append(proof)
            except WitnessTimeoutException:
                # Poison found — don't append partial, split and recurse
                if len(sub_batch) == 1:
                    quarantined.append(sub_batch[0])
                    await nc.publish(
                        QUARANTINE_SUBJECT,
                        json.dumps(sub_batch[0]).encode(),
                    )
                    return
                mid = len(sub_batch) // 2
                await _process(sub_batch[:mid])
                await _process(sub_batch[mid:])
                return
        # Whole sub-batch healthy — append once
        healthy.extend(local_proofs)

    await _process(batch)
    return healthy, quarantined

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
        try:
            proof = witness_gen_with_timeout(payload)
            await nc.publish(msg.reply, json.dumps(proof).encode())
        except WitnessTimeoutException:
            # Single poison event — quarantine directly
            await nc.publish(QUARANTINE_SUBJECT, json.dumps(payload).encode())

    # Batch handler: receives array of payloads, returns array of proofs
    async def batch_handler(msg):
        nonlocal count, l1_count
        batch_data = json.loads(msg.data.decode())
        if isinstance(batch_data, list):
            count += len(batch_data)
            # Binary bisect: isolate poison events, keep healthy 99%
            healthy, quarantined = await binary_bisect_and_quarantine(batch_data, nc)
            await nc.publish(msg.reply, json.dumps(healthy).encode())
            if quarantined:
                print(f"  🚨 Quarantined {len(quarantined)} poison event(s) "
                      f"out of {len(batch_data)}")
            if len(healthy) >= 100:
                l1_count += 1  # One L1 anchor per full batch

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

    # Deep-state query responder (Panzergrenadier → Diver request/reply)
    async def deep_state_handler(msg):
        try:
            q = json.loads(msg.data.decode())
            account_id = q.get("account_id", "unknown")
            # Simulated state: deterministic "spent" flag from account hash
            spent = int.from_bytes(
                hashlib.sha256(account_id.encode()).digest()[:2], "big"
            ) % 2 == 0
            proof = {
                "account_id": account_id,
                "request_type": q.get("request_type", "NULLIFIER_CHECK"),
                "spent": spent,
                "state_root": hashlib.sha256(account_id.encode()).hexdigest()[:32],
                "shard_id": q.get("shard_id", 0),
                "verified": True,
            }
            await nc.publish(msg.reply, json.dumps(proof).encode())
        except Exception:
            pass

    await nc.subscribe(SUBJECT, cb=handler, queue="d01-workers")
    await nc.subscribe(SUBJECT + "_batch", cb=batch_handler, queue="d01-workers")
    await nc.subscribe("agentx.deep.state.query.*", cb=deep_state_handler, queue="d01-workers")
    print(f"🧮 D01 Mock ZK Responder ready on {SUBJECT} (+ batch + deep-state) ({NATS_URL})")
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
