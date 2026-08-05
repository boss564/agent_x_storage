"""
Agent X — Klasse C: Unified Data Models (DeFi-Events).

Gemeinsame Datenstrukturen für Swap-Erkennung,
Flash-Loan-Analyse und Arbitrage-Detection.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Dict, Optional
import json
from datetime import datetime, timezone


class DexProtocol(Enum):
    UNISWAP_V3 = "UniswapV3"
    UNISWAP_V2 = "UniswapV2"
    CURVE = "Curve"
    BALANCER = "Balancer"
    SUSHISWAP = "SushiSwap"
    RAYDIUM = "Raydium"
    ORCA = "Orca"
    JUPITER = "Jupiter"


class ArbitrageType(Enum):
    CROSS_POOL = "cross_pool"       # Gleiche Chain, verschiedene Pools
    CROSS_CHAIN = "cross_chain"     # Verschiedene Chains (atomar via A3-1c)
    TRIANGULAR = "triangular"       # A→B→C→A auf gleichem DEX
    FLASH_LOAN = "flash_loan"       # Flash-Loan-basierte Arbitrage
    LIQUIDATION = "liquidation"     # Liquidations-Arbitrage (B3-Signal)


class OpportunityStatus(Enum):
    DETECTED = "detected"
    VALIDATING = "validating"
    PROFITABLE = "profitable"
    EXECUTING = "executing"
    EXECUTED = "executed"
    REVERTED = "reverted"
    EXPIRED = "expired"


# ─── Swap-Event ──────────────────────────────────────────────────────

@dataclass
class SwapEvent:
    tx_hash: str
    chain: str  # ETHEREUM, ARBITRUM, SOLANA
    protocol: DexProtocol
    block_number: int
    token_in: str
    token_out: str
    amount_in: float
    amount_out: float
    pool_address: str
    sender: str
    recipient: str
    gas_used: int = 0
    gas_price_gwei: float = 0.0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    @property
    def price(self) -> float:
        """Preis = amount_out / amount_in (inverse des Swap-Kurses)."""
        return self.amount_out / self.amount_in if self.amount_in > 0 else 0.0

    @property
    def volume_usd(self) -> float:
        """Geschätztes USD-Volumen (vereinfacht)."""
        return self.amount_in  # Annäherung, Preisfeed nötig

    def to_dict(self) -> dict:
        return {
            "tx_hash": self.tx_hash,
            "chain": self.chain,
            "protocol": self.protocol.value,
            "block_number": self.block_number,
            "token_in": self.token_in,
            "token_out": self.token_out,
            "amount_in": self.amount_in,
            "amount_out": self.amount_out,
            "pool_address": self.pool_address,
            "sender": self.sender,
            "recipient": self.recipient,
            "price": round(self.price, 8),
            "volume_usd": round(self.volume_usd, 2),
            "timestamp": self.timestamp,
        }


# ─── Flash-Loan ──────────────────────────────────────────────────────

@dataclass
class FlashLoanEvent:
    tx_hash: str
    chain: str
    protocol: str  # AaveV3, Balancer, UniswapV3, Maker
    block_number: int
    asset: str
    amount: float
    amount_usd: float
    initiator: str
    target_contract: str
    premium_paid: float = 0.0  # Fee an das Protokoll
    premium_pct: float = 0.0
    was_profitable: bool = False
    net_profit_usd: float = 0.0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if self.premium_pct == 0.0 and self.amount > 0:
            self.premium_pct = (self.premium_paid / self.amount) * 100 if self.amount > 0 else 0

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Arbitrage-Opportunity ───────────────────────────────────────────

@dataclass
class ArbitrageOpportunity:
    id: str
    type: ArbitrageType
    chain: str
    timestamp: str = ""

    # Route
    steps: List[dict] = field(default_factory=list)  # [{pool, token_in, token_out, amount}]
    entry_token: str = ""
    entry_amount: float = 0.0
    exit_amount: float = 0.0

    # Economics
    gross_profit_usd: float = 0.0
    gas_cost_usd: float = 0.0
    flash_loan_fee_usd: float = 0.0
    net_profit_usd: float = 0.0
    roi_pct: float = 0.0

    # Execution parameters
    optimal_gas_price_gwei: float = 0.0
    optimal_broadcast_slot: int = 0  # Von A3-3
    deadline_unix: float = 0.0
    trusted_validator: str = ""  # Von A3-3a

    # Risk
    mev_risk: str = "low"  # low | medium | high | extreme
    revert_risk: str = "low"
    competition_estimate: int = 0  # Geschätzte Konkurrenten
    status: OpportunityStatus = OpportunityStatus.DETECTED

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.id:
            import uuid
            self.id = str(uuid.uuid4())[:8]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        d["status"] = self.status.value
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ─── Pool-State ──────────────────────────────────────────────────────

@dataclass
class PoolState:
    pool_address: str
    chain: str
    protocol: DexProtocol
    token0: str
    token1: str
    token0_symbol: str = ""
    token1_symbol: str = ""
    reserve0: float = 0.0
    reserve1: float = 0.0
    price: float = 0.0  # token1 / token0
    tvl_usd: float = 0.0
    fee_bps: int = 30  # 0.30% = 30 bps
    volume_24h_usd: float = 0.0
    last_swap_block: int = 0
    last_updated: str = ""

    def __post_init__(self):
        if not self.last_updated:
            self.last_updated = datetime.now(timezone.utc).isoformat()
        if self.price == 0.0 and self.reserve0 > 0 and self.reserve1 > 0:
            self.price = self.reserve1 / self.reserve0

    def get_output_amount(self, amount_in: float, token_in_is_0: bool = True) -> float:
        """Berechnet Output-Menge via CPMM (x*y=k) mit Fee."""
        if self.reserve0 <= 0 or self.reserve1 <= 0:
            return 0.0

        fee_multiplier = (10000 - self.fee_bps) / 10000
        amount_in_with_fee = amount_in * fee_multiplier

        if token_in_is_0:
            reserve_in = self.reserve0
            reserve_out = self.reserve1
        else:
            reserve_in = self.reserve1
            reserve_out = self.reserve0

        # CPMM: amount_out = reserve_out * amount_in_with_fee / (reserve_in + amount_in_with_fee)
        amount_out = (reserve_out * amount_in_with_fee) / (reserve_in + amount_in_with_fee)
        return amount_out

    def get_price_impact(self, amount_in: float, token_in_is_0: bool = True) -> float:
        """Preis-Impact in Prozent."""
        if self.reserve0 <= 0 or self.reserve1 <= 0:
            return 100.0

        if token_in_is_0:
            spot = self.reserve1 / self.reserve0
            amount_out = self.get_output_amount(amount_in, True)
            execution_price = amount_out / amount_in if amount_in > 0 else spot
            return abs((spot - execution_price) / spot) * 100
        else:
            spot = self.reserve0 / self.reserve1
            amount_out = self.get_output_amount(amount_in, False)
            execution_price = amount_out / amount_in if amount_in > 0 else spot
            return abs((spot - execution_price) / spot) * 100

    def to_dict(self) -> dict:
        return {
            "pool_address": self.pool_address,
            "chain": self.chain,
            "protocol": self.protocol.value,
            "token0": self.token0,
            "token1": self.token1,
            "token0_symbol": self.token0_symbol,
            "token1_symbol": self.token1_symbol,
            "reserve0": self.reserve0,
            "reserve1": self.reserve1,
            "price": round(self.price, 8),
            "tvl_usd": self.tvl_usd,
            "fee_bps": self.fee_bps,
            "volume_24h_usd": self.volume_24h_usd,
            "last_updated": self.last_updated,
        }


# ─── Pool-Registry (Bekannte DEX-Pools) ──────────────────────────────

KNOWN_POOLS: Dict[str, PoolState] = {
    "ETH-USDC_UniV3": PoolState(
        pool_address="0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640",
        chain="ETHEREUM", protocol=DexProtocol.UNISWAP_V3,
        token0="ETH", token1="USDC",
        token0_symbol="ETH", token1_symbol="USDC",
        reserve0=1000, reserve1=3_200_000,  # 1000 ETH + 3.2M USDC
        tvl_usd=6_400_000, fee_bps=5,
    ),
    "WBTC-USDC_UniV3": PoolState(
        pool_address="0x99ac8cA7087fA4A2A1FB6357269965A2014ABc35",
        chain="ETHEREUM", protocol=DexProtocol.UNISWAP_V3,
        token0="WBTC", token1="USDC",
        token0_symbol="WBTC", token1_symbol="USDC",
        reserve0=100, reserve1=6_500_000,
        tvl_usd=13_000_000, fee_bps=30,
    ),
    "ETH-USDC_UniV2": PoolState(
        pool_address="0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc",
        chain="ETHEREUM", protocol=DexProtocol.UNISWAP_V2,
        token0="ETH", token1="USDC",
        token0_symbol="ETH", token1_symbol="USDC",
        reserve0=500, reserve1=1_590_000,
        tvl_usd=3_180_000, fee_bps=30,
    ),
    "SOL-USDC_Orca": PoolState(
        pool_address="orca_SOL_USDC",
        chain="SOLANA", protocol=DexProtocol.ORCA,
        token0="SOL", token1="USDC",
        token0_symbol="SOL", token1_symbol="USDC",
        reserve0=500_000, reserve1=90_000_000,
        tvl_usd=180_000_000, fee_bps=30,
    ),
}


# ─── Aave V3 Flash-Loan-Fee ──────────────────────────────────────────

AAVE_V3_FLASH_LOAN_FEE = 0.0009  # 0.09% (9 bps)
UNISWAP_V3_FLASH_LOAN_FEE = 0.0030  # 0.30% (30 bps auf Swap-Gebühr)
BALANCER_FLASH_LOAN_FEE = 0.0  # 0% (keine Fee)
MAKER_FLASH_LOAN_FEE = 0.0  # DAI Flash Mint: 0%


def get_flash_loan_fee(protocol: str) -> float:
    """Gibt die Flash-Loan-Gebühr für ein Protokoll zurück."""
    fees = {
        "AaveV3": AAVE_V3_FLASH_LOAN_FEE,
        "UniswapV3": UNISWAP_V3_FLASH_LOAN_FEE,
        "Balancer": BALANCER_FLASH_LOAN_FEE,
        "Maker": MAKER_FLASH_LOAN_FEE,
    }
    return fees.get(protocol, 0.0009)
