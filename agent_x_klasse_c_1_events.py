"""
Agent X — Klasse C: Cluster C1 (DeFi-Event-Ingestion).

Rohdaten-Beschaffung von DEX-Events: Mempool-Überwachung,
Swap-Event-Parsing und Pool-Liquiditäts-Monitoring.

Agenten:
  C1-1: Mempool-Watcher (Pending-Transaction-Analyse)  — 3 Subagenten
  C1-2: Swap-Event-Parser (Uniswap V3, Curve, etc.)   — 3 Subagenten
  C1-3: Pool-State-Monitor (Liquidität, Preis, TVL)    — 3 Subagenten
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from agent_x_klasse_c_models import (
    DexProtocol, SwapEvent, PoolState, ArbitrageType, KNOWN_POOLS,
)

logger = logging.getLogger("klasse_c1_events")

# ─── Konfiguration ───────────────────────────────────────────────────

MEMPOOL_POLL_MS = int(os.getenv("MEMPOOL_POLL_MS", "2000"))
SWAP_SIZE_THRESHOLD_USD = float(os.getenv("SWAP_SIZE_THRESHOLD_USD", "10000"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════
# AGENT C1-1: Mempool-Watcher
# ═══════════════════════════════════════════════════════════════════════

def c1_1_mempool_watcher(
    action: str = "poll",
    max_txs: int = 200,
) -> dict:
    """Überwacht den Mempool auf relevante DeFi-Transaktionen.

    Erkennt: Swap-TXs, Flash-Loan-Aufrufe, große Transfers,
    Sandwich-fähige Transaktionen.

    Args:
        action: 'poll' | 'status'
        max_txs: Max Transaktionen pro Poll

    Returns:
        {"status": "...", "txs_found": N, "subagents": {...}}
    """
    try:
        if action == "status":
            return {
                "status": "ok",
                "agent": "C1-1",
                "targets": ["UniswapV3", "AaveV3", "Curve", "Balancer"],
                "poll_interval_ms": MEMPOOL_POLL_MS,
                "timestamp": _now_iso(),
            }

        raw_txs = _c1_1a_fetch_pending_txs(max_txs)
        classified = _c1_1b_classify_transactions(raw_txs)
        sandwiches = _c1_1c_detect_sandwich_targets(classified)

        return {
            "status": "completed",
            "agent": "C1-1",
            "total_txs_scanned": raw_txs.get("txs_scanned", 0),
            "subagents": {
                "c1_1a_tx_fetcher": raw_txs,
                "c1_1b_classifier": classified,
                "c1_1c_sandwich_detector": sandwiches,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("C1-1 Fehler: %s", e)
        return {"status": "failed", "agent": "C1-1", "error": str(e)}


def _c1_1a_fetch_pending_txs(max_txs: int) -> dict:
    """Holt pending Transactions aus dem Mempool.

    Im Produktivbetrieb: eth_subscribe("newPendingTransactions") via WebSocket.
    Hier: Simulation mit typischen DeFi-TX-Mustern.
    """
    known_routers = [
        "0xE592427A0AEce92De3Edee1F18E0157C05861564",  # Uniswap V3 Router
        "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",  # Uniswap V2 Router
        "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",  # Aave V3 Pool
    ]

    # Simulierte Mempool-TXs (typische Strukturen)
    simulated = [
        {
            "hash": "0xm1", "from": "0xTrader1", "to": known_routers[0],
            "input": "0x5ae401dc...", "value": 0, "gasPrice": 25_000_000_000,
            "method_id": "0x5ae401dc",  # exactInputSingle (Uniswap V3)
            "value_usd": 150_000,
        },
        {
            "hash": "0xm2", "from": "0xTrader2", "to": known_routers[2],
            "input": "0xab9c4b5d...", "value": 0, "gasPrice": 22_000_000_000,
            "method_id": "0xab9c4b5d",  # flashLoan (Aave V3)
            "value_usd": 2_000_000,
        },
        {
            "hash": "0xm3", "from": "0xBot1", "to": known_routers[1],
            "input": "0x7ff36ab5...", "value": 5_000_000_000_000_000_000, "gasPrice": 80_000_000_000,
            "method_id": "0x7ff36ab5",  # swapExactETHForTokens (Uniswap V2)
            "value_usd": 16_000, "high_gas": True,  # Sandwich-Bot!
        },
        {
            "hash": "0xm4", "from": "0xTrader3", "to": known_routers[0],
            "input": "0x5ae401dc...", "value": 0, "gasPrice": 20_000_000_000,
            "method_id": "0x5ae401dc",
            "value_usd": 45_000,
        },
    ]

    return {
        "status": "ok",
        "subagent": "C1-1a",
        "role": "TX-Fetcher",
        "txs_scanned": len(simulated),
        "known_routers_monitored": len(known_routers),
        "transactions": simulated[:max_txs],
    }


def _c1_1b_classify_transactions(fetch_result: dict) -> dict:
    """Klassifiziert Mempool-TXs nach Typ.

    Methoden-Signaturen:
      - 0x5ae401dc: exactInputSingle (Uniswap V3)
      - 0x7ff36ab5: swapExactETHForTokens (Uniswap V2)
      - 0xab9c4b5d: flashLoan (Aave V3)
      - 0x38ed1739: swapExactTokensForTokens (Uniswap V2)
    """
    txs = fetch_result.get("transactions", [])
    classified = {"swap": [], "flash_loan": [], "large_transfer": [], "sandwich_candidate": [], "other": []}

    swap_ids = {"0x5ae401dc", "0x7ff36ab5", "0x38ed1739", "0x04e45aaf"}
    flash_ids = {"0xab9c4b5d", "0x5cffe9de"}

    for tx in txs:
        mid = tx.get("method_id", "")
        if mid in flash_ids:
            classified["flash_loan"].append(tx)
        elif mid in swap_ids:
            classified["swap"].append(tx)
            if tx.get("high_gas") or tx.get("gasPrice", 0) > 50_000_000_000:
                classified["sandwich_candidate"].append(tx)
        elif tx.get("value", 0) > 1_000_000_000_000_000_000_000:  # >1000 ETH
            classified["large_transfer"].append(tx)
        else:
            classified["other"].append(tx)

    total = sum(len(v) for v in classified.values())
    return {
        "status": "ok",
        "subagent": "C1-1b",
        "role": "TX-Classifier",
        "total_classified": total,
        "by_type": {k: len(v) for k, v in classified.items()},
        "classified_txs": classified,
    }


def _c1_1c_detect_sandwich_targets(classified: dict) -> dict:
    """Erkennt potenzielle Sandwich-Angriffsziele im Mempool.

    Sandwich-Indikatoren:
      - Swap mit hohem Slippage-Toleranz (großes amountOutMin)
      - TX wartet lange im Mempool (> 3 Blöcke)
      - Hoher Gas-Preis (MEV-Bot-Aktivität)
    """
    sandwich_candidates = classified.get("classified_txs", {}).get("sandwich_candidate", [])
    swaps = classified.get("classified_txs", {}).get("swap", [])

    high_value_targets = []
    for tx in swaps:
        if tx.get("value_usd", 0) > SWAP_SIZE_THRESHOLD_USD:
            high_value_targets.append({
                "tx_hash": tx.get("hash"),
                "from": tx.get("from"),
                "value_usd": tx.get("value_usd"),
                "risk": "high" if tx.get("high_gas") else "medium",
            })

    return {
        "status": "ok",
        "subagent": "C1-1c",
        "role": "Sandwich-Detector",
        "sandwich_bots_detected": len(sandwich_candidates),
        "high_value_targets": len(high_value_targets),
        "targets": high_value_targets,
        "recommendation": (
            f"VORSICHT: {len(sandwich_candidates)} MEV-Bots im Mempool aktiv"
            if sandwich_candidates else "Mempool sauber"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT C1-2: Swap-Event-Parser
# ═══════════════════════════════════════════════════════════════════════

def c1_2_swap_event_parser(
    action: str = "parse",
    raw_swaps: list[dict] | None = None,
) -> dict:
    """Parst Swap-Events von Uniswap V2/V3, Curve, Balancer, SushiSwap.

    Args:
        action: 'parse' | 'status'
        raw_swaps: Rohe Swap-Daten aus Logs/Mempool

    Returns:
        {"status": "...", "swaps_parsed": N, "subagents": {...}}
    """
    try:
        if action == "status":
            return {
                "status": "ok",
                "agent": "C1-2",
                "protocols": ["UniswapV3", "UniswapV2", "Curve", "Balancer", "SushiSwap"],
                "timestamp": _now_iso(),
            }

        swaps = raw_swaps or _demo_swaps()

        evm_swaps = _c1_2a_parse_evm_swaps(swaps)
        sol_swaps = _c1_2b_parse_solana_swaps(swaps)
        anomalies = _c1_2c_detect_price_anomalies(evm_swaps, sol_swaps)

        return {
            "status": "completed",
            "agent": "C1-2",
            "total_swaps_parsed": evm_swaps.get("evm_swaps", 0) + sol_swaps.get("sol_swaps", 0),
            "subagents": {
                "c1_2a_evm_swap_parser": evm_swaps,
                "c1_2b_sol_swap_parser": sol_swaps,
                "c1_2c_anomaly_detector": anomalies,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("C1-2 Fehler: %s", e)
        return {"status": "failed", "agent": "C1-2", "error": str(e)}


def _c1_2a_parse_evm_swaps(swaps: list[dict]) -> dict:
    """Parst EVM-Swap-Events (Uniswap V3 Swap-Event, V2 Swap-Event)."""
    parsed = []
    for s in swaps:
        if s.get("chain", "").upper() in ("SOLANA", "SOL"):
            continue

        amount0 = s.get("amount0", 0)
        amount1 = s.get("amount1", 0)
        token_in = s.get("token0", s.get("token_in", "ETH"))
        token_out = s.get("token1", s.get("token_out", "USDC"))
        amount_in = abs(amount0) if amount0 < 0 else abs(amount1) if amount1 < 0 else s.get("amount_in", 0)
        amount_out = abs(amount1) if amount1 > 0 else abs(amount0) if amount0 > 0 else s.get("amount_out", 0)

        parsed.append(SwapEvent(
            tx_hash=s.get("tx_hash", s.get("transactionHash", "")),
            chain="ETHEREUM",
            protocol=DexProtocol.UNISWAP_V3,
            block_number=s.get("block_number", 0),
            token_in=token_in,
            token_out=token_out,
            amount_in=amount_in,
            amount_out=amount_out,
            pool_address=s.get("pool_address", s.get("address", "")),
            sender=s.get("sender", s.get("from", "")),
            recipient=s.get("recipient", s.get("to", "")),
        ))

    return {
        "status": "ok",
        "subagent": "C1-2a",
        "role": "EVM-Swap-Parser",
        "evm_swaps": len(parsed),
        "total_volume_usd": sum(s.volume_usd for s in parsed),
        "swaps": [s.to_dict() for s in parsed],
    }


def _c1_2b_parse_solana_swaps(swaps: list[dict]) -> dict:
    """Parst Solana-Swap-Events (Orca, Raydium, Jupiter)."""
    parsed = []
    for s in swaps:
        if s.get("chain", "").upper() not in ("SOLANA", "SOL"):
            continue
        parsed.append({
            "tx_hash": s.get("tx_hash", ""),
            "protocol": s.get("protocol", "Orca"),
            "token_in": s.get("token_in", "SOL"),
            "token_out": s.get("token_out", "USDC"),
            "amount_in": s.get("amount_in", 0),
            "amount_out": s.get("amount_out", 0),
        })

    return {
        "status": "ok",
        "subagent": "C1-2b",
        "role": "Solana-Swap-Parser",
        "sol_swaps": len(parsed),
        "swaps": parsed,
    }


def _c1_2c_detect_price_anomalies(evm_result: dict, sol_result: dict) -> dict:
    """Erkennt Preisanomalien, die auf Arbitrage-Chancen hindeuten.

    Anomalie-Indikatoren:
      - Gleiches Token-Paar handelt auf verschiedenen Pools zu unterschiedlichen Preisen
      - Plötzliche große Swaps, die den Preis > 1% bewegen
    """
    evm_swaps_raw = evm_result.get("swaps", [])
    anomalies = []

    # Gruppiere nach Token-Paar (ohne SwapEvent-Rekonstruktion)
    pairs: dict[str, list] = {}
    for s in evm_swaps_raw:
        if not isinstance(s, dict):
            continue
        token_in = s.get("token_in", "")
        token_out = s.get("token_out", "")
        amount_in = s.get("amount_in", 0)
        amount_out = s.get("amount_out", 0)
        key = f"{token_in}-{token_out}"
        price = amount_out / amount_in if amount_in > 0 else 0
        pairs.setdefault(key, []).append({"price": price, "tx": s.get("tx_hash")})

    # Prüfe Preis-Abweichungen innerhalb eines Paars
    for pair, swap_data in pairs.items():
        if len(swap_data) < 2:
            continue
        prices = [d["price"] for d in swap_data if d["price"] > 0]
        if len(prices) < 2:
            continue
        max_p = max(prices)
        min_p = min(prices)
        spread_pct = ((max_p - min_p) / min_p * 100) if min_p > 0 else 0
        if spread_pct > 0.5:  # >0.5% Spread = Arbitrage-Chance
            anomalies.append({
                "pair": pair,
                "max_price": round(max_p, 8),
                "min_price": round(min_p, 8),
                "spread_pct": round(spread_pct, 4),
                "opportunity": spread_pct > 1.0,
            })

    return {
        "status": "ok",
        "subagent": "C1-2c",
        "role": "Anomaly-Detector",
        "anomalies_found": len(anomalies),
        "arbitrage_opportunities": sum(1 for a in anomalies if a.get("opportunity")),
        "anomalies": anomalies,
    }


def _demo_swaps() -> list[dict]:
    """Demo-Swap-Daten für Test und Entwicklung."""
    return [
        {"tx_hash": "0xs1", "chain": "ETHEREUM", "amount0": -50.0, "amount1": 160000.0,
         "token0": "ETH", "token1": "USDC", "pool_address": "0x88e6...",
         "sender": "0xTrader1", "block_number": 19000100},
        {"tx_hash": "0xs2", "chain": "ETHEREUM", "amount0": 160500.0, "amount1": -50.0,
         "token0": "ETH", "token1": "USDC", "pool_address": "0xB4e1...",
         "sender": "0xArbitrageur1", "block_number": 19000100},
        {"tx_hash": "0xs3", "chain": "SOLANA", "amount_in": 1000, "amount_out": 178000,
         "token_in": "SOL", "token_out": "USDC", "protocol": "Orca"},
    ]


# ═══════════════════════════════════════════════════════════════════════
# AGENT C1-3: Pool-State-Monitor
# ═══════════════════════════════════════════════════════════════════════

def c1_3_pool_state_monitor(action: str = "poll") -> dict:
    """Überwacht Liquidität, Preis und TVL bekannter DEX-Pools.

    Args:
        action: 'poll' | 'status'

    Returns:
        {"status": "...", "pools_monitored": N, "subagents": {...}}
    """
    try:
        if action == "status":
            return {
                "status": "ok",
                "agent": "C1-3",
                "known_pools": len(KNOWN_POOLS),
                "chains": ["ETHEREUM", "SOLANA"],
                "timestamp": _now_iso(),
            }

        snapshot = _c1_3a_snapshot_pools()
        tvl_analysis = _c1_3b_analyze_tvl_changes(snapshot)
        liquidity = _c1_3c_assess_liquidity_depth(snapshot)

        return {
            "status": "completed",
            "agent": "C1-3",
            "pools_monitored": len(KNOWN_POOLS),
            "subagents": {
                "c1_3a_pool_snapshot": snapshot,
                "c1_3b_tvl_analysis": tvl_analysis,
                "c1_3c_liquidity_depth": liquidity,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("C1-3 Fehler: %s", e)
        return {"status": "failed", "agent": "C1-3", "error": str(e)}


def _c1_3a_snapshot_pools() -> dict:
    """Erstellt Snapshot aller bekannten Pools."""
    pools = {}
    for name, pool in KNOWN_POOLS.items():
        pools[name] = pool.to_dict()

    return {
        "status": "ok",
        "subagent": "C1-3a",
        "role": "Pool-Snapshot",
        "pools": pools,
        "total_tvl_usd": sum(p.tvl_usd for p in KNOWN_POOLS.values()),
    }


def _c1_3b_analyze_tvl_changes(snapshot: dict) -> dict:
    """Analysiert TVL-Änderungen gegenüber letztem Snapshot."""
    return {
        "status": "ok",
        "subagent": "C1-3b",
        "role": "TVL-Analyzer",
        "tvl_changes": {},
        "significant_outflows": [],
    }


def _c1_3c_assess_liquidity_depth(snapshot: dict) -> dict:
    """Bewertet Liquiditätstiefe: Wie viel Kapital kann bewegt werden ohne >1% Slippage?"""
    depth_report = {}
    for name, pool in KNOWN_POOLS.items():
        # Wieviel Input für 1% Price Impact?
        # CPMM: price_impact ≈ amount_in / reserve_in
        impact_amount = pool.reserve0 * 0.01  # 1% der Reserve
        depth_report[name] = {
            "pool": name,
            "reserve0": pool.reserve0,
            "reserve1": pool.reserve1,
            "max_trade_1pct_impact": round(impact_amount, 2),
            "max_trade_1pct_impact_usd": round(impact_amount * pool.price, 2),
            "arbitrage_feasible": impact_amount * pool.price > 1000,  # >$1k Volumen möglich
        }

    return {
        "status": "ok",
        "subagent": "C1-3c",
        "role": "Liquidity-Depth-Assessor",
        "depth_report": depth_report,
        "pools_with_deep_liquidity": sum(
            1 for d in depth_report.values() if d.get("arbitrage_feasible")
        ),
    }


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "c1_1":
        print(json.dumps(c1_1_mempool_watcher("poll"), indent=2))
    elif cmd == "c1_2":
        print(json.dumps(c1_2_swap_event_parser("parse"), indent=2))
    elif cmd == "c1_3":
        print(json.dumps(c1_3_pool_state_monitor("poll"), indent=2))
    elif cmd == "status":
        print(json.dumps({
            "c1_1": c1_1_mempool_watcher("status"),
            "c1_2": c1_2_swap_event_parser("status"),
            "c1_3": c1_3_pool_state_monitor("status"),
        }, indent=2))
    else:
        print(f"Verwendung: {sys.argv[0]} [c1_1|c1_2|c1_3|status]")
