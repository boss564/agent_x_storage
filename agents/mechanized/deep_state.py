#!/usr/bin/env python3
"""Deep-state coupling — Panzergrenadier → Diver request/reply.

During a dismounted fight, P01–P09 may need verified state from the
D01–D08 darkpool enclaves (nullifier status, shard history, cross-chain
locks). Uses NATS Request-Reply with a hard 2ms SLA timeout; on timeout,
falls back to local reconstruction.

Subject: agentx.deep.state.query.<shard_id>
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional

from .metrics import REGISTRY

logger = logging.getLogger("Panzergrenadier-DeepState")

DEEP_STATE_TIMEOUT_S = 0.002  # 2ms hard SLA


async def fetch_deep_state_proof(
    nats_client,
    account_id: str,
    shard_id: int,
    request_type: str = "NULLIFIER_CHECK",
) -> Optional[Dict[str, Any]]:
    """Fetch deep state evidence from a D-shard during dismounted execution.

    Returns the parsed state proof, or None on timeout (caller falls back
    to local reconstruction).
    """
    subject = f"agentx.deep.state.query.{shard_id}"
    payload = json.dumps({
        "account_id": account_id,
        "request_type": request_type,
    }).encode()

    t0 = time.time()
    try:
        msg = await nats_client.request(subject, payload, timeout=DEEP_STATE_TIMEOUT_S)
        elapsed_ms = (time.time() - t0) * 1000
        REGISTRY.agent(f"D{shard_id:02d}").record_deep_state_query(elapsed_ms)
        return json.loads(msg.data.decode())
    except asyncio.TimeoutError:
        logger.error(
            "❌ State-Query Timeout an Shard %d! Fallback auf lokale Rekonstruktion.",
            shard_id,
        )
        return None
    except Exception as e:
        logger.error("State-Query Fehler (Shard %d): %s", shard_id, e)
        return None


async def fetch_nullifier_status(nats_client, account_id: str, shard_id: int) -> bool:
    """Convenience: check whether a nullifier is spent on a given shard."""
    proof = await fetch_deep_state_proof(
        nats_client, account_id, shard_id, request_type="NULLIFIER_CHECK"
    )
    if proof is None:
        return False  # timeout → conservative: assume not spent (will re-check)
    return bool(proof.get("spent", False))
