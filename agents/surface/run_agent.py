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


def _to_prometheus_text(d: dict) -> str:
    """Flatten a (possibly nested) metrics dict into Prometheus text format."""
    out = []

    def walk(obj, path):
        if isinstance(obj, dict):
            for k, v in obj.items():
                walk(v, path + [str(k)])
        elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
            out.append(f"{'_'.join(path)} {obj}")

    walk(d, [])
    return "\n".join(out) + ("\n" if out else "")


def start_metrics_server(port: int, get_status) -> None:
    """Serve /metrics — Prometheus text (default) or JSON (?format=json)."""
    import json as _json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import urlparse, parse_qs

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path.rstrip("/") in ("/metrics", ""):
                if parse_qs(parsed.query).get("format", [""])[0] == "json":
                    body = _json.dumps(get_status()).encode()
                    ctype = "application/json"
                else:
                    body = _to_prometheus_text(get_status()).encode()
                    ctype = "text/plain; version=0.0.4"
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()


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

    # Dependency-free /metrics endpoint (stdlib http.server, daemon thread)
    start_metrics_server(8080, handler.status)
    logger.info("📊 Metrics endpoint on :8080/metrics")

    await handler.run_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 %s shutting down", resolve_agent_id())
        sys.exit(0)
