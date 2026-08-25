"""Post-MEV diagnostic config — additive Wave-38 extension."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class PostMEVConfigError(RuntimeError):
    """Raised when post-mev config is invalid."""


@dataclass(frozen=True)
class PostMEVConfig:
    """Immutable runtime config for Post-MEV diagnostic stage."""

    project_root: Path
    data_root: Path
    log_dir: Path
    cooldown_h: float
    finality_l1: int
    cte_drift_threshold: float
    max_retries: int
    retry_backoff_base_s: float
    trigger_event: str

    @classmethod
    def load(cls, project_root: Path | None = None) -> PostMEVConfig:
        root = project_root or Path(__file__).resolve().parent.parent.parent.parent
        cooldown = float(os.getenv("POST_MEV_COOLDOWN_H", "24"))
        finality = int(os.getenv("POST_MEV_FINALITY_L1", "12"))
        if cooldown <= 0 or finality < 1:
            raise PostMEVConfigError("invalid cooldown or finality")
        return cls(
            project_root=root,
            data_root=Path(os.getenv("POST_MEV_DATA_ROOT", os.getenv("WAVE38_DATA_ROOT", "data"))),
            log_dir=Path(os.getenv("POST_MEV_LOG_DIR", "logs")),
            cooldown_h=cooldown,
            finality_l1=finality,
            cte_drift_threshold=float(os.getenv("POST_MEV_CTE_DRIFT", "0.15")),
            max_retries=int(os.getenv("POST_MEV_MAX_RETRIES", "3")),
            retry_backoff_base_s=float(os.getenv("POST_MEV_RETRY_BACKOFF_S", "0.05")),
            trigger_event=os.getenv("POST_MEV_TRIGGER", "mev_tail_completed"),
        )

    def tenant_root(self, user_id: str) -> Path:
        path = self.data_root / user_id / "wave38" / "post_mev"
        path.mkdir(parents=True, exist_ok=True)
        return path
