"""Air Interceptor — A01–A09 dual air-superiority layer.

Commit 1 covers Schwarm 1 (Air Superiority): A01 AWACS (mode decision),
A02 Fast-Path Jäger (speculative soft-finality), A03 Soft-Finality Verifikator.
Schwarm 2 (A04–A06 CAS) and Schwarm 3 (A07–A09 Logistics) follow next.
"""

from .base import (
    AirAction,
    AirInterceptResult,
    SoftFinalityGuarantee,
    AirInterceptorAgent,
    AirCoordinator,
)
from .a01_awacs import A01Awacs
from .a02_fastpath import A02FastpathHunter
from .a03_soft_finality import A03SoftFinalityVerifier

__all__ = [
    "AirAction",
    "AirInterceptResult",
    "SoftFinalityGuarantee",
    "AirInterceptorAgent",
    "AirCoordinator",
    "A01Awacs",
    "A02FastpathHunter",
    "A03SoftFinalityVerifier",
]
