"""A1: SensorAggregatorChain — Sovereign DePIN appchain, 1000 TPS.

Chain: DEPIN_APPCHAIN | Consensus: batch every 1000 events | Block time: ~1s
Each block produces a Merkle root from 1000 IoT sensor readings.
"""

import hashlib
import logging
import os
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("SensorAggregatorChain")


class SensorAggregatorChain:
    """Sovereign appchain: aggregates 1000 sensor events per block."""

    def __init__(
        self,
        chain_id: str = "DEPIN_APPCHAIN",
        user_id: Optional[str] = None,
        batch_size: Optional[int] = None,
        total_sensors: Optional[int] = None,
    ):
        self.chain_id = chain_id
        self.user_id = user_id or os.getenv("MULTICHAIN_USER_ID", "default")
        self.batch_size = batch_size or int(os.getenv("MC_SENSOR_BATCH", "1000"))
        self.total_sensors = total_sensors or int(os.getenv("MC_TOTAL_SENSORS", "10000"))
        self.block_height = 0
        self.mempool: List[Dict] = []
        self.state_root = "0x0"
        self._sensor_types = ["temperature", "humidity", "pressure", "vibration", "energy_kwh"]
        self._total_events = 0
        self._total_volume = 0.0

    async def process_block(self, cycle: int) -> Dict[str, Any]:
        """Mine one block — aggregate 1000 sensor events."""
        job_id = str(uuid.uuid4())
        start_time = time.time()
        logs: List[str] = []

        try:
            logger.info(
                "SensorChain mining block",
                extra={"job_id": job_id, "cycle": cycle, "chain": self.chain_id},
            )

            txs = []
            for i in range(self.batch_size):
                sensor_id = f"SENSOR_{random.randint(1, self.total_sensors)}"
                sensor_type = random.choice(self._sensor_types)
                amount = round(random.uniform(0.001, 0.50), 6)
                tx = {
                    "sensor_id": sensor_id,
                    "sensor_type": sensor_type,
                    "amount": amount,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "proof": hashlib.sha256(
                        f"{sensor_id}{amount}{cycle}{i}".encode()
                    ).hexdigest()[:16],
                }
                txs.append(tx)

            # Merkle root for this block
            merkle_input = "".join(t["proof"] for t in txs)
            state_root = hashlib.sha256(merkle_input.encode()).hexdigest()
            self.state_root = state_root
            self.block_height += 1
            self.mempool.extend(txs)
            self._total_events += len(txs)
            total_amount = round(sum(t["amount"] for t in txs), 6)
            self._total_volume += total_amount

            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logs.append(f"[INFO] block={self.block_height} txs={len(txs)} root={state_root[:16]}")

            return {
                "status": "completed",
                "job_id": job_id,
                "artifacts": [{
                    "type": "sensor_block",
                    "chain_id": self.chain_id,
                    "block_height": self.block_height,
                    "event_count": len(txs),
                    "total_amount": total_amount,
                    "state_root": state_root,
                    "transactions": txs,
                }],
                "error": None,
                "logs": logs,
                "metadata": {
                    "total_events_all_time": self._total_events,
                    "total_volume_all_time": round(self._total_volume, 6),
                    "elapsed_ms": elapsed_ms,
                    "user_id": self.user_id,
                },
            }

        except Exception as e:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logger.error("SensorChain failed", extra={"job_id": job_id, "error": str(e)})
            return {
                "status": "failed",
                "job_id": job_id,
                "artifacts": [],
                "error": {"code": "SENSOR_CHAIN_FAILED", "message": str(e)},
                "logs": [f"[ERROR] {e}"],
                "metadata": {"elapsed_ms": elapsed_ms, "user_id": self.user_id},
            }

    def get_chain_state(self) -> Dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "block_height": self.block_height,
            "state_root": self.state_root,
            "mempool_size": len(self.mempool),
            "total_events": self._total_events,
            "total_volume": round(self._total_volume, 6),
        }
