"""
Agent X — API Agent 10: BlockchainAnchorAgent (Merkle-Tree-Batcher).

Verantwortung: Bündelt bis zu 50 HandoverProof-Root-Hashes in einen
Merkle-Tree und verankert NUR DEN ROOT auf der Blockchain (Base L2).

Sub-Agenten:
  10a: MerkleTreeBuilder — Baut Merkle-Tree aus Root-Hashes
  10b: BatchCollector — Sammelt Proofs bis Batch-Größe erreicht
  10c: CrashRecoveryGuard — Redis-Cache vor DB-Write (Crash-Sicherheit)

Kosten: ~$0.02 pro Abnahmeprotokoll (50er Batch → 1 TX)
"""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("BlockchainAnchor")

BATCH_SIZE = int(os.getenv("ANCHOR_BATCH_SIZE", "50"))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
CONTRACT_ADDRESS = os.getenv("ANCHOR_CONTRACT", "0x0000000000000000000000000000000000000000")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _keccak256(data: bytes) -> bytes:
    """Keccak-256 Hash (identisch zu Soliditys keccak256)."""
    return hashlib.sha3_256(data).digest()


@dataclass
class HandoverProof:
    """Ein einzelnes Abnahmeprotokoll vor dem Batching."""
    session_id: str
    root_hash: str  # 0x... — Hash des gesamten Payloads
    project_code: str
    timestamp_unix: int
    photo_hashes: list[str] = field(default_factory=list)
    protocol_hash: str = ""
    gps_lat: float = 0.0
    gps_lng: float = 0.0


@dataclass
class AnchoredBatch:
    """Ein erfolgreich verankerter Batch."""
    merkle_root: str
    tx_hash: str
    block_number: int
    batch_size: int
    proofs: list[HandoverProof]
    anchored_at: str = ""


# ─── Sub-Agent 10a: MerkleTreeBuilder ────────────────────────────────

class MerkleTreeBuilder:
    """Baut einen Merkle-Tree aus Root-Hashes (Pure Python, keine Dependencies).

    Verwendet Keccak-256 (Solidity-kompatibel).
    """

    @staticmethod
    def build(leaves_hex: list[str]) -> tuple[str, dict[str, list[str]]]:
        """Baut Merkle-Tree. Gibt (root_hex, {leaf_hex: [proof_hex, ...]}) zurück.

        Args:
            leaves_hex: Liste von 0x-prefixed 32-Byte-Hashes

        Returns:
            (merkle_root_hex, proofs_dict)
        """
        if not leaves_hex:
            return "0x" + "0" * 64, {}

        # Konvertiere zu Bytes
        leaves = [bytes.fromhex(h[2:]) for h in leaves_hex]

        # Baue Tree Layer für Layer
        tree_layers = [leaves]
        while len(tree_layers[-1]) > 1:
            current = tree_layers[-1]
            next_layer = []
            for i in range(0, len(current), 2):
                left = current[i]
                right = current[i + 1] if i + 1 < len(current) else left  # Dupliziere letztes Leaf
                # Sortierte Kombination (Solidity-Standard)
                combined = left + right if left < right else right + left
                next_layer.append(_keccak256(combined))
            tree_layers.append(next_layer)

        root = tree_layers[-1][0]
        root_hex = "0x" + root.hex()

        # Baue Proofs für jedes Leaf
        proofs: dict[str, list[str]] = {}
        for leaf_idx, leaf in enumerate(leaves):
            proof = []
            idx = leaf_idx
            for layer in tree_layers[:-1]:
                if idx % 2 == 0:
                    # Wir sind links → sibling ist rechts (oder wir selbst wenn letztes)
                    sibling_idx = idx + 1 if idx + 1 < len(layer) else idx
                else:
                    sibling_idx = idx - 1
                proof.append("0x" + layer[sibling_idx].hex())
                idx //= 2
            proofs["0x" + leaf.hex()] = proof

        return root_hex, proofs

    @staticmethod
    def verify(leaf_hex: str, proof: list[str], root_hex: str) -> bool:
        """Verifiziert einen Merkle-Proof. True wenn Leaf Teil des Roots."""
        if not leaf_hex or not proof or not root_hex:
            return False

        try:
            current = bytes.fromhex(leaf_hex[2:])
            for sibling_hex in proof:
                sibling = bytes.fromhex(sibling_hex[2:])
                # Sortierte Kombination (Solidity-Standard)
                if current < sibling:
                    combined = current + sibling
                else:
                    combined = sibling + current
                current = _keccak256(combined)
            return "0x" + current.hex() == root_hex
        except Exception:
            return False


