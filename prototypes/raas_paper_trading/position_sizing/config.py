"""Env configuration — default disabled (POSITION_SIZING_ENABLED=false)."""

from __future__ import annotations

import json
import os
from typing import Dict, Optional, Tuple

DEFAULT_GAMMA_MAP: Dict[str, float] = {
    "STABLE": 0.25,
    "STABLE_SIDEWAYS": 0.10,
    "LOW_LEVEL_DRIFT": 0.20,
    "DRIFT_IID_UNRELIABLE": 0.00,
    "HIGH_VOL_TREND": 0.40,
    "HIGH_VOL_TREND_BEARISH": 0.35,
}


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


def min_regime_flag_trigger() -> int:
    return int(os.environ.get("POSITION_SIZING_MIN_REGIME_FLAG", "1"))


def audit_path_default(data_root: str = "/data") -> str:
    override = os.environ.get("POSITION_SIZING_AUDIT_PATH", "").strip()
    if override:
        return override
    return f"{data_root.rstrip('/')}/audit/position_sizing.jsonl"


def load_gamma_map() -> Dict[str, float]:
    merged = dict(DEFAULT_GAMMA_MAP)
    raw = os.environ.get("POSITION_SIZING_GAMMA_MAP", "").strip()
    if not raw:
        return merged
    overrides = json.loads(raw)
    if not isinstance(overrides, dict):
        raise ValueError("POSITION_SIZING_GAMMA_MAP must be a JSON object")
    for key, val in overrides.items():
        merged[str(key)] = float(val)
    return merged


def resolve_gamma(
    classified_regime: Optional[str],
    gamma_map: Optional[Dict[str, float]] = None,
) -> Tuple[float, str]:
    """Regime → γ per docs/POSITION_SIZING_REGIME_MAPPING.md §2 / §6.1."""
    gmap = gamma_map if gamma_map is not None else load_gamma_map()
    regime = (classified_regime or "").strip()
    if regime == "DRIFT_IID_UNRELIABLE":
        return 0.0, "iid_safe_mode"
    if regime in gmap:
        return float(gmap[regime]), "regime_map"
    return float(gmap.get("STABLE", gamma_default())), "default"
