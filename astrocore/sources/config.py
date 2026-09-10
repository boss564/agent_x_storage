"""PhaseSource defaults — local diagnostic adapters, not cluster config."""
from __future__ import annotations

from pathlib import Path
from typing import Dict

_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_LOOKBACK_HOURS = 24.0
DEFAULT_JSONL_PATH = _ROOT / "data" / "news_scores.jsonl"

# Per-asset weights for news sentiment aggregation. Unknown tickers use 0.5.
ASSET_WEIGHT: Dict[str, float] = {
    "BTC": 1.0,
    "ETH": 0.9,
    "SOL": 0.8,
    "BNB": 0.7,
    "XRP": 0.6,
    "AVAX": 0.6,
    "LINK": 0.6,
    "SUI": 0.6,
    "DOGE": 0.5,
    "PEPE": 0.5,
}

MACRO_WEIGHT = 0.5
GENERAL_WEIGHT = 0.3
UNKNOWN_ASSET_WEIGHT = 0.5
OVERALL_CONFIDENCE = 0.7
ASSET_CONFIDENCE = 0.8
PROVIDER_ID = "news_sentiment_v1"

# Price-gap PhaseSource. Scales frozen (2× detector thresholds). Do not retune.
DEFAULT_GAP_JSONL_PATH = _ROOT / "data" / "gap_reports.jsonl"
GAP_PROVIDER_ID = "price_gap_v1"
GAP_SCALE_1H = 10.0  # |Δ1h|=10% → |bias|=1; detector threshold is 5%
GAP_SCALE_24H = 16.0  # |Δ24h|=16% → |bias|=1; detector threshold is 8%
GAP_ASSET_CONFIDENCE = 0.75
GAP_OVERALL_CONFIDENCE = 0.65