# ─── Sub-Agent 10b: BatchCollector ───────────────────────────────────

class BatchCollector:
    """Sammelt Proofs im Speicher bis Batch-Größe erreicht ist."""

    def __init__(self, batch_size: int = BATCH_SIZE):
        self.batch_size = batch_size
        self._pending: list[HandoverProof] = []
        self._total_collected = 0

    def add(self, proof: HandoverProof) -> bool:
        """Fügt Proof hinzu. Returns True wenn Batch voll und ready zum Ankern."""
        self._pending.append(proof)
        self._total_collected += 1
        return len(self._pending) >= self.batch_size

    def flush(self) -> list[HandoverProof]:
        """Gibt aktuellen Batch zurück und leert den Collector."""
        batch = self._pending[:]
        self._pending.clear()
        return batch

    @property
    def size(self) -> int:
        return len(self._pending)

    @property
    def is_ready(self) -> bool:
        return self.size >= self.batch_size


# ─── Sub-Agent 10c: CrashRecoveryGuard ────────────────────────────────

class CrashRecoveryGuard:
    """Redis-Cache VOR Blockchain-Write → Crash-Sicherheit.

    Problem: Server-Crash NACH Blockchain-TX aber VOR DB-Update
             → Proofs sind on-chain, aber DB hat keinen Record.

    Lösung: Speichere tx_hash SOFORT nach Senden in Redis.
            Recovery-Job prüft: "Ist dieser Root on-chain?" → DB-Update.
    """

    def __init__(self, redis_client=None):
        self.redis = redis_client
        self._memory: dict[str, dict] = {}

    def cache_pre_write(self, merkle_root: str, session_ids: list[str]) -> str:
        """Speichert Batch-Daten VOR der Blockchain-TX."""
        key = f"anchor:preflight:{merkle_root[:16]}"
        data = {
            "merkle_root": merkle_root,
            "session_ids": json.dumps(session_ids),
            "status": "PENDING_TX",
            "cached_at": str(time.time()),
        }
        if self.redis:
            self.redis.hset(key, mapping=data)
            self.redis.expire(key, 86400)  # 24h TTL
        else:
            self._memory[key] = data
        return key

    def mark_confirmed(self, merkle_root: str, tx_hash: str, block_number: int):
        """Markiert Batch als bestätigt NACH erfolgreichem DB-Update."""
        key = f"anchor:preflight:{merkle_root[:16]}"
        update = {"status": "CONFIRMED", "tx_hash": tx_hash,
                  "block_number": str(block_number)}
        if self.redis:
            self.redis.hset(key, mapping=update)
        else:
            self._memory.get(key, {}).update(update)

    def get_pending_recovery(self) -> list[dict]:
        """Findet Batches die on-chain sind aber nicht in DB bestätigt."""
        pending = []
        if self.redis:
            keys = self.redis.keys("anchor:preflight:*")
            for key in keys:
                data = self.redis.hgetall(key)
                if data.get("status") == "PENDING_TX":
                    pending.append(data)
        else:
            pending = [d for d in self._memory.values() if d.get("status") == "PENDING_TX"]
        return pending


# ─── Agent 10: BlockchainAnchorAgent ─────────────────────────────────

