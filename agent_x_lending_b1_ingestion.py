"""
Agent X — Klasse B: Cluster B1 (Lending Ingestion).

Rohdaten-Beschaffung von Lending-Protokollen (Aave V3, Compound, Solend).
Parsing von On-Chain-Events und Normalisierung.

Agenten:
  B1-1: EVM-Lending-Subscriber (Aave V3)  — 3 Subagenten
  B1-2: Solana-Lending-Subscriber (Solend) — 3 Subagenten
  B1-3: Cross-Chain Event-Normalizer       — 3 Subagenten
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

from agent_x_lending_models import (
    Chain, RiskZone, LendingProtocol,
    AssetPosition, UserLendingState, LiquidationEvent, ReserveData,
    get_reserve_default,
)

logger = logging.getLogger("klasse_b1_ingestion")

# ─── Konfiguration ───────────────────────────────────────────────────

ETH_RPC_WS = os.getenv("ETH_RPC_WS", "wss://eth-mainnet.g.alchemy.com/v2/demo")
ARB_RPC_WS = os.getenv("ARB_RPC_WS", "wss://arb-mainnet.g.alchemy.com/v2/demo")
SOL_RPC_WS = os.getenv("SOL_RPC_WS", "wss://api.mainnet-beta.solana.com")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
POLL_INTERVAL_S = int(os.getenv("LENDING_POLL_INTERVAL", "12"))  # 1 ETH-Slot

# Aave V3 Pool-Adressen (Mainnet)
AAVE_V3_POOL_ETH = os.getenv("AAVE_V3_POOL_ETH", "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2")
AAVE_V3_POOL_ARB = os.getenv("AAVE_V3_POOL_ARB", "0x794a61358D6845594F94dc1DB02A252b5b4814aD")

# Solend Main Pool
SOLEND_PROGRAM_ID = os.getenv("SOLEND_PROGRAM_ID", "So1endDq2YkqhipRh3WViPa8hdiSpxWy6z3Z6tMCpAo")

# Aave V3 Event-Signaturen (keccak256 Topics)
AAVE_V3_TOPICS = {
    "Supply":   "0x2b627736bca15cd5381dcf80b0bf11fd197d01a037c52b927a881a10fb73ba61",
    "Withdraw": "0x3115d1449a7b732c986cba18244e897a450f61e1bb8d589cd2e69e6c8924f9f7",
    "Borrow":   "0xb3d084820fb1a9decffb176436bd02558d15fac9b0ddfed8c465bc7359d7dce0",
    "Repay":    "0xa534c8dbe71f871f9f3530e97a74601fea17b426cae02e1c5aee42c96c784051",
    "LiquidationCall": "0xe413a321e8681d30f05110415e5e28c2a6d37b98a7e8a8a828d2f7f9e9cdcba9",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Redis-Client (mit Fallback) ─────────────────────────────────────

def _get_redis():
    """Redis-Client mit Fallback auf In-Memory-Dict."""
    try:
        import redis
        r = redis.from_url(REDIS_URL)
        r.ping()
        return r
    except Exception:
        logger.warning("Redis nicht verfügbar — Fallback auf In-Memory-Store")
        return _InMemoryStore()


class _InMemoryStore:
    """Minimaler Redis-kompatibler In-Memory-Store für Dev/Test."""
    def __init__(self):
        self._data: dict = {}
        self._hashes: dict = {}
        self._lists: dict = {}
        self._streams: dict = {}
        self._sets: dict = {}
        self._sorted_sets: dict = {}

    def ping(self): return True
    def get(self, key: str) -> str | None: return self._data.get(key)
    def set(self, key: str, value: str): self._data[key] = value
    def hgetall(self, key: str) -> dict: return self._hashes.get(key, {})
    def hset(self, key: str, mapping: dict): self._hashes.setdefault(key, {}).update(mapping)
    def hget(self, key: str, field: str) -> str | None:
        return self._hashes.get(key, {}).get(field)
    def keys(self, pattern: str = "*") -> list:
        import fnmatch
        return [k for k in self._data if fnmatch.fnmatch(k, pattern)]
    def publish(self, channel: str, message: str): pass
    def xadd(self, stream: str, data: dict): pass
    def xread(self, streams: dict, block: int = 0) -> list: return []
    def sadd(self, key: str, *values): pass
    def smembers(self, key: str) -> set: return self._sets.get(key, set())
    def zadd(self, key: str, mapping: dict): self._sorted_sets.setdefault(key, {}).update(mapping)
    def incr(self, key: str) -> int:
        v = int(self._data.get(key, 0)) + 1
        self._data[key] = str(v)
        return v
    def expire(self, key: str, ttl: int): pass


# ═══════════════════════════════════════════════════════════════════════
# AGENT B1-1: EVM-Lending-Subscriber (Aave V3)
# ═══════════════════════════════════════════════════════════════════════

def b1_1_evm_lending_subscriber(
    action: str = "poll",
    chain: str = "ETHEREUM",
    max_events: int = 100,
) -> dict:
    """Abonniert Supply/Borrow/Repay/Liquidation-Events via WebSocket.

    Args:
        action: 'status' | 'poll' | 'subscribe'
        chain: 'ETHEREUM' | 'ARBITRUM'
        max_events: Max Events pro Poll

    Returns:
        {"status": "...", "events": {"supply": N, "borrow": N, ...}, "subagents": {...}}
    """
    try:
        if action == "status":
            return {
                "status": "ok",
                "agent": "B1-1",
                "chain": chain,
                "protocol": "AaveV3",
                "pool_eth": AAVE_V3_POOL_ETH,
                "pool_arb": AAVE_V3_POOL_ARB,
                "events_monitored": list(AAVE_V3_TOPICS.keys()),
                "timestamp": _now_iso(),
            }

        # Versuche Aave V3 WebSocket-Subscriber (primär), Fallback auf Poll
        try:
            from agent_x_aave_subscriber import sync_poll_aave_events
            polled = sync_poll_aave_events(max_events)
        except ImportError:
            polled = _b1_1a_poll_evm_events_demo(chain, max_events)
        parsed = _b1_1b_parse_evm_events(polled)
        reserves = _b1_1c_fetch_reserve_data(chain, parsed)

        return {
            "status": "completed",
            "agent": "B1-1",
            "chain": chain,
            "action": action,
            "total_events": len(polled),
            "subagents": {
                "b1_1a_evm_poller": polled,
                "b1_1b_event_parser": parsed,
                "b1_1c_reserve_data": reserves,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("B1-1 Fehler: %s", e)
        return {"status": "failed", "agent": "B1-1", "error": str(e)}


def _b1_1a_poll_evm_events_demo(chain: str, max_events: int) -> dict:
    """Demo: EVM-Event-Polling (Fallback wenn Aave-Subscriber nicht verfügbar)."""
    try:
        import urllib.request
        rpc_url = ETH_RPC_WS.replace("wss://", "https://") if chain == "ETHEREUM" else ARB_RPC_WS.replace("wss://", "https://")

        # eth_getLogs für Aave V3 Events
        all_logs = []
        for event_name, topic0 in AAVE_V3_TOPICS.items():
            payload = json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": "eth_getLogs",
                "params": [{
                    "address": AAVE_V3_POOL_ETH if chain == "ETHEREUM" else AAVE_V3_POOL_ARB,
                    "topics": [topic0],
                    "fromBlock": "latest",
                }],
            }).encode()

            req = urllib.request.Request(
                rpc_url,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    result = json.loads(resp.read().decode())
                    for log in result.get("result", []):
                        log["_event_type"] = event_name
                        all_logs.append(log)
            except Exception as e:
                logger.debug("RPC-Abfrage %s fehlgeschlagen: %s", event_name, e)

        return {
            "status": "ok",
            "subagent": "B1-1a",
            "role": "EVM-Event-Poller",
            "chain": chain,
            "events_found": len(all_logs),
            "events_by_type": {
                t: sum(1 for l in all_logs if l.get("_event_type") == t)
                for t in AAVE_V3_TOPICS
            },
            "events": all_logs[:max_events],
        }
    except Exception as e:
        return {"status": "degraded", "subagent": "B1-1a", "events_found": 0, "error": str(e)}


def _b1_1b_parse_evm_events(poll_result: dict) -> dict:
    """Parst rohe EVM-Logs in strukturierte Lending-Events.

    Extrahiert: user, reserve, amount, onBehalfOf, referralCode.
    """
    events = poll_result.get("events", [])
    parsed = {"supply": [], "borrow": [], "repay": [], "liquidation": [], "withdraw": []}

    for log in events:
        etype = log.get("_event_type", "").lower()
        if etype not in parsed:
            continue

        # ABI-Dekodierung (vereinfacht — im Produktivbetrieb via web3.py decode_log)
        topics = log.get("topics", [])
        data = log.get("data", "0x")

        entry = {
            "tx_hash": log.get("transactionHash", ""),
            "block_number": int(log.get("blockNumber", "0x0"), 16),
            "pool": log.get("address", ""),
        }

        if etype == "supply":
            entry["user"] = _addr_from_topic(topics, 1)
            entry["reserve"] = _addr_from_topic(topics, 0)
            entry["on_behalf_of"] = _addr_from_topic(topics, 2)
            entry["amount"] = _uint256_from_data(data, 0)
        elif etype == "borrow":
            entry["user"] = _addr_from_topic(topics, 1)
            entry["reserve"] = _addr_from_topic(topics, 0)
            entry["on_behalf_of"] = _addr_from_topic(topics, 2)
            entry["amount"] = _uint256_from_data(data, 0)
        elif etype == "liquidation":
            entry["collateral_asset"] = _addr_from_topic(topics, 0)
            entry["debt_asset"] = _addr_from_topic(topics, 1)
            entry["user"] = _addr_from_topic(topics, 2)
            entry["debt_to_cover"] = _uint256_from_data(data, 0)
            entry["liquidated_collateral"] = _uint256_from_data(data, 64)
            entry["liquidator"] = _addr_from_data(data, 128)

        parsed[etype].append(entry)

    total = sum(len(v) for v in parsed.values())
    return {
        "status": "ok",
        "subagent": "B1-1b",
        "role": "EVM-Event-Parser",
        "total_parsed": total,
        "by_type": {k: len(v) for k, v in parsed.items()},
        "parsed_events": parsed,
    }


def _b1_1c_fetch_reserve_data(chain: str, parsed: dict) -> dict:
    """Holt aktuelle Reserve-Parameter (LTV, Threshold, Zinssätze).

    Im Produktivbetrieb: Aave Pool.getReserveData() via web3.py Contract-Call.
    """
    # Sammle alle einzigartigen Reserve-Adressen aus den geparsten Events
    reserves_seen: set[str] = set()
    for etype, events in (parsed.get("parsed_events", {}) or {}).items():
        for ev in events:
            for key in ("reserve", "collateral_asset", "debt_asset"):
                addr = ev.get(key, "")
                if addr:
                    reserves_seen.add(addr)

    reserve_list = []
    for addr in reserves_seen:
        default = get_reserve_default(addr[:6].upper())  # Näherung
        reserve_list.append({
            "asset_address": addr,
            "symbol": default["symbol"],
            "ltv": default["ltv"],
            "liquidation_threshold": default["liquidation_threshold"],
            "liquidation_bonus": default["liquidation_bonus"],
            "liquidity_index": 1.0,
            "variable_borrow_index": 1.0,
        })

    return {
        "status": "ok",
        "subagent": "B1-1c",
        "role": "Reserve-Data-Fetcher",
        "reserves_fetched": len(reserve_list),
        "reserves": reserve_list,
    }


# ─── ABI-Helfer ──────────────────────────────────────────────────────

def _addr_from_topic(topics: list, idx: int) -> str:
    """Extrahiert Adresse aus Event-Topic (32-Byte Hex → 20-Byte Adresse)."""
    if idx < len(topics):
        t = topics[idx]
        if t.startswith("0x") and len(t) >= 66:
            return "0x" + t[26:]  # letzte 20 Bytes
    return "0x0000000000000000000000000000000000000000"


def _uint256_from_data(data: str, offset: int) -> int:
    """Extrahiert uint256 aus data-String an Byte-Offset."""
    if not data or data == "0x":
        return 0
    data = data[2:] if data.startswith("0x") else data
    start = offset * 2
    end = start + 64
    if start < len(data):
        chunk = data[start:end].lstrip("0") or "0"
        try:
            return int(chunk, 16)
        except ValueError:
            return 0
    return 0


def _addr_from_data(data: str, offset: int) -> str:
    """Extrahiert Adresse aus data (32-Byte-Word, letzte 20 Bytes)."""
    if not data or data == "0x":
        return "0x0000000000000000000000000000000000000000"
    data = data[2:] if data.startswith("0x") else data
    start = offset * 2
    end = start + 64
    if start + 64 <= len(data):
        word = data[start:end]
        return "0x" + word[24:]  # letzte 20 Bytes
    return "0x0000000000000000000000000000000000000000"


# ═══════════════════════════════════════════════════════════════════════
# AGENT B1-2: Solana-Lending-Subscriber (Solend/Kamino)
# ═══════════════════════════════════════════════════════════════════════

def b1_2_solana_lending_subscriber(action: str = "poll") -> dict:
    """Subscribed auf Solend-Program-Logs via WebSocket.

    Args:
        action: 'status' | 'poll'

    Returns:
        {"status": "...", "subagents": {...}}
    """
    try:
        if action == "status":
            return {
                "status": "ok",
                "agent": "B1-2",
                "chain": "SOLANA",
                "protocols": ["Solend", "Kamino", "Marginfi"],
                "solend_program": SOLEND_PROGRAM_ID,
                "rpc_ws": SOL_RPC_WS,
                "timestamp": _now_iso(),
            }

        logs = _b1_2a_poll_solana_logs()
        parsed = _b1_2b_parse_solana_logs(logs)
        reserves = _b1_2c_fetch_solana_reserves()

        return {
            "status": "completed",
            "agent": "B1-2",
            "chain": "SOLANA",
            "subagents": {
                "b1_2a_solana_poller": logs,
                "b1_2b_log_parser": parsed,
                "b1_2c_reserves": reserves,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("B1-2 Fehler: %s", e)
        return {"status": "failed", "agent": "B1-2", "error": str(e)}


def _b1_2a_poll_solana_logs() -> dict:
    """Pollt Solana-Program-Logs via RPC getSignaturesForAddress."""
    try:
        import urllib.request

        payload = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress",
            "params": [SOLEND_PROGRAM_ID, {"limit": 50}],
        }).encode()

        req = urllib.request.Request(
            SOL_RPC_WS.replace("wss://", "https://").replace("api.mainnet-beta.solana.com", "api.mainnet-beta.solana.com"),
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            txs = result.get("result", [])

        return {
            "status": "ok",
            "subagent": "B1-2a",
            "role": "Solana-Log-Poller",
            "transactions_found": len(txs),
            "transactions": txs[:20],
        }
    except Exception as e:
        return {"status": "degraded", "subagent": "B1-2a",
                "transactions_found": 0, "error": str(e)}


def _b1_2b_parse_solana_logs(logs: dict) -> dict:
    """Parst Solana-Transaktionen in Lending-Events.

    Erkennt Solend-Instruktionen: deposit, withdraw, borrow, repay, liquidate.
    """
    txs = logs.get("transactions", [])
    parsed = {"deposit": [], "withdraw": [], "borrow": [], "repay": [], "liquidate": []}

    for tx in txs:
        sig = tx.get("signature", "")
        slot = tx.get("slot", 0)
        # Vereinfachte Heuristik — im Produktivbetrieb via anchorpy/cpi-Decoding
        entry = {
            "signature": sig,
            "slot": slot,
            "block_time": tx.get("blockTime"),
        }
        # Memo-Feld kann Instruktions-Hinweise enthalten
        memo = tx.get("memo", "")
        if "deposit" in memo.lower():
            parsed["deposit"].append(entry)
        elif "borrow" in memo.lower():
            parsed["borrow"].append(entry)
        elif "liquidate" in memo.lower():
            parsed["liquidate"].append(entry)
        else:
            parsed["deposit"].append(entry)  # Default-Kategorie

    total = sum(len(v) for v in parsed.values())
    return {
        "status": "ok",
        "subagent": "B1-2b",
        "role": "Solana-Log-Parser",
        "total_parsed": total,
        "by_type": {k: len(v) for k, v in parsed.items()},
        "parsed_events": parsed,
    }


def _b1_2c_fetch_solana_reserves() -> dict:
    """Holt Solend/Kamino-Reserve-Daten via On-Chain-Account-Deserialisierung."""
    return {
        "status": "ok",
        "subagent": "B1-2c",
        "role": "Solana-Reserve-Fetcher",
        "reserves_fetched": 0,
        "reserves": [],
        "note": "anchorpy account deserialization pending for production",
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT B1-3: Cross-Chain Event-Normalizer
# ═══════════════════════════════════════════════════════════════════════

def b1_3_event_normalizer(
    evm_events: dict | None = None,
    solana_events: dict | None = None,
) -> dict:
    """Wandelt heterogene Chain-Events in einheitliche UserLendingStates um.

    Konsumiert Output von B1-1 und B1-2.
    """
    try:
        evm = evm_events or {}
        sol = solana_events or {}

        evm_states = _b1_3a_normalize_evm(evm)
        sol_states = _b1_3b_normalize_solana(sol)
        merged = _b1_3c_merge_states(evm_states, sol_states)

        return {
            "status": "completed",
            "agent": "B1-3",
            "subagents": {
                "b1_3a_evm_normalizer": evm_states,
                "b1_3b_solana_normalizer": sol_states,
                "b1_3c_state_merger": merged,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("B1-3 Fehler: %s", e)
        return {"status": "failed", "agent": "B1-3", "error": str(e)}


def _b1_3a_normalize_evm(evm_events: dict) -> dict:
    """Normalisiert EVM-Events → UserLendingState-Liste."""
    by_type = evm_events.get("subagents", {}).get("b1_1b_event_parser", {}).get("by_type", {})
    parsed = evm_events.get("subagents", {}).get("b1_1b_event_parser", {}).get("parsed_events", {})

    user_states: dict[str, dict] = {}
    for etype, events in parsed.items():
        for ev in events:
            user = ev.get("user", "")
            if not user:
                continue
            if user not in user_states:
                user_states[user] = {
                    "user_address": user,
                    "chain": "ETHEREUM",
                    "protocol": "AaveV3",
                    "positions": [],
                    "total_collateral_usd": 0.0,
                    "total_debt_usd": 0.0,
                }

            amount = ev.get("amount", 0) / 1e18
            if etype == "supply":
                user_states[user]["positions"].append({
                    "asset_address": ev.get("reserve", ""),
                    "type": "collateral",
                    "amount": amount,
                    "is_collateral": True,
                })
                reserve = get_reserve_default(ev.get("reserve", "ETH"))
                user_states[user]["total_collateral_usd"] += amount * 2000  # placeholder price
            elif etype == "borrow":
                user_states[user]["positions"].append({
                    "asset_address": ev.get("reserve", ""),
                    "type": "debt",
                    "amount": amount,
                    "is_collateral": False,
                })
                user_states[user]["total_debt_usd"] += amount * 2000

    return {
        "status": "ok",
        "subagent": "B1-3a",
        "role": "EVM-Normalizer",
        "users_tracked": len(user_states),
        "user_states": list(user_states.values()),
    }


def _b1_3b_normalize_solana(sol_events: dict) -> dict:
    """Normalisiert Solana-Events → UserLendingState-Liste."""
    return {
        "status": "ok",
        "subagent": "B1-3b",
        "role": "Solana-Normalizer",
        "users_tracked": 0,
        "user_states": [],
        "note": "anchorpy account deserialization pending",
    }


def _b1_3c_merge_states(evm_states: dict, sol_states: dict) -> dict:
    """Merge EVM und Solana User-Lending-States. Dedupliziert nach user_address."""
    evm_users = evm_states.get("user_states", [])
    sol_users = sol_states.get("user_states", [])

    merged = {u["user_address"]: u for u in evm_users}
    for u in sol_users:
        addr = u.get("user_address", "")
        if addr not in merged:
            merged[addr] = u

    return {
        "status": "ok",
        "subagent": "B1-3c",
        "role": "State-Merger",
        "total_unique_users": len(merged),
        "evm_users": len(evm_users),
        "solana_users": len(sol_users),
        "merged_states": list(merged.values()),
    }


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "b1_1":
        print(json.dumps(b1_1_evm_lending_subscriber("poll"), indent=2))
    elif cmd == "b1_2":
        print(json.dumps(b1_2_solana_lending_subscriber("poll"), indent=2))
    elif cmd == "b1_3":
        evm = b1_1_evm_lending_subscriber("poll")
        sol = b1_2_solana_lending_subscriber("poll")
        print(json.dumps(b1_3_event_normalizer(evm, sol), indent=2))
    elif cmd == "status":
        print(json.dumps({
            "b1_1": b1_1_evm_lending_subscriber("status"),
            "b1_2": b1_2_solana_lending_subscriber("status"),
            "b1_3": b1_3_event_normalizer(),
        }, indent=2))
    else:
        print(f"Verwendung: {sys.argv[0]} [b1_1|b1_2|b1_3|status]")
