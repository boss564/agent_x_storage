#!/usr/bin/env python3
"""Panzergrenadier metrics — observable counters and latency tracking.

Tracks, per agent and coordinator-wide:
  - panzergrenadier_dismounts_total
  - panzergrenadier_clearance_latency_seconds
  - deep_state_query_latency_ms
  - dismount_reconstructions_total

Self-contained (no external Prometheus dependency). Can be exported to
Prometheus text format later.
"""

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class AgentMetrics:
    agent_id: str
    dismounts_total: int = 0
    clearances_total: int = 0
    reconstructions_total: int = 0
    clearance_latency_ms: List[float] = field(default_factory=list)
    deep_state_query_latency_ms: List[float] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record_dismount(self):
        with self._lock:
            self.dismounts_total += 1

    def record_clearance(self, elapsed_ms: float):
        with self._lock:
            self.clearances_total += 1
            self.clearance_latency_ms.append(elapsed_ms)

    def record_reconstruction(self):
        with self._lock:
            self.reconstructions_total += 1

    def record_deep_state_query(self, elapsed_ms: float):
        with self._lock:
            self.deep_state_query_latency_ms.append(elapsed_ms)

    def _percentile(self, values: List[float], pct: float) -> float:
        if not values:
            return 0.0
        s = sorted(values)
        idx = min(len(s) - 1, int(len(s) * pct))
        return s[idx]

    def snapshot(self) -> Dict:
        with self._lock:
            return {
                "agent_id": self.agent_id,
                "dismounts_total": self.dismounts_total,
                "clearances_total": self.clearances_total,
                "reconstructions_total": self.reconstructions_total,
                "clearance_p50_ms": round(self._percentile(self.clearance_latency_ms, 0.50), 3),
                "clearance_p95_ms": round(self._percentile(self.clearance_latency_ms, 0.95), 3),
                "clearance_p99_ms": round(self._percentile(self.clearance_latency_ms, 0.99), 3),
                "deep_state_p50_ms": round(self._percentile(self.deep_state_query_latency_ms, 0.50), 3),
                "deep_state_p99_ms": round(self._percentile(self.deep_state_query_latency_ms, 0.99), 3),
            }


class MetricsRegistry:
    """Registry of per-agent metrics + coordinator-level aggregates."""

    def __init__(self):
        self.agents: Dict[str, AgentMetrics] = {}
        self._lock = threading.Lock()

    def agent(self, agent_id: str) -> AgentMetrics:
        with self._lock:
            if agent_id not in self.agents:
                self.agents[agent_id] = AgentMetrics(agent_id=agent_id)
            return self.agents[agent_id]

    def snapshot(self) -> Dict:
        with self._lock:
            return {
                "agents": {k: v.snapshot() for k, v in self.agents.items()},
                "total_dismounts": sum(a.dismounts_total for a in self.agents.values()),
                "total_clearances": sum(a.clearances_total for a in self.agents.values()),
                "total_reconstructions": sum(a.reconstructions_total for a in self.agents.values()),
            }

    def prometheus_text(self) -> str:
        """Export in Prometheus text format (for the /metrics endpoint)."""
        lines = []
        for aid, a in self.agents.items():
            s = a.snapshot()
            lines.append(f'panzergrenadier_dismounts_total{{agent="{aid}"}} {s["dismounts_total"]}')
            lines.append(f'panzergrenadier_clearances_total{{agent="{aid}"}} {s["clearances_total"]}')
            lines.append(f'panzergrenadier_reconstructions_total{{agent="{aid}"}} {s["reconstructions_total"]}')
            lines.append(f'panzergrenadier_clearance_p99_ms{{agent="{aid}"}} {s["clearance_p99_ms"]}')
            lines.append(f'deep_state_query_p99_ms{{agent="{aid}"}} {s["deep_state_p99_ms"]}')
        return "\n".join(lines)


# Global singleton for the coordinator to use
REGISTRY = MetricsRegistry()