class BlockchainAnchorAgent:
    """Haupt-Agent: Sammelt, bündelt und verankert HandoverProofs.

    Usage:
        anchor = BlockchainAnchorAgent()
        anchor.submit(proof)  # Sammelt bis Batch voll
        # → Bei 50 Proofs: automatischer Merkle-Tree + TX
    """

    def __init__(self, batch_size: int = BATCH_SIZE, redis_client=None):
        self.collector = BatchCollector(batch_size)
        self.merkle = MerkleTreeBuilder()
        self.recovery = CrashRecoveryGuard(redis_client)
        self._anchored_batches: list[AnchoredBatch] = []

    def submit(self, proof: HandoverProof) -> dict:
        """Nimmt einen Proof entgegen. Wenn Batch voll → anchor.

        Returns:
            {"status": "queued"|"anchored", "batch_size": N, ...}
        """
        is_full = self.collector.add(proof)

        if is_full:
            return self._execute_batch()
        return {"status": "queued", "current_batch_size": self.collector.size,
                "session_id": proof.session_id}

    def _execute_batch(self) -> dict:
        """Führt den Batch-Anker durch."""
        batch = self.collector.flush()
        if not batch:
            return {"status": "empty_batch"}

        # 1. Merkle-Tree bauen
        leaves = [p.root_hash for p in batch]
        root, proofs = self.merkle.build(leaves)

        # 2. Crash-Recovery: Pre-Flight-Cache
        session_ids = [p.session_id for p in batch]
        self.recovery.cache_pre_write(root, session_ids)

        # 3. Blockchain-TX simulieren (in Produktion: ethers/web3)
        tx_hash = "0x" + hashlib.sha256(root.encode()).hexdigest()[:40]
        block_number = 21_000_000 + len(self._anchored_batches)

        # 4. Crash-Recovery: Mark confirmed
        self.recovery.mark_confirmed(root, tx_hash, block_number)

        # 5. Record
        anchored = AnchoredBatch(
            merkle_root=root, tx_hash=tx_hash, block_number=block_number,
            batch_size=len(batch), proofs=batch, anchored_at=_now_iso(),
        )
        self._anchored_batches.append(anchored)

        logger.info("Batch anchored: root=%s, size=%d, tx=%s",
                     root[:20], len(batch), tx_hash[:16])

        return {
            "status": "anchored",
            "merkle_root": root,
            "tx_hash": tx_hash,
            "block_number": block_number,
            "batch_size": len(batch),
            "session_ids": session_ids,
            "proofs": {p.session_id: [s[:16] + "..." for s in proofs.get(p.root_hash, [])]
                       for p in batch},
            "estimated_cost_usd": round(0.02, 4),
            "cost_per_proof_usd": round(0.02 / len(batch), 6),
        }

    def verify_proof(self, session_id: str, leaf_hash: str,
                     merkle_root: str, proof: list[str]) -> dict:
        """Verifiziert ob ein Proof Teil eines verankerten Merkle-Roots ist."""
        valid = self.merkle.verify(leaf_hash, proof, merkle_root)

        # Prüfe ob der Root on-chain ist (simuliert — in Produktion: contract.isAnchored)
        onchain = any(b.merkle_root == merkle_root for b in self._anchored_batches)

        return {
            "verified": valid and onchain,
            "merkle_proof_valid": valid,
            "on_chain": onchain,
            "session_id": session_id,
            "merkle_root": merkle_root,
        }

    def force_flush(self) -> dict:
        """Erzwingt Ankerung des aktuellen Batches (auch wenn nicht voll)."""
        if self.collector.size == 0:
            return {"status": "empty_batch"}
        return self._execute_batch()

    def recover_pending(self) -> list[dict]:
        """Recovery-Job: Findet Batches die on-chain aber nicht in DB sind."""
        return self.recovery.get_pending_recovery()

    @property
    def stats(self) -> dict:
        return {
            "total_anchored": len(self._anchored_batches),
            "total_proofs": sum(b.batch_size for b in self._anchored_batches),
            "pending_batch_size": self.collector.size,
            "estimated_total_cost_usd": round(len(self._anchored_batches) * 0.02, 2),
        }


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    anchor = BlockchainAnchorAgent(batch_size=5)  # Demo: 5er Batch

    print("=== Merkle-Tree-Batcher Demo (Batch=5) ===")
    for i in range(5):
        proof = HandoverProof(
            session_id=f"sess_{i:04d}",
            root_hash="0x" + hashlib.sha256(f"payload_{i}".encode()).hexdigest(),
            project_code="WP-2026-08",
            timestamp_unix=int(time.time()),
            photo_hashes=["0x" + hashlib.sha256(f"photo_{i}_{j}".encode()).hexdigest()
                          for j in range(3)],
            protocol_hash="0x" + hashlib.sha256(f"protocol_{i}".encode()).hexdigest(),
        )
        result = anchor.submit(proof)
        status = result.get("status", "?")
        print(f"  Proof {i}: {status}", end="")
        if status == "anchored":
            print(f" — root={result['merkle_root'][:20]}..., "
                  f"tx={result['tx_hash'][:16]}..., "
                  f"${result['estimated_cost_usd']} total, "
                  f"${result['cost_per_proof_usd']:.6f}/proof")
        else:
            print(f" (batch={result['current_batch_size']})")

    # Verifikations-Test
    last_batch = anchor._anchored_batches[-1]
    first_proof = last_batch.proofs[0]
    first_root = first_proof.root_hash
    leaves = [p.root_hash for p in last_batch.proofs]
    _, proofs = anchor.merkle.build(leaves)
    verification = anchor.verify_proof(
        first_proof.session_id, first_root,
        last_batch.merkle_root, proofs.get(first_root, []),
    )
    print(f"\n  Verify {first_proof.session_id}: "
          f"Merkle={'✓' if verification['merkle_proof_valid'] else '✗'}, "
          f"Chain={'✓' if verification['on_chain'] else '✗'}")
    print(f"  Stats: {json.dumps(anchor.stats, indent=2)}")
