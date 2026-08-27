"""RaaS Paper-Trading — DEFENSIVE_CAUSAL_GROUNDING · live_execution=false.

Map: docs/PAPER_TRADING_SETUP_v0.md
Never sends orders. Primary metric = envelope hit-rate, not profit factor.
"""

from prototypes.raas_paper_trading.envelope_score import EnvelopeHitStats, score_envelope_hits
from prototypes.raas_paper_trading.feed import PaperTick, ReplayFeed, fetch_binance_rest_sample
from prototypes.raas_paper_trading.ledger import PaperLedger, FeeSchedule
from prototypes.raas_paper_trading.runner import PaperTradingRunner
from prototypes.raas_paper_trading.worm_log import PaperWormLog

__all__ = [
    "EnvelopeHitStats",
    "FeeSchedule",
    "PaperLedger",
    "PaperTick",
    "PaperTradingRunner",
    "PaperWormLog",
    "ReplayFeed",
    "fetch_binance_rest_sample",
    "score_envelope_hits",
]
