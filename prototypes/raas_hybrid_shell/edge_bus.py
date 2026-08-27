"""Stage-1 EdgeBus — NATS Queue-Group adapter (no broadcast).

Gate 0: QUEUEGROUP_RING_PASS — only queue-group subjects allowed.
This module does NOT replace TrustedCoreGateway by default; it is the
first kernel-adjacent hop (pilot edge P1→P2).

Charter: DEFENSIVE_CAUSAL_GROUNDING · live_execution=false
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

NATS_URL = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")
SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"

Handler = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]


def edge_subject(src: str, dst: str) -> str:
    return f"edge.{src}.{dst}"


def edge_queue(src: str, dst: str) -> str:
    """Queue-Group name — mandatory for Stage-1 delivery."""
    return f"queue.edge.{src}.{dst}"


def forbid_broadcast(subject: str) -> None:
    s = subject.lower()
    if "broadcast" in s or subject.endswith(".>"):  # wildcard fan-out control
        raise ValueError(f"broadcast/wildcard control plane forbidden: {subject}")


@dataclass
class EdgeHopResult:
    src: str
    dst: str
    request_hash: str
    response: Dict[str, Any]
    via: str = "nats_queue_group"


class EdgeBus:
    """Minimal request/reply over one edge with Queue-Group semantics."""

    def __init__(self, nats_url: str = NATS_URL) -> None:
        self.nats_url = nats_url
        self._nc: Any = None

    async def connect(self) -> None:
        from nats.aio.client import Client as NATS

        self._nc = NATS()
        await self._nc.connect(servers=[self.nats_url], connect_timeout=2)

    async def close(self) -> None:
        if self._nc is not None:
            await self._nc.drain()
            self._nc = None

    async def serve_edge(
        self,
        src: str,
        dst: str,
        handler: Handler,
        *,
        stop: Optional[asyncio.Event] = None,
    ) -> None:
        """Worker: Queue-Group subscriber on edge.src.dst (1-of-N)."""
        if self._nc is None:
            await self.connect()
        subject = edge_subject(src, dst)
        queue = edge_queue(src, dst)
        forbid_broadcast(subject)

        async def _cb(msg: Any) -> None:
            try:
                body = json.loads(msg.data.decode())
            except Exception:
                body = {}
            # Never accept decision fields from the wire into gate space
            body.pop("gate_verdict", None)
            body.pop("audit_verdict", None)
            out = await handler(body)
            out.setdefault("scope", SCOPE)
            out.setdefault("live_execution", False)
            if msg.reply:
                await self._nc.publish(msg.reply, json.dumps(out, sort_keys=True).encode())

        sub = await self._nc.subscribe(subject, queue=queue, cb=_cb)
        if stop is None:
            stop = asyncio.Event()
        await stop.wait()
        await sub.unsubscribe()

    async def request_edge(
        self,
        src: str,
        dst: str,
        payload: Dict[str, Any],
        *,
        timeout: float = 2.0,
    ) -> EdgeHopResult:
        if self._nc is None:
            await self.connect()
        subject = edge_subject(src, dst)
        forbid_broadcast(subject)
        material = dict(payload)
        material["live_execution"] = False
        material["scope"] = SCOPE
        raw = json.dumps(material, sort_keys=True, default=str).encode()
        req_hash = hashlib.sha256(raw).hexdigest()
        msg = await self._nc.request(subject, raw, timeout=timeout)
        resp = json.loads(msg.data.decode())
        return EdgeHopResult(
            src=src,
            dst=dst,
            request_hash=req_hash,
            response=resp,
        )


async def pilot_p1_p2_echo(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic pilot handler for edge P1→P2 (no execution)."""
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return {
        "hop": "P1->P2",
        "echo_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "keys": sorted(payload.keys()),
        "scope": SCOPE,
        "live_execution": False,
        "note": "stage1_pilot_echo",
    }


def run_pilot_roundtrip(
    payload: Dict[str, Any],
    *,
    nats_url: str = NATS_URL,
    timeout: float = 2.0,
) -> Dict[str, Any]:
    """Sync helper: spawn P1→P2 worker, request once, tear down."""

    async def _run() -> Dict[str, Any]:
        bus_w = EdgeBus(nats_url)
        bus_c = EdgeBus(nats_url)
        stop = asyncio.Event()
        await bus_w.connect()
        await bus_c.connect()
        worker = asyncio.create_task(
            bus_w.serve_edge("P1", "P2", pilot_p1_p2_echo, stop=stop)
        )
        await asyncio.sleep(0.1)
        try:
            hop = await bus_c.request_edge("P1", "P2", payload, timeout=timeout)
            return {
                "request_hash": hop.request_hash,
                "response": hop.response,
                "src": hop.src,
                "dst": hop.dst,
                "via": hop.via,
            }
        finally:
            stop.set()
            await asyncio.sleep(0.05)
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass
            await bus_c.close()
            await bus_w.close()

    return asyncio.run(_run())
