"""
Agent X — Druckventile: Unified Data Models (MEV, Gas, Priority Fees).

Gemeinsame Datenstrukturen für Gas-Analyse, MEV-Bribe-Tracking,
Block-Auslastung und Validator-Tips.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Dict, Optional
import json
from datetime import datetime, timezone
from collections import deque
import math


class MEVSource(Enum):
    FLASHBOTS = "flashbots"
    JITO = "jito"
    MEV_BOOST = "mev_boost"
    EDEN = "eden"


class PressureLevel(Enum):
    LOW = "low"           # 0-30
    MODERATE = "moderate"  # 30-50
    ELEVATED = "elevated"  # 50-70
    HIGH = "high"          # 70-85
    EXTREME = "extreme"    # 85-100


# ─── Gas-Data (EVM) ──────────────────────────────────────────────────

@dataclass
class EVMGasData:
    block_number: int
    base_fee_gwei: float
    base_fee_usd: float = 0.0
    priority_fee_avg_gwei: float = 0.0
    priority_fee_p50_gwei: float = 0.0
    priority_fee_p95_gwei: float = 0.0
    priority_fee_p99_gwei: float = 0.0
    gas_used_pct: float = 0.0       # 0-100
    gas_limit: int = 30_000_000
    gas_used: int = 0
    tx_count: int = 0
    blob_gas_price_gwei: float = 0.0
    blob_gas_used: int = 0
    blob_gas_limit: int = 393_216   # 6 Blobs à 128KB
    blob_utilization_pct: float = 0.0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if self.blob_gas_limit > 0:
            self.blob_utilization_pct = (self.blob_gas_used / self.blob_gas_limit) * 100

    def to_dict(self) -> dict:
        return asdict(self)


# ─── MEV-Bundle ──────────────────────────────────────────────────────

@dataclass
class MEVBundle:
    bundle_hash: str
    source: MEVSource
    block_number: int
    miner_bribe_eth: float        # Bestechungsgeld in ETH
    miner_bribe_usd: float = 0.0
    tx_count: int = 0
    total_gas: int = 0
    included_in_block: bool = False
    inclusion_block: int = 0
    searcher_address: str = ""
    target_contracts: List[str] = field(default_factory=list)
    estimated_profit_usd: float = 0.0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source"] = self.source.value
        return d


# ─── Jito-Tip (Solana) ───────────────────────────────────────────────

@dataclass
class SolanaTipData:
    slot: int
    leader_pubkey: str
    total_tips_lamports: int = 0
    total_tips_sol: float = 0.0
    total_tips_usd: float = 0.0
    avg_tip_lamports: float = 0.0
    p50_tip_lamports: float = 0.0
    p95_tip_lamports: float = 0.0
    p99_tip_lamports: float = 0.0
    max_tip_lamports: int = 0
    tx_count: int = 0
    bundled_tx_count: int = 0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if self.total_tips_lamports > 0:
            self.total_tips_sol = self.total_tips_lamports / 1e9
            self.total_tips_usd = self.total_tips_sol * 180  # SOL-Preis-Näherung
        if self.tx_count > 0:
            self.avg_tip_lamports = self.total_tips_lamports / self.tx_count

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Block-Pressure ──────────────────────────────────────────────────

@dataclass
class BlockPressureSnapshot:
    block_number: int
    chain: str  # ETHEREUM or SOLANA
    gas_pressure_index: float = 0.0       # 0-100
    mev_pressure_index: float = 0.0       # 0-100
    combined_pressure_index: float = 0.0  # 0-100 (weighted)
    pressure_level: PressureLevel = PressureLevel.LOW
    basefee_z_score: float = 0.0
    bribe_p99_eth: float = 0.0
    block_fullness_pct: float = 0.0
    mempool_queue_length: int = 0
    validator_greed_score: float = 0.0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["pressure_level"] = self.pressure_level.value
        return d


# ─── Transaction-Timing-Recommendation ────────────────────────────────

@dataclass
class TxTimingRecommendation:
    target_slot: int
    target_chain: str
    optimal_gas_price_gwei: float = 0.0
    optimal_priority_fee_gwei: float = 0.0
    estimated_confirmation_ms: int = 0
    mev_risk: str = "low"  # low | medium | high | extreme
    sandwich_protection: bool = False
    trusted_validator: str = ""
    reason: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Block-Forensik-Report ────────────────────────────────────────────

@dataclass
class BlockForensicReport:
    block_number: int
    chain: str
    total_txs: int = 0
    total_priority_fees_eth: float = 0.0
    mev_tx_count: int = 0
    mev_bundles_count: int = 0
    estimated_mev_profit_eth: float = 0.0
    sandwich_attacks: int = 0
    frontrun_attacks: int = 0
    backrun_attacks: int = 0
    arbitrage_txs: int = 0
    liquidations: int = 0
    summary: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ─── Rolling Stats Helper ────────────────────────────────────────────

class RollingStats:
    """Gleitende Statistiken mit fixem Fenster."""

    def __init__(self, window_size: int = 100):
        self.window = window_size
        self.values: deque = deque(maxlen=window_size)

    def add(self, value: float):
        self.values.append(value)

    @property
    def mean(self) -> float:
        if not self.values:
            return 0.0
        return sum(self.values) / len(self.values)

    @property
    def std(self) -> float:
        if len(self.values) < 2:
            return 0.0
        m = self.mean
        variance = sum((v - m) ** 2 for v in self.values) / (len(self.values) - 1)
        return math.sqrt(variance)

    @property
    def z_score(self) -> float:
        """Z-Score des aktuellsten Werts."""
        if len(self.values) < 2 or self.std == 0:
            return 0.0
        latest = list(self.values)[-1]
        return (latest - self.mean) / self.std

    @property
    def p50(self) -> float:
        return self._percentile(50)

    @property
    def p95(self) -> float:
        return self._percentile(95)

    @property
    def p99(self) -> float:
        return self._percentile(99)

    def _percentile(self, pct: float) -> float:
        if not self.values:
            return 0.0
        sorted_vals = sorted(self.values)
        idx = int(len(sorted_vals) * pct / 100)
        idx = min(idx, len(sorted_vals) - 1)
        return sorted_vals[idx]

    @property
    def count(self) -> int:
        return len(self.values)

    def snapshot(self) -> dict:
        return {
            "count": self.count,
            "mean": round(self.mean, 4),
            "std": round(self.std, 4),
            "z_score_latest": round(self.z_score, 2),
            "p50": round(self.p50, 4),
            "p95": round(self.p95, 4),
            "p99": round(self.p99, 4),
        }
