"""
Agent X — Druckventile: Cluster B1 (Ingestion).

Rohdaten-Beschaffung: EVM Gas/Blob-Preise, Solana Jito-Tips, Flashbots-Bundles.

Agenten:
  B1-1: EVM-Gas- & Blob-Preis-Listener   — 3 Subagenten
  B1-2: Solana-Jito-Tip-Listener         — 3 Subagenten
  B1-3: Flashbots-MEV-Listener (Ethereum) — 3 Subagenten
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from agent_x_klasse_b_pressure_models import (
    MEVSource, PressureLevel, EVMGasData, MEVBundle, SolanaTipData, RollingStats,
)

logger = logging.getLogger("pressure_b1_ingestion")

# ─── Konfiguration ───────────────────────────────────────────────────

ETH_RPC_URL = os.getenv("ETH_RPC_URL", "https://eth-mainnet.g.alchemy.com/v2/demo")
FLASHBOTS_API = os.getenv("FLASHBOTS_API", "https://relay.flashbots.net")
JITO_API = os.getenv("JITO_API", "https://bundles.jito.wtf/api/v1")
GWEI_TO_ETH = 1e-9
LAMPORT_TO_SOL = 1e-9

# Lazy imports für reale Clients
_flashbots_client = None
_jito_client = None


def _get_flashbots_client():
    """Lazy-Init Flashbots-Client (mit Fallback)."""
    global _flashbots_client
    if _flashbots_client is None:
        try:
            from agent_x_flashbots_client import FlashbotsRelayClient
            _flashbots_client = FlashbotsRelayClient()
            logger.info("Flashbots-Client initialisiert")
        except Exception as e:
            logger.warning("Flashbots-Client nicht verfügbar: %s — Fallback aktiv", e)
            _flashbots_client = None
    return _flashbots_client


def _get_jito_client():
    """Lazy-Init Jito-Client (mit Fallback)."""
    global _jito_client
    if _jito_client is None:
        try:
            from agent_x_jito_client import JitoTipClient
            _jito_client = JitoTipClient()
            logger.info("Jito-Client initialisiert")
        except Exception as e:
            logger.warning("Jito-Client nicht verfügbar: %s — Fallback aktiv", e)
            _jito_client = None
    return _jito_client


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── In-Memory Stats (Ersatz für Redis im Dev-Modus) ────────────────

# Globale Stats-Windows (werden von B2 konsumiert)
basefee_stats = RollingStats(100)
priority_fee_stats = RollingStats(100)
bribe_stats = RollingStats(50)
jito_tip_stats = RollingStats(50)


# ═══════════════════════════════════════════════════════════════════════
# AGENT B1-1: EVM-Gas- & Blob-Preis-Listener
# ═══════════════════════════════════════════════════════════════════════

def b1_1_evm_gas_listener(
    action: str = "poll",
    blocks: int = 10,
) -> dict:
    """Holt Basefee, Priority-Fees und Blob-Preise für neue Blöcke.

    Args:
        action: 'poll' | 'status'
        blocks: Anzahl Blöcke abzurufen

    Returns:
        {"status": "...", "blocks_scanned": N, "subagents": {...}}
    """
    try:
        if action == "status":
            return {
                "status": "ok",
                "agent": "B1-1",
                "targets": ["baseFeePerGas", "blobGasPrice", "priorityFee"],
                "rpc": ETH_RPC_URL,
                "timestamp": _now_iso(),
            }

        basefee_data = _b1_1a_collect_basefee(blocks)
        blob_data = _b1_1b_collect_blob_prices(blocks)
        trend = _b1_1c_analyze_gas_trend(basefee_data, blob_data)

        # Feed RollingStats
        for bf in basefee_data.get("basefees", []):
            basefee_stats.add(bf["base_fee_gwei"])

        return {
            "status": "completed",
            "agent": "B1-1",
            "blocks_scanned": blocks,
            "basefee_stats_snapshot": basefee_stats.snapshot(),
            "subagents": {
                "b1_1a_basefee": basefee_data,
                "b1_1b_blob": blob_data,
                "b1_1c_trend": trend,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("B1-1 Fehler: %s", e)
        return {"status": "failed", "agent": "B1-1", "error": str(e)}


def _b1_1a_collect_basefee(blocks: int) -> dict:
    """Sammelt Basefee-Werte für die letzten N Blöcke.

    Im Produktivbetrieb: eth_getBlockByNumber via WebSocket für jeden neuen Block.
    """
    # Realistische Mainnet-Werte (August 2026)
    demo_basefees = [
        {"block": 21_000_000 + i, "base_fee_gwei": 18.5 + i * 0.3, "gas_used_pct": 65 + i * 2,
         "priority_fee_avg": 1.2 + i * 0.05, "priority_fee_p95": 3.5, "tx_count": 210}
        for i in range(blocks)
    ]

    fees = []
    for b in demo_basefees:
        fees.append({
            "block": b["block"],
            "base_fee_gwei": round(b["base_fee_gwei"], 2),
            "gas_used_pct": b["gas_used_pct"],
            "priority_fee_avg_gwei": round(b["priority_fee_avg"], 2),
            "priority_fee_p95_gwei": b["priority_fee_p95"],
            "tx_count": b["tx_count"],
        })

    return {
        "status": "ok",
        "subagent": "B1-1a",
        "role": "Basefee-Collector",
        "blocks_collected": len(fees),
        "current_basefee_gwei": fees[-1]["base_fee_gwei"] if fees else 0,
        "basefees": fees,
    }


def _b1_1b_collect_blob_prices(blocks: int) -> dict:
    """Sammelt Blob-Gas-Preise (EIP-4844).

    Im Produktivbetrieb: Beacon-API /eth/v1/beacon/blocks/{slot} parsen.
    """
    demo_blobs = [
        {"block": 21_000_000 + i, "blob_gas_price": 15.0 + i * 0.5, "blob_gas_used": min(i * 20000, 393216)}
        for i in range(blocks)
    ]

    blob_stats = []
    for b in demo_blobs:
        utilization = (b["blob_gas_used"] / 393216) * 100
        blob_stats.append({
            "block": b["block"],
            "blob_gas_price_gwei": round(b["blob_gas_price"], 2),
            "blob_gas_used": b["blob_gas_used"],
            "blob_utilization_pct": round(utilization, 1),
        })

    return {
        "status": "ok",
        "subagent": "B1-1b",
        "role": "BlobPrice-Collector",
        "current_blob_price_gwei": blob_stats[-1]["blob_gas_price_gwei"] if blob_stats else 0,
        "avg_blob_utilization_pct": round(
            sum(b["blob_utilization_pct"] for b in blob_stats) / len(blob_stats), 1
        ) if blob_stats else 0,
        "blob_data": blob_stats,
    }


def _b1_1c_analyze_gas_trend(basefee_result: dict, blob_result: dict) -> dict:
    """Berechnet gleitende Durchschnitte und erkennt Spikes."""
    basefees = [b["base_fee_gwei"] for b in basefee_result.get("basefees", [])]
    if not basefees:
        return {"status": "ok", "subagent": "B1-1c", "role": "Gas-Trend-Analyst", "trend": "unknown"}

    avg_10 = sum(basefees[-10:]) / min(10, len(basefees))
    avg_all = sum(basefees) / len(basefees)
    spike_detected = basefees[-1] > avg_10 * 1.5  # >50% über 10-Block-Mittel

    trend = "surging" if spike_detected else "rising" if basefees[-1] > basefees[0] else "stable"

    return {
        "status": "ok",
        "subagent": "B1-1c",
        "role": "Gas-Trend-Analyst",
        "trend": trend,
        "avg_10_blocks": round(avg_10, 2),
        "avg_all_blocks": round(avg_all, 2),
        "current_basefee": round(basefees[-1], 2),
        "spike_detected": spike_detected,
        "spike_magnitude_pct": round((basefees[-1] / avg_10 - 1) * 100, 1) if avg_10 > 0 else 0,
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT B1-2: Solana-Jito-Tip-Listener
# ═══════════════════════════════════════════════════════════════════════

def b1_2_jito_tip_listener(action: str = "poll", slots: int = 10) -> dict:
    """Überwacht Jito-Tips für Solana-Transaktionen.

    Args:
        action: 'poll' | 'status'
        slots: Anzahl Slots zu analysieren

    Returns:
        {"status": "...", "total_tips_sol": N, "subagents": {...}}
    """
    try:
        if action == "status":
            return {
                "status": "ok",
                "agent": "B1-2",
                "chain": "SOLANA",
                "api": JITO_API,
                "timestamp": _now_iso(),
            }

        # Versuche echten Jito-Client, fallback auf Demo
        jito_client = _get_jito_client()
        if jito_client:
            try:
                real_bundles = jito_client.get_recent_bundles_sync(limit=slots)
                bundles = _b1_2a_process_real_bundles(real_bundles)
            except Exception as e:
                logger.warning("Jito-Client-Fehler: %s — Fallback auf Demo", e)
                bundles = _b1_2a_collect_jito_bundles_demo(slots)
        else:
            bundles = _b1_2a_collect_jito_bundles_demo(slots)
        tips = _b1_2b_extract_tips(bundles)
        aggregate = _b1_2c_aggregate_tips(tips)

        # Feed stats
        for t in tips.get("tips", []):
            jito_tip_stats.add(t.get("tip_lamports", 0) * LAMPORT_TO_SOL)

        return {
            "status": "completed",
            "agent": "B1-2",
            "slots_scanned": slots,
            "subagents": {
                "b1_2a_bundles": bundles,
                "b1_2b_tip_extractor": tips,
                "b1_2c_aggregator": aggregate,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("B1-2 Fehler: %s", e)
        return {"status": "failed", "agent": "B1-2", "error": str(e)}


def _b1_2a_process_real_bundles(raw_bundles: list[dict]) -> dict:
    """Verarbeitet echte Jito-Bundles aus der API."""
    processed = []
    for b in raw_bundles:
        processed.append({
            "slot": b.get("slot", 0),
            "leader": b.get("leader_pubkey", b.get("leader", "")),
            "bundle_count": 1,
            "total_tips_lamports": b.get("total_tip_lamports", 0),
            "tx_count": b.get("transaction_count", b.get("tx_count", 1)),
        })
    return {
        "status": "ok",
        "subagent": "B1-2a",
        "role": "Jito-Bundle-Sub",
        "source": "jito_api_live",
        "bundles_found": len(processed),
        "bundles": processed,
    }


def _b1_2a_collect_jito_bundles_demo(slots: int) -> dict:
    """Demo-Bundles für Offline-Entwicklung."""
    demo_bundles = []
    for i in range(slots):
        demo_bundles.append({
            "slot": 300_000_000 + i,
            "leader": f"validator_{100 + i}",
            "bundle_count": 3 + i % 5,
            "total_tips_lamports": 500_000 + i * 100_000,
            "tx_count": 15 + i * 2,
        })

    return {
        "status": "ok",
        "subagent": "B1-2a",
        "role": "Jito-Bundle-Sub",
        "bundles_found": len(demo_bundles),
        "bundles": demo_bundles,
    }


def _b1_2b_extract_tips(bundles_result: dict) -> dict:
    """Extrahiert Tip-Daten aus Jito-Bundles."""
    bundles = bundles_result.get("bundles", [])
    tips_list = []
    for b in bundles:
        total = b.get("total_tips_lamports", 0)
        txs = max(1, b.get("tx_count", 1))
        tips_list.append({
            "slot": b["slot"],
            "leader": b["leader"],
            "tip_lamports": total,
            "tip_sol": round(total * LAMPORT_TO_SOL, 6),
            "tx_count": txs,
            "avg_tip_per_tx_lamports": total // txs,
        })

    return {
        "status": "ok",
        "subagent": "B1-2b",
        "role": "Tip-Extractor",
        "tips": tips_list,
    }


def _b1_2c_aggregate_tips(tips_result: dict) -> dict:
    """Aggregiert Tips: Summe, Durchschnitt, Perzentile pro Block."""
    tips = tips_result.get("tips", [])
    total_sol = sum(t.get("tip_sol", 0) for t in tips)
    avg_per_slot = total_sol / len(tips) if tips else 0

    return {
        "status": "ok",
        "subagent": "B1-2c",
        "role": "Tip-Aggregator",
        "total_tips_sol": round(total_sol, 6),
        "total_tips_usd": round(total_sol * 180, 2),
        "avg_tip_per_slot_sol": round(avg_per_slot, 6),
        "slot_count": len(tips),
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT B1-3: Flashbots-MEV-Listener (Ethereum)
# ═══════════════════════════════════════════════════════════════════════

def b1_3_flashbots_mev_listener(action: str = "poll", max_bundles: int = 20) -> dict:
    """Beobachtet Flashbots-Relay für MEV-Bundles.

    Args:
        action: 'poll' | 'status'
        max_bundles: Max Bundles zu sammeln

    Returns:
        {"status": "...", "bundles_found": N, "subagents": {...}}
    """
    try:
        if action == "status":
            return {
                "status": "ok",
                "agent": "B1-3",
                "chain": "ETHEREUM",
                "api": FLASHBOTS_API,
                "timestamp": _now_iso(),
            }

        # Versuche echten Flashbots-Client, fallback auf Demo
        fb_client = _get_flashbots_client()
        if fb_client:
            try:
                # Sync Stats + Bundle-Analyse
                stats = fb_client.get_builder_stats_sync()
                demo_bundles = []
                if "builders" in stats and stats["builders"]:
                    for name, info in list(stats["builders"].items())[:max_bundles]:
                        demo_bundles.append({
                            "hash": f"fb_{name}",
                            "block": 0,
                            "bribe_eth": info.get("builder_balance", "0"),
                            "tx_count": 0,
                            "searcher": name,
                            "included": True,
                        })

                if demo_bundles:
                    bundles = {"status": "ok", "subagent": "B1-3a",
                               "role": "Bundle-Sub", "source": "flashbots_api_live",
                               "count": len(demo_bundles), "bundles": demo_bundles}
                else:
                    bundles = _b1_3a_collect_bundles_demo(max_bundles)
            except Exception as e:
                logger.warning("Flashbots-Client-Fehler: %s — Fallback auf Demo", e)
                bundles = _b1_3a_collect_bundles_demo(max_bundles)
        else:
            bundles = _b1_3a_collect_bundles_demo(max_bundles)
        parsed = _b1_3b_parse_bundles(bundles)
        success = _b1_3c_track_bundle_success(parsed)

        # Feed stats
        for b in parsed.get("bundles", []):
            bribe_stats.add(b.get("bribe_eth", 0))

        return {
            "status": "completed",
            "agent": "B1-3",
            "bundles_found": bundles.get("count", 0),
            "subagents": {
                "b1_3a_bundle_collector": bundles,
                "b1_3b_bundle_parser": parsed,
                "b1_3c_success_tracker": success,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("B1-3 Fehler: %s", e)
        return {"status": "failed", "agent": "B1-3", "error": str(e)}


def _b1_3a_collect_bundles_demo(max_bundles: int) -> dict:
    """Demo-Bundles für Offline-Entwicklung."""
    demo_bundles = [
        {"hash": f"0xfb{i:04x}", "block": 21_000_050 + i, "bribe_eth": 0.01 + i * 0.005,
         "tx_count": 3 + i % 2, "searcher": f"0xSearcher{i}", "included": i % 3 != 0}
        for i in range(max_bundles)
    ]

    return {
        "status": "ok",
        "subagent": "B1-3a",
        "role": "Bundle-Sub",
        "count": len(demo_bundles),
        "bundles": demo_bundles,
    }


def _b1_3b_parse_bundles(bundles_result: dict) -> dict:
    """Extrahiert Bribe und Transaktionen aus Bundles."""
    raw = bundles_result.get("bundles", [])
    parsed = []
    for b in raw:
        parsed.append({
            "hash": b["hash"],
            "block": b["block"],
            "bribe_eth": round(b["bribe_eth"], 6),
            "bribe_usd": round(b["bribe_eth"] * 3200, 2),
            "tx_count": b["tx_count"],
            "searcher": b["searcher"],
            "included": b["included"],
        })

    total_bribe = sum(p["bribe_eth"] for p in parsed)
    return {
        "status": "ok",
        "subagent": "B1-3b",
        "role": "Bundle-Parser",
        "bundles": parsed,
        "total_bribe_eth": round(total_bribe, 6),
        "avg_bribe_eth": round(total_bribe / len(parsed), 6) if parsed else 0,
    }


def _b1_3c_track_bundle_success(parsed_result: dict) -> dict:
    """Trackt, ob Bundles tatsächlich in Blöcke aufgenommen wurden."""
    bundles = parsed_result.get("bundles", [])
    included = [b for b in bundles if b.get("included")]
    excluded = [b for b in bundles if not b.get("included")]

    inclusion_rate = len(included) / len(bundles) * 100 if bundles else 0

    return {
        "status": "ok",
        "subagent": "B1-3c",
        "role": "Bundle-Success-Tracker",
        "total": len(bundles),
        "included": len(included),
        "excluded": len(excluded),
        "inclusion_rate_pct": round(inclusion_rate, 1),
        "avg_bribe_included_eth": round(
            sum(b["bribe_eth"] for b in included) / len(included), 6
        ) if included else 0,
        "avg_bribe_excluded_eth": round(
            sum(b["bribe_eth"] for b in excluded) / len(excluded), 6
        ) if excluded else 0,
    }


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "b1_1":
        print(json.dumps(b1_1_evm_gas_listener("poll"), indent=2))
    elif cmd == "b1_2":
        print(json.dumps(b1_2_jito_tip_listener("poll"), indent=2))
    elif cmd == "b1_3":
        print(json.dumps(b1_3_flashbots_mev_listener("poll"), indent=2))
    elif cmd == "status":
        print(json.dumps({
            "b1_1": b1_1_evm_gas_listener("status"),
            "b1_2": b1_2_jito_tip_listener("status"),
            "b1_3": b1_3_flashbots_mev_listener("status"),
        }, indent=2))
    else:
        print(f"Verwendung: {sys.argv[0]} [b1_1|b1_2|b1_3|status]")
