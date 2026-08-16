"""MetricsRegistry for the air layer.

Mirrors agents/mechanized/metrics.py: thread-safe counters, gauges and
bounded latency observations with p50/p99. Renders Prometheus text
format for the /metrics endpoint (handler.py, port 8083 — surface runs
8081, mechanized 8082).
"""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

_MAX_OBSERVATIONS = 4096   # bounded reservoir per series


class MetricsRegistry:
    def __init__(self):
        self._lock = threading.RLock()
        self._counters: Dict[Tuple[str, Tuple], float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._observations: Dict[str, List[float]] = defaultdict(list)

    # -- mutation -------------------------------------------------------

    def inc(self, name: str, value: float = 1.0,
            labels: Optional[dict] = None) -> None:
        with self._lock:
            self._counters[self._key(name, labels)] += value

    def set(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = float(value)

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            obs = self._observations[name]
            obs.append(float(value))
            if len(obs) > _MAX_OBSERVATIONS:
                del obs[: len(obs) - _MAX_OBSERVATIONS]

    # -- queries ----------------------------------------------------------

    def counter(self, name: str, labels: Optional[dict] = None) -> float:
        with self._lock:
            return self._counters.get(self._key(name, labels), 0.0)

    def gauge(self, name: str) -> float:
        with self._lock:
            return self._gauges.get(name, 0.0)

    def percentile(self, name: str, q: float) -> float:
        with self._lock:
            obs = sorted(self._observations.get(name, []))
        if not obs:
            return 0.0
        return obs[min(len(obs) - 1, int(round(q / 100.0 * (len(obs) - 1))))]

    # -- rendering ------------------------------------------------------------

    def render(self) -> str:
        """Prometheus text exposition format."""
        lines: List[str] = []
        with self._lock:
            counters = dict(self._counters)
            gauges = dict(self._gauges)
            observations = {k: sorted(v) for k, v in self._observations.items() if v}
        for (name, lbl), value in sorted(counters.items()):
            lines.append(f"{name}{self._fmt_labels(lbl)} {value:g}")
        for name, value in sorted(gauges.items()):
            lines.append(f"{name} {value:g}")
        for name, obs in sorted(observations.items()):
            lines.append(f'{name}{{quantile="0.5"}} {self._pick(obs, 50):g}')
            lines.append(f'{name}{{quantile="0.99"}} {self._pick(obs, 99):g}')
            lines.append(f"{name}_count {len(obs)}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _pick(obs: List[float], q: float) -> float:
        return obs[min(len(obs) - 1, int(round(q / 100.0 * (len(obs) - 1))))]

    @staticmethod
    def _key(name: str, labels: Optional[dict]) -> Tuple[str, Tuple]:
        return (name, tuple(sorted((labels or {}).items())))

    @staticmethod
    def _fmt_labels(lbl: Tuple) -> str:
        if not lbl:
            return ""
        return "{" + ",".join(f'{k}="{v}"' for k, v in lbl) + "}"
