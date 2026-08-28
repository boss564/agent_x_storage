"""Environment / Helm-driven thresholds for A0 and A2.5."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return float(raw)


@dataclass
class InfraGatesConfig:
    enabled: bool = True
    g0_max_price_change_pct: float = 20.0
    g0_max_spread_pct: float = 5.0
    g25_max_latency_ms: float = 500.0

    @classmethod
    def from_env(cls) -> InfraGatesConfig:
        return cls(
            enabled=_env_bool("SWARM_INFRA_GATES_ENABLED", _env_bool("INFRA_GATES_ENABLED", True)),
            g0_max_price_change_pct=_env_float(
                "SWARM_G0_MAX_PRICE_CHANGE_PCT",
                _env_float("G0_MAX_PRICE_CHANGE_PCT", 20.0),
            ),
            g0_max_spread_pct=_env_float(
                "SWARM_G0_MAX_SPREAD_PCT",
                _env_float("G0_MAX_SPREAD_PCT", 5.0),
            ),
            g25_max_latency_ms=_env_float(
                "SWARM_G25_MAX_LATENCY_MS",
                _env_float("G25_MAX_LATENCY_MS", 500.0),
            ),
        )
