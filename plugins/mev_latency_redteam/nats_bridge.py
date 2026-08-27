"""NATS bridge — P2 ↔ Red-Team sandbox worker (Queue-Group only).

Subject: edge.P2.redteam.sandbox
Queue:   queue.edge.P2.redteam.sandbox

Broadcast forbidden. Request/reply; no gate signing.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, Optional

from plugins.mev_latency_redteam.scenario_runner import (
    initialize_scenario,
    report_scenario,
    run_attack_scenario,
)

NATS_URL = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")
SUBJECT = "edge.P2.redteam.sandbox"
QUEUE = "queue.edge.P2.redteam.sandbox"
SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"


def forbid_broadcast(subject: str) -> None:
    s = subject.lower()
    if "broadcast" in s or subject.endswith(".>"):
        raise ValueError(f"broadcast/wildcard control plane forbidden: {subject}")


async def handle_job(body: Dict[str, Any], *, repo_root: Optional[str] = None) -> Dict[str, Any]:
    """Process one scenario job; never emit decision fields."""
    body = dict(body)
    body.pop("gate_verdict", None)
    body.pop("audit_verdict", None)
    body.pop("envelope_id", None)
    body.pop("egress_seal", None)
    body.pop("certificate_id", None)

    kind = str(body.get("kind", "LATENCY_SPIKE"))
    scenario_id = str(body.get("scenario_id", "rt-nats"))
    seed = int(body.get("seed", 20260827))
    params = body.get("params") if isinstance(body.get("params"), dict) else {}

    state = initialize_scenario(
        kind, scenario_id=scenario_id, params=params, seed=seed
    )
    attack = run_attack_scenario(state)
    report = report_scenario(state, attack, repo_root=repo_root)
    return {
        "type": "attack_result",
        "attack": attack,
        "report": report,
        "via": "nats_queue_group",
        "subject": SUBJECT,
        "live_execution": False,
        "scope": SCOPE,
        "role": "RED_TEAM",
    }


async def serve_worker(
    *,
    nats_url: str = NATS_URL,
    stop: Optional[asyncio.Event] = None,
    repo_root: Optional[str] = None,
) -> None:
    from nats.aio.client import Client as NATS

    forbid_broadcast(SUBJECT)
    nc = NATS()
    await nc.connect(servers=[nats_url], connect_timeout=2)

    async def _cb(msg: Any) -> None:
        try:
            body = json.loads(msg.data.decode())
        except Exception:
            body = {}
        out = await handle_job(body, repo_root=repo_root)
        if msg.reply:
            await nc.publish(msg.reply, json.dumps(out, sort_keys=True).encode())

    sub = await nc.subscribe(SUBJECT, queue=QUEUE, cb=_cb)
    if stop is None:
        stop = asyncio.Event()
    await stop.wait()
    await sub.unsubscribe()
    await nc.drain()


async def request_scenario(
    payload: Dict[str, Any],
    *,
    nats_url: str = NATS_URL,
    timeout: float = 3.0,
) -> Dict[str, Any]:
    from nats.aio.client import Client as NATS

    forbid_broadcast(SUBJECT)
    nc = NATS()
    await nc.connect(servers=[nats_url], connect_timeout=2)
    try:
        material = dict(payload)
        material["live_execution"] = False
        material["scope"] = SCOPE
        raw = json.dumps(material, sort_keys=True).encode()
        msg = await nc.request(SUBJECT, raw, timeout=timeout)
        return json.loads(msg.data.decode())
    finally:
        await nc.drain()


def run_nats_roundtrip(
    payload: Dict[str, Any],
    *,
    nats_url: str = NATS_URL,
    timeout: float = 3.0,
    repo_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Sync helper: start worker, request once, tear down."""

    async def _run() -> Dict[str, Any]:
        stop = asyncio.Event()
        worker = asyncio.create_task(
            serve_worker(nats_url=nats_url, stop=stop, repo_root=repo_root)
        )
        await asyncio.sleep(0.15)
        try:
            return await request_scenario(payload, nats_url=nats_url, timeout=timeout)
        finally:
            stop.set()
            await asyncio.sleep(0.05)
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass

    return asyncio.run(_run())


if __name__ == "__main__":
    asyncio.run(serve_worker())
