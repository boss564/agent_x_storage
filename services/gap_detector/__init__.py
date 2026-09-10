"""Price-anomaly + cashtag gap detector (diagnostic_only).

Public Binance via ccxt — no API key. Does not touch the cluster.
"""
from __future__ import annotations

from services.gap_detector.detector import WATCHLIST, run_once

__all__ = ["WATCHLIST", "run_once"]
