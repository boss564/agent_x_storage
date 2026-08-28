"""Shared types for the 9-agent regime drift swarm."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"

# Frozen v0 swarm parameters
SWARM_SCHEMA = "raas_regime_swarm_v1"
COOLING_OFF_CYCLES = 3
KS_SCREEN_ALPHA = 0.05  # A5 screen before A6 (resource gate)
CRITICAL_ALPHA = 0.01
RSI_STABLE_MAX = 30
RSI_CRITICAL_MIN = 70
STANDARDIZED_DRIFT_THRESHOLD = 2.0  # >2× Pre-Reg amendment reference
AUTOCORR_RHO_THRESHOLD = 0.3  # A7 pseudo-drift gate (Line 74)
N_EFF_RATIO_THRESHOLD = 0.5  # A4: n_eff/n below → i.i.d. violation
R2_CUBED_BLOCK = 3


@dataclass
class IidStatus:
    """A4 autocorrelation monitor output for r2_cubed current window."""

    rho: float
    n_raw: int
    n_eff: float
    is_iid_violation: bool
    feature: str = "r2_cubed"

    def to_dict(self) -> Dict[str, Any]:
        ratio = self.n_eff / self.n_raw if self.n_raw else 0.0
        return {
            "feature": self.feature,
            "rho": round(self.rho, 6),
            "n_raw": self.n_raw,
            "n_eff": round(self.n_eff, 4),
            "n_eff_ratio": round(ratio, 4),
            "is_iid_violation": self.is_iid_violation,
            "warning": (
                "i.i.d.-Näherung für r₂³ ungültig (überlappende Fenster)"
                if self.is_iid_violation
                else None
            ),
        }


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
    standardized_drift: float = 0.0
    allow_amendment: bool = False
    iid_unreliable: bool = False
    pre_reg_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "regime_shift_index": round(self.regime_shift_index, 2),
            "regime_flag": self.regime_flag,
            "classified_regime": self.classified_regime,
            "drift_type": self.drift_type,
            "ks_p_value_min": round(self.ks_p_value_min, 6),
            "anomaly_count": self.anomaly_count,
            "mean_shift_sigma": round(self.mean_shift_sigma, 4),
            "standardized_drift": round(self.standardized_drift, 4),
            "allow_amendment": self.allow_amendment,
            "iid_unreliable": self.iid_unreliable,
        }
        if self.pre_reg_reason:
            out["pre_reg_reason"] = self.pre_reg_reason
        return out


@dataclass
class PreRegIntervention:
    """A7/A9 — Line 74 i.i.d.-caveat audit block."""

    triggered: bool
    rule_reference: str = "Line 74 – i.i.d.-Caveat"
    autocorrelation_rho_for_r2_cubed: float = 0.0
    effective_sample_size: float = 0.0
    raw_sample_size: int = 0
    decision: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "triggered": self.triggered,
            "rule_reference": self.rule_reference,
            "autocorrelation_rho_for_r2_cubed": round(self.autocorrelation_rho_for_r2_cubed, 6),
            "effective_sample_size": round(self.effective_sample_size, 4),
            "raw_sample_size": self.raw_sample_size,
            "decision": self.decision,
        }


@dataclass
class AdaptiveAdvisory:
    """A8 output — diagnostic suggestions only (never executed)."""

    risk_multiplier_suggestion: str
    max_position_size_suggestion: str
    strategy_mode_suggestion: str
    advisory_only: bool = True
    amendment_skipped: bool = False
    final_action: str = "PARAMETER_ADVISORY"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": "A8_StrategyAdapter",
            "advisory_only": self.advisory_only,
            "live_execution": False,
            "amendment_skipped": self.amendment_skipped,
            "final_action": self.final_action,
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
    pre_reg_intervention: Optional[Dict[str, Any]] = None
    final_action: str = "PARAMETER_UNCHANGED"

    def to_audit_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
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
            "final_action": self.final_action,
            "hash_checksum": self.hash_checksum,
            "diagnostic_only": self.diagnostic_only,
            "not_investment_advice": self.not_investment_advice,
            "scope": self.scope,
            "live_execution": self.live_execution,
            "agents": self.agents,
        }
        if self.pre_reg_intervention is not None:
            out["pre_reg_intervention"] = self.pre_reg_intervention
        return out
