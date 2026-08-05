"""
Agent X — Solana-RPC-Client.

Async-first RPC-Client für Solana-Validatoren.
Nutzt solana-py/solders wo verfügbar, mit JSON-RPC-Fallback.

RPC-Methoden:
  - getLeaderSchedule          Leader-Schedule für bis zu 432k Slots
  - getSlot                    Aktueller Slot-Index
  - getBlock                   Block-Details (Transaktionen, Leader)
  - getEpochInfo               Epochen-Status (Slot-Index, Absolute Slot)
  - getBlockProduction         Block-Produktions-Statistiken
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("solana_client")

# ─── Konfiguration ───────────────────────────────────────────────────

SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "http://localhost:8899")
SOLANA_RPC_TIMEOUT = int(os.getenv("SOLANA_RPC_TIMEOUT", "30"))
SOLANA_RETRIES = int(os.getenv("SOLANA_RETRIES", "3"))
SOLANA_RETRY_BACKOFF = float(os.getenv("SOLANA_RETRY_BACKOFF", "1.2"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_unix() -> float:
    return datetime.now(timezone.utc).timestamp()


# ─── JSON-RPC-Core ───────────────────────────────────────────────────

def _rpc_call(method: str, params: list | None = None,
              timeout: int = SOLANA_RPC_TIMEOUT) -> dict:
    """Synchroner Solana JSON-RPC-Aufruf."""
    import urllib.request
    import urllib.error

    payload = {
        "jsonrpc": "2.0",
        "id": int(time.time() * 1000),
        "method": method,
        "params": params or [],
    }
    body = json.dumps(payload).encode()
    last_err = None

    for attempt in range(1, SOLANA_RETRIES + 1):
        try:
            req = urllib.request.Request(
                SOLANA_RPC_URL,
                data=body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode())
                if "error" in result:
                    raise ConnectionError(f"RPC-Error: {result['error']}")
                return result.get("result", {})
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = e
            backoff = SOLANA_RETRY_BACKOFF ** attempt
            logger.warning("Solana RPC %s (Versuch %d/%d): %s — retry in %.1fs",
                           method, attempt, SOLANA_RETRIES, e, backoff)
            if attempt < SOLANA_RETRIES:
                time.sleep(backoff)

    raise ConnectionError(f"Solana RPC nicht erreichbar nach {SOLANA_RETRIES} Versuchen: {last_err}")


async def _rpc_call_async(method: str, params: list | None = None,
                          timeout: int = SOLANA_RPC_TIMEOUT) -> dict:
    """Async Solana JSON-RPC-Aufruf."""
    try:
        import aiohttp
    except ImportError:
        return _rpc_call(method, params, timeout)

    payload = {
        "jsonrpc": "2.0",
        "id": int(time.time() * 1000),
        "method": method,
        "params": params or [],
    }
    last_err = None

    for attempt in range(1, SOLANA_RETRIES + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    SOLANA_RPC_URL, json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp:
                    result = await resp.json()
                    if "error" in result:
                        raise ConnectionError(f"RPC-Error: {result['error']}")
                    return result.get("result", {})
        except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError) as e:
            last_err = e
            backoff = SOLANA_RETRY_BACKOFF ** attempt
            logger.warning("Solana RPC %s (Versuch %d/%d): %s — retry in %.1fs",
                           method, attempt, SOLANA_RETRIES, e, backoff)
            if attempt < SOLANA_RETRIES:
                await asyncio.sleep(backoff)

    raise ConnectionError(f"Solana RPC nicht erreichbar nach {SOLANA_RETRIES} Versuchen: {last_err}")


# ═══════════════════════════════════════════════════════════════════════
# Core-API-Funktionen
# ═══════════════════════════════════════════════════════════════════════

# ─── Leader-Schedule ─────────────────────────────────────────────────

def get_leader_schedule_sync(
    slot: int | None = None,
    limit: int | None = None,
) -> dict:
    """Lädt den Leader-Schedule für die nächsten Slots.

    Args:
        slot: Start-Slot (None = aktuell)
        limit: Max Slots (None = alle verfügbaren)

    Returns:
        {"schedule": {slot: pubkey, ...}, "first_slot": N, "last_slot": N}
    """
    try:
        params = []
        if slot is not None:
            params.append(slot)
            if limit is not None:
                params.append(limit)
        elif limit is not None:
            params.append(None)  # Kein slot, aber limit
            params.append(limit)

        if params:
            data = _rpc_call("getLeaderSchedule", params)
        else:
            data = _rpc_call("getLeaderSchedule")

        if isinstance(data, dict):
            return {
                "schedule": data,
                "first_slot": min(int(k) for k in data.keys()) if data else 0,
                "last_slot": max(int(k) for k in data.keys()) if data else 0,
                "total_slots": len(data),
                "timestamp": _now_iso(),
            }
        return {"schedule": {}, "first_slot": 0, "last_slot": 0, "total_slots": 0,
                "raw": data, "timestamp": _now_iso()}
    except Exception as e:
        logger.error("get_leader_schedule: %s", e)
        return {"schedule": {}, "error": str(e), "timestamp": _now_iso()}


async def get_leader_schedule_async(
    slot: int | None = None,
    limit: int | None = None,
) -> dict:
    """Async-Variante."""
    try:
        params = []
        if slot is not None:
            params.append(slot)
            if limit is not None:
                params.append(limit)
        elif limit is not None:
            params.append(None)
            params.append(limit)

        data = await _rpc_call_async(
            "getLeaderSchedule", params if params else None,
        )
        if isinstance(data, dict):
            return {
                "schedule": data,
                "first_slot": min(int(k) for k in data.keys()) if data else 0,
                "last_slot": max(int(k) for k in data.keys()) if data else 0,
                "total_slots": len(data),
                "timestamp": _now_iso(),
            }
        return {"schedule": {}, "first_slot": 0, "last_slot": 0,
                "total_slots": 0, "raw": data}
    except Exception as e:
        logger.error("get_leader_schedule_async: %s", e)
        return {"schedule": {}, "error": str(e)}


# ─── Current Slot ────────────────────────────────────────────────────

def get_current_slot_sync() -> int:
    """Gibt aktuellen Slot-Index zurück."""
    try:
        return int(_rpc_call("getSlot"))
    except Exception:
        return 0


async def get_current_slot_async() -> int:
    """Async-Variante."""
    try:
        result = await _rpc_call_async("getSlot")
        return int(result)
    except Exception:
        return 0


# ─── Epoch Info ──────────────────────────────────────────────────────

def get_epoch_info_sync() -> dict:
    """Holt Epochen-Statusdaten."""
    try:
        data = _rpc_call("getEpochInfo")
        return {
            "absolute_slot": int(data.get("absoluteSlot", 0)),
            "block_height": int(data.get("blockHeight", 0)),
            "epoch": int(data.get("epoch", 0)),
            "slot_index": int(data.get("slotIndex", 0)),
            "slots_in_epoch": int(data.get("slotsInEpoch", 432000)),
            "transaction_count": int(data.get("transactionCount", 0)),
            "timestamp": _now_iso(),
        }
    except Exception as e:
        return {"error": str(e), "timestamp": _now_iso()}


# ─── Block Info ──────────────────────────────────────────────────────

def get_block_sync(slot: int) -> dict:
    """Holt Block-Daten für einen bestimmten Slot.

    Returns:
        {"slot": N, "leader": "pubkey", "tx_count": N, "blockhash": "...", ...}
    """
    try:
        data = _rpc_call("getBlock", [slot, {"maxSupportedTransactionVersion": 0}])
        if not data:
            return {"slot": slot, "empty": True, "skipped": True}
        txs = data.get("transactions", [])
        return {
            "slot": slot,
            "blockhash": data.get("blockhash", ""),
            "parent_slot": int(data.get("parentSlot", 0)),
            "transaction_count": len(txs),
            "block_time": data.get("blockTime"),
            "skipped": False,
            "timestamp": _now_iso(),
        }
    except Exception as e:
        return {"slot": slot, "error": str(e), "skipped": True}


# ─── Block Production Stats ──────────────────────────────────────────

def get_block_production_sync(
    first_slot: int | None = None,
    last_slot: int | None = None,
) -> dict:
    """Holt Block-Produktions-Statistiken für Slot-Range.

    Returns:
        {"byIdentity": {pubkey: [leader_slots, produced_slots]}, ...}
    """
    try:
        params = []
        if first_slot is not None:
            params.append(first_slot)
            if last_slot is not None:
                params.append(last_slot)

        data = _rpc_call("getBlockProduction", params if params else None)
        identity = data.get("value", {}).get("byIdentity", {})
        total_leader = 0
        total_produced = 0
        skipped_by_leader = {}

        for pubkey, counts in identity.items():
            leader_count = counts[0] if len(counts) > 0 else 0
            produced_count = counts[1] if len(counts) > 1 else 0
            skipped = leader_count - produced_count
            total_leader += leader_count
            total_produced += produced_count
            if skipped > 0:
                skipped_by_leader[pubkey] = skipped

        return {
            "total_leader_slots": total_leader,
            "total_blocks_produced": total_produced,
            "total_skipped": total_leader - total_produced,
            "skip_rate_pct": round(
                (1 - total_produced / total_leader) * 100, 2
            ) if total_leader else 0,
            "skipped_by_leader": skipped_by_leader,
            "unique_leaders": len(identity),
            "timestamp": _now_iso(),
        }
    except Exception as e:
        return {"error": str(e), "timestamp": _now_iso()}


# ─── Bulk-Fetch (Orchestrator) ───────────────────────────────────────

async def fetch_all_solana_data_async() -> dict:
    """Sammelt alle Solana-Daten parallel ein.

    Nutzt async RPC-Calls für minimale Latenz.
    """
    slot_task = get_current_slot_async()
    epoch_task = _rpc_call_async("getEpochInfo")

    slot, epoch_info = await asyncio.gather(slot_task, epoch_task)

    # Schedule und Production basieren auf dem aktuellen Slot
    schedule_task = get_leader_schedule_async(slot=slot)

    # Block-Production für die letzten 1024 Slots
    production_task = _rpc_call_async(
        "getBlockProduction",
        [{"identity": str(max(0, slot - 1024)), "range": {"firstSlot": max(0, slot - 1024), "lastSlot": slot}}],
    )

    schedule, production_raw = await asyncio.gather(schedule_task, production_task)

    # Production-Daten parsen
    identity = production_raw.get("value", {}).get("byIdentity", {})
    total_leader = 0
    total_produced = 0
    for counts in identity.values():
        total_leader += counts[0] if len(counts) > 0 else 0
        total_produced += counts[1] if len(counts) > 1 else 0

    return {
        "current_slot": slot,
        "epoch": int(epoch_info.get("epoch", 0)),
        "slot_in_epoch": int(epoch_info.get("slotIndex", 0)),
        "leader_schedule": schedule,
        "block_production": {
            "total_leader_slots": total_leader,
            "total_blocks_produced": total_produced,
            "total_skipped": total_leader - total_produced,
            "skip_rate_pct": round(
                (1 - total_produced / total_leader) * 100, 2
            ) if total_leader else 0,
            "unique_leaders": len(identity),
        },
        "timestamp": _now_iso(),
    }


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "slot":
        print(f"Current Slot: {get_current_slot_sync()}")
    elif cmd == "epoch":
        print(json.dumps(get_epoch_info_sync(), indent=2))
    elif cmd == "schedule":
        data = get_leader_schedule_sync(limit=10)
        # Nur Zählung, nicht Keys ausgeben
        print(f"Slots geladen: {data.get('total_slots', 0)}")
        print(f"First: {data.get('first_slot')}, Last: {data.get('last_slot')}")
    elif cmd == "production":
        print(json.dumps(get_block_production_sync(), indent=2))
    elif cmd == "status":
        print(json.dumps({
            "slot": get_current_slot_sync(),
            "epoch_info": get_epoch_info_sync(),
            "production": get_block_production_sync(),
        }, indent=2))
    else:
        print(f"Verwendung: {sys.argv[0]} [slot|epoch|schedule|production|status]")
