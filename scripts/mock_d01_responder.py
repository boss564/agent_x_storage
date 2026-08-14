#!/usr/bin/env python3
"""Mock D01 ZK Responder — replies to subsurface ZK requests with a simulated proof.

Subscribes to agentx.subsurface.zk_request, generates a mocked Groth16
proof payload (Base64-encoded JSON), and replies with the proof.

Poison events (oversized custom_proof_data) trigger WitnessGen timeout and
are isolated via binary bisect onto the quarantine subject. Every event that
D01 receives reaches exactly one terminal state — healthy (settled) or
quarantined — so `l1_settled_events_total == total_events` holds.

Usage:
  python3 scripts/mock_d01_responder.py
  python3 scripts/mock_d01_responder.py --latency 5  # 5ms simulated latency
"""

import asyncio
import hashlib
import json
import os
import sys
import threading
import time
import uuid

import nats

# ─── WitnessGen DoS Defense ────────────────────────────────────────────────

WITNESS_TIMEOUT_MS = 15.0  # Hard ceiling for witness generation
QUARANTINE_SUBJECT = "agentx.surface.quarantine"
METRICS_PORT = 8081

# L1 settlement target: "anvil" (local, high-frequency) or "sepolia" (public testnet).
L1_NETWORK = os.getenv("L1_NETWORK", "anvil")
SEPOLIA_RPC_URL = os.getenv("SEPOLIA_RPC_URL", "")
SEPOLIA_PRIVATE_KEY = os.getenv("SEPOLIA_PRIVATE_KEY", "")
SEPOLIA_CONTRACT_ADDRESS = os.getenv("SEPOLIA_CONTRACT_ADDRESS", "")

# Epoch SLA — env-configurable. Sepolia aggregates far more aggressively to
# stay under public-RPC rate limits and gas cost.
EPOCH_SIZE = int(os.getenv("SETTLEMENT_EPOCH_SIZE") or
                 ("500" if L1_NETWORK == "sepolia" else "100"))
EPOCH_MAX_AGE_S = float(os.getenv("SETTLEMENT_EPOCH_MAX_AGE_S") or
                        ("30.0" if L1_NETWORK == "sepolia" else "2.0"))

# ─── D01 metrics state (single process; read by /metrics thread) ───────────

STATE = {
    "total_events": 0,          # every non-warmup event D01 received
    "quarantined_total": 0,     # poison events isolated via binary bisect
    "healthy_settled_total": 0, # healthy proofs settled
    "l1_settled_events_total": 0,  # = healthy + quarantined (terminal states)
    "l1_anchors": 0,            # L1 anchor transactions (batch-granular)
    "witness_hist": [0] * 25,   # ms buckets × 0.5ms, last bucket overflow
    "witness_count": 0,
    "started_at": time.time(),
    # Settlement epoch accumulator — decouples L1 anchors from ingest batches
    # so poison-fragmented batches still commit once 100 healthy proofs accrue.
    "epoch_buffer": [],
    "epoch_started_at": time.time(),
}


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


def _record_witness(elapsed_ms: float) -> None:
    idx = min(int(elapsed_ms / 0.5), len(STATE["witness_hist"]) - 1)
    STATE["witness_hist"][idx] += 1
    STATE["witness_count"] += 1


def witness_gen_timed(payload: dict) -> dict:
    """Timed wrapper around witness_gen_with_timeout (records P99 histogram)."""
    t0 = time.perf_counter()
    try:
        proof = witness_gen_with_timeout(payload)
        _record_witness((time.perf_counter() - t0) * 1000)
        return proof
    except WitnessTimeoutException:
        _record_witness((time.perf_counter() - t0) * 1000)
        raise


def _witness_p99_ms() -> float:
    if STATE["witness_count"] == 0:
        return 0.0
    target = int(STATE["witness_count"] * 0.99)
    cum = 0
    for idx, n in enumerate(STATE["witness_hist"]):
        cum += n
        if cum >= target:
            return idx * 0.5
    return len(STATE["witness_hist"]) * 0.5


def metrics_snapshot() -> dict:
    elapsed = time.time() - STATE["started_at"]
    return {
        "total_events": STATE["total_events"],
        "quarantined_total": STATE["quarantined_total"],
        "healthy_settled_total": STATE["healthy_settled_total"],
        "l1_settled_events_total": STATE["l1_settled_events_total"],
        "l1_anchors": STATE["l1_anchors"],
        "epoch_buffer_size": len(STATE["epoch_buffer"]),
        "witness_gen_p99_ms": round(_witness_p99_ms(), 3),
        "tps": round(STATE["total_events"] / elapsed, 1) if elapsed > 0 else 0.0,
    }


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
                proof = witness_gen_timed(payload)
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


_W3 = None  # cached Anvil Web3 connection (avoid reconnecting per anchor)
_W3_LOCK = None  # serializes nonce fetch + send to avoid nonce races across threads


