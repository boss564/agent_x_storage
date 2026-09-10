"""M2 shadow diagnostics — lag stratification overlays (not live execution)."""

from services.m2_shadow.risk_alpha import (
    AlphaDecayDiagnostic,
    AssetLiquidityGate,
    LagTradeObservation,
    V1_CORE_ASSETS,
)

__all__ = [
    "AlphaDecayDiagnostic",
    "AssetLiquidityGate",
    "LagTradeObservation",
    "V1_CORE_ASSETS",
]
