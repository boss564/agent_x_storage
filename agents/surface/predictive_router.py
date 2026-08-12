#!/usr/bin/env python3
"""Predictive Health Router — pre-flight traffic shunting for ZK workers.

Replaces passive error-telemetry with predictive degradation detection.
Each D01 replica emits a micro-benchmark score every 100ms. The surface
router shunts traffic away from degraded replicas BEFORE the batch is sent,
rather than discovering the failure after the L1 consensus has expired.

Score: S = (f_current / f_base) × (1 - T_microbench / T_threshold)
Healthy: S >= 0.95
Degraded: S < 0.95 (reroute to fallback)
Stale: no telemetry for >500ms (treat as dead)
"""

import logging
import time
from typing import Dict, List, Optional

logger = logging.getLogger("PredictiveHealthRouter")

DEGRADATION_THRESHOLD = 0.95
STALE_TIMEOUT_S = 0.5
SLA_P99_HARD_MS = 20.0
COOLDOWN_S = 30.0


class PredictiveHealthRouter:
    """Routes ZK traffic to the healthiest replica based on live telemetry."""

    def __init__(self, degradation_threshold: float = DEGRADATION_THRESHOLD):
        self.replica_scores: Dict[str, float] = {}
        self.last_telemetry_time: Dict[str, float] = {}
        self.cooldown_until: Dict[str, float] = {}
        self.degradation_threshold = degradation_threshold
        self.shunt_count: int = 0

    # ── Telemetry Ingestion ────────────────────────────────────────────

    def update_telemetry(self, replica_id: str, score: float):
        """Ingest a micro-benchmark score from a D01 replica."""
        # Respect cooldown: forced score 0.0 during thermal recovery
        if time.time() < self.cooldown_until.get(replica_id, 0):
            score = 0.0
        self.replica_scores[replica_id] = score
        self.last_telemetry_time[replica_id] = time.time()

    def record_sla_violation(self, replica_id: str, latency_ms: float):
        """Hard SLA circuit breaker: force replica into cooldown."""
        if latency_ms > SLA_P99_HARD_MS:
            self.cooldown_until[replica_id] = time.time() + COOLDOWN_S
            self.replica_scores[replica_id] = 0.0
            logger.warning(
                "🚨 SLA VIOLATION: %s took %.1fms (P99.9 limit %.1fms). "
                "Cooldown %ds.",
                replica_id, latency_ms, SLA_P99_HARD_MS, COOLDOWN_S,
            )

    # ── Health Evaluation ──────────────────────────────────────────────

    def _is_healthy(self, replica_id: str) -> bool:
        """Replica is healthy if score >= threshold AND telemetry is fresh."""
        score = self.replica_scores.get(replica_id, 0.0)
        last_seen = self.last_telemetry_time.get(replica_id, 0)
        stale = (time.time() - last_seen) > STALE_TIMEOUT_S
        in_cooldown = time.time() < self.cooldown_until.get(replica_id, 0)
        return (not stale) and (not in_cooldown) and (score >= self.degradation_threshold)

    def get_healthy_replica(
        self,
        primary_shard_replica: str,
        fallback_replicas: List[str],
    ) -> str:
        """Return the healthiest replica, shunting away from degraded primary."""
        # 1. Primary healthy?
        if self._is_healthy(primary_shard_replica):
            return primary_shard_replica

        # 2. Find a healthy fallback
        for fallback in fallback_replicas:
            if self._is_healthy(fallback):
                primary_score = self.replica_scores.get(primary_shard_replica, 0.0)
                logger.warning(
                    "⚠️ PREDICTIVE SHUNT: %s degraded (%.2f) → %s",
                    primary_shard_replica, primary_score, fallback,
                )
                self.shunt_count += 1
                return fallback

        # 3. Emergency: best available (least-degraded)
        candidates = [primary_shard_replica] + fallback_replicas
        best = max(candidates, key=lambda r: self.replica_scores.get(r, 0.0))
        logger.error(
            "❌ No healthy replica! All degraded. Using %s (best score %.2f)",
            best, self.replica_scores.get(best, 0.0),
        )
        return best

    # ── Micro-benchmark Score Computation ──────────────────────────────

    @staticmethod
    def compute_score(
        current_freq_mhz: float,
        base_freq_mhz: float,
        microbench_us: float,
        threshold_us: float = 1000.0,
    ) -> float:
        """S = (f_current/f_base) × (1 - T_microbench/T_threshold), clipped [0,1]."""
        freq_ratio = current_freq_mhz / base_freq_mhz if base_freq_mhz > 0 else 1.0
        load_penalty = 1.0 - (microbench_us / threshold_us) if threshold_us > 0 else 1.0
        score = freq_ratio * load_penalty
        return max(0.0, min(1.0, score))

    def status(self) -> Dict:
        return {
            "replica_scores": {k: round(v, 3) for k, v in self.replica_scores.items()},
            "healthy_count": sum(1 for r in self.replica_scores if self._is_healthy(r)),
            "total_replicas": len(self.replica_scores),
            "shunt_count": self.shunt_count,
        }


# ─── Micro-benchmark Collector ─────────────────────────────────────────────

async def microbenchmark_loop(router: PredictiveHealthRouter, replica_id: str):
    """Emit a synthetic micro-benchmark score every 100ms.

    In production, this runs inside the D01 enclave and measures real
    EC scalar-multiplication latency + CPU frequency. Here we simulate
    healthy operation with occasional degradation spikes.
    """
    import asyncio
    import random

    base_freq = 3.2  # GHz
    threshold_us = 1000.0  # 1ms — a healthy micro-benchmark is ~10µs
    while True:
        await asyncio.sleep(0.1)
        # Simulate: mostly healthy, occasional thermal throttling
        if random.random() < 0.02:
            # Degraded: thermal throttling → freq drops, benchmark slows
            freq = base_freq * 0.7
            bench_us = 500.0
        else:
            freq = base_freq
            bench_us = 10.0
        score = router.compute_score(freq, base_freq, bench_us, threshold_us)
        router.update_telemetry(replica_id, score)
