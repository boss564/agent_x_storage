"""NATS bridge — Gateway ↔ risk prefilter (Queue-Group only).

Subject: edge.gateway.prefilter.request
Queue:   queue.edge.gateway.prefilter.request

Emits prefilter_score only. Broadcast forbidden. No gate signing.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from plugins.risk_prefilter.scorer import score_features

NATS_URL = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")
SUBJECT = "edge.gateway.prefilter.request"
QUEUE = "queue.edge.gateway.prefilter.request"
MODEL_PATH = os.environ.get(
    "PREFILTER_MODEL_PATH",
    str(Path("models/prefilter/prefilter_gbt.pkl")),
)
SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"


def forbid_broadcast(subject: str) -> None:
    s = subject.lower()
    if "broadcast" in s or subject.endswith(".>"):
        raise ValueError(f"broadcast/wildcard control plane forbidden: {subject}")


async def handle_job(body: Dict[str, Any]) -> Dict[str, Any]:
    body = dict(body)
    for key in (
        "gate_verdict",
        "audit_verdict",
        "envelope_id",
        "egress_seal",
        "certificate_id",
    ):
        body.pop(key, None)
    features = body.get("features") if isinstance(body.get("features"), dict) else body
    out = score_features(features, model_path=MODEL_PATH)
    out["via"] = "nats_queue_group"
    out["subject"] = SUBJECT
    return out


async def serve_worker(
    *,
    nats_url: str = NATS_URL,
    stop: Optional[asyncio.Event] = None,
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
        out = await handle_job(body)
        if msg.reply:
            await nc.publish(msg.reply, json.dumps(out, sort_keys=True).encode())

    sub = await nc.subscribe(SUBJECT, queue=QUEUE, cb=_cb)
    if stop is None:
        stop = asyncio.Event()
    await stop.wait()
    await sub.unsubscribe()
    await nc.drain()


def run_nats_roundtrip(
    features: Dict[str, float],
    *,
    nats_url: str = NATS_URL,
    timeout: float = 3.0,
) -> Dict[str, Any]:
    async def _run() -> Dict[str, Any]:
        stop = asyncio.Event()
        worker = asyncio.create_task(serve_worker(nats_url=nats_url, stop=stop))
        await asyncio.sleep(0.15)
        from nats.aio.client import Client as NATS

        nc = NATS()
        await nc.connect(servers=[nats_url], connect_timeout=2)
        try:
            raw = json.dumps({"features": features, "live_execution": False}, sort_keys=True).encode()
            msg = await nc.request(SUBJECT, raw, timeout=timeout)
            return json.loads(msg.data.decode())
        finally:
            await nc.drain()
            stop.set()
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass

    return asyncio.run(_run())


if __name__ == "__main__":
    asyncio.run(serve_worker())
