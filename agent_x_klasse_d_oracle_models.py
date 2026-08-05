"""
Agent X — Klasse D: Oracle Heartbeats (Unified Data Models).

Datenstrukturen für Oracle-Update-Tracking, Heartbeat-Timing
und Off-Chain-Preis-Frühwarnung.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Dict, Optional
import json
import time
from datetime import datetime, timezone


class OracleProvider(Enum):
    CHAINLINK = "chainlink"
    PYTH = "pyth"
    CHRONICLE = "chronicle"
    TELLOR = "tellor"


class UpdateTrigger(Enum):
    HEARTBEAT = "heartbeat"
    DEVIATION = "deviation"
    MANUAL = "manual"
    UNKNOWN = "unknown"


# ─── Oracle Price Feed ───────────────────────────────────────────────

@dataclass
class PriceFeed:
    provider: OracleProvider
    asset_pair: str  # z.B. "ETH/USD"
    chain: str  # ETHEREUM, ARBITRUM, SOLANA
    contract_address: str
    proxy_address: str = ""

    # Aktueller On-Chain-Zustand
    last_onchain_price: float = 0.0
    last_onchain_round_id: int = 0
    last_onchain_timestamp: int = 0
    last_onchain_block: int = 0

    # Heartbeat-Parameter
    heartbeat_seconds: int = 3600  # Chainlink default
    deviation_threshold_pct: float = 0.5  # 0.5%

    # Off-Chain (aktueller Börsenpreis)
    offchain_price: float = 0.0
    offchain_confidence: float = 0.0
    offchain_last_fetched: str = ""

    # Berechnete Felder
    deviation_from_onchain_pct: float = 0.0
    seconds_since_last_update: int = 0
    next_heartbeat_unix: float = 0.0
    update_probability_5s: float = 0.0  # 0-100

    def __post_init__(self):
        if not self.offchain_last_fetched:
            self.offchain_last_fetched = datetime.now(timezone.utc).isoformat()
        if self.last_onchain_timestamp > 0:
            self.seconds_since_last_update = int(time.time() - self.last_onchain_timestamp)
        if self.heartbeat_seconds > 0:
            self.next_heartbeat_unix = self.last_onchain_timestamp + self.heartbeat_seconds
        if self.last_onchain_price > 0 and self.offchain_price > 0:
            self.deviation_from_onchain_pct = abs(
                (self.offchain_price - self.last_onchain_price) / self.last_onchain_price * 100
            )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["provider"] = self.provider.value
        return d


# ─── Oracle Update Event ──────────────────────────────────────────────

@dataclass
class OracleUpdateEvent:
    provider: OracleProvider
    asset_pair: str
    chain: str
    tx_hash: str
    block_number: int
    round_id: int
    new_price: float
    old_price: float
    deviation_pct: float
    update_trigger: UpdateTrigger
    timestamp: str = ""
    confidence_interval: float = 0.0

    # Mempool-Daten
    detected_in_mempool: bool = False
    mempool_detected_at: float = 0.0  # Unix
    confirmed_at: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["provider"] = self.provider.value
        d["update_trigger"] = self.update_trigger.value
        return d


# ─── Impact Simulation ────────────────────────────────────────────────

@dataclass
class ImpactSimulation:
    asset_pair: str
    new_price: float
    old_price: float

    # Betroffene Positionen
    positions_checked: int = 0
    positions_becoming_liquidatable: int = 0
    positions_becoming_critical: int = 0
    total_collateral_at_risk_usd: float = 0.0

    # Arbitrage
    uniswap_price: float = 0.0
    dex_oracle_spread_pct: float = 0.0
    arbitrage_profitable: bool = False
    estimated_profit_usd: float = 0.0
    estimated_gas_cost_usd: float = 0.0
    net_profit_usd: float = 0.0

    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Pre-Update Alert ─────────────────────────────────────────────────

@dataclass
class PreUpdateAlert:
    alert_id: str
    asset_pair: str
    provider: OracleProvider
    expected_trigger: UpdateTrigger
    expected_price: float
    confidence_pct: float  # Wie sicher ist die Vorhersage?
    seconds_until_update: float
    positions_at_risk: int = 0
    arbitrage_expected_profit_usd: float = 0.0
    recommended_slippage_pct: float = 0.5
    priority: str = "MEDIUM"  # LOW | MEDIUM | HIGH | CRITICAL
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.alert_id:
            import uuid
            self.alert_id = str(uuid.uuid4())[:8]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["provider"] = self.provider.value
        d["expected_trigger"] = self.expected_trigger.value
        return d


# ─── Heartbeat Schedule ───────────────────────────────────────────────

@dataclass
class HeartbeatSchedule:
    asset_pair: str
    provider: OracleProvider
    heartbeat_seconds: int
    last_update_unix: float
    next_heartbeat_unix: float
    next_deviation_unix: float = 0.0  # Geschätzt
    seconds_until_next: int = 0
    deviation_approaching: bool = False
    deviation_buffer_pct: float = 0.0  # Entfernung zum Trigger

    def __post_init__(self):
        self.seconds_until_next = max(0, int(self.next_heartbeat_unix - time.time()))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["provider"] = self.provider.value
        return d


# ─── Known Oracle Feeds (Production addresses) ────────────────────────

KNOWN_FEEDS: Dict[str, PriceFeed] = {
    "ETH-USD_CL": PriceFeed(
        provider=OracleProvider.CHAINLINK, asset_pair="ETH/USD", chain="ETHEREUM",
        contract_address="0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419",
        proxy_address="0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419",
        heartbeat_seconds=3600, deviation_threshold_pct=0.5,
    ),
    "BTC-USD_CL": PriceFeed(
        provider=OracleProvider.CHAINLINK, asset_pair="BTC/USD", chain="ETHEREUM",
        contract_address="0xF4030086522a5bEEa4988F8cA5B36dbC97BeE88c",
        heartbeat_seconds=3600, deviation_threshold_pct=0.5,
    ),
    "ETH-USD_PYTH": PriceFeed(
        provider=OracleProvider.PYTH, asset_pair="ETH/USD", chain="ETHEREUM",
        contract_address="0x4305FB66699C3B2702D4d05CF36551390A4c69C6",
        heartbeat_seconds=60, deviation_threshold_pct=0.05,
    ),
    "SOL-USD_PYTH": PriceFeed(
        provider=OracleProvider.PYTH, asset_pair="SOL/USD", chain="SOLANA",
        contract_address="H6ARHf6YXhGYeQfUzQNGk6rDNnLBQKrenN712K4AQJEG",
        heartbeat_seconds=1, deviation_threshold_pct=0.025,
    ),
    "BTC-USD_PYTH": PriceFeed(
        provider=OracleProvider.PYTH, asset_pair="BTC/USD", chain="ETHEREUM",
        contract_address="0xE62df6c8C0f5c5b2A1E54A5B5F5eB5F5e5e5E5e5E",
        heartbeat_seconds=60, deviation_threshold_pct=0.05,
    ),
}

# Chainlink Data Streams (Off-Chain REST API)
CHAINLINK_OFFCHAIN_API = "https://api.chain.link/data-streams"

# Pyth Hermes (Off-Chain REST API)
PYTH_HERMES_API = "https://hermes.pyth.network/api"

# Chainlink OCR2 Event Topics
CHAINLINK_EVENT_TRANSMITTED = "0xb1d8d0c8d3c7c1d8d0c8d3c7c1d8d0c8d3c7c1d8d0c8d3c7c1d8d0c8d3c7"  # OCR2 Transmitted
CHAINLINK_EVENT_ANSWER_UPDATED = "0x0559884b4a9ab2b9b6e6d7e6d3e7d6e4d5e6d7e4d5e6d7e4d5e6d7e4d5e"  # Legacy AnswerUpdated

# Pyth Event Topics
PYTH_EVENT_PRICE_FEED_UPDATE = "0x0000000000000000000000000000000000000000000000000000000000000000"  # placeholder
