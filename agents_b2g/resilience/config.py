"""Wave 40 configuration — Execution Resilience & Risk Shield."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ResilienceConfigError(RuntimeError):
    """Raised when resilience config is invalid."""


@dataclass(frozen=True)
class ResilienceConfig:
    """Immutable runtime config for Wave 40."""

    project_root: Path
    data_root: Path
    log_dir: Path
    finality_l1: int
    finality_l2: int
    rpc_switch_ms: float
    rpc_p99_sla_us: float
    max_gas_per_tx: int
    daily_burn_limit: int
    max_retries: int
    retry_backoff_base_s: float
    black_swan_sigma: float
    vol_spike_factor: float
    confounder_cooldown_h: float
    gas_bho_epsilon: float

    @classmethod
    def load(cls, project_root: Path | None = None) -> ResilienceConfig:
        root = project_root or Path(__file__).resolve().parent.parent.parent
        finality_l1 = int(os.getenv("RESILIENCE_FINALITY_L1", "12"))
        finality_l2 = int(os.getenv("RESILIENCE_FINALITY_L2", "64"))
        if finality_l1 < 1 or finality_l2 < 1:
            raise ResilienceConfigError("finality thresholds must be >= 1")

        max_gas = int(os.getenv("RESILIENCE_MAX_GAS_PER_TX", "500000"))
        daily = int(os.getenv("RESILIENCE_DAILY_BURN_LIMIT", "50000000"))
        if max_gas < 1 or daily < max_gas:
            raise ResilienceConfigError("invalid gas caps")

        return cls(
            project_root=root,
            data_root=Path(os.getenv("RESILIENCE_DATA_ROOT", "data")),
            log_dir=Path(os.getenv("RESILIENCE_LOG_DIR", "logs")),
            finality_l1=finality_l1,
            finality_l2=finality_l2,
            rpc_switch_ms=float(os.getenv("RESILIENCE_RPC_SWITCH_MS", "200")),
            rpc_p99_sla_us=float(os.getenv("RESILIENCE_RPC_P99_SLA_US", "54")),
            max_gas_per_tx=max_gas,
            daily_burn_limit=daily,
            max_retries=int(os.getenv("RESILIENCE_MAX_RETRIES", "3")),
            retry_backoff_base_s=float(os.getenv("RESILIENCE_RETRY_BACKOFF_S", "0.05")),
            black_swan_sigma=float(os.getenv("RESILIENCE_BLACK_SWAN_SIGMA", "5.0")),
            vol_spike_factor=float(os.getenv("RESILIENCE_VOL_SPIKE_FACTOR", "3.0")),
            confounder_cooldown_h=float(os.getenv("RESILIENCE_CONFOUNDER_COOLDOWN_H", "24")),
            gas_bho_epsilon=float(os.getenv("RESILIENCE_GAS_BHO_EPSILON", "0.01")),
        )

    def tenant_root(self, user_id: str) -> Path:
        path = self.data_root / user_id / "resilience"
        path.mkdir(parents=True, exist_ok=True)
        return path
