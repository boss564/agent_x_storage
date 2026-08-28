"""Shared types for the 9-agent regime drift swarm."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"

# Frozen v0 swarm parameters
SWARM_SCHEMA = "raas_regime_swarm_v0"
COOLING_OFF_CYCLES = 3
KS_SCREEN_ALPHA = 0.05  # A5 screen before A6 (resource gate)
CRITICAL_ALPHA = 0.01
RSI_STABLE_MAX = 30
RSI_CRITICAL_MIN = 70


@dataclass
class FeatureMatrix:
    """Aligned feature columns from A3."""

    names: List[str]
    baseline: Dict[str, List[float]]
    current: Dict[str, List[float]]

    def feature_names(self) -> List[str]:
        return list(self.names)


@dataclass
class KSFeatureResult:
    feature: str
    d_stat: float
    p_value: float
    drift_detected: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature": self.feature,
            "D": round(self.d_stat, 6),
            "p": round(self.p_value, 6),
            "drift_detected": self.drift_detected,
        }


@dataclass
class WassersteinResult:
    mean_w1: float
    max_w1: float
    per_feature: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mean_w1": round(self.mean_w1, 8),
            "max_w1": round(self.max_w1, 8),
            "per_feature": {k: round(v, 8) for k, v in self.per_feature.items()},
        }


@dataclass
class DriftClassification:
    regime_shift_index: float
    regime_flag: int  # 0=stable, 1=warning, 2=critical
    classified_regime: str
    drift_type: str
    ks_p_value_min: float
    anomaly_count: int
    mean_shift_sigma: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "regime_shift_index": round(self.regime_shift_index, 2),
            "regime_flag": self.regime_flag,
            "classified_regime": self.classified_regime,
            "drift_type": self.drift_type,
            "ks_p_value_min": round(self.ks_p_value_min, 6),
            "anomaly_count": self.anomaly_count,
            "mean_shift_sigma": round(self.mean_shift_sigma, 4),
        }


@dataclass
class AdaptiveAdvisory:
    """A8 output — diagnostic suggestions only (never executed)."""

    risk_multiplier_suggestion: str
    max_position_size_suggestion: str
    strategy_mode_suggestion: str
    advisory_only: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": "A8_StrategyAdapter",
            "advisory_only": self.advisory_only,
            "live_execution": False,
            "changes": {
                "risk_multiplier": self.risk_multiplier_suggestion,
                "max_position_size": self.max_position_size_suggestion,
                "strategy_mode": self.strategy_mode_suggestion,
            },
        }


@dataclass
class SwarmCycleResult:
    cycle_id: str
    symbol: str
    agent_trigger: str
    drift_summary: Dict[str, Any]
    statistical_significance: str
    deviation_from_backtest: str
    adaptive_action: Dict[str, Any]
    alert_level: str
    cooling_off_cycles_required: int
    cooling_off_cycles_seen: int
    regime_flag_confirmed: bool
    hash_checksum: str
    diagnostic_only: bool = True
    not_investment_advice: bool = True
    scope: str = SCOPE
    live_execution: bool = False
    agents: Dict[str, Any] = field(default_factory=dict)

    def to_audit_dict(self) -> Dict[str, Any]:
        return {
            "schema": SWARM_SCHEMA,
            "timestamp": None,  # filled by A9
            "cycle_id": self.cycle_id,
            "symbol": self.symbol,
            "agent_trigger": self.agent_trigger,
            "drift_summary": self.drift_summary,
            "statistical_significance": self.statistical_significance,
            "deviation_from_backtest": self.deviation_from_backtest,
            "adaptive_action": self.adaptive_action,
            "alert_level": self.alert_level,
            "cooling_off": {
                "required": self.cooling_off_cycles_required,
                "seen": self.cooling_off_cycles_seen,
                "regime_flag_confirmed": self.regime_flag_confirmed,
            },
            "hash_checksum": self.hash_checksum,
            "diagnostic_only": self.diagnostic_only,
            "not_investment_advice": self.not_investment_advice,
            "scope": self.scope,
            "live_execution": self.live_execution,
            "agents": self.agents,
        }
