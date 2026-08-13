#!/usr/bin/env python3
"""Panzergrenadier NATS Handler — subscribes to agentx.infantry.edge.

The surface layer (C01–C09) publishes complex events to agentx.infantry.edge
without slowing its own throughput. This handler consumes them, routes through
the PanzergrenadierCoordinator (P01–P09), and publishes clearance results to
agentx.infantry.cleared.

Usage:
  NATS_URL=nats://localhost:4222 python -m agents.mechanized.handler
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, Optional

from .base import PanzergrenadierCoordinator, ClearanceResult
from .p01_cross_shard import P01CrossShardLeader
from .p02_state_conflict import P02StateConflictLeader
from .p03_compliance import P03ComplianceLeader
from .p04_isolation import P04Isolation
from .p05_forensics import P05Forensics
from .p06_correction import P06Correction
from .p07_reintegration import P07Reintegration
from .p08_security import P08Security
from .p09_reconnaissance import P09Reconnaissance

logger = logging.getLogger("PanzergrenadierHandler")

NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
EDGE_SUBJECT = "agentx.infantry.edge"
CLEARED_SUBJECT = "agentx.infantry.cleared"


class PanzergrenadierHandler:
    """NATS consumer that routes edge-clearance requests through P01–P09."""

    def __init__(self, nats_url: str = NATS_URL):
        self.nats_url = nats_url
        self.coord = PanzergrenadierCoordinator()
        self._build_coordinator()
        self._nc = None
        self.total_processed = 0
        self.total_cleared = 0
        self.total_errors = 0

    def _build_coordinator(self):
        self.coord.register_leader(P01CrossShardLeader())
        self.coord.register_leader(P02StateConflictLeader())
        self.coord.register_leader(P03ComplianceLeader())
        self.coord.register_subagent(P04Isolation())
        self.coord.register_subagent(P05Forensics())
        self.coord.register_subagent(P06Correction())
        self.coord.register_subagent(P07Reintegration())
        self.coord.set_security(P08Security())
        self.coord.set_recon(P09Reconnaissance())

    async def run_forever(self):
        logger.info("🪖 PanzergrenadierHandler starting — subscribing to %s", EDGE_SUBJECT)
        try:
            import nats
            self._nc = await nats.connect(self.nats_url, max_reconnect_attempts=-1)
            await self._nc.subscribe(EDGE_SUBJECT, cb=self._on_event, queue="infantry-workers")
            logger.info("📡 Subscribed to %s (queue=infantry-workers)", EDGE_SUBJECT)
        except Exception as e:
            logger.warning("⚠️ NATS unavailable (%s) — loopback mode", e)
            self._nc = None

        while True:
            await asyncio.sleep(1)

    async def _on_event(self, msg):
        self.total_processed += 1
        t0 = time.time()
        try:
            event = json.loads(msg.data.decode())
            result = await self.coord.process(event)
            await self._publish_result(result, msg.reply)
            if result.cleared:
                self.total_cleared += 1
        except Exception as e:
            self.total_errors += 1
            logger.error("Panzergrenadier event error: %s", e)

    async def _publish_result(self, result: ClearanceResult, reply: str):
        payload = json.dumps({
            "event_id": result.event_id,
            "dismounted": result.dismounted,
            "cleared": result.cleared,
            "agent_id": result.agent_id,
            "note": result.note,
            "elapsed_ms": result.elapsed_ms,
        }).encode()
        if not self._nc:
            return
        await self._nc.publish(CLEARED_SUBJECT, payload)
        if reply:
            await self._nc.publish(reply, payload)

    def status(self) -> Dict[str, Any]:
        return {
            "total_processed": self.total_processed,
            "total_cleared": self.total_cleared,
            "total_errors": self.total_errors,
            "coordinator": self.coord.stats(),
        }


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    handler = PanzergrenadierHandler()
    await handler.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
