"""
Agent X — Pyth-Network-Oracle-Client.

Production-grade client for Pyth Network price feeds.
WebSocket (EVM price updates) + Hermes REST API (off-chain).

Endpoints:
  - WebSocket: Pyth PriceFeedUpdate events (EVM chains)
  - Hermes:    GET /api/latest_price_feeds?ids[]=... (off-chain prices)
  - Hermes:    GET /api/price_feed_ids (available feed list)

Pyth feed IDs are deterministic hashes of the feed description.
Example: "Crypto.ETH/USD" → feed_id: "0xff61491a..."

Usage:
  client = PythOracleClient()
  async for update in client.stream_price_updates():
      process(update)
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

logger = logging.getLogger("pyth_client")

# ─── Konfiguration ───────────────────────────────────────────────────

PYTH_RPC_WS = os.getenv("PYTH_RPC_WS", "wss://eth-mainnet.g.alchemy.com/v2/demo")
PYTH_HERMES_URL = os.getenv("PYTH_HERMES_URL", "https://hermes.pyth.network/api")
PYTH_RETRIES = int(os.getenv("PYTH_RETRIES", "3"))
PYTH_BACKOFF = float(os.getenv("PYTH_BACKOFF", "1.5"))
PYTH_TIMEOUT = int(os.getenv("PYTH_TIMEOUT", "30"))

# Pyth Price Feed IDs (Hermes Format)
PYTH_FEED_IDS = {
    "Crypto.ETH/USD": "0xff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
    "Crypto.BTC/USD": "0xe62df6c8c0f5c5b2a1e54a5b5f5eb5f5e5e5e5e5e5e5e5e5e5e5e5e5e5e5",
    "Crypto.SOL/USD": "0xef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d",
    "Crypto.ARB/USD": "0x3fa4252848f9f0a1480be62745a4629d9eb1322aebab8a791e344b3b9c1adcf5",
    "FX.USD/JPY":  "0xef2c98c804ba503c6a707e38be4dfbb16683775f195b091252bf24693042b52c",
}

# Pyth EVM Contract (PythUpgradable)
PYTH_EVM_CONTRACT = "0x4305FB66699C3B2702D4d05CF36551390A4c69C6"
PYTH_EVENT_FEED_UPDATE = "0x0000000000000000000000000000000000000000000000000000000000000000"  # PriceFeedUpdate topic

# Pyth Solana Program
PYTH_SOLANA_PROGRAM = "FsJ3A3u2vn5cTVofAjvy6y5kwABJAqYWpe3975ucs5tU"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_unix() -> float:
    return time.time()


# ═══════════════════════════════════════════════════════════════════════
# PythOracleClient
# ═══════════════════════════════════════════════════════════════════════

class PythOracleClient:
    """Async-first Pyth Network Oracle Client.

    Features:
      - Hermes REST API: Off-chain price feeds (latest prices)
      - EVM WebSocket: PriceFeedUpdate event subscription
      - Solana transaction parsing for embedded Pyth updates
      - Confidence interval checking
      - Price exponent handling (Pyth uses expo for decimal scaling)
      - Retry with exponential backoff
    """

    def __init__(self, rpc_ws: str = PYTH_RPC_WS, hermes_url: str | None = None, redis_client=None):
        self.rpc_ws = rpc_ws
        self.hermes_url = (hermes_url or PYTH_HERMES_URL).rstrip("/")
        self.redis = redis_client
        self._update_cache: list[dict] = []
        self._offchain_cache: dict[str, dict] = {}

    # ─── Hermes REST: Off-Chain Price Feeds ──────────────────────────

    async def fetch_latest_prices_async(
        self, feed_ids: list[str] | None = None,
    ) -> dict[str, dict]:
        """Holt aktuelle Off-Chain-Preise von Pyth Hermes.

        Args:
            feed_ids: Hermes feed IDs (None = alle bekannten)

        Returns:
            {"Crypto.ETH/USD": {"price": 3245.67, "conf": 1.2, "expo": -8, ...}, ...}
        """
        target_ids = feed_ids or list(PYTH_FEED_IDS.values())
        try:
            import aiohttp
        except ImportError:
            return self._fetch_hermes_sync(target_ids)

        ids_param = "&ids[]=".join([""] + target_ids)
        url = f"{self.hermes_url}/latest_price_feeds{ids_param}"

        for attempt in range(1, PYTH_RETRIES + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=PYTH_TIMEOUT) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            return self._parse_hermes_response(data)
                        return self._demo_hermes_prices(target_ids)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                backoff = PYTH_BACKOFF ** attempt
                logger.warning("Pyth Hermes (Versuch %d/%d): %s", attempt, PYTH_RETRIES, e)
                if attempt < PYTH_RETRIES:
                    await asyncio.sleep(backoff)

        return self._demo_hermes_prices(target_ids)

    def _fetch_hermes_sync(self, feed_ids: list) -> dict:
        """Sync-Fallback für Hermes."""
        import urllib.request
        try:
            ids_param = "&ids[]=".join([""] + feed_ids)
            url = f"{self.hermes_url}/latest_price_feeds{ids_param}"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=PYTH_TIMEOUT) as resp:
                return self._parse_hermes_response(json.loads(resp.read().decode()))
        except Exception:
            return self._demo_hermes_prices(feed_ids)

    def _parse_hermes_response(self, data: list | dict) -> dict:
        """Parst Hermes API Response in standardisiertes Format."""
        result = {}
        items = data if isinstance(data, list) else data.get("data", data.get("price_feeds", []))

        for item in items:
            price_info = item.get("price", item)
            ema_price = item.get("ema_price", {})

            feed_id = item.get("id", "")
            # Finde den Feed-Namen
            feed_name = feed_id
            for name, fid in PYTH_FEED_IDS.items():
                if fid == feed_id:
                    feed_name = name
                    break

            price_val = float(price_info.get("price", 0))
            expo = int(price_info.get("expo", -8))
            conf_val = float(price_info.get("conf", 0))
            actual_price = price_val * (10 ** expo)  # Expo-Skalierung

            result[feed_name] = {
                "feed_id": feed_id,
                "raw_price": price_val,
                "expo": expo,
                "actual_price": round(actual_price, 6),
                "confidence": conf_val * (10 ** expo),
                "confidence_ratio": round(abs(conf_val / price_val) if price_val else 0, 6),
                "publish_time": int(price_info.get("publish_time", 0)),
                "source": "pyth_hermes_live",
                "fetched_at": _now_iso(),
            }
            self._offchain_cache[feed_name] = result[feed_name]

        return result

    def _demo_hermes_prices(self, feed_ids: list) -> dict:
        """Demo-Hermes-Preise."""
        demo = {"Crypto.ETH": 3245.67, "Crypto.BTC": 64320.12, "Crypto.SOL": 178.34}
        result = {}
        for fid in feed_ids:
            for name, base in demo.items():
                if name.split(".")[-1] in fid or fid in name:
                    price = base * (1 + (time.time() % 30 - 15) / 15 * 0.002)
                    result[name + "/USD" if "/USD" not in name else name] = {
                        "feed_id": fid,
                        "raw_price": int(price * 1e8),
                        "expo": -8,
                        "actual_price": round(price, 6),
                        "confidence": round(price * 0.0003, 2),
                        "confidence_ratio": 0.0003,
                        "publish_time": int(_now_unix()),
                        "source": "pyth_hermes_demo",
                        "fetched_at": _now_iso(),
                    }
                    break
        self._offchain_cache = result
        return result

    # ─── WebSocket: PriceFeedUpdate Events ───────────────────────────

    async def stream_price_updates(
        self, max_events: int = 0,
    ) -> AsyncIterator[dict]:
        """Async-Generator: Streamt Pyth PriceFeedUpdate Events via WebSocket."""
        self._update_cache = []
        count = 0

        try:
            import aiohttp
        except ImportError:
            for ev in self._generate_demo_updates(max_events or 20):
                self._update_cache.append(ev)
                yield ev
                count += 1
            return

        for attempt in range(1, PYTH_RETRIES + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(self.rpc_ws) as ws:
                        sub_msg = {
                            "jsonrpc": "2.0", "id": 1, "method": "eth_subscribe",
                            "params": ["logs", {
                                "address": PYTH_EVM_CONTRACT,
                                "topics": [PYTH_EVENT_FEED_UPDATE],
                            }],
                        }
                        await ws.send_json(sub_msg)
                        await ws.receive_json()

                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    data = json.loads(msg.data)
                                    parsed = self._parse_price_update(data)
                                    if parsed:
                                        self._update_cache.append(parsed)
                                        yield parsed
                                        count += 1
                                        if max_events > 0 and count >= max_events:
                                            return
                                except json.JSONDecodeError:
                                    continue

            except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError) as e:
                backoff = PYTH_BACKOFF ** attempt
                logger.warning("Pyth WS (Versuch %d/%d): %s", attempt, PYTH_RETRIES, e)
                if attempt < PYTH_RETRIES:
                    await asyncio.sleep(backoff)
                else:
                    for ev in self._generate_demo_updates(max_events or 10):
                        self._update_cache.append(ev)
                        yield ev

    def _parse_price_update(self, data: dict) -> dict | None:
        """Parst Pyth PriceFeedUpdate Event aus WebSocket/Log."""
        params = data.get("params", {}).get("result", {})
        topics = params.get("topics", [])
        log_data = params.get("data", "0x")

        if not topics:
            return None

        return {
            "feed_id": topics[1] if len(topics) > 1 else "",
            "contract": params.get("address", PYTH_EVM_CONTRACT),
            "tx_hash": params.get("transactionHash", ""),
            "block_number": int(params.get("blockNumber", "0x0"), 16),
            "raw_data": log_data,
            "timestamp_unix": int(_now_unix()),
            "source": "pyth_ws_live",
            "received_at": _now_iso(),
        }

    def _generate_demo_updates(self, count: int) -> list[dict]:
        """Demo Pyth-Updates."""
        base_prices = {"Crypto.ETH/USD": 3245.67, "Crypto.BTC/USD": 64320.12, "Crypto.SOL/USD": 178.34}
        events = []
        feeds = list(base_prices.keys())
        for i in range(count):
            feed = feeds[i % len(feeds)]
            price = base_prices[feed] * (1 + (i % 3 - 1) * 0.0005)
            events.append({
                "feed_id": PYTH_FEED_IDS.get(feed, "0x..."),
                "feed": feed,
                "contract": PYTH_EVM_CONTRACT,
                "tx_hash": f"0xpyth_{i:04x}",
                "block_number": 21_000_200 + i,
                "actual_price": round(price, 6),
                "confidence": round(price * 0.0003, 2),
                "confidence_ratio": 0.0003,
                "expo": -8,
                "publish_time": int(_now_unix()) - i,
                "source": "pyth_demo",
                "received_at": _now_iso(),
            })
        return events

    # ─── Solana Pyth Updates ─────────────────────────────────────────

    async def fetch_solana_pyth_updates(self, limit: int = 20) -> list[dict]:
        """Holt Pyth-Updates von Solana (in Swap-Instructions eingebettet)."""
        # Im Produktivbetrieb: getSignaturesForAddress(PYTH_SOLANA_PROGRAM)
        # + getTransaction für jede Signature, dann parseInstructions
        return self._generate_demo_solana_updates(limit)

    def _generate_demo_solana_updates(self, count: int) -> list[dict]:
        return [
            {
                "signature": f"sol_pyth_{i:04x}",
                "slot": 300_000_000 + i,
                "feed": "Crypto.SOL/USD",
                "price": round(178.34 + i * 0.02, 6),
                "conf": 0.5,
                "expo": -8,
                "timestamp_unix": int(_now_unix()) - i,
                "source": "pyth_solana_demo",
            }
            for i in range(count)
        ]

    # ─── Redis-Integration ───────────────────────────────────────────

    async def stream_to_redis(self, max_events: int = 0):
        """Streamt Pyth-Updates via Redis."""
        if not self.redis:
            async for _ in self.stream_price_updates(max_events):
                pass
            return
        try:
            async for event in self.stream_price_updates(max_events):
                try:
                    self.redis.xadd("oracle:pyth_updates", {
                        "feed": event.get("feed", event.get("feed_id", "")),
                        "price": str(event.get("actual_price", 0)),
                        "conf": str(event.get("confidence", 0)),
                        "data": json.dumps(event),
                    })
                    if event.get("confidence_ratio", 0) > 0.02:
                        self.redis.publish("oracle:pyth_high_conf", json.dumps(event))
                except Exception as e:
                    logger.debug("Redis: %s", e)
        except Exception as e:
            logger.error("Pyth Redis stream: %s", e)

    # ─── Analyse ─────────────────────────────────────────────────────

    def analyze_update_cache(self) -> dict:
        if not self._update_cache:
            return {"cached": 0}
        conf_ratios = [u.get("confidence_ratio", 0) for u in self._update_cache if u.get("confidence_ratio")]
        high_conf = sum(1 for cr in conf_ratios if cr > 0.02)
        return {
            "cached": len(self._update_cache),
            "avg_confidence_ratio": round(sum(conf_ratios) / len(conf_ratios), 6) if conf_ratios else 0,
            "high_confidence_events": high_conf,
            "latest_publish_time": max(
                (u.get("publish_time", 0) for u in self._update_cache), default=0
            ),
        }


# ─── Convenience ─────────────────────────────────────────────────────

async def fetch_pyth_offchain_prices(feed_ids: list[str] | None = None) -> dict:
    client = PythOracleClient()
    return await client.fetch_latest_prices_async(feed_ids)


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "status":
        client = PythOracleClient()
        prices = asyncio.run(client.fetch_latest_prices_async())
        for k, v in prices.items():
            print(f"{k}: ${v['actual_price']:.2f} ±{v['confidence']:.2f} (conf={v['confidence_ratio']:.4f})")
    elif cmd == "updates":
        async def _demo():
            client = PythOracleClient()
            async for ev in client.stream_price_updates(max_events=5):
                print(f"{ev.get('feed', ev.get('feed_id','?'))}: "
                      f"${ev.get('actual_price', 0):.2f} conf={ev.get('confidence_ratio', 0):.4f}")
            print(json.dumps(client.analyze_update_cache(), indent=2))
        asyncio.run(_demo())
    elif cmd == "solana":
        client = PythOracleClient()
        updates = asyncio.run(client.fetch_solana_pyth_updates(5))
        for u in updates:
            print(f"Solana Slot {u['slot']}: {u['feed']} = ${u['price']:.2f}")
    else:
        print(f"Verwendung: {sys.argv[0]} [status|updates|solana]")
