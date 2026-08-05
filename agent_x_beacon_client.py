"""
Agent X — Beacon-Node-Client.

Async-first REST/SSE-Client für Ethereum Beacon-Node (Lighthouse/Prysm/Nimbus).
Bietet synchrone und asynchrone Zugriffe auf die Beacon-API v1.

Endpunkte:
  - GET  /eth/v1/events?topics=...        SSE-Stream (block, attestation, chain_reorg)
  - GET  /eth/v1/beacon/states/head/validators  Validator-Queue-Daten
  - GET  /eth/v1/beacon/states/head/finality_checkpoints
  - GET  /eth/v1/node/syncing                  Sync-Status
  - GET  /eth/v1/beacon/states/head/epoch      Aktuelle Epoche
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

logger = logging.getLogger("beacon_client")

# ─── Konfiguration ───────────────────────────────────────────────────

BEACON_NODE_URL = os.getenv("BEACON_NODE_URL", "http://localhost:5052")
BEACON_TIMEOUT = int(os.getenv("BEACON_TIMEOUT", "30"))
BEACON_RETRIES = int(os.getenv("BEACON_RETRIES", "3"))
BEACON_RETRY_BACKOFF = float(os.getenv("BEACON_RETRY_BACKOFF", "1.5"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_unix() -> float:
    return datetime.now(timezone.utc).timestamp()


# ─── HTTP-Utilities (sync + async) ───────────────────────────────────

def _http_get_sync(endpoint: str, timeout: int = BEACON_TIMEOUT) -> dict:
    """Synchroner GET via urllib — Fallback wenn aiohttp nicht verfügbar."""
    import urllib.request
    import urllib.error

    url = f"{BEACON_NODE_URL}{endpoint}"
    last_err = None
    for attempt in range(1, BEACON_RETRIES + 1):
        try:
            req = urllib.request.Request(url)
            req.add_header("Accept", "application/json")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.URLError as e:
            last_err = e
            backoff = BEACON_RETRY_BACKOFF ** attempt
            logger.warning("Beacon GET %s (Versuch %d/%d): %s — retry in %.1fs",
                           endpoint, attempt, BEACON_RETRIES, e, backoff)
            if attempt < BEACON_RETRIES:
                import time
                time.sleep(backoff)

    raise ConnectionError(f"Beacon-Node nicht erreichbar nach {BEACON_RETRIES} Versuchen: {last_err}")


async def _http_get_async(endpoint: str, timeout: int = BEACON_TIMEOUT) -> dict:
    """Async GET via aiohttp."""
    try:
        import aiohttp
    except ImportError:
        logger.warning("aiohttp nicht installiert — fallback auf sync GET")
        return _http_get_sync(endpoint, timeout)

    url = f"{BEACON_NODE_URL}{endpoint}"
    last_err = None
    for attempt in range(1, BEACON_RETRIES + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=timeout) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        raise ConnectionError(f"HTTP {resp.status}: {await resp.text()}")
        except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError) as e:
            last_err = e
            backoff = BEACON_RETRY_BACKOFF ** attempt
            logger.warning("Beacon GET %s (Versuch %d/%d): %s — retry in %.1fs",
                           endpoint, attempt, BEACON_RETRIES, e, backoff)
            if attempt < BEACON_RETRIES:
                await asyncio.sleep(backoff)

    raise ConnectionError(f"Beacon-Node nicht erreichbar nach {BEACON_RETRIES} Versuchen: {last_err}")


# ─── SSE-Stream ──────────────────────────────────────────────────────

async def sse_stream(
    topics: list[str],
    max_events: int = 0,
    timeout: int = BEACON_TIMEOUT,
) -> AsyncIterator[dict]:
    """Async-Generator für Beacon-Node SSE-Events.

    Args:
        topics: Event-Typen (block, attestation, chain_reorg, finalized_checkpoint)
        max_events: 0 = unbegrenzt, >0 = nach N Events stoppen
        timeout: HTTP-Timeout pro Verbindung

    Yields:
        Events als Dicts mit {'event': typ, 'data': {...}}
    """
    topic_str = "&topics=".join([""] + topics)
    endpoint = f"/eth/v1/events{topic_str}"
    url = f"{BEACON_NODE_URL}{endpoint}"

    try:
        import aiohttp
    except ImportError:
        logger.error("aiohttp erforderlich für SSE-Stream")
        return

    count = 0
    for attempt in range(1, BEACON_RETRIES + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=timeout) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise ConnectionError(f"HTTP {resp.status}: {body}")

                    # SSE-Parsing: Zeilenweise lesen
                    current_event = ""
                    current_data = ""
                    async for line_bytes in resp.content:
                        line = line_bytes.decode("utf-8").strip()
                        if not line:
                            # Leerzeile = Event-Ende
                            if current_data:
                                try:
                                    parsed = json.loads(current_data)
                                except json.JSONDecodeError:
                                    parsed = {"raw": current_data}
                                yield {
                                    "event": current_event or "unknown",
                                    "data": parsed,
                                    "received_at": _now_iso(),
                                }
                                count += 1
                                if max_events > 0 and count >= max_events:
                                    logger.info("SSE: %d Events erreicht", max_events)
                                    return
                            current_event = ""
                            current_data = ""
                        elif line.startswith("event:"):
                            current_event = line[6:].strip()
                        elif line.startswith("data:"):
                            current_data = line[5:].strip()
                        # Andere Felder ignorieren (id:, retry:)

        except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError) as e:
            backoff = BEACON_RETRY_BACKOFF ** attempt
            logger.warning("SSE-Stream abgebrochen (Versuch %d/%d): %s — reconnect in %.1fs",
                           attempt, BEACON_RETRIES, e, backoff)
            if attempt < BEACON_RETRIES:
                await asyncio.sleep(backoff)
            else:
                raise ConnectionError(f"SSE-Stream endgültig fehlgeschlagen: {e}")


# ═══════════════════════════════════════════════════════════════════════
# Spezialisierte API-Aufrufe (sync + async)
# ═══════════════════════════════════════════════════════════════════════

# ─── Validator-Daten (Exit-Queue, Activation-Queue, Churn) ──────────

def get_validator_queue_data_sync() -> dict:
    """Liest Validator-Stats vom Beacon-Node (sync).

    Returns:
        {
            "exit_queue_length": N,
            "activation_queue_length": N,
            "churn_limit": 8,
            "active_validators": N,
            "current_epoch": N,
            "total_validators": N,
        }
    """
    try:
        # Head-State abfragen (liefert alle Validatoren — im Produktivbetrieb
        # mit pagination oder Filter für grosse Validator-Sets)
        head = _http_get_sync("/eth/v1/beacon/states/head/validators")
        data_list = head.get("data", [])

        # Queue-Status aus Validator-Status ableiten
        exit_queue = sum(1 for v in data_list
                         if v.get("status") == "active_exiting")
        activation_queue = sum(1 for v in data_list
                               if v.get("status") == "pending_queued")
        active = sum(1 for v in data_list
                     if v.get("status") in ("active_ongoing", "active_exiting"))

        # Finality-Checkpoint für aktuelle Epoche
        finality = _http_get_sync("/eth/v1/beacon/states/head/finality_checkpoints")
        current_epoch = int(finality.get("data", {}).get("finalized", {}).get("epoch", 0))

        return {
            "exit_queue_length": exit_queue,
            "activation_queue_length": activation_queue,
            "churn_limit": 8,  # fest im Protokoll bis Electra
            "active_validators": active,
            "total_validators": len(data_list),
            "current_epoch": current_epoch,
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("get_validator_queue_data: %s", e)
        return {
            "exit_queue_length": 0,
            "activation_queue_length": 0,
            "churn_limit": 8,
            "active_validators": 0,
            "current_epoch": 0,
            "error": str(e),
        }


async def get_validator_queue_data_async() -> dict:
    """Async-Variante von get_validator_queue_data."""
    try:
        head = await _http_get_async("/eth/v1/beacon/states/head/validators")
        data_list = head.get("data", [])

        exit_queue = sum(1 for v in data_list if v.get("status") == "active_exiting")
        activation_queue = sum(1 for v in data_list if v.get("status") == "pending_queued")
        active = sum(1 for v in data_list if v.get("status") in ("active_ongoing", "active_exiting"))

        finality = await _http_get_async("/eth/v1/beacon/states/head/finality_checkpoints")
        current_epoch = int(finality.get("data", {}).get("finalized", {}).get("epoch", 0))

        return {
            "exit_queue_length": exit_queue,
            "activation_queue_length": activation_queue,
            "churn_limit": 8,
            "active_validators": active,
            "total_validators": len(data_list),
            "current_epoch": current_epoch,
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("get_validator_queue_data_async: %s", e)
        return {"exit_queue_length": 0, "activation_queue_length": 0,
                "churn_limit": 8, "active_validators": 0, "error": str(e)}


# ─── Sync-Status ─────────────────────────────────────────────────────

def get_sync_status_sync() -> dict:
    """Prüft, ob der Beacon-Node synchronisiert ist."""
    try:
        data = _http_get_sync("/eth/v1/node/syncing")
        status = data.get("data", {})
        return {
            "syncing": status.get("is_syncing", False),
            "head_slot": int(status.get("head_slot", 0)),
            "sync_distance": int(status.get("sync_distance", 0)),
            "timestamp": _now_iso(),
        }
    except Exception as e:
        return {"syncing": None, "error": str(e), "timestamp": _now_iso()}


# ─── Aktuelle Epoche ─────────────────────────────────────────────────

def get_current_epoch_sync() -> int:
    """Gibt aktuelle Epochen-Nummer zurück."""
    try:
        epoch_data = _http_get_sync("/eth/v1/beacon/states/head/epoch")
        return int(epoch_data.get("data", 0))
    except Exception:
        return 0


# ─── Batch-Sammlung ──────────────────────────────────────────────────

async def collect_events_batch(
    topics: list[str],
    max_events: int = 100,
) -> list[dict]:
    """Sammelt Events als Batch (nicht streamend) — nützlich für Polling.

    Wartet bis max_events erreicht oder Timeout.
    """
    events = []
    try:
        async for event in sse_stream(topics, max_events=max_events):
            events.append(event)
    except ConnectionError as e:
        logger.error("Batch-Sammlung abgebrochen: %s", e)
    return events


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "status":
        sync = get_sync_status_sync()
        print(json.dumps(sync, indent=2))
    elif cmd == "validators":
        data = get_validator_queue_data_sync()
        print(json.dumps(data, indent=2))
    elif cmd == "epoch":
        print(f"Aktuelle Epoche: {get_current_epoch_sync()}")
    elif cmd == "stream":
        async def _demo():
            count = 0
            async for ev in sse_stream(["block", "chain_reorg"], max_events=5):
                print(json.dumps(ev["data"], indent=2))
                count += 1
            print(f"--- {count} Events empfangen ---")
        asyncio.run(_demo())
    else:
        print(f"Verwendung: {sys.argv[0]} [status|validators|epoch|stream]")
