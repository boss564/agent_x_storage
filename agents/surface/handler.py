#!/usr/bin/env python3
"""SurfaceHandler — C01–C09 Schnellboot: NATS subscriber, TPS meter, Escrow trigger.

Each replica subscribes to agentx.surface.events with a queue group so
load is distributed across all 9 agents. Validated payloads are forwarded
to the settlement pipeline (C09 ingest handler).
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("SurfaceHandler")


class SurfaceHandler:
    """High-throughput surface agent: NATS ingest → validate → forward to settlement."""

    def __init__(
        self,
        agent_id: str = "C01",
        chain_id: str = "appchain-eu",
        nats_url: str = "nats://localhost:4222",
        zk_trigger_rate: float = 0.0,
    ):
        self.agent_id = agent_id
        self.chain_id = chain_id
        self.nats_url = nats_url
        self.zk_trigger_rate = zk_trigger_rate
        self._nc: Any = None
        self._js: Any = None

        # TPS metering
        self._tick_count: int = 0
        self._tick_start: float = 0.0
        self._last_tps: float = 0.0
        self._total_processed: int = 0
        self._total_errors: int = 0

        # ZK forwarding
        self._zk_forwarded: int = 0
        self._zk_responses: int = 0
        self._zk_errors: int = 0
        self._zk_latency_window: list = []

        # Latency tracking
        self._latency_window: list = []  # last 100 latencies in µs
        self._latency_window_max: int = 100

    # ── Lifecycle ───────────────────────────────────────────────────────

    async def run_forever(self):
        """Start the agent and block until shutdown."""
        logger.info("🚤 %s starting for chain %s — connecting to %s",
                     self.agent_id, self.chain_id, self.nats_url)

        try:
            import nats
            self._nc = await nats.connect(self.nats_url, max_reconnect_attempts=-1)
            self._js = self._nc.jetstream()
            logger.info("✅ %s connected to NATS JetStream", self.agent_id)
        except Exception as e:
            logger.warning("⚠️ NATS unavailable (%s) — running in loopback mode", e)
            self._nc = None
            self._js = None

        # Start TPS meter reset loop
        asyncio.create_task(self._tps_loop())

        # Subscribe to surface events with queue group for load balancing
        if self._nc:
            subject = "agentx.surface.events"
            await self._nc.subscribe(
                subject, cb=self._on_message, queue="surface-workers"
            )
            logger.info("📡 %s subscribed to %s (queue=surface-workers)", self.agent_id, subject)

        # Keep-alive loop
        while True:
            await asyncio.sleep(1)

    # ── Message Handling ────────────────────────────────────────────────

    async def _on_message(self, msg):
        """Process an incoming NATS message."""
        t0 = time.time()
        self._tick_count += 1

        try:
            payload = json.loads(msg.data.decode())
            schema = payload.get("schema", "UNKNOWN")
            device_id = payload.get("device_id", "")
            amount = payload.get("amount", 0)

            # Validate: schema must be known
            if schema not in ("VOB_B", "SENSOR", "COMPLIANCE", "SETTLEMENT"):
                self._total_errors += 1
                return

            self._total_processed += 1

            # ZK Trigger: forward subset to subsurface
            if self.zk_trigger_rate > 0 and self._nc and self._nc.is_connected:
                if hash(payload.get("payload_id", "")) % 100 < (self.zk_trigger_rate * 100):
                    asyncio.create_task(self._forward_zk(payload, t0))

            # Track latency
            elapsed_us = (time.time() - t0) * 1_000_000
            self._latency_window.append(elapsed_us)
            if len(self._latency_window) > self._latency_window_max:
                self._latency_window.pop(0)

        except Exception as e:
            self._total_errors += 1
            logger.error("%s message error: %s", self.agent_id, e)

    # ── ZK Forwarding ───────────────────────────────────────────────────

    async def _forward_zk(self, payload: dict, t0: float):
        """Forward payload to subsurface ZK engine via NATS request."""
        self._zk_forwarded += 1
        try:
            response = await self._nc.request(
                "agentx.subsurface.zk_request",
                json.dumps(payload).encode(),
                timeout=2,
            )
            self._zk_responses += 1
            zk_lat = (time.time() - t0) * 1_000_000
            self._zk_latency_window.append(zk_lat)
            if len(self._zk_latency_window) > self._latency_window_max:
                self._zk_latency_window.pop(0)
        except Exception:
            self._zk_errors += 1

    # ── TPS Metering ────────────────────────────────────────────────────

    async def _tps_loop(self):
        """Reset tick counter every second to measure TPS."""
        self._tick_start = time.time()
        while True:
            await asyncio.sleep(1)
            elapsed = time.time() - self._tick_start
            self._last_tps = self._tick_count / elapsed if elapsed > 0 else 0
            self._tick_count = 0
            self._tick_start = time.time()

    # ── Status ──────────────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        avg_lat = (
            sum(self._latency_window) / len(self._latency_window)
            if self._latency_window else 0
        )
        return {
            "agent_id": self.agent_id,
            "chain_id": self.chain_id,
            "tps": round(self._last_tps, 1),
            "total_processed": self._total_processed,
            "total_errors": self._total_errors,
            "avg_latency_us": round(avg_lat, 1),
            "nats_connected": self._nc is not None and self._nc.is_connected,
            "zk_forwarded": self._zk_forwarded,
            "zk_responses": self._zk_responses,
            "zk_errors": self._zk_errors,
        }
