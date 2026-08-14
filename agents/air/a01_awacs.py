#!/usr/bin/env python3
"""A01 AWACS — Airborne Warning & Control: mode decision for the air layer.

Monitors the NATS JetStream for latency outliers and backpressure and decides
whether to engage the air layer (fast-path / CAS / neutralize / passthrough).
"""

import time
from typing import Any, Dict

from .base import AirAction, AirInterceptorAgent


class A01Awacs(AirInterceptorAgent):
    """Decides the tactical mode per event."""

    def __init__(self, spike_threshold_tps: float = 100_000):
        super().__init__("A01")
        self.spike_threshold_tps = spike_threshold_tps
        self._window: list[float] = []  # recent timestamps (1s) for spike detection

    def decide(self, event: Dict[str, Any]) -> AirAction:
        now = time.perf_counter()
        self._window.append(now)
        # prune the 1-second window
        self._window = [t for t in self._window if now - t < 1.0]

        # 1. Poison pattern → in-flight neutralize (Schwarm 3 / A07)
        if self._looks_poisoned(event):
            return AirAction.NEUTRALIZE
        # 2. Payment obligation / HFT → speculative soft-finality (A02/A03)
        if event.get("payment_obligation") or event.get("is_hft"):
            return AirAction.FASTPATH
        # 3. Traffic spike → transient CAS (Schwarm 2 / A04–A06)
        if len(self._window) >= self.spike_threshold_tps:
            return AirAction.CAS
        # 4. Normal → passthrough to Surface
        return AirAction.PASSTHROUGH

    @staticmethod
    def _looks_poisoned(event: Dict[str, Any]) -> bool:
        """Oversized custom_proof_data is the algorithmic-complexity trigger."""
        cd = event.get("custom_proof_data")
        return bool(cd) and len(str(cd)) > 1000
