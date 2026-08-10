"""S2: BridgeAgent — Cross-chain message relay with Merkle proofs and latency.

Chain: BRIDGE_LAYER | Asynchronous | Variable latency (2–5 ticks)
Transfers sensor batches from DEPIN_APPCHAIN to SETTLEMENT_L1.
"""

import hashlib
import logging
import os
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("BridgeAgent")


class BridgeAgent:
    """Relays batches across chains with Merkle proof generation and latency simulation."""

    def __init__(
        self,
        chain: str = "BRIDGE_LAYER",
        user_id: Optional[str] = None,
        latency_ticks: Optional[List[int]] = None,
    ):
        self.chain = chain
        self.user_id = user_id or os.getenv("SIMCHAIN_USER_ID", "default")
        self.latency_ticks = latency_ticks or [2, 3, 4, 5]
        self._total_messages_relayed = 0
        self._total_volume_bridged = 0.0

    async def process_batch(
        self, txs: List[Dict], target_chain: str = "SETTLEMENT_L1"
    ) -> Dict[str, Any]:
        """Process a batch of transactions for cross-chain relay."""
        job_id = str(uuid.uuid4())
        start_time = time.time()
        logs: List[str] = []

        try:
            logger.info(
                "BridgeAgent relaying batch",
                extra={
                    "job_id": job_id,
                    "tx_count": len(txs),
                    "target": target_chain,
                    "user_id": self.user_id,
                },
            )
            logs.append(
                f"[INFO] relaying {len(txs)} txs DEPIN→{target_chain}"
            )

            messages = []
            total_amount = 0.0
            latencies = []

            for tx in txs:
                merkle_root = hashlib.sha256(
                    f"{tx.get('sensor_id','')}{tx.get('amount',0)}{tx.get('timestamp','')}".encode()
                ).hexdigest()
                latency = random.choice(self.latency_ticks)
                latencies.append(latency)
                amount = tx.get("amount", 0)
                total_amount += amount

                msg = {
                    "source_chain": "DEPIN_APPCHAIN",
                    "target_chain": target_chain,
                    "payload": tx,
                    "bridge_proof": merkle_root,
                    "latency_ticks": latency,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                messages.append(msg)

            self._total_messages_relayed += len(messages)
            self._total_volume_bridged += total_amount

            avg_latency = sum(latencies) / len(latencies) if latencies else 0
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logs.append(
                f"[INFO] {len(messages)} bridged, "
                f"Ø_latency={avg_latency:.1f} ticks, "
                f"volume={total_amount:.4f}€, "
                f"elapsed={elapsed_ms}ms"
            )

            return {
                "status": "completed",
                "job_id": job_id,
                "artifacts": [
                    {
                        "type": "bridge_batch",
                        "chain": self.chain,
                        "source_chain": "DEPIN_APPCHAIN",
                        "target_chain": target_chain,
                        "message_count": len(messages),
                        "total_amount": round(total_amount, 6),
                        "avg_latency_ticks": round(avg_latency, 2),
                        "messages": messages,
                    }
                ],
                "error": None,
                "logs": logs,
                "metadata": {
                    "total_relayed_all_time": self._total_messages_relayed,
                    "total_volume_bridged": round(self._total_volume_bridged, 6),
                    "elapsed_ms": elapsed_ms,
                    "user_id": self.user_id,
                },
            }

        except Exception as e:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logger.error(
                "BridgeAgent failed",
                extra={"job_id": job_id, "error": str(e)},
            )
            logs.append(f"[ERROR] {e}")

            return {
                "status": "failed",
                "job_id": job_id,
                "artifacts": [],
                "error": {"code": "BRIDGE_RELAY_FAILED", "message": str(e)},
                "logs": logs,
                "metadata": {"elapsed_ms": elapsed_ms, "user_id": self.user_id},
            }

    def get_stats(self) -> Dict[str, Any]:
        """Return current bridge statistics."""
        return {
            "total_messages_relayed": self._total_messages_relayed,
            "total_volume_bridged": round(self._total_volume_bridged, 6),
            "latency_ticks_range": self.latency_ticks,
            "chain": self.chain,
        }
