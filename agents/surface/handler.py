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
        self._bg_tasks: set = set()  # GC-safe task references

        # TPS metering
        self._tick_count: int = 0
        self._tick_start: float = 0.0
        self._last_tps: float = 0.0
        self._total_processed: int = 0
        self._total_errors: int = 0

        # ZK forwarding — adaptive batching (tri-trigger: count OR weight OR delay)
        self._zk_forwarded: int = 0
        self._zk_responses: int = 0
        self._zk_errors: int = 0
        self._zk_latency_window: list = []
        self._zk_batch: list = []               # Batch accumulation buffer
        self._zk_batch_size: int = 100           # Volume trigger: flush at N events
        self._zk_weight_budget: int = 10_000     # Constraint-weight trigger
        self._zk_current_weight: int = 0         # Accumulated weight in buffer
        self._zk_max_delay: float = 0.05         # Time trigger: flush after 50ms idle
        self._zk_last_flush: float = 0.0
        self._zk_timer_task: asyncio.Task | None = None
        self._last_activity: float = 0.0         # Warm-up heartbeat tracking

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

        # Warm-up heartbeat: keep D01 enclaves hot during idle
        asyncio.create_task(self._warmup_loop())

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
            self._last_activity = time.time()

            # ZK Trigger: adaptive accumulation (tri-trigger: count OR weight OR delay)
            if self.zk_trigger_rate > 0 and self._nc and self._nc.is_connected:
                if hash(payload.get("payload_id", "")) % 100 < (self.zk_trigger_rate * 100):
                    self._zk_batch.append(payload)
                    self._zk_forwarded += 1
                    self._zk_current_weight += self.estimate_constraint_weight(payload)

                    # Volume trigger: flush at N events
                    if len(self._zk_batch) >= self._zk_batch_size:
                        self._flush_now()
                    # Weight trigger: flush when constraint budget exceeded
                    elif self._zk_current_weight >= self._zk_weight_budget:
                        self._flush_now()

                    # Time trigger: arm timer if first event in buffer
                    elif len(self._zk_batch) == 1 and self._zk_timer_task is None:
                        self._zk_timer_task = asyncio.create_task(self._time_flush())

            # Track latency
            elapsed_us = (time.time() - t0) * 1_000_000
            self._latency_window.append(elapsed_us)
            if len(self._latency_window) > self._latency_window_max:
                self._latency_window.pop(0)

        except Exception as e:
            self._total_errors += 1
            logger.error("%s message error: %s", self.agent_id, e)

    # ── ZK Forwarding ───────────────────────────────────────────────────

    @staticmethod
    def estimate_constraint_weight(payload: dict) -> int:
        """Estimate WitnessGen cost — defends against algorithmic complexity attacks.

        Simple state transfer ≈ 50 constraints. Complex BHO special rule (§48b)
        ≈ 800 constraints. Poisoned payloads with oversized custom_proof_data
        or special exemptions get penalized to keep WitnessGen bounded.
        """
        weight = 50
        if "custom_proof_data" in payload:
            weight += len(str(payload["custom_proof_data"])) * 2
        if payload.get("has_special_exemption", False):
            weight += 750
        return weight

    def _flush_now(self):
        """Synchronously hand off the current batch (no await, called from handler)."""
        if not self._zk_batch:
            return
        if self._zk_timer_task and not self._zk_timer_task.done():
            self._zk_timer_task.cancel()
        self._zk_timer_task = None
        batch = self._zk_batch
        self._zk_batch = []
        self._zk_current_weight = 0
        task = asyncio.create_task(self._flush_zk_batch(batch))
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    async def _time_flush(self):
        """Time trigger: flush after max_delay even if volume cap not reached."""
        await asyncio.sleep(self._zk_max_delay)
        self._zk_timer_task = None
        if self._zk_batch:
            self._flush_now()

    async def _warmup_loop(self):
        """Keep D01 enclaves warm during idle (5s heartbeat)."""
        while True:
            await asyncio.sleep(5.0)
            if self._nc and self._nc.is_connected and \
               (time.time() - self._last_activity) >= 5.0:
                warmup = {"type": "WARMUP_PING", "agent_id": self.agent_id,
                          "timestamp_ns": time.time_ns(), "dummy_pairing": True}
                try:
                    await self._nc.publish(
                        "agentx.subsurface.zk_request",
                        json.dumps(warmup).encode(),
                    )
                except Exception:
                    pass

    async def _flush_zk_batch(self, batch: list):
        """Flush accumulated ZK events as a single batch request to D01."""
        t0 = time.time()
        batch_count = len(batch)
        try:
            response = await self._nc.request(
                "agentx.subsurface.zk_request_batch",
                json.dumps(batch).encode(),
                timeout=5,
            )
            self._zk_responses += batch_count
            zk_lat = (time.time() - t0) * 1_000_000 / batch_count
            self._zk_latency_window.append(zk_lat)
            if len(self._zk_latency_window) > self._latency_window_max:
                self._zk_latency_window.pop(0)
        except Exception as e:
            self._zk_errors += batch_count
            if self._zk_errors <= batch_count * 2:
                logger.error("ZK batch error (%d events): %s", batch_count, e)

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
