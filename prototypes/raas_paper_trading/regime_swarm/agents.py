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
    MIN_SAMPLES_PER_WINDOW,
    REF_FRAC,
    TEST_FRAC,
    load_signal_prices,
    permutation_ks_pvalue,
    prices_to_feature_rows,
    wasserstein_1d,
)
from prototypes.raas_paper_trading.regime_swarm.types import (
    AUTOCORR_RHO_THRESHOLD,
    CRITICAL_ALPHA,
    COOLING_OFF_CYCLES,
    AdaptiveAdvisory,
    DriftClassification,
    FeatureMatrix,
    IidStatus,
    KSFeatureResult,
    KS_SCREEN_ALPHA,
    N_EFF_RATIO_THRESHOLD,
    PreRegIntervention,
    R2_CUBED_BLOCK,
    STANDARDIZED_DRIFT_THRESHOLD,
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


def _pearson_lag1(series: Sequence[float]) -> float:
    if len(series) < 3:
        return 0.0
    x = [float(v) for v in series[:-1]]
    y = [float(v) for v in series[1:]]
    mx = statistics.fmean(x)
    my = statistics.fmean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den_x = sum((a - mx) ** 2 for a in x) ** 0.5
    den_y = sum((b - my) ** 2 for b in y) ** 0.5
    if den_x * den_y < 1e-12:
        return 0.0
    rho = num / (den_x * den_y)
    return max(-1.0, min(1.0, rho))


def build_r2_cubed_series(
    log_returns: Sequence[float],
    *,
    block: int = R2_CUBED_BLOCK,
) -> List[float]:
    """Squared returns over overlapping block windows, cubed (A4 i.i.d. probe)."""
    if len(log_returns) < block:
        return []
    out: List[float] = []
    for i in range(len(log_returns) - block + 1):
        chunk = [float(r) for r in log_returns[i : i + block]]
        r2_mean = statistics.fmean(r * r for r in chunk)
        out.append(r2_mean**3)
    return out


def calculate_iid_violation_flag(
    series: Sequence[float],
    *,
    n_eff_ratio_threshold: float = N_EFF_RATIO_THRESHOLD,
) -> IidStatus:
    """Lag-1 autocorrelation + Bartlett-style n_eff for overlapping windows."""
    n = len(series)
    if n < 4:
        return IidStatus(rho=0.0, n_raw=n, n_eff=float(n), is_iid_violation=False)
    rho = _pearson_lag1(series)
    if abs(1.0 + rho) < 1e-12:
        n_eff = float(n)
    else:
        n_eff = max(1.0, n * (1.0 - rho) / (1.0 + rho))
    ratio = n_eff / n if n else 1.0
    return IidStatus(
        rho=rho,
        n_raw=n,
        n_eff=n_eff,
        is_iid_violation=ratio < n_eff_ratio_threshold,
    )


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
    """A4 — reference/current windows + autocorrelation monitor (r2_cubed)."""

    name: str = "A4_WindowManager"

    def run(self, matrix: FeatureMatrix) -> Tuple[Dict[str, Any], IidStatus]:
        log_current = matrix.current.get("log_return_pct", [])
        r2_series = build_r2_cubed_series(log_current)
        iid = calculate_iid_violation_flag(r2_series)
        meta = {
            "agent": self.name,
            "ref_frac": REF_FRAC,
            "test_frac": TEST_FRAC,
            "min_samples": MIN_SAMPLES_PER_WINDOW,
            "features": matrix.feature_names(),
            "n_baseline": {k: len(v) for k, v in matrix.baseline.items()},
            "n_current": {k: len(v) for k, v in matrix.current.items()},
            "iid_monitor": iid.to_dict(),
        }
        return meta, iid


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
    """A7 — aggregate KS + Wasserstein → RSI; i.i.d.-override (Pre-Reg Line 74)."""

    name: str = "A7_DriftClassifier"
    critical_alpha: float = CRITICAL_ALPHA
    drift_threshold: float = STANDARDIZED_DRIFT_THRESHOLD
    rho_threshold: float = AUTOCORR_RHO_THRESHOLD

    def _base_classify(
        self,
        ks_results: Sequence[KSFeatureResult],
        w_result: WassersteinResult,
        matrix: FeatureMatrix,
        *,
        standardized_drift: float,
    ) -> DriftClassification:
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

        if p_min > KS_SCREEN_ALPHA and w_result.mean_w1 < 1e-6:
            rsi, flag, regime, drift_type = 10.0, 0, "STABLE_SIDEWAYS", "none"
        elif p_min < self.critical_alpha and w_result.mean_w1 > 0.01:
            rsi = min(100.0, 70.0 + 30.0 * min(1.0, w_result.mean_w1 / 0.05))
            flag = 2
            if mean_b < mean_a and vol_ratio > 1.2:
                regime, drift_type = "HIGH_VOL_TREND_BEARISH", "covariate_shift"
            elif vol_ratio > 1.2:
                regime, drift_type = "HIGH_VOL_TREND", "covariate_shift"
            else:
                regime, drift_type = "LOW_VOL_DRIFT", "prior_shift"
        else:
            rsi, flag, regime, drift_type = 50.0, 1, "LOW_VOL_DRIFT", "concept_drift_suspected"

        allow = flag >= 1
        return DriftClassification(
            regime_shift_index=rsi,
            regime_flag=flag,
            classified_regime=regime,
            drift_type=drift_type,
            ks_p_value_min=p_min,
            anomaly_count=anomaly_count,
            mean_shift_sigma=mean_shift_sigma,
            standardized_drift=standardized_drift,
            allow_amendment=allow,
            iid_unreliable=False,
        )

    def _apply_pre_reg_override(
        self,
        classification: DriftClassification,
        iid: IidStatus,
    ) -> Tuple[DriftClassification, Optional[PreRegIntervention]]:
        if classification.regime_flag < 1:
            return classification, None
        if not (
            classification.standardized_drift > self.drift_threshold
            and iid.is_iid_violation
            and iid.rho > self.rho_threshold
            and classification.ks_p_value_min < KS_SCREEN_ALPHA
        ):
            return classification, None

        reason = (
            "Drift erkannt, aber Raten-Vergleich gegen i.i.d.-Tabelle nicht verlässlich "
            "(überlappende Fenster / Autokorrelation) – Amendment gesperrt, Alarm bleibt."
        )
        overridden = DriftClassification(
            regime_shift_index=classification.regime_shift_index,
            regime_flag=classification.regime_flag,
            classified_regime="DRIFT_IID_UNRELIABLE",
            drift_type="iid_rate_unreliable",
            ks_p_value_min=classification.ks_p_value_min,
            anomaly_count=classification.anomaly_count,
            mean_shift_sigma=classification.mean_shift_sigma,
            standardized_drift=classification.standardized_drift,
            allow_amendment=False,
            iid_unreliable=True,
            pre_reg_reason=reason,
        )
        intervention = PreRegIntervention(
            triggered=True,
            autocorrelation_rho_for_r2_cubed=iid.rho,
            effective_sample_size=iid.n_eff,
            raw_sample_size=iid.n_raw,
            decision=(
                "AMENDMENT_BLOCKED – Rate nicht gegen i.i.d.-Tabelle prüfbar; "
                f"regime_flag={classification.regime_flag} bleibt für Cooling-Off/Alert."
            ),
        )
        return overridden, intervention

    def run(
        self,
        ks_results: Sequence[KSFeatureResult],
        w_result: WassersteinResult,
        matrix: FeatureMatrix,
        *,
        iid_status: IidStatus,
    ) -> Tuple[DriftClassification, Dict[str, Any], Optional[PreRegIntervention]]:
        ref_ret = matrix.baseline.get("log_return_pct", [])
        baseline_std = statistics.pstdev(ref_ret) if len(ref_ret) > 1 else 1e-12
        if baseline_std < 1e-12:
            baseline_std = 1e-12
        standardized_drift = w_result.mean_w1 / baseline_std

        classification = self._base_classify(
            ks_results, w_result, matrix, standardized_drift=standardized_drift
        )
        classification, intervention = self._apply_pre_reg_override(classification, iid_status)

        meta = {
            "agent": self.name,
            **classification.to_dict(),
            "baseline_std": round(baseline_std, 8),
        }
        if intervention:
            meta["pre_reg_intervention"] = intervention.to_dict()
        return classification, meta, intervention


# --- A8 Strategie-Adapter (advisory only) -------------------------------------


@dataclass
class StrategyAdapterAgent:
    """A8 — diagnostic suggestions; interlock on allow_amendment (never executed)."""

    name: str = "A8_StrategyAdapter"

    def run(self, classification: DriftClassification) -> Tuple[AdaptiveAdvisory, Dict[str, Any]]:
        if not classification.allow_amendment:
            reason = classification.pre_reg_reason or "allow_amendment=False"
            advisory = AdaptiveAdvisory(
                risk_multiplier_suggestion="unchanged (1.0)",
                max_position_size_suggestion="unchanged",
                strategy_mode_suggestion="unchanged",
                amendment_skipped=True,
                final_action="PARAMETER_UNCHANGED",
            )
            meta = advisory.to_dict()
            meta["skip_reason"] = f"AMENDMENT_SKIPPED: {reason}"
            return advisory, meta

        flag = classification.regime_flag
        if flag == 0:
            advisory = AdaptiveAdvisory(
                risk_multiplier_suggestion="unchanged (1.0)",
                max_position_size_suggestion="unchanged",
                strategy_mode_suggestion="unchanged",
                final_action="PARAMETER_UNCHANGED",
            )
        elif flag == 1:
            advisory = AdaptiveAdvisory(
                risk_multiplier_suggestion="advisory: consider 1.0 → 1.25 if drift persists",
                max_position_size_suggestion="advisory: reduce shadow notional ~20% in replay",
                strategy_mode_suggestion="advisory: tighten envelope thresholds (diagnostic)",
                final_action="PARAMETER_ADVISORY",
            )
        else:
            advisory = AdaptiveAdvisory(
                risk_multiplier_suggestion="advisory: 1.0 → 1.5 (not executed)",
                max_position_size_suggestion="advisory: reduce ~40% (paper shadow only)",
                strategy_mode_suggestion="advisory: MeanReversion → caution / momentum-bias review",
                final_action="PARAMETER_ADVISORY",
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
