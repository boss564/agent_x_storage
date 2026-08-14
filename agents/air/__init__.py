"""Air Interceptor — A01–A09 dual air-superiority layer.

Commit 1 covers Schwarm 1 (Air Superiority): A01 AWACS (mode decision),
A02 Fast-Path Jäger (speculative attestation), A03 Soft-Finality Verifikator
(finality state machine + versioned cache). Commit 1.5 adds the refined
SoftFinalityEngine + FastPathInterceptor on a DedupKey-based contract.
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
]
