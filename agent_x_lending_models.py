"""
Agent X — Klasse B: Unified Data Models (Lending & Risiko).

Gemeinsame Datenstrukturen für alle B-Agenten.
Chain-agnostische Repräsentation von Lending-Positionen,
Health-Factors und Liquidations-Events.
"""

from dataclasses import dataclass, field, asdict
from decimal import Decimal
from enum import Enum
from typing import List, Dict, Optional
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("klasse_b_models")


class Chain(Enum):
    ETHEREUM = "ETHEREUM"
    ARBITRUM = "ARBITRUM"
    SOLANA = "SOLANA"
    BASE = "BASE"
    MONAD = "MONAD"


class RiskZone(Enum):
    SAFE = "SAFE"              # HF > 1.5
    WARNING = "WARNING"        # 1.05 < HF <= 1.5
    CRITICAL = "CRITICAL"      # 1.0 < HF <= 1.05
    LIQUIDATABLE = "LIQUIDATABLE"  # HF <= 1.0


class LendingProtocol(Enum):
    AAVE_V3 = "AaveV3"
    COMPOUND_V3 = "CompoundV3"
    SOLEND = "Solend"
    KAMINO = "Kamino"
    MARGINFI = "Marginfi"


# ─── Asset-Position ──────────────────────────────────────────────────

@dataclass
class AssetPosition:
    asset_address: str
    chain: Chain
    protocol: LendingProtocol
    amount: float                 # Skalierte Anzahl (z. B. 1.5 ETH)
    amount_usd: float = 0.0       # USD-Gegenwert
    normalized_income: float = 1.0  # aToken-Skalierung (liquidityIndex)
    is_collateral: bool = False
    collateral_enabled: bool = True
    liquidation_threshold: float = 0.8  # 0.8 = 80% (aus Protokoll)
    ltv: float = 0.75             # Loan-to-Value
    last_updated: str = ""

    def __post_init__(self):
        if not self.last_updated:
            self.last_updated = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "asset_address": self.asset_address,
            "chain": self.chain.value,
            "protocol": self.protocol.value,
            "amount": self.amount,
            "amount_usd": self.amount_usd,
            "normalized_income": self.normalized_income,
            "is_collateral": self.is_collateral,
            "collateral_enabled": self.collateral_enabled,
            "liquidation_threshold": self.liquidation_threshold,
            "ltv": self.ltv,
            "last_updated": self.last_updated,
        }


# ─── User-Lending-State ──────────────────────────────────────────────

@dataclass
class UserLendingState:
    user_address: str
    chain: Chain
    protocol: LendingProtocol
    positions: List[AssetPosition] = field(default_factory=list)
    total_collateral_usd: float = 0.0
    total_debt_usd: float = 0.0
    health_factor: float = float("inf")  # inf = keine Schulden
    risk_zone: RiskZone = RiskZone.SAFE
    last_updated_block: int = 0
    last_updated_slot: int = 0
    last_updated_timestamp: str = ""

    def __post_init__(self):
        if not self.last_updated_timestamp:
            self.last_updated_timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "user_address": self.user_address,
            "chain": self.chain.value,
            "protocol": self.protocol.value,
            "positions": [p.to_dict() for p in self.positions],
            "total_collateral_usd": self.total_collateral_usd,
            "total_debt_usd": self.total_debt_usd,
            "health_factor": self.health_factor,
            "risk_zone": self.risk_zone.value,
            "last_updated_block": self.last_updated_block,
            "last_updated_slot": self.last_updated_slot,
            "last_updated_timestamp": self.last_updated_timestamp,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ─── Liquidation-Event ───────────────────────────────────────────────

@dataclass
class LiquidationEvent:
    tx_hash: str
    chain: Chain
    protocol: LendingProtocol
    block_number: int
    slot: int
    user_address: str
    liquidator_address: str
    collateral_asset: str
    debt_asset: str
    collateral_taken: float
    debt_covered: float
    collateral_usd: float
    debt_usd: float
    bonus_pct: float  # Aave 5%, Solend 5-10%
    timestamp: str = ""
    cascade_count: int = 0  # >1 wenn Kaskade

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


# ─── Reserve-Daten (aus Protokoll) ───────────────────────────────────

@dataclass
class ReserveData:
    asset_address: str
    chain: Chain
    protocol: LendingProtocol
    symbol: str
    decimals: int = 18
    liquidity_rate: float = 0.0
    variable_borrow_rate: float = 0.0
    stable_borrow_rate: float = 0.0
    liquidity_index: float = 1.0
    variable_borrow_index: float = 1.0
    ltv: float = 0.0
    liquidation_threshold: float = 0.0
    liquidation_bonus: float = 0.05  # 5%
    available_liquidity: float = 0.0
    total_supplied: float = 0.0
    total_borrowed: float = 0.0
    utilization_rate: float = 0.0
    is_active: bool = True
    is_frozen: bool = False

    def to_dict(self) -> dict:
        return {
            "asset_address": self.asset_address,
            "chain": self.chain.value,
            "protocol": self.protocol.value,
            "symbol": self.symbol,
            "decimals": self.decimals,
            "liquidity_rate": self.liquidity_rate,
            "variable_borrow_rate": self.variable_borrow_rate,
            "stable_borrow_rate": self.stable_borrow_rate,
            "liquidity_index": self.liquidity_index,
            "variable_borrow_index": self.variable_borrow_index,
            "ltv": self.ltv,
            "liquidation_threshold": self.liquidation_threshold,
            "liquidation_bonus": self.liquidation_bonus,
            "available_liquidity": self.available_liquidity,
            "total_supplied": self.total_supplied,
            "total_borrowed": self.total_borrowed,
            "utilization_rate": self.utilization_rate,
            "is_active": self.is_active,
            "is_frozen": self.is_frozen,
        }


# ─── Reserve-Registry (Protokoll-Defaults) ───────────────────────────

RESERVE_DEFAULTS: Dict[str, dict] = {
    "ETH": {
        "symbol": "ETH", "decimals": 18, "ltv": 0.80,
        "liquidation_threshold": 0.825, "liquidation_bonus": 0.05,
    },
    "wstETH": {
        "symbol": "wstETH", "decimals": 18, "ltv": 0.75,
        "liquidation_threshold": 0.79, "liquidation_bonus": 0.075,
    },
    "WBTC": {
        "symbol": "WBTC", "decimals": 8, "ltv": 0.73,
        "liquidation_threshold": 0.78, "liquidation_bonus": 0.05,
    },
    "USDC": {
        "symbol": "USDC", "decimals": 6, "ltv": 0.80,
        "liquidation_threshold": 0.85, "liquidation_bonus": 0.05,
    },
    "USDT": {
        "symbol": "USDT", "decimals": 6, "ltv": 0.75,
        "liquidation_threshold": 0.80, "liquidation_bonus": 0.05,
    },
    "DAI": {
        "symbol": "DAI", "decimals": 18, "ltv": 0.77,
        "liquidation_threshold": 0.80, "liquidation_bonus": 0.05,
    },
    "SOL": {
        "symbol": "SOL", "decimals": 9, "ltv": 0.65,
        "liquidation_threshold": 0.75, "liquidation_bonus": 0.05,
    },
}


def get_reserve_default(asset: str) -> dict:
    """Holt Default-Reserve-Daten für ein Asset."""
    return RESERVE_DEFAULTS.get(asset, {
        "symbol": asset, "decimals": 18, "ltv": 0.60,
        "liquidation_threshold": 0.70, "liquidation_bonus": 0.05,
    })
