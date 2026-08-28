"""A2–A9 subagents for regime drift detection (paper / WORM monitoring only)."""
from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from prototypes.raas_paper_trading.regime_drift import (
    ALPHA,
    MIN_SAMPLES_PER_WINDOW,
    REF_FRAC,
    TEST_FRAC,
    load_signal_prices,
    permutation_ks_pvalue,
    prices_to_feature_rows,
    wasserstein_1d,
)
from prototypes.raas_paper_trading.regime_swarm.types import (
    CRITICAL_ALPHA,
    COOLING_OFF_CYCLES,
    AdaptiveAdvisory,
    DriftClassification,
    FeatureMatrix,
    KSFeatureResult,
    KS_SCREEN_ALPHA,
    RSI_CRITICAL_MIN,
    RSI_STABLE_MAX,
    WassersteinResult,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _split_feature_windows(
    series: Sequence[float],
) -> Optional[Tuple[List[float], List[float]]]:
    n = len(series)
    if n < 2 * MIN_SAMPLES_PER_WINDOW:
        return None
    ref_n = max(MIN_SAMPLES_PER_WINDOW, int(n * REF_FRAC))
    test_n = max(MIN_SAMPLES_PER_WINDOW, int(n * TEST_FRAC))
    if ref_n + test_n > n:
        return None
    return list(series[:ref_n]), list(series[-test_n:])


def _rolling_std(values: Sequence[float], window: int = 10) -> List[float]:
    if len(values) < window + 1:
        return []
    out: List[float] = []
    for i in range(window, len(values)):
        chunk = [float(v) for v in values[i - window : i]]
        out.append(statistics.pstdev(chunk) if len(chunk) > 1 else 0.0)
    return out


# --- A2 Data-Ingestor ---------------------------------------------------------


@dataclass
class DataIngestorAgent:
    """A2 — WORM / price stream ingest (read-only)."""

    name: str = "A2_DataIngestor"

    def load_prices(self, worm_path: Path) -> List[float]:
        return load_signal_prices(worm_path)

    def run(self, worm_path: Path) -> Dict[str, Any]:
        prices = self.load_prices(worm_path)
        return {
            "agent": self.name,
            "worm_path": str(worm_path),
            "n_ticks": len(prices),
            "source": "worm_signal_mark_price",
        }


# --- A3 Feature-Engineer ------------------------------------------------------


@dataclass
class FeatureEngineerAgent:
    """A3 — features + online z-score vs baseline window stats."""

    name: str = "A3_FeatureEngineer"
    feature_names: Tuple[str, ...] = (
        "log_return_pct",
        "abs_return_pct",
        "down_move_pct",
        "rolling_vol_pct",
    )

    def _engineer(self, prices: Sequence[float]) -> Dict[str, List[float]]:
        base = prices_to_feature_rows(prices)
        base["rolling_vol_pct"] = _rolling_std(base.get("log_return_pct", []), window=10)
        return {k: base.get(k, []) for k in self.feature_names}

    def run(self, prices: Sequence[float]) -> Dict[str, Any]:
        raw = self._engineer(prices)
        zscored: Dict[str, List[float]] = {}
        for name, series in raw.items():
            windows = _split_feature_windows(series)
            if not windows:
                zscored[name] = []
                continue
            ref, _cur = windows
            mu = statistics.fmean(ref) if ref else 0.0
            sigma = statistics.pstdev(ref) if len(ref) > 1 else 1e-12
            zscored[name] = [(float(v) - mu) / sigma for v in series]
        return {
            "agent": self.name,
            "features": list(self.feature_names),
            "raw_lengths": {k: len(v) for k, v in raw.items()},
            "zscore_applied": True,
        }

    def build_matrix(self, prices: Sequence[float]) -> Optional[FeatureMatrix]:
        raw = self._engineer(prices)
        baseline: Dict[str, List[float]] = {}
        current: Dict[str, List[float]] = {}
        for name, series in raw.items():
            windows = _split_feature_windows(series)
            if not windows:
                return None
            ref, cur = windows
            baseline[name] = ref
            current[name] = cur
        return FeatureMatrix(names=list(self.feature_names), baseline=baseline, current=current)


# --- A4 Window-Manager --------------------------------------------------------


@dataclass
class WindowManagerAgent:
    """A4 — reference baseline vs trailing current window."""

    name: str = "A4_WindowManager"

    def run(self, matrix: FeatureMatrix) -> Dict[str, Any]:
        return {
            "agent": self.name,
            "ref_frac": REF_FRAC,
            "test_frac": TEST_FRAC,
            "min_samples": MIN_SAMPLES_PER_WINDOW,
            "features": matrix.feature_names(),
            "n_baseline": {k: len(v) for k, v in matrix.baseline.items()},
            "n_current": {k: len(v) for k, v in matrix.current.items()},
        }


# --- A5 KS-Test-Agent ---------------------------------------------------------


@dataclass
class KSTestAgent:
    """A5 — univariate two-sample KS per feature."""

    name: str = "A5_KSTestAgent"
    screen_alpha: float = KS_SCREEN_ALPHA
    seed: int = 42

    def run(self, matrix: FeatureMatrix) -> Tuple[List[KSFeatureResult], Dict[str, Any]]:
        results: List[KSFeatureResult] = []
        for name in matrix.feature_names():
            ref = matrix.baseline.get(name, [])
            cur = matrix.current.get(name, [])
            d_stat, p_val = permutation_ks_pvalue(ref, cur, seed=self.seed)
            results.append(
                KSFeatureResult(
                    feature=name,
                    d_stat=d_stat,
                    p_value=p_val,
                    drift_detected=p_val < self.screen_alpha,
                )
            )
        anomaly_count = sum(1 for r in results if r.drift_detected)
        p_min = min((r.p_value for r in results), default=1.0)
        return results, {
            "agent": self.name,
            "anomaly_count": anomaly_count,
            "ks_p_value_min": round(p_min, 6),
            "per_feature": [r.to_dict() for r in results],
        }


# --- A6 Wasserstein-Agent -----------------------------------------------------


@dataclass
class WassersteinAgent:
    """A6 — 1D Wasserstein per feature (multivariate proxy = mean/max)."""

    name: str = "A6_WassersteinAgent"

    def run(self, matrix: FeatureMatrix) -> Tuple[WassersteinResult, Dict[str, Any]]:
        per: Dict[str, float] = {}
        for name in matrix.feature_names():
            per[name] = wasserstein_1d(
                matrix.baseline.get(name, []),
                matrix.current.get(name, []),
            )
        vals = list(per.values()) or [0.0]
        result = WassersteinResult(
            mean_w1=statistics.fmean(vals),
            max_w1=max(vals),
            per_feature=per,
        )
        return result, {"agent": self.name, **result.to_dict()}


# --- A7 Drift-Klassifizierer --------------------------------------------------


@dataclass
class DriftClassifierAgent:
    """A7 — aggregate KS + Wasserstein → RSI + regime flag."""

    name: str = "A7_DriftClassifier"
    critical_alpha: float = CRITICAL_ALPHA

    def run(
        self,
        ks_results: Sequence[KSFeatureResult],
        w_result: WassersteinResult,
        matrix: FeatureMatrix,
    ) -> Tuple[DriftClassification, Dict[str, Any]]:
        p_min = min((r.p_value for r in ks_results), default=1.0)
        anomaly_count = sum(1 for r in ks_results if r.drift_detected)

        ref_ret = matrix.baseline.get("log_return_pct", [])
        cur_ret = matrix.current.get("log_return_pct", [])
        mean_a = statistics.fmean(ref_ret) if ref_ret else 0.0
        mean_b = statistics.fmean(cur_ret) if cur_ret else 0.0
        std_a = statistics.pstdev(ref_ret) if len(ref_ret) > 1 else 1e-12
        mean_shift_sigma = abs(mean_b - mean_a) / std_a

        ref_vol = matrix.baseline.get("abs_return_pct", []) or ref_ret
        cur_vol = matrix.current.get("abs_return_pct", []) or cur_ret
        vol_ratio = (
            (statistics.fmean(cur_vol) / statistics.fmean(ref_vol))
            if ref_vol and statistics.fmean(ref_vol) > 0
            else 1.0
        )

        # RSI index 0–100 (heuristic, frozen v0)
        if p_min > KS_SCREEN_ALPHA and w_result.mean_w1 < 1e-6:
            rsi = 10.0
            flag = 0
            regime = "STABLE_SIDEWAYS"
            drift_type = "none"
        elif p_min < self.critical_alpha and w_result.mean_w1 > 0.01:
            rsi = min(100.0, 70.0 + 30.0 * min(1.0, w_result.mean_w1 / 0.05))
            flag = 2
            if mean_b < mean_a and vol_ratio > 1.2:
                regime = "HIGH_VOL_TREND_BEARISH"
                drift_type = "covariate_shift"
            elif vol_ratio > 1.2:
                regime = "HIGH_VOL_TREND"
                drift_type = "covariate_shift"
            else:
                regime = "LOW_VOL_DRIFT"
                drift_type = "prior_shift"
        else:
            rsi = 50.0
            flag = 1
            regime = "LOW_VOL_DRIFT"
            drift_type = "concept_drift_suspected"

        classification = DriftClassification(
            regime_shift_index=rsi,
            regime_flag=flag,
            classified_regime=regime,
            drift_type=drift_type,
            ks_p_value_min=p_min,
            anomaly_count=anomaly_count,
            mean_shift_sigma=mean_shift_sigma,
        )
        return classification, {"agent": self.name, **classification.to_dict()}


# --- A8 Strategie-Adapter (advisory only) -------------------------------------


@dataclass
class StrategyAdapterAgent:
    """A8 — diagnostic parameter suggestions (never applied)."""

    name: str = "A8_StrategyAdapter"

    def run(self, classification: DriftClassification) -> Tuple[AdaptiveAdvisory, Dict[str, Any]]:
        flag = classification.regime_flag
        if flag == 0:
            advisory = AdaptiveAdvisory(
                risk_multiplier_suggestion="unchanged (1.0)",
                max_position_size_suggestion="unchanged",
                strategy_mode_suggestion="unchanged",
            )
        elif flag == 1:
            advisory = AdaptiveAdvisory(
                risk_multiplier_suggestion="advisory: consider 1.0 → 1.25 if drift persists",
                max_position_size_suggestion="advisory: reduce shadow notional ~20% in replay",
                strategy_mode_suggestion="advisory: tighten envelope thresholds (diagnostic)",
            )
        else:
            advisory = AdaptiveAdvisory(
                risk_multiplier_suggestion="advisory: 1.0 → 1.5 (not executed)",
                max_position_size_suggestion="advisory: reduce ~40% (paper shadow only)",
                strategy_mode_suggestion="advisory: MeanReversion → caution / momentum-bias review",
            )
        return advisory, advisory.to_dict()


# --- A9 Audit- & Alerting-Agent -----------------------------------------------


@dataclass
class AuditAlertAgent:
    """A9 — append-only audit with hash checksum."""

    name: str = "A9_AuditAlert"
    audit_path: Path = Path("logs/worm/regime_drift_audit.jsonl")

    def _checksum(self, payload: Dict[str, Any]) -> str:
        blob = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def run(
        self,
        entry: Dict[str, Any],
        *,
        prev_hash: str = "0" * 64,
    ) -> Dict[str, Any]:
        entry["timestamp"] = _now()
        entry["prev_hash"] = prev_hash
        digest = self._checksum({**entry, "hash": ""})
        entry["hash_checksum"] = digest
        entry["hash"] = hashlib.sha256((prev_hash + digest).encode()).hexdigest()
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        return {
            "agent": self.name,
            "audit_path": str(self.audit_path),
            "hash_checksum": digest,
            "alert_level": entry.get("alert_level"),
        }


# --- Cooling-off state --------------------------------------------------------


class CoolingOffTracker:
    """A1 sub-component — regime_flag=2 must repeat COOLING_OFF_CYCLES times."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._counts: Dict[str, int] = {}
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                sym = str(row.get("symbol", ""))
                self._counts[sym] = int(row.get("streak", 0))

    def update(self, symbol: str, regime_flag: int) -> Tuple[int, bool]:
        if regime_flag >= 2:
            self._counts[symbol] = self._counts.get(symbol, 0) + 1
        else:
            self._counts[symbol] = 0
        streak = self._counts[symbol]
        confirmed = streak >= COOLING_OFF_CYCLES
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "symbol": symbol,
                        "regime_flag": regime_flag,
                        "streak": streak,
                        "confirmed": confirmed,
                        "ts": _now(),
                    }
                )
                + "\n"
            )
        return streak, confirmed
