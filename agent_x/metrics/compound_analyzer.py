"""
AgentXCompoundAnalyzer — EWMA-based signal analysis for Agent X risk zones.

Detects static/adaptive disagreements in "caution" triggers by comparing a static Z-score
threshold against an adaptive EWMA baseline. Used for post-hoc
calibration of agent sensitivity.

Reads signal events from JSONL log files and produces:
  - Per-block evaluation (raw_zone vs calibrated_zone)
  - Over-sensitivity rate (% of blocks where static threshold is too aggressive)
  - Calibration recommendation (suggested threshold adjustment)

Usage:
    analyzer = AgentXCompoundAnalyzer(alpha=0.15, static_caution_threshold=2.0)
    report = analyzer.analyze_sequence(events)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BlockEvaluation:
    """Single block analysis result."""
    block_id: str
    raw_signal: float
    rolling_mean: float
    rolling_std: float
    z_score: float
    raw_zone: str          # "NORMAL" or "CAUTION" (based on static threshold)
    calibrated_zone: str    # "NORMAL" or "CAUTION" (based on adaptive EWMA)
    is_disagreement: bool   # True if static CAUTION but adaptive NORMAL (not an error)


class AgentXCompoundAnalyzer:
    """
    EWMA-based compound risk analyzer for Agent X signal events.

    Compares a static caution threshold against an adaptive EWMA baseline
    to identify where the two heuristics disagree. "Disagreement" does NOT
    imply an error — it measures a discrepancy between two decision rules.
    Without independent ground truth, neither rule is provably correct.

    The adaptive threshold adjusts to the observed noise level:
      adaptive_threshold = static_threshold × (1 + CV × volatility_penalty)
    where CV = σ/μ (coefficient of variation).
    """

    def __init__(
        self,
        alpha: float = 0.15,                 # EWMA smoothing factor
        static_caution_threshold: float = 2.0, # Agent X current threshold
        volatility_penalty: float = 0.5,      # Noise-to-threshold scaling
        min_samples: int = 20,                # Minimum for stable statistics
        high_is_healthy: bool = True,         # True for CHI (high=good), False for gas (high=bad)
    ):
        self.alpha = alpha
        self.static_threshold = static_caution_threshold
        self.volatility_penalty = volatility_penalty
        self.min_samples = min_samples
        self.high_is_healthy = high_is_healthy

    # ------------------------------------------------------------------
    # Core analysis
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Ground-truth-based accuracy analysis
    # ------------------------------------------------------------------

    def analyze_with_ground_truth(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Evaluate static thresholds against independent ground truth labels.

        Uses the 'expected_state' field in each event as ground truth.
        Treats 'caution', 'stressed', and 'critical' as POSITIVE (requires alert),
        and 'healthy' as NEGATIVE (no alert needed).

        Returns precision, recall, F1, and false-positive rate for each
        candidate threshold, plus the optimal threshold by F1 score.

        Events must have: 'signal_value', 'expected_state'.
        """
        if len(events) < self.min_samples:
            return {"error": f"Need ≥{self.min_samples} events with ground truth, got {len(events)}"}

        # Filter: ONLY use events that have an explicit expected_state label.
        # Unlabeled events (e.g. synthetic samples) are excluded from accuracy metrics.
        labeled = [ev for ev in events if "expected_state" in ev]
        if len(labeled) < self.min_samples:
            return {"error": f"Need ≥{self.min_samples} labeled events, got {len(labeled)} "
                             f"({len(events) - len(labeled)} unlabeled excluded)"}

        # Binary ground truth: healthy = negative, everything else = positive
        POSITIVE_STATES = {"caution", "stressed", "critical"}
        y_true = [
            1 if ev.get("expected_state", "healthy") in POSITIVE_STATES else 0
            for ev in labeled
        ]
        signals = [float(ev.get("signal_value", 0.0)) for ev in labeled]
        pos_count = sum(y_true)
        neg_count = len(y_true) - pos_count

        if pos_count == 0 or neg_count == 0:
            return {"error": f"Need both positive ({pos_count}) and negative ({neg_count}) examples"}

        # Test thresholds across signal range
        sig_min, sig_max = min(signals), max(signals)
        step = (sig_max - sig_min) / 30
        candidates = []
        best_f1 = -1.0
        best_threshold = self.static_threshold

        for thr in [sig_min + i * step for i in range(31)]:
            thr = round(thr, 1)
            # CHI: high=healthy → alarm when value < threshold
            if self.high_is_healthy:
                y_pred = [1 if s < thr else 0 for s in signals]
            else:
                y_pred = [1 if abs(s) > thr else 0 for s in signals]

            tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
            fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
            fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
            tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
            fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0  # False positive rate

            candidates.append({
                "threshold": thr,
                "tp": tp, "fp": fp, "fn": fn, "tn": tn,
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "fpr": round(fpr, 4),
            })

            if f1 > best_f1:
                best_f1 = f1
                best_threshold = thr

        # Find best candidate
        best = next((c for c in candidates if c["threshold"] == best_threshold), candidates[0])

        return {
            "ground_truth_available": True,
            "total_events": len(events),
            "labeled_events": len(labeled),
            "unlabeled_excluded": len(events) - len(labeled),
            "signal_direction": "high_is_healthy" if self.high_is_healthy else "high_is_bad",
            "positive_labels": pos_count,
            "negative_labels": neg_count,
            "signal_range": [sig_min, sig_max],
            "best_threshold": best_threshold,
            "best_f1": round(best_f1, 4),
            "best_precision": best["precision"],
            "best_recall": best["recall"],
            "current_threshold_performance": next(
                (c for c in candidates if c["threshold"] == self.static_threshold),
                candidates[0],
            ),
            "all_candidates": candidates,
            "recommendation": (
                f"Optimal threshold = {best_threshold} (F1={best_f1:.3f}, "
                f"precision={best['precision']:.3f}, recall={best['recall']:.3f}). "
                f"Current threshold {self.static_threshold}: "
                f"F1={next((c['f1'] for c in candidates if c['threshold'] == self.static_threshold), 0):.3f}."
            ),
        }

    # ------------------------------------------------------------------
    # Core analysis (heuristic comparison, no ground truth)
    # ------------------------------------------------------------------

    def analyze_sequence(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Analyze a sequence of signal events and produce a calibration report.

        Args:
            events: List of dicts with at least 'block_id' and 'signal_value'.

        Returns:
            Report dict with evaluations, metrics, and recommendation.
        """
        if len(events) < self.min_samples:
            return {
                "total_blocks_analyzed": len(events),
                "error": f"Insufficient data: need >= {self.min_samples} events, got {len(events)}",
                "evaluations": [],
            }

        evaluations: list[BlockEvaluation] = []
        mean = 0.0
        variance = 0.0
        disagreement_count = 0

        for i, ev in enumerate(events):
            value = float(ev.get("signal_value", ev.get("value", 0.0)))
            block_id = ev.get("block_id", f"BLK-{i:04d}")

            # EWMA update
            if i == 0:
                mean = value
                variance = 0.0
            else:
                delta = value - mean
                mean = self.alpha * value + (1.0 - self.alpha) * mean
                variance = self.alpha * (delta * delta) + (1.0 - self.alpha) * variance

            std = math.sqrt(variance + 1e-8)
            z_score = (value - mean) / (std + 1e-8) if std > 0 else 0.0

            # Raw zone: CHI is high=healthy, low=alarm — compare direction depends on signal semantics
            if self.high_is_healthy:
                raw_zone = "CAUTION" if value < self.static_threshold else "NORMAL"
            else:
                raw_zone = "CAUTION" if abs(value) > self.static_threshold else "NORMAL"

            # Calibrated zone: Z-score sign reversed for high_is_healthy (negative = below mean = alarm)
            cv = std / (abs(mean) + 1e-8)
            adaptive_threshold = self.static_threshold * (1.0 + cv * self.volatility_penalty)
            effective_z = -abs(z_score) if self.high_is_healthy else abs(z_score)
            calibrated_zone = "CAUTION" if abs(effective_z) > adaptive_threshold else "NORMAL"

            is_disagreement = (raw_zone == "CAUTION" and calibrated_zone == "NORMAL")
            if is_disagreement:
                disagreement_count += 1

            evaluations.append(BlockEvaluation(
                block_id=block_id,
                raw_signal=round(value, 4),
                rolling_mean=round(mean, 4),
                rolling_std=round(std, 4),
                z_score=round(z_score, 4),
                raw_zone=raw_zone,
                calibrated_zone=calibrated_zone,
                is_disagreement=is_disagreement,
            ))

        total = len(evaluations)
        disagreement_pct = round(disagreement_count / max(total, 1) * 100, 2)

        # Data-driven recommendation: test multiple thresholds
        caution_signals = sorted(
            [ev.raw_signal for ev in evaluations if ev.raw_zone == "CAUTION"],
            reverse=True,
        )
        candidates = []
        for thr in [2.0, 2.2, 2.4, 2.6, 2.8, 3.0, 3.2, 3.5, 4.0]:
            remaining = [s for s in caution_signals if s > thr]
            candidates.append({
                "threshold": thr,
                "caution_removed": len(caution_signals) - len(remaining),
                "caution_remaining": len(remaining),
                "removed_pct": round(
                    (len(caution_signals) - len(remaining)) / max(len(caution_signals), 1) * 100, 1
                ),
            })

        if caution_signals:
            # Recommend threshold that removes ≥50% of static-only cautions
            best = next(
                (c for c in candidates if c["caution_removed"] / max(len(caution_signals), 1) >= 0.5),
                candidates[-1],
            )
            rec = (
                f"Static threshold {self.static_threshold} produces {len(caution_signals)} CAUTIONs. "
                f"At threshold {best['threshold']}, {best['caution_removed']} of {len(caution_signals)} "
                f"({best['removed_pct']}%) are removed. "
                f"Remaining {best['caution_remaining']} are the strongest outliers "
                f"(≥{best['threshold']})."
            )
        else:
            rec = f"No CAUTIONs at current threshold {self.static_threshold}. No adjustment needed."

        return {
            "total_blocks_analyzed": total,
            "disagreement_count": disagreement_count,
            "disagreement_rate_percent": disagreement_pct,
            "static_caution_count": len(caution_signals),
            "threshold_candidates": candidates,
            "config": {
                "alpha": self.alpha,
                "static_caution_threshold": self.static_threshold,
                "volatility_penalty": self.volatility_penalty,
            },
            "evaluations": [self._eval_to_dict(e) for e in evaluations],
            "recommendation": rec,
        }

    @staticmethod
    def _eval_to_dict(e: BlockEvaluation) -> dict:
        return {
            "block_id": e.block_id,
            "raw_signal": e.raw_signal,
            "rolling_mean": e.rolling_mean,
            "rolling_std": e.rolling_std,
            "z_score": e.z_score,
            "raw_zone": e.raw_zone,
            "calibrated_zone": e.calibrated_zone,
            "is_disagreement": e.is_disagreement,
        }
