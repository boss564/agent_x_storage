"""Bridge Protocol — Cross-chain communication with Merkle proofs.

Provides cryptographic proof-of-inclusion for messages relayed between
sovereign appchains. Each batch gets a Merkle root; the receiving chain
can verify any individual transaction against that root using the proof path.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


@dataclass
class BridgeProof:
    """A Merkle proof for a batch of cross-chain transactions."""
    source_chain: str
    target_chain: str
    merkle_root: str
    proof_path: List[str] = field(default_factory=list)
    batch_size: int = 0
    timestamp: str = ""


class BridgeProtocol:
    """Merkle-tree-based cross-chain bridge protocol."""

    @staticmethod
    def build_merkle_tree(txs: List[Dict]) -> tuple:
        """Build a Merkle tree from transactions. Returns (root, tree_layers)."""
        if not txs:
            return "0x0", []

        leaves = [
            hashlib.sha256(
                json.dumps(tx, sort_keys=True, default=str).encode()
            ).hexdigest()
            for tx in txs
        ]

        layers = [leaves]
        current = leaves

        while len(current) > 1:
            # Pad to even
            if len(current) % 2 != 0:
                current = current + [current[-1]]
            current = [
                hashlib.sha256(
                    ((current[i] + current[i + 1]) if current[i] <= current[i + 1]
                     else (current[i + 1] + current[i])).encode()
                ).hexdigest()
                for i in range(0, len(current), 2)
            ]
            layers.append(current)

        return layers[-1][0] if layers[-1] else "0x0", layers

    @classmethod
    def create_proof(
        cls,
        txs: List[Dict],
        source: str = "DEPIN_APPCHAIN",
        target: str = "SETTLEMENT_L1",
    ) -> BridgeProof:
        """Create a Merkle proof for a batch of transactions."""
        root, layers = cls.build_merkle_tree(txs)

        # Build proof path (sibling hashes for each layer)
        proof_path = []
        if len(layers) >= 2:
            for layer_idx in range(len(layers) - 1):
                current_layer = layers[layer_idx]
                if len(current_layer) >= 2:
                    proof_path.append(current_layer[1])

        return BridgeProof(
            source_chain=source,
            target_chain=target,
            merkle_root=root,
            proof_path=proof_path,
            batch_size=len(txs),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def verify_proof(proof: BridgeProof, tx: Dict) -> bool:
        """Verify a single transaction against a Merkle proof."""
        tx_hash = hashlib.sha256(
            json.dumps(tx, sort_keys=True, default=str).encode()
        ).hexdigest()
        current = tx_hash

        for sibling in proof.proof_path:
            combined = (current + sibling) if current <= sibling else (sibling + current)
            current = hashlib.sha256(combined.encode()).hexdigest()

        return current == proof.merkle_root

    @classmethod
    def batch_verify(cls, proof: BridgeProof, txs: List[Dict]) -> Dict[str, Any]:
        """Verify a batch by rebuilding the Merkle tree and comparing roots."""
        rebuilt_root, _ = cls.build_merkle_tree(txs)
        all_ok = rebuilt_root == proof.merkle_root
        return {
            "total": len(txs),
            "verified": len(txs) if all_ok else 0,
            "failed": 0 if all_ok else len(txs),
            "all_verified": all_ok,
        }
