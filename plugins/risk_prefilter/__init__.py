"""Risk prefilter — Untrusted queue-priority scorer (Phase 4A).

Loads trained GBT model; emits prefilter_score only. Never gate_verdict.
Charter: DEFENSIVE_CAUSAL_GROUNDING · live_execution=false
"""

from plugins.risk_prefilter.scorer import load_scorer, score_features

__all__ = ["load_scorer", "score_features"]