def anchor_to_l1(state_root: str, nullifier: str) -> str:
    """Send state root hash to Anvil L1. Returns tx hash or '' on failure."""
    global _W3, _W3_LOCK
    try:
        from web3 import Web3
        if _W3 is None:
            _W3 = Web3(Web3.HTTPProvider(ANVIL_RPC))
            _W3_LOCK = threading.Lock()
        w3 = _W3
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
        with _W3_LOCK:
            for _ in range(10):  # retry nonce collisions (8 replicas share one account)
                try:
                    tx_hash = w3.eth.send_transaction({
                        "from": acct, "to": acct, "data": data, "gas": 100_000,
                    })
                    return "0x" + tx_hash.hex()
                except Exception:
                    time.sleep(0.02)  # let the winning tx enter the pending pool
        return ""
    except Exception:
        return ""


class SepoliaSettlementBridge:
    """EIP-1559 settlement bridge — signs locally, escalates priority fee on underpriced.

    Target switched via L1_NETWORK=sepolia. Uses a local private key (env
    SEPOLIA_PRIVATE_KEY) in place of AWS KMS for the testnet run; the same
    code path applies to a production KMS signer.
    """

    def __init__(self, rpc_url: str, private_key: str, contract_address: str = ""):
        from web3 import Web3
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.acct = self.w3.eth.account.from_key(private_key)
        self.contract_address = contract_address or self.acct.address
        self._lock = threading.Lock()

    def _encode_anchor(self, state_root: str, nullifier: str) -> bytes:
        from web3 import Web3
        return (
            Web3.keccak(text="anchor(bytes32,bytes32)")[:4]
            + Web3.to_bytes(hexstr=state_root).rjust(32, b'\0')
            + Web3.to_bytes(hexstr=nullifier).rjust(32, b'\0')
        )

    def anchor(self, state_root: str, nullifier: str) -> str:
        """Send an EIP-1559 tx; bump priority fee on 'transaction underpriced'."""
        with self._lock:
            for attempt in range(5):
                try:
                    nonce = self.w3.eth.get_transaction_count(self.acct.address, "pending")
                    base_fee = self.w3.eth.fee_history(1, "latest", [25])["baseFeePerGas"][-1]
                    max_priority = self.w3.to_wei(2 * (attempt + 1), "gwei")  # +2 gwei/retry
                    max_fee = int(base_fee * 1.3) + max_priority
                    tx = {
                        "nonce": nonce,
                        "from": self.acct.address,
                        "to": self.contract_address,
                        "value": 0,
                        "gas": 100_000,
                        "maxFeePerGas": max_fee,
                        "maxPriorityFeePerGas": max_priority,
                        "chainId": self.w3.eth.chain_id,
                        "data": self._encode_anchor(state_root, nullifier),
                    }
                    signed = self.acct.sign_transaction(tx)
                    tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
                    return "0x" + tx_hash.hex()
                except Exception:
                    time.sleep(0.05 * (attempt + 1))  # backoff; next attempt bumps fee
        return ""


_SEPOLIA_BRIDGE = None


def _get_sepolia_bridge():
    global _SEPOLIA_BRIDGE
    if _SEPOLIA_BRIDGE is None:
        if not SEPOLIA_RPC_URL or not SEPOLIA_PRIVATE_KEY:
            return None
        _SEPOLIA_BRIDGE = SepoliaSettlementBridge(
            SEPOLIA_RPC_URL, SEPOLIA_PRIVATE_KEY, SEPOLIA_CONTRACT_ADDRESS
        )
    return _SEPOLIA_BRIDGE


async def _anchor_epoch(root: str, proof_count: int) -> str:
    """Route the epoch anchor to the configured L1 target (anvil or sepolia)."""
    if L1_NETWORK == "sepolia":
        bridge = _get_sepolia_bridge()
        if bridge is None:
            return ""
        return await asyncio.to_thread(bridge.anchor, root, root)
    if ANVIL_ENABLED:
        return await asyncio.to_thread(anchor_to_l1, root, root)
    return ""  # no L1 target — logical anchor only


def _batch_state_root(healthy_proofs: list) -> str:
    """Derive a combined ProtoGalaxy epoch root from a healthy batch."""
    digest = "".join(p.get("nullifier_hash", "") for p in healthy_proofs).encode()
    return hashlib.sha256(digest).hexdigest()[:32]


async def _commit_epoch(epoch: list) -> None:
    """Anchor one settlement epoch (list of healthy proofs) to L1."""
    if not epoch:
        return
    root = _batch_state_root(epoch)
    STATE["l1_anchors"] += 1
    tx = await _anchor_epoch(root, len(epoch))
    if not tx:
        print(f"  ⚠️ L1 anchor tx failed for epoch root {root[:12]}…")
    else:
        print(f"  ⚓ L1 anchored: {tx} (epoch {root[:12]}…, {len(epoch)} proofs)")


