"""Env configuration — default disabled (POSITION_SIZING_ENABLED=false)."""

from __future__ import annotations

import os
from decimal import Decimal


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def position_sizing_enabled() -> bool:
    return _env_bool("POSITION_SIZING_ENABLED", False)


def gamma_default() -> float:
    return float(os.environ.get("POSITION_SIZING_GAMMA", "0.25"))


def stats_window_size() -> int:
    return int(os.environ.get("POSITION_SIZING_WINDOW", "50"))


def risk_limit_fraction() -> float:
    return float(os.environ.get("POSITION_SIZING_RISK_LIMIT", "0.02"))


def audit_path_default(data_root: str = "/data") -> str:
    override = os.environ.get("POSITION_SIZING_AUDIT_PATH", "").strip()
    if override:
        return override
    return f"{data_root.rstrip('/')}/audit/position_sizing.jsonl"
