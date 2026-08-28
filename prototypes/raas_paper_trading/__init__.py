"""RaaS Paper-Trading — DEFENSIVE_CAUSAL_GROUNDING · live_execution=false.

Map: docs/PAPER_TRADING_SETUP_v0.md
Never sends orders. Primary metric = envelope hit-rate, not profit factor.
"""

from prototypes.raas_paper_trading.config_loader import (
    PaperTradingSettings,
    config_manifest_hash,
)
from prototypes.raas_paper_trading.envelope_score import EnvelopeHitStats, score_envelope_hits
from prototypes.raas_paper_trading.feed import PaperTick, ReplayFeed, fetch_binance_rest_sample
from prototypes.raas_paper_trading.ledger import (
    FeeSchedule,
    PaperLedger,
    SlippageSettings,
    ledger_from_config,
)
from prototypes.raas_paper_trading.runner import PaperTradingRunner
from prototypes.raas_paper_trading.slippage import calculate_dynamic_slippage, synthetic_orderbook
from prototypes.raas_paper_trading.worm_log import PaperWormLog

__all__ = [
    "EnvelopeHitStats",
    "FeeSchedule",
    "PaperLedger",
    "PaperTradingSettings",
    "PaperTick",
    "PaperTradingRunner",
    "PaperWormLog",
    "ReplayFeed",
    "SlippageSettings",
    "calculate_dynamic_slippage",
    "config_manifest_hash",
    "fetch_binance_rest_sample",
    "ledger_from_config",
    "score_envelope_hits",
    "synthetic_orderbook",
]
