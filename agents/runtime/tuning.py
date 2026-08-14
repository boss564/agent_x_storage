#!/usr/bin/env python3
"""Performance Tuning — high-throughput runtime optimizations.

- uvloop (C-based event loop) when available
- TCP_NODELAY guidance for NATS connections
- BurstGarbageCollector: disable GC during burst phases to avoid
  stop-the-world pauses, re-enable + gen0 collect on exit.
"""

import gc
import logging
import socket

logger = logging.getLogger("PerformanceTuning")


def apply_high_throughput_tuning() -> None:
    """Install uvloop and set socket defaults for low-latency I/O."""
    try:
        import uvloop
        uvloop.install()
        logger.info("🚀 uvloop als Standard-Event-Loop registriert.")
    except ImportError:
        logger.warning("⚠️ uvloop nicht verfügbar — Fallback auf Standard-asyncio.")

    # NOTE: TCP_NODELAY is a per-socket option, not a global default.
    # NATS clients set it per-connection; this default timeout is a
    # coarse guard against indefinite blocking sockets.
    socket.setdefaulttimeout(2.0)
    logger.info("⚡ Socket-Defaults gesetzt (TCP_NODELAY wird pro Connection gesetzt).")


class BurstGarbageCollector:
    """Context manager: disable GC during a burst, collect gen0 on exit."""

    def __enter__(self):
        gc.disable()

    def __exit__(self, exc_type, exc_val, exc_tb):
        gc.enable()
        gc.collect(generation=0)
