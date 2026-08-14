#!/usr/bin/env python3
"""Feature Flags — live-parameter control via NATS JetStream KV (optional).

Runtime toggles without container restart. Falls back to local defaults
when NATS KV is unavailable, so the system never hard-depends on it.

Flags:
  ENABLE_DISMOUNT          — allow the infantry layer to dismount
  STRICT_2MS_SLA           — enforce the 2ms deep-state SLA
  MAX_CONSTRAINT_BUDGET    — dismount trigger threshold
  FORCE_CUDA_FAILOVER      — force GPU backend
  WARMUP_PING_INTERVAL_SEC — D01 enclave warm-up cadence
"""

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("FeatureFlags")

DEFAULT_FLAGS: Dict[str, Any] = {
    "ENABLE_DISMOUNT": True,
    "STRICT_2MS_SLA": True,
    "MAX_CONSTRAINT_BUDGET": 10000,
    "FORCE_CUDA_FAILOVER": False,
    "WARMUP_PING_INTERVAL_SEC": 5.0,
}


class FeatureFlagManager:
    """Loads flags from NATS KV (if present), otherwise uses local defaults."""

    def __init__(self, kv_bucket=None):
        self.kv = kv_bucket  # Optional nats.js.kv.KeyValue
        self._cache = dict(DEFAULT_FLAGS)

    async def sync_flags(self) -> None:
        if self.kv is None:
            return
        for key in DEFAULT_FLAGS:
            try:
                entry = await self.kv.get(key)
                if entry and entry.value:
                    self._cache[key] = json.loads(entry.value.decode())
            except Exception:
                pass  # KV miss → keep local cache

    def get(self, flag_name: str) -> Any:
        return self._cache.get(flag_name, DEFAULT_FLAGS.get(flag_name))

    async def set_flag(self, flag_name: str, value: Any) -> None:
        self._cache[flag_name] = value
        if self.kv is not None:
            try:
                await self.kv.put(flag_name, json.dumps(value).encode())
            except Exception as e:
                logger.warning("Flag persist failed (KV): %s", e)
        logger.info("🚩 FeatureFlag %s = %s", flag_name, value)

    def snapshot(self) -> Dict[str, Any]:
        return dict(self._cache)