async def _flush_epoch() -> None:
    """Commit exactly EPOCH_SIZE healthy proofs as one full settlement epoch."""
    buf = STATE["epoch_buffer"]
    if len(buf) < EPOCH_SIZE:
        return
    epoch = buf[:EPOCH_SIZE]
    del buf[:EPOCH_SIZE]
    await _commit_epoch(epoch)


async def _epoch_sla_loop() -> None:
    """Time-SLA: flush the remaining partial epoch after EPOCH_MAX_AGE_S."""
    while True:
        await asyncio.sleep(EPOCH_MAX_AGE_S)
        buf = STATE["epoch_buffer"]
        if buf:
            epoch = buf[:]
            del buf[:]
            await _commit_epoch(epoch)


def _to_prometheus_text(d: dict) -> str:
    """Flatten a (possibly nested) metrics dict into Prometheus text format."""
    out = []

    def walk(obj, path):
        if isinstance(obj, dict):
            for k, v in obj.items():
                walk(v, path + [str(k)])
        elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
            out.append(f"{'_'.join(path)} {obj}")

    walk(d, [])
    return "\n".join(out) + ("\n" if out else "")


def start_metrics_server(port: int, get_metrics) -> None:
    """Serve /metrics — Prometheus text (default) or JSON (?format=json)."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import urlparse, parse_qs

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path.rstrip("/") in ("/metrics", ""):
                if parse_qs(parsed.query).get("format", [""])[0] == "json":
                    body = json.dumps(get_metrics()).encode()
                    ctype = "application/json"
                else:
                    body = _to_prometheus_text(get_metrics()).encode()
                    ctype = "text/plain; version=0.0.4"
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()


async def main():
    latency_ms = 0.0
    if len(sys.argv) > 1 and sys.argv[1] == "--latency":
        latency_ms = float(sys.argv[2]) / 1000.0 if len(sys.argv) > 2 else 0.0

    nc = await nats.connect(NATS_URL)
    t0 = time.time()

    async def handler(msg):
        if latency_ms > 0:
            await asyncio.sleep(latency_ms)
        payload = json.loads(msg.data.decode())
        # Warm-up heartbeats are not part of the settlement event stream
        if payload.get("type") == "WARMUP_PING":
            return  # warm-up heartbeat — fire-and-forget, no reply subject
        STATE["total_events"] += 1
        try:
            proof = witness_gen_timed(payload)
            await nc.publish(msg.reply, json.dumps(proof).encode())
            STATE["healthy_settled_total"] += 1
            STATE["l1_settled_events_total"] += 1
            STATE["epoch_buffer"].append(proof)
            if len(STATE["epoch_buffer"]) >= EPOCH_SIZE:
                await _flush_epoch()
        except WitnessTimeoutException:
            # Single poison event — quarantine directly
            await nc.publish(QUARANTINE_SUBJECT, json.dumps(payload).encode())
            STATE["quarantined_total"] += 1
            STATE["l1_settled_events_total"] += 1

    # Batch handler: receives array of payloads, returns array of proofs
    async def batch_handler(msg):
        batch_data = json.loads(msg.data.decode())
        if not isinstance(batch_data, list):
            return
        STATE["total_events"] += len(batch_data)
        # Binary bisect: isolate poison events, keep healthy 99%
        healthy, quarantined = await binary_bisect_and_quarantine(batch_data, nc)
        await nc.publish(msg.reply, json.dumps(healthy).encode())
        STATE["healthy_settled_total"] += len(healthy)
        STATE["quarantined_total"] += len(quarantined)
        STATE["l1_settled_events_total"] += len(healthy) + len(quarantined)
        if quarantined:
            print(f"  🚨 Quarantined {len(quarantined)} poison event(s) "
                  f"out of {len(batch_data)}")
        # Accumulate healthy proofs into the settlement epoch (across batches)
        STATE["epoch_buffer"].extend(healthy)
        if len(STATE["epoch_buffer"]) >= EPOCH_SIZE:
            await _flush_epoch()

        if STATE["total_events"] % 100 == 0:
            elapsed = time.time() - t0
            tps = STATE["total_events"] / elapsed if elapsed > 0 else 0
            l1_info = f"| L1: {STATE['l1_anchors']} anchored" if ANVIL_ENABLED else ""
            print(f"  [D01 Mock] {STATE['total_events']} events | {tps:.0f}/s {l1_info}")

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

    start_metrics_server(METRICS_PORT, metrics_snapshot)
    asyncio.create_task(_epoch_sla_loop())
    print(f"🧮 D01 Mock ZK Responder ready on {SUBJECT} (+ batch + deep-state) ({NATS_URL})")
    print(f"   📊 Metrics endpoint on :{METRICS_PORT}/metrics")
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
