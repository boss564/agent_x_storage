#!/usr/bin/env python3
"""A03 Soft-Finality Verifikator — verifies the speculative guarantee against state."""

from typing import Any, Dict

from .base import AirInterceptorAgent, SoftFinalityGuarantee


class A03SoftFinalityVerifier(AirInterceptorAgent):
    """Checks soft-finality guarantees against the current state-root cache."""

    def __init__(self):
        super().__init__("A03")
        self._state_root_cache: Dict[str, str] = {}

    def verify(self, guarantee: SoftFinalityGuarantee, state_root: str) -> bool:
        """Reject a guarantee that contradicts the cached or current state root."""
        cached = self._state_root_cache.get(guarantee.event_id)
        if cached is not None and cached != guarantee.state_root:
            return False
        ok = guarantee.verify(state_root)
        if ok:
            self._state_root_cache[guarantee.event_id] = guarantee.state_root
        self.intercept_count += 1
        return ok

    def stats(self) -> Dict[str, Any]:
        return {**super().stats(), "cached_roots": len(self._state_root_cache)}
