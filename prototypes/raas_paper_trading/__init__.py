"""RaaS Paper-Trading — DEFENSIVE_CAUSAL_GROUNDING · live_execution=false.

Map: docs/PAPER_TRADING_SETUP_v0.md
Never sends orders. Primary metric = envelope hit-rate, not profit factor.
"""

from prototypes.raas_paper_trading.config_loader import (
    PaperTradingSettings,
    config_manifest_hash,
    pair_manifest_hash,
)
from prototypes.raas_paper_trading.envelope_score import EnvelopeHitStats, score_envelope_hits
from prototypes.raas_paper_trading.feed import (
    PaperTick,
    ReplayFeed,
    assert_no_order_urls,
    fetch_binance_depth,
    fetch_binance_rest_sample,
    orderbook_to_snapshot,
    parse_orderbook_snapshot,
)
from prototypes.raas_paper_trading.depth_snapshot import (
    DepthSnapshot,
    age_stratum,
    make_live_depth_fetcher,
    make_worm_depth_fetcher,
    snapshot_age_seconds,
)
from prototypes.raas_paper_trading.depth_worm import DepthWormLog
from prototypes.raas_paper_trading.ledger import (
    FeeSchedule,
    PaperLedger,
    SlippageSettings,
    ledger_from_config,
)
from prototypes.raas_paper_trading.replay import (
    FillTuple,
    load_all_fills,
    load_fills_from_worm,
    replay_slippage_ab,
)
from prototypes.raas_paper_trading.slippage import (
    SYNTHETIC_QTY_PER_LEVEL,
    SYNTHETIC_SPREAD_BPS,
    calculate_dynamic_slippage,
    synthetic_orderbook,
)
from prototypes.raas_paper_trading.worm_log import PaperWormLog

__all__ = [
    "EnvelopeHitStats",
    "FeeSchedule",
    "PaperLedger",
    "PaperTradingSettings",
    "PaperTick",
    "FillTuple",
    "load_all_fills",
    "load_fills_from_worm",
    "replay_slippage_ab",
    "PaperTradingRunner",
    "PaperWormLog",
    "ReplayFeed",
    "SlippageSettings",
    "SYNTHETIC_QTY_PER_LEVEL",
    "SYNTHETIC_SPREAD_BPS",
    "calculate_dynamic_slippage",
    "config_manifest_hash",
    "pair_manifest_hash",
    "DepthSnapshot",
    "DepthWormLog",
    "age_stratum",
    "make_live_depth_fetcher",
    "make_worm_depth_fetcher",
    "snapshot_age_seconds",
    "assert_no_order_urls",
    "fetch_binance_depth",
    "fetch_binance_rest_sample",
    "orderbook_to_snapshot",
    "parse_orderbook_snapshot",
    "ledger_from_config",
    "score_envelope_hits",
    "synthetic_orderbook",
]
