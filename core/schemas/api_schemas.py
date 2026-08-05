"""Agent X — Pydantic API Schemas (Request/Response DTOs)."""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from enum import Enum


class RiskZone(str, Enum):
    HEALTHY = "healthy"
    CAUTION = "caution"
    STRESSED = "stressed"
    CRITICAL = "critical"


# ─── Request DTOs ─────────────────────────────────────────────────────

class PositionDTO(BaseModel):
    """Eine einzelne Asset-Position (Collateral oder Debt)."""
    symbol: str = Field(..., min_length=1, max_length=10, description="ETH, USDC, WBTC, ...")
    amount: float = Field(..., gt=0, description="Menge des Assets")
    price_usd: float = Field(..., gt=0, description="Aktueller USD-Preis")
    is_collateral: bool = Field(True, description="True = Collateral, False = Debt")
    liquidation_threshold: float = Field(0.80, ge=0, le=1.0, description="0.80 = 80%")

    @field_validator("symbol")
    @classmethod
    def symbol_uppercase(cls, v: str) -> str:
        return v.upper()


class TimelockDTO(BaseModel):
    """Angekündigte Governance-Aktion."""
    action: str = Field(..., description="setReserveBorrowRate, setCollateralFactor, ...")
    hours_until_executable: float = Field(..., ge=0, description="Stunden bis Ausführung")
    impact_score: int = Field(5, ge=1, le=10, description="1=minimal, 10=extrem")


class SnapshotRequestDTO(BaseModel):
    """Request für /v1/evaluate — bewertet einen Snapshot."""
    user_address: Optional[str] = Field(None, pattern=r"^0x[a-fA-F0-9]{40}$")
    positions: List[PositionDTO] = Field(default_factory=list, min_length=0)
    gas_pressure: Optional[float] = Field(None, ge=0, le=100)
    mev_pressure: Optional[float] = Field(None, ge=0, le=100)
    consensus_health: Optional[float] = Field(None, ge=0, le=100)
    mempool_bots: Optional[int] = Field(None, ge=0)
    oracle_update_in_s: Optional[float] = Field(None, ge=0)
    leader_utilization: Optional[float] = Field(None, ge=0, le=100)
    expected_profit_usd: Optional[float] = Field(None, ge=0)
    pending_timelocks: Optional[List[TimelockDTO]] = None

    @field_validator("positions")
    @classmethod
    def at_least_one_collateral_if_positions(cls, v, info):
        if v and not any(p.is_collateral for p in v):
            raise ValueError("Wenn Positionen angegeben sind, muss mindestens eine Collateral sein")
        return v


# ─── Response DTOs ────────────────────────────────────────────────────

class EvaluationResponseDTO(BaseModel):
    """Response für /v1/evaluate."""
    request_id: str
    chi_score: float = Field(..., ge=0, le=100)
    risk_zone: RiskZone
    action_recommended: str
    alerts: List[str] = Field(default_factory=list)
    state_accuracy_pct: float = 0.0
    correlation_id: str
    tenant_id: str = "default"
    gas_advice_eth_gwei: float = 0.0
    gas_advice_sol_cu: int = 0
    elapsed_ms: int = 0


class BatchRequestDTO(BaseModel):
    """Batch-Request — mehrere Snapshots auf einmal."""
    snapshots: List[SnapshotRequestDTO] = Field(..., min_length=1, max_length=100)


class BatchResponseDTO(BaseModel):
    """Batch-Response."""
    total: int
    results: List[EvaluationResponseDTO]
    errors: List[dict] = Field(default_factory=list)
    correlation_id: str


class BacktestRequestDTO(BaseModel):
    """Request für /v1/backtest."""
    scenarios: Optional[List[str]] = Field(None, description="['terra','ftx','svb','bull','flash','aave','arb','compound']")
    report: bool = False


class BacktestResponseDTO(BaseModel):
    """Response für /v1/backtest."""
    scenarios_run: int
    overall_score: float
    overall_grade: str
    results: List[dict]
