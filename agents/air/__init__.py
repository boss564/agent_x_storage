"""Air Interceptor — A01–A09 dual air-superiority layer.

Schwarm 1 (Air Superiority): A01 AWACS, A02 Fast-Path, A03 Soft-Finality.
Schwarm 2 (Ground Attack): A04 CAS-Coordinator, A05 CAS-Bomber (GPU burst),
A06 Airspace-Watch (poison scan). Schwarm 3 (A07–A09 Logistics) follows.
"""

from .base import (
    AirAction,
    AirInterceptResult,
    AirInterceptorAgent,
    AirCoordinator,
)
from .finality_types import (
    FinalityTier,
    FinalityState,
    TERMINAL_STATES,
    FINALITY_TRANSITIONS,
    DedupKey,
    build_dedup_key,
    AttestationEnvelope,
)
from .soft_finality_cache import SoftFinalityCache, CacheEntry
from .a01_awacs import A01Awacs
from .a02_fastpath import A02FastpathHunter, FastPathInterceptor
from .a03_soft_finality import (
    A03SoftFinalityVerifier,
    SoftFinalityEngine,
    CASConflictError,
)
from .a04_cas_coordinator import (
    CASCoordinator,
    CASRequest,
    CASSlotOp,
    CASResult,
    CASStatus,
)
from .a05_cas_bomber import (
    CASBomber,
    BurstReport,
    CPUBackend,
    GPUBurstBackend,
)
from .a06_airspace_watch import AirspaceWatch, PoisonKind, WatchAlert

__all__ = [
    "AirAction",
    "AirInterceptResult",
    "AirInterceptorAgent",
    "AirCoordinator",
    "FinalityTier",
    "FinalityState",
    "TERMINAL_STATES",
    "FINALITY_TRANSITIONS",
    "DedupKey",
    "build_dedup_key",
    "AttestationEnvelope",
    "SoftFinalityCache",
    "CacheEntry",
    "A01Awacs",
    "A02FastpathHunter",
    "FastPathInterceptor",
    "A03SoftFinalityVerifier",
    "SoftFinalityEngine",
    "CASConflictError",
    "CASCoordinator",
    "CASRequest",
    "CASSlotOp",
    "CASResult",
    "CASStatus",
    "CASBomber",
    "BurstReport",
    "CPUBackend",
    "GPUBurstBackend",
    "AirspaceWatch",
    "PoisonKind",
    "WatchAlert",
]
