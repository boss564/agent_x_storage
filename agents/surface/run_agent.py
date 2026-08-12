#!/usr/bin/env python3
"""C01–C09 Surface Agent Entrypoint.

Reads AGENT_ID from environment (set by Docker Compose via HOSTNAME
or explicitly). Connects to NATS, subscribes to the surface event
stream, and processes at 1000 TPS with < 2ms latency.

Usage:
  AGENT_ID=C01 NATS_URL=nats://nats:4222 python -m agents.surface.run_agent
"""

import asyncio
import logging
import os
import re
import sys

from .handler import SurfaceHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("run_agent")

AGENT_CONFIGS = {
    "C01": "appchain-eu",
    "C02": "appchain-us",
    "C03": "appchain-asia",
    "C04": "appchain-latam",
    "C05": "appchain-africa",
    "C06": "appchain-ocean",
    "C07": "appchain-polar",
    "C08": "appchain-desert",
    "C09": "appchain-moon",
}


def resolve_agent_id() -> str:
    """Resolve AGENT_ID from env or hostname (Docker sets hostname=surface-agent-N)."""
    agent_id = os.getenv("AGENT_ID", "")
    if agent_id:
        return agent_id

    hostname = os.getenv("HOSTNAME", "")
    match = re.search(r"(\d+)$", hostname)
    if match:
        idx = int(match.group(1))
        if 1 <= idx <= 9:
            return f"C{idx:02d}"
    return "C01"


async def main():
    agent_id = resolve_agent_id()
    chain_id = AGENT_CONFIGS.get(agent_id, "appchain-default")
    nats_url = os.getenv("NATS_URL", "nats://localhost:4222")

    zk_rate = float(os.getenv("ZK_TRIGGER_RATE", "0.0"))
    handler = SurfaceHandler(
        agent_id=agent_id,
        chain_id=chain_id,
        nats_url=nats_url,
        zk_trigger_rate=zk_rate,
    )

    # Lightweight HTTP metrics endpoint — aiohttp installation:
    # Add 'aiohttp' to agents/surface/Dockerfile for production metrics
    try:
        from aiohttp import web
        async def metrics(request):
            return web.json_response(handler.status())
        app = web.Application()
        app.router.add_get("/metrics", metrics)
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", 8080).start()
        logger.info("📊 Metrics endpoint on :8080/metrics")
    except ImportError:
        logger.info("⚠️ aiohttp not installed — metrics skipped. Add to Dockerfile.")

    await handler.run_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 %s shutting down", resolve_agent_id())
        sys.exit(0)
