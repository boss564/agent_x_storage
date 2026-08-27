"""Score features for backlog prioritization — no gate decisions."""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Union

import numpy as np

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"
FEATURE_NAMES = [
    "latency_ms",
    "slippage_pct",
    "pool_depth_usd",
    "volatility_24h",
    "gas_price_gwei",
    "oracle_deviation_pct",
    "mev_bundle_activity",
    "strategy_complexity_score",
]


class PrefilterScorer:
    def __init__(self, backend: str, model: Any, features: Sequence[str]) -> None:
        self.backend = backend
        self.model = model
        self.features = list(features)

    def score(self, features: Mapping[str, float]) -> Dict[str, Any]:
        x = np.array([[float(features.get(c, 0.0)) for c in self.features]], dtype=np.float64)
        if self.backend == "lightgbm":
            pred = float(self.model.predict(x)[0])
        else:
            pred = float(self.model.predict(x)[0])
        return {
            "type": "prefilter_score",
            "prefilter_score": pred,
            "backend": self.backend,
            "role": "UNTRUSTED_SHELL",
            "live_execution": False,
            "scope": SCOPE,
            "purpose": "queue_prioritization_under_backlog",
            "note": "Score for queue order only — core must still fully evaluate",
        }


def load_scorer(model_path: Union[str, Path]) -> PrefilterScorer:
    path = Path(model_path)
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    if path.suffix == ".txt" or (meta_path.exists() and "lightgbm" in meta_path.read_text()):
        try:
            import lightgbm as lgb

            model = lgb.Booster(model_file=str(path))
            return PrefilterScorer("lightgbm", model, FEATURE_NAMES)
        except Exception:
            pass
    with path.open("rb") as f:
        blob = pickle.load(f)
    return PrefilterScorer(
        blob.get("backend", "sklearn_hist_gradient_boosting"),
        blob["model"],
        blob.get("features", FEATURE_NAMES),
    )


def score_features(
    features: Mapping[str, float],
    *,
    model_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    path = Path(model_path or "models/prefilter/prefilter_gbt.pkl")
    scorer = load_scorer(path)
    out = scorer.score(features)
    # Hard strip any decision fields if caller smuggled them in
    for k in ("gate_verdict", "audit_verdict", "envelope_id", "egress_seal", "certificate_id"):
        out.pop(k, None)
    return out
