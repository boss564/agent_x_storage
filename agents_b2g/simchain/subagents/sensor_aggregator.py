"""S1: SensorAggregatorAgent — High-frequency sensor data aggregation.

Chain: DEPIN_APPCHAIN | 1000 TPS | Low-Value (€0.001–0.50)
Produces batch Merkle proofs from simulated IoT sensor streams.
"""

import hashlib
import logging
import os
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("SensorAggregatorAgent")


class SensorAggregatorAgent:
    """Aggregates sensor events into batch proofs for the DePIN appchain."""

    def __init__(
        self,
        chain: str = "DEPIN_APPCHAIN",
        user_id: Optional[str] = None,
        batch_size: Optional[int] = None,
        total_sensors: Optional[int] = None,
    ):
        self.chain = chain
        self.user_id = user_id or os.getenv("SIMCHAIN_USER_ID", "default")
        self.batch_size = batch_size or int(os.getenv("SIMCHAIN_SENSOR_BATCH_SIZE", "1000"))
        self.total_sensors = total_sensors or int(os.getenv("SIMCHAIN_TOTAL_SENSORS", "10000"))
        self._sensor_types = ["temperature", "humidity", "pressure", "vibration", "energy_kwh"]
        self._total_events = 0
        self._total_volume = 0.0

    async def process_batch(self, cycle: int) -> Dict[str, Any]:
        """Process one batch of sensor events and return standardized JSON."""
        job_id = str(uuid.uuid4())
        start_time = time.time()
        logs: List[str] = []

        try:
            logger.info(
                "SensorAggregator processing batch",
                extra={"job_id": job_id, "cycle": cycle, "user_id": self.user_id},
            )
            logs.append(f"[INFO] cycle={cycle} batch_size={self.batch_size}")

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

            batch_hash = hashlib.sha256(str(txs).encode()).hexdigest()
            total_amount = round(sum(t["amount"] for t in txs), 6)
            self._total_events += len(txs)
            self._total_volume += total_amount

            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logs.append(
                f"[INFO] {len(txs)} events aggregated, "
                f"volume={total_amount:.4f}€, hash={batch_hash[:16]}, "
                f"elapsed={elapsed_ms}ms"
            )

            return {
                "status": "completed",
                "job_id": job_id,
                "artifacts": [
                    {
                        "type": "sensor_batch",
                        "chain": self.chain,
                        "cycle": cycle,
                        "event_count": len(txs),
                        "total_amount": total_amount,
                        "batch_hash": batch_hash,
                        "sensor_types_used": self._sensor_types,
                        "transactions": txs,
                    }
                ],
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
            logger.error(
                "SensorAggregator failed",
                extra={"job_id": job_id, "cycle": cycle, "error": str(e)},
            )
            logs.append(f"[ERROR] {e}")

            return {
                "status": "failed",
                "job_id": job_id,
                "artifacts": [],
                "error": {"code": "SENSOR_AGGREGATION_FAILED", "message": str(e)},
                "logs": logs,
                "metadata": {"elapsed_ms": elapsed_ms, "user_id": self.user_id},
            }

    def get_stats(self) -> Dict[str, Any]:
        """Return current agent statistics."""
        return {
            "total_events": self._total_events,
            "total_volume": round(self._total_volume, 6),
            "batch_size": self.batch_size,
            "total_sensors": self.total_sensors,
            "chain": self.chain,
        }
