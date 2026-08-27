"""Primary paper metric: envelope break-prediction hit rate (not profit)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence


@dataclass
class EnvelopeHitStats:
    """Precision/recall of predicted vs observed break conditions."""

    predicted_breaks: int
    observed_breaks: int
    true_positives: int
    false_positives: int
    false_negatives: int

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return (self.true_positives / denom) if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return (self.true_positives / denom) if denom else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric": "envelope_break_hit_rate",
            "role": "primary",
            "predicted_breaks": self.predicted_breaks,
            "observed_breaks": self.observed_breaks,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "precision": round(self.precision, 6),
            "recall": round(self.recall, 6),
            "not_investment_advice": True,
            "note": "Validates Safety Envelope under live marks — not strategy endorsement",
        }


def score_envelope_hits(
    predictions: Sequence[Dict[str, Any]],
    observations: Sequence[Dict[str, Any]],
) -> EnvelopeHitStats:
    """Match by condition_id: predicted break vs observed break.

    Each item: {"condition_id": str, "break": bool}
    """
    pred_map = {str(p["condition_id"]): bool(p.get("break")) for p in predictions}
    obs_map = {str(o["condition_id"]): bool(o.get("break")) for o in observations}
    ids = set(pred_map) | set(obs_map)
    tp = fp = fn = 0
    predicted = observed = 0
    for cid in ids:
        p = pred_map.get(cid, False)
        o = obs_map.get(cid, False)
        if p:
            predicted += 1
        if o:
            observed += 1
        if p and o:
            tp += 1
        elif p and not o:
            fp += 1
        elif o and not p:
            fn += 1
    return EnvelopeHitStats(
        predicted_breaks=predicted,
        observed_breaks=observed,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
    )
