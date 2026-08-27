"""Stage-1 EdgeBus — NATS Queue-Group adapter (no broadcast).

Gate 0: QUEUEGROUP_RING_PASS — only queue-group subjects allowed.
Does NOT replace TrustedCoreGateway by default. Stage-1 migrates ring
edges P1→…→P9→P1 via request/reply under a sequential orchestrator.

Charter: DEFENSIVE_CAUSAL_GROUNDING · live_execution=false
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple

NATS_URL = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")
SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"

# Sparse ring (⟨k⟩=1): P1→P2→…→P9→P1 — one subject + queue-group per edge
RING_NODES: Tuple[str, ...] = tuple(f"P{i}" for i in range(1, 10))
RING_EDGES: Tuple[Tuple[str, str], ...] = tuple(
    (RING_NODES[i], RING_NODES[(i + 1) % len(RING_NODES)])
    for i in range(len(RING_NODES))
)

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


@dataclass
class RingRunResult:
    hops: List[EdgeHopResult] = field(default_factory=list)
    chain_sha256: str = ""
    edges: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edges": list(self.edges),
            "chain_sha256": self.chain_sha256,
            "hop_count": len(self.hops),
            "hops": [
                {
                    "src": h.src,
                    "dst": h.dst,
                    "request_hash": h.request_hash,
                    "response": h.response,
                    "via": h.via,
                }
                for h in self.hops
            ],
            "via": "nats_queue_group_sequential",
            "scope": SCOPE,
            "live_execution": False,
        }


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


def make_echo_handler(src: str, dst: str) -> Handler:
    """Deterministic per-edge echo (no execution, no role remap)."""

    async def _handler(payload: Dict[str, Any]) -> Dict[str, Any]:
        canonical = json.dumps(payload, sort_keys=True, default=str)
        return {
            "hop": f"{src}->{dst}",
            "echo_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
            "keys": sorted(payload.keys()),
            "scope": SCOPE,
            "live_execution": False,
            "note": "stage1_edge_echo",
        }

    return _handler


async def pilot_p1_p2_echo(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Backward-compatible alias for edge P1→P2."""
    return await make_echo_handler("P1", "P2")(payload)


class RingOrchestrator:
    """Sequential publisher: wait for each edge reply before the next hop.

    Prevents reordering non-determinism. Does not fan-out or broadcast.
    """

    def __init__(
        self,
        bus: EdgeBus,
        *,
        edges: Sequence[Tuple[str, str]] = RING_EDGES,
        timeout: float = 2.0,
    ) -> None:
        self.bus = bus
        self.edges = list(edges)
        self.timeout = timeout

    async def run(self, payload: Dict[str, Any]) -> RingRunResult:
        carry: Dict[str, Any] = dict(payload)
        carry["live_execution"] = False
        carry["scope"] = SCOPE
        hops: List[EdgeHopResult] = []
        edge_labels: List[str] = []

        for src, dst in self.edges:
            hop = await self.bus.request_edge(
                src, dst, carry, timeout=self.timeout
            )
            hops.append(hop)
            edge_labels.append(f"{src}->{dst}")
            # Fixed sequence: next edge sees prior hop digest only (deterministic)
            carry = {
                **payload,
                "prior_hop": hop.response.get("hop"),
                "prior_echo_sha256": hop.response.get("echo_sha256"),
                "hop_index": len(hops),
                "live_execution": False,
                "scope": SCOPE,
            }

        chain_material = [
            {
                "edge": f"{h.src}->{h.dst}",
                "request_hash": h.request_hash,
                "echo_sha256": h.response.get("echo_sha256"),
            }
            for h in hops
        ]
        chain_raw = json.dumps(chain_material, sort_keys=True).encode()
        return RingRunResult(
            hops=hops,
            chain_sha256=hashlib.sha256(chain_raw).hexdigest(),
            edges=edge_labels,
        )


async def _cancel_tasks(tasks: Sequence[asyncio.Task]) -> None:
    for t in tasks:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass


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
            bus_w.serve_edge("P1", "P2", make_echo_handler("P1", "P2"), stop=stop)
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
            await _cancel_tasks([worker])
            await bus_c.close()
            await bus_w.close()

    return asyncio.run(_run())


def run_ring_roundtrip(
    payload: Dict[str, Any],
    *,
    nats_url: str = NATS_URL,
    timeout: float = 2.0,
    edges: Sequence[Tuple[str, str]] = RING_EDGES,
) -> Dict[str, Any]:
    """Sync helper: serve all ring edges, orchestrate sequential hops, tear down."""

    async def _run() -> Dict[str, Any]:
        stop = asyncio.Event()
        workers_buses: List[EdgeBus] = []
        worker_tasks: List[asyncio.Task] = []
        for src, dst in edges:
            bus_w = EdgeBus(nats_url)
            await bus_w.connect()
            workers_buses.append(bus_w)
            worker_tasks.append(
                asyncio.create_task(
                    bus_w.serve_edge(
                        src, dst, make_echo_handler(src, dst), stop=stop
                    )
                )
            )
        await asyncio.sleep(0.15)
        bus_c = EdgeBus(nats_url)
        await bus_c.connect()
        try:
            orch = RingOrchestrator(bus_c, edges=edges, timeout=timeout)
            result = await orch.run(payload)
            return result.to_dict()
        finally:
            stop.set()
            await asyncio.sleep(0.05)
            await _cancel_tasks(worker_tasks)
            await bus_c.close()
            for b in workers_buses:
                await b.close()

    return asyncio.run(_run())
