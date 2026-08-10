"""A2: BridgeRelayerChain — Cross-chain message relay with Merkle proofs.

Chain: BRIDGE_LAYER | Async relay between sovereign chains
Generates Merkle proofs for batch verification on the target chain.
"""

import logging
import os
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..bridge_protocol import BridgeProtocol

logger = logging.getLogger("BridgeRelayerChain")


class BridgeRelayerChain:
    """Sovereign relay chain: batches sensor data for cross-chain settlement."""

    def __init__(
        self,
        chain_id: str = "BRIDGE_LAYER",
        user_id: Optional[str] = None,
        latency_range: Optional[tuple] = None,
    ):
        self.chain_id = chain_id
        self.user_id = user_id or os.getenv("MULTICHAIN_USER_ID", "default")
        lo = int(os.getenv("MC_BRIDGE_LATENCY_LO", "100"))
        hi = int(os.getenv("MC_BRIDGE_LATENCY_HI", "500"))
        self.latency_range = latency_range or (lo, hi)
        self.block_height = 0
        self.mempool: List[Dict] = []
        self.state_root = "0x0"
        self._total_relayed = 0
        self._total_volume = 0.0
        self._bridge = BridgeProtocol()

    async def relay(
        self,
        source: str,
        target: str,
        payload: List[Dict],
        merkle_root: str,
    ) -> Dict[str, Any]:
        """Relay a batch with Merkle proof to the target chain."""
        job_id = str(uuid.uuid4())
        start_time = time.time()
        logs: List[str] = []

        try:
            logger.info(
                "BridgeRelayer relaying batch",
                extra={"job_id": job_id, "source": source, "target": target,
                       "tx_count": len(payload)},
            )

            proof = self._bridge.create_proof(payload, source, target)
            latency = random.randint(*self.latency_range)
            total_amount = round(sum(p.get("amount", 0) for p in payload), 6)

            self._total_relayed += len(payload)
            self._total_volume += total_amount
            self.block_height += 1

            elapsed_ms = round((time.time() - start_time) * 1000, 2)

            return {
                "status": "completed",
                "job_id": job_id,
                "artifacts": [{
                    "type": "bridge_relay",
                    "chain_id": self.chain_id,
                    "source_chain": source,
                    "target_chain": target,
                    "merkle_root": proof.merkle_root,
                    "proof_path": proof.proof_path,
                    "batch_size": proof.batch_size,
                    "total_amount": total_amount,
                    "latency_ms": latency,
                    "transactions": payload,
                }],
                "error": None,
                "logs": logs,
                "metadata": {
                    "total_relayed": self._total_relayed,
                    "total_volume": round(self._total_volume, 6),
                    "elapsed_ms": elapsed_ms,
                    "user_id": self.user_id,
                },
            }

        except Exception as e:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logger.error("BridgeRelayer failed", extra={"job_id": job_id, "error": str(e)})
            return {
                "status": "failed",
                "job_id": job_id,
                "artifacts": [],
                "error": {"code": "BRIDGE_RELAY_FAILED", "message": str(e)},
                "logs": [f"[ERROR] {e}"],
                "metadata": {"elapsed_ms": elapsed_ms, "user_id": self.user_id},
            }

    def get_chain_state(self) -> Dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "block_height": self.block_height,
            "total_relayed": self._total_relayed,
            "total_volume": round(self._total_volume, 6),
        }
