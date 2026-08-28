"""A1/A4/A8/A9 adaptive extensions — cooling, dynamic window, soft adapt, stuck telemetry."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence

from prototypes.raas_paper_trading.regime_swarm.types import (
    REAL_DRIFT_COOLING_THRESHOLD,
    SOFT_ADAPT_STEP,
    SOFT_ADAPT_UNRELIABLE_FACTOR,
    SOFT_ADAPT_UNRELIABLE_CAP_FRAC,
    STUCK_UNRELIABLE_HOURS,
    TARGET_RISK_MULTIPLIER,
    UNRELIABLE_COOLING_THRESHOLD,
    WINDOW_BASE_SIZE,
    WINDOW_MAX_SIZE,
    WINDOW_RHO_STRETCH,
    WINDOW_SHRINK_STEP,
)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def pearson_lag1(series: Sequence[float]) -> float:
    if len(series) < 3:
        return 0.0
    x = [float(v) for v in series[:-1]]
    y = [float(v) for v in series[1:]]
    mx = sum(x) / len(x)
    my = sum(y) / len(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den_x = sum((a - mx) ** 2 for a in x) ** 0.5
    den_y = sum((b - my) ** 2 for b in y) ** 0.5
    if den_x * den_y < 1e-12:
        return 0.0
    rho = num / (den_x * den_y)
    return max(-1.0, min(1.0, rho))


@dataclass
class AdaptiveCoolingOffManager:
    """A1 — dual counters: unreliable (2+) vs real drift (5+)."""

    path: Path
    unreliable_threshold: int = UNRELIABLE_COOLING_THRESHOLD
    real_drift_threshold: int = REAL_DRIFT_COOLING_THRESHOLD
    _unreliable: Dict[str, int] = field(default_factory=dict)
    _real: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.path.is_file():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                sym = str(row.get("symbol", ""))
                self._unreliable[sym] = int(row.get("unreliable_counter", 0))
                self._real[sym] = int(row.get("real_drift_counter", 0))

    def update(
        self,
        symbol: str,
        *,
        regime_flag: int,
        classified_regime: str,
    ) -> Dict[str, Any]:
        if regime_flag == 0:
            self._unreliable[symbol] = 0
            self._real[symbol] = 0
            decision = {
                "action": "NOP",
                "confirmed": False,
                "cooling_status": "NOP",
                "unreliable_counter": 0,
                "real_drift_counter": 0,
            }
        elif classified_regime == "DRIFT_IID_UNRELIABLE":
            self._unreliable[symbol] = self._unreliable.get(symbol, 0) + 1
            self._real[symbol] = 0
            u, r = self._unreliable[symbol], self._real[symbol]
            if u >= self.unreliable_threshold:
                decision = {
                    "action": "WARN_ONLY",
                    "confirmed": True,
                    "type": "unreliable",
                    "cooling_status": "WARN_ONLY",
                    "unreliable_counter": u,
                    "real_drift_counter": r,
                }
            else:
                decision = {
                    "action": "OBSERVE",
                    "confirmed": False,
                    "cooling_status": "OBSERVE",
                    "unreliable_counter": u,
                    "real_drift_counter": r,
                }
        elif regime_flag >= 2 and classified_regime in (
            "HIGH_VOL_TREND",
            "HIGH_VOL_TREND_BEARISH",
            "REGIME_SHIFT",
        ):
            self._real[symbol] = self._real.get(symbol, 0) + 1
            self._unreliable[symbol] = 0
            u, r = self._unreliable[symbol], self._real[symbol]
            if r >= self.real_drift_threshold:
                decision = {
                    "action": "ADAPT",
                    "confirmed": True,
                    "type": "real_drift",
                    "cooling_status": "ADAPT",
                    "unreliable_counter": u,
                    "real_drift_counter": r,
                }
            else:
                decision = {
                    "action": "OBSERVE",
                    "confirmed": False,
                    "cooling_status": "OBSERVE",
                    "unreliable_counter": u,
                    "real_drift_counter": r,
                }
        else:
            u = self._unreliable.get(symbol, 0)
            r = self._real.get(symbol, 0)
            decision = {
                "action": "OBSERVE",
                "confirmed": False,
                "cooling_status": "OBSERVE",
                "unreliable_counter": u,
                "real_drift_counter": r,
            }

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "symbol": symbol,
                        "regime_flag": regime_flag,
                        "classified_regime": classified_regime,
                        **decision,
                        "ts": _now_utc().isoformat(),
                    }
                )
                + "\n"
            )
        return decision


@dataclass
class DynamicWindowManager:
    """A4 — stretch current window when lag-1 ρ exceeds threshold."""

    base_window_size: int = WINDOW_BASE_SIZE
    max_window_size: int = WINDOW_MAX_SIZE
    rho_threshold: float = WINDOW_RHO_STRETCH
    shrink_step: int = WINDOW_SHRINK_STEP
    _sizes: Dict[str, int] = field(default_factory=dict)

    def adapt_window(self, symbol: str, raw_series: Sequence[float]) -> Dict[str, Any]:
        current = self._sizes.get(symbol, self.base_window_size)
        rho = pearson_lag1(raw_series)
        if rho > self.rho_threshold:
            new_size = min(current * 2, self.max_window_size)
        else:
            new_size = max(self.base_window_size, current - self.shrink_step)
        self._sizes[symbol] = new_size
        return {
            "current_window_size": new_size,
            "rho_autocorr": round(rho, 6),
            "was_stretched": new_size > self.base_window_size,
            "effective_n": new_size,
        }


@dataclass
class SoftStrategyState:
    """A8 — per-symbol gradual risk multiplier (advisory only)."""

    target_risk_multiplier: float = TARGET_RISK_MULTIPLIER
    step_size: float = SOFT_ADAPT_STEP
    _current: Dict[str, float] = field(default_factory=dict)

    def current(self, symbol: str) -> float:
        return self._current.get(symbol, 1.0)

    def apply(
        self,
        symbol: str,
        *,
        classified_regime: str,
        allow_amendment: bool,
        cooling_decision: Dict[str, Any],
    ) -> Dict[str, Any]:
        cur = self.current(symbol)
        action = str(cooling_decision.get("action", "OBSERVE"))
        confirmed = bool(cooling_decision.get("confirmed"))

        if allow_amendment and confirmed and action == "ADAPT":
            self._current[symbol] = self.target_risk_multiplier
            return {
                "action_taken": "FULL_ADAPT",
                "new_multiplier": round(self.target_risk_multiplier, 3),
                "full_adapt_blocked": False,
                "adaption_mode": "FULL",
            }

        if not allow_amendment and classified_regime == "DRIFT_IID_UNRELIABLE":
            cap = 1.0 + (self.target_risk_multiplier - 1.0) * SOFT_ADAPT_UNRELIABLE_CAP_FRAC
            delta = self.step_size * SOFT_ADAPT_UNRELIABLE_FACTOR
            if action in ("WARN_ONLY", "OBSERVE") and cur < cap:
                cur = min(cur + delta, cap)
            self._current[symbol] = cur
            return {
                "action_taken": "SOFT_ADAPT",
                "new_multiplier": round(cur, 3),
                "full_adapt_blocked": True,
                "adaption_mode": "SOFT",
                "target_multiplier": self.target_risk_multiplier,
            }

        if classified_regime in ("STABLE", "STABLE_SIDEWAYS", "LOW_LEVEL_DRIFT"):
            cur = max(1.0, cur - self.step_size * 0.1)
            self._current[symbol] = cur

        return {
            "action_taken": "HOLD",
            "new_multiplier": round(cur, 3),
            "full_adapt_blocked": not allow_amendment,
            "adaption_mode": "SOFT" if not allow_amendment else "HOLD",
            "target_multiplier": self.target_risk_multiplier,
        }


@dataclass
class StuckUnreliableTracker:
    """A9 — flag REVIEW_REQUIRED after prolonged DRIFT_IID_UNRELIABLE."""

    threshold_hours: float = STUCK_UNRELIABLE_HOURS
    now_fn: Callable[[], datetime] = _now_utc
    _start: Dict[str, Optional[datetime]] = field(default_factory=dict)

    def evaluate(
        self,
        symbol: str,
        classified_regime: str,
    ) -> Dict[str, Any]:
        now = self.now_fn()
        if classified_regime == "DRIFT_IID_UNRELIABLE":
            if self._start.get(symbol) is None:
                self._start[symbol] = now
            start = self._start[symbol]
            assert start is not None
            duration_h = (now - start).total_seconds() / 3600.0
            out: Dict[str, Any] = {
                "stuck_duration_hours": round(duration_h, 3),
                "compliance_alert": "NONE",
            }
            if duration_h > self.threshold_hours:
                out["compliance_alert"] = "REVIEW_REQUIRED"
                out["alert_reason"] = (
                    f"System stuck in UNRELIABLE for > {self.threshold_hours:g} hours. "
                    "Baseline refresh proposed."
                )
                out["proposed_action"] = "Manually refresh reference window to last 30 days."
            return out

        if self._start.get(symbol) is not None:
            self._start[symbol] = None
        return {"stuck_duration_hours": 0.0, "compliance_alert": "NONE"}
