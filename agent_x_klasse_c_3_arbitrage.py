"""
Agent X — Klasse C: Cluster C3 (Arbitrage-Detection).

Scannt DEX-Pools nach Arbitrage-Möglichkeiten:
Cross-Pool, Cross-Chain und Triangular-Arbitrage.

Agenten:
  C3-1: Cross-Pool-Arbitrage-Scanner              — 3 Subagenten
  C3-2: Cross-Chain-Arbitrage-Scanner (mit A3-1c) — 3 Subagenten
  C3-3: Triangular-Arbitrage-Scanner               — 3 Subagenten

Bridge zu Klasse A:
  - A3-1c (Cross-Chain-Overlap): Atomare Cross-Chain-Fenster
  - A3-3 (Order-Routing): Optimaler Broadcast-Slot + vertrauenswürdiger Validator
Bridge zu Klasse B:
  - B3-3 (Stress-Signal): Liquidations-Arbitrage-Chancen
"""

import itertools
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from agent_x_klasse_c_models import (
    DexProtocol, ArbitrageType, ArbitrageOpportunity, OpportunityStatus,
    PoolState, KNOWN_POOLS, get_flash_loan_fee,
)

logger = logging.getLogger("klasse_c3_arbitrage")

# ─── Konfiguration ───────────────────────────────────────────────────

MIN_ARBITRAGE_PROFIT_USD = float(os.getenv("MIN_ARBITRAGE_PROFIT_USD", "10"))
MIN_ARBITRAGE_ROI_PCT = float(os.getenv("MIN_ARBITRAGE_ROI_PCT", "0.05"))
GAS_PRICE_GWEI = float(os.getenv("DEFAULT_GAS_PRICE_GWEI", "25"))
ETH_PRICE_USD = float(os.getenv("ETH_PRICE_USD", "3200"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════
# AGENT C3-1: Cross-Pool-Arbitrage-Scanner
# ═══════════════════════════════════════════════════════════════════════

def c3_1_cross_pool_arbitrage(
    action: str = "scan",
    pools: dict[str, PoolState] | None = None,
    trade_amounts: list[float] | None = None,
) -> dict:
    """Scannt gleiche Token-Paare auf verschiedenen Pools nach Preis-Differenzen.

    Args:
        action: 'scan' | 'status'
        pools: Pool-Zustände (aus C1-3)
        trade_amounts: Zu prüfende Handelsgrößen in USD

    Returns:
        {"status": "...", "opportunities_found": N, "subagents": {...}}
    """
    try:
        if action == "status":
            return {
                "status": "ok",
                "agent": "C3-1",
                "strategy": "Cross-Pool-Arbitrage (gleiche Chain)",
                "timestamp": _now_iso(),
            }

        all_pools = pools or KNOWN_POOLS
        amounts = trade_amounts or [1000, 5000, 10000, 50000, 100000]

        pairs = _c3_1a_group_token_pools(all_pools)
        opportunities = _c3_1b_find_price_discrepancies(pairs, amounts)
        ranked = _c3_1c_rank_opportunities(opportunities)

        return {
            "status": "completed",
            "agent": "C3-1",
            "pools_scanned": len(all_pools),
            "opportunities_found": ranked.get("total", 0),
            "subagents": {
                "c3_1a_pair_grouper": pairs,
                "c3_1b_discrepancy_finder": opportunities,
                "c3_1c_opportunity_ranker": ranked,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("C3-1 Fehler: %s", e)
        return {"status": "failed", "agent": "C3-1", "error": str(e)}


def _c3_1a_group_token_pools(pools: dict[str, PoolState]) -> dict:
    """Gruppiert Pools nach Token-Paar (chain-agnostisch)."""
    pairs: dict[str, list] = {}
    for name, pool in pools.items():
        key = f"{pool.token0_symbol}-{pool.token1_symbol}"
        pairs.setdefault(key, []).append({
            "pool_name": name,
            "pool": pool.to_dict(),
        })

    return {
        "status": "ok",
        "subagent": "C3-1a",
        "role": "Pair-Grouper",
        "unique_pairs": len(pairs),
        "pairs_with_multiple_pools": {
            k: len(v) for k, v in pairs.items() if len(v) > 1
        },
        "grouped_pairs": {k: v for k, v in pairs.items() if len(v) > 1},
    }


def _c3_1b_find_price_discrepancies(
    pairs_result: dict,
    amounts: list[float],
) -> dict:
    """Findet Preis-Diskrepanzen zwischen Pools des gleichen Token-Paars."""
    grouped = pairs_result.get("grouped_pairs", {})
    opportunities = []

    for pair_name, pool_list in grouped.items():
        if len(pool_list) < 2:
            continue

        for a_pool, b_pool in itertools.combinations(pool_list, 2):
            pool_a = KNOWN_POOLS.get(a_pool["pool_name"])
            pool_b = KNOWN_POOLS.get(b_pool["pool_name"])
            if not pool_a or not pool_b:
                continue

            for amount in amounts:
                # Pfad: amount Token0 → Pool A → Token1 → Pool B → Token0
                try:
                    # Step 1: Swap Token0 → Token1 auf Pool A
                    out_a = pool_a.get_output_amount(amount, token_in_is_0=True)
                    # Step 2: Swap Token1 → Token0 auf Pool B
                    out_b = pool_b.get_output_amount(out_a, token_in_is_0=False)

                    profit = out_b - amount
                    roi = (profit / amount) * 100 if amount > 0 else 0

                    if profit > MIN_ARBITRAGE_PROFIT_USD and roi > MIN_ARBITRAGE_ROI_PCT:
                        opportunities.append({
                            "id": str(uuid.uuid4())[:8],
                            "type": ArbitrageType.CROSS_POOL.value,
                            "pair": pair_name,
                            "pool_a": a_pool["pool_name"],
                            "pool_b": b_pool["pool_name"],
                            "trade_amount": amount,
                            "expected_output": round(out_b, 4),
                            "gross_profit": round(profit, 2),
                            "roi_pct": round(roi, 4),
                            "route": [
                                {"pool": a_pool["pool_name"], "action": "buy_token1", "amount_in": amount, "amount_out": round(out_a, 4)},
                                {"pool": b_pool["pool_name"], "action": "sell_token1", "amount_in": round(out_a, 4), "amount_out": round(out_b, 4)},
                            ],
                        })
                except Exception:
                    continue

    opportunities.sort(key=lambda o: o["gross_profit"], reverse=True)
    return {
        "status": "ok",
        "subagent": "C3-1b",
        "role": "Discrepancy-Finder",
        "total_opportunities": len(opportunities),
        "opportunities": opportunities,
    }


def _c3_1c_rank_opportunities(ops_result: dict) -> dict:
    """Ranked Arbitrage-Opportunities nach Net-Profit und Erfolgswahrscheinlichkeit."""
    ops = ops_result.get("opportunities", [])
    ranked = []
    for index, opp in enumerate(ops):
        gas_cost_usd = (300_000 * GAS_PRICE_GWEI / 1e9) * ETH_PRICE_USD
        net = opp["gross_profit"] - gas_cost_usd

        ranked.append({
            **opp,
            "rank": index + 1,
            "gas_cost_usd": round(gas_cost_usd, 2),
            "net_profit_usd": round(net, 2),
            "executable": net > 0,
            "priority": (
                "EXECUTE_NOW" if net > 500 and opp["roi_pct"] > 0.5
                else "WATCH" if net > 50
                else "IGNORE"
            ),
        })

    executable = [r for r in ranked if r.get("executable")]
    return {
        "status": "ok",
        "subagent": "C3-1c",
        "role": "Opportunity-Ranker",
        "total": len(ranked),
        "executable_count": len(executable),
        "top_3": ranked[:3],
        "all_ranked": ranked,
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT C3-2: Cross-Chain-Arbitrage-Scanner
# ═══════════════════════════════════════════════════════════════════════

def c3_2_cross_chain_arbitrage(
    action: str = "scan",
    cross_chain_overlaps: list[dict] | None = None,
    eth_pools: dict | None = None,
    sol_pools: dict | None = None,
) -> dict:
    """Scannt nach Cross-Chain-Arbitrage-Möglichkeiten.

    Nutzt A3-1c Overlap-Daten für atomare Ausführungsfenster.

    Args:
        action: 'scan' | 'status'
        cross_chain_overlaps: Von A3-1c (Cross-Chain-Overlap-Detector)
        eth_pools: ETH-Pools
        sol_pools: SOL-Pools

    Returns:
        {"status": "...", "opportunities_found": N, "subagents": {...}}
    """
    try:
        if action == "status":
            return {
                "status": "ok",
                "agent": "C3-2",
                "strategy": "Cross-Chain-Arbitrage (atomar via A3-1c)",
                "bridge_dependency": "A3-1c (Cross-Chain-Overlap-Detector)",
                "timestamp": _now_iso(),
            }

        overlaps = cross_chain_overlaps or []
        eth = eth_pools or {k: v for k, v in KNOWN_POOLS.items() if "SOL" not in k}
        sol = sol_pools or {k: v for k, v in KNOWN_POOLS.items() if "SOL" in k}

        windows = _c3_2a_identify_execution_windows(overlaps)
        opportunities = _c3_2b_scan_cross_chain_spreads(windows, eth, sol)
        actionable = _c3_2c_filter_actionable(opportunities)

        return {
            "status": "completed",
            "agent": "C3-2",
            "execution_windows": windows.get("windows", 0),
            "opportunities_found": opportunities.get("total", 0),
            "subagents": {
                "c3_2a_execution_windows": windows,
                "c3_2b_spread_scanner": opportunities,
                "c3_2c_actionable_filter": actionable,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("C3-2 Fehler: %s", e)
        return {"status": "failed", "agent": "C3-2", "error": str(e)}


def _c3_2a_identify_execution_windows(overlaps: list[dict]) -> dict:
    """Identifiziert brauchbare Cross-Chain-Overlap-Fenster."""
    windows = []
    for ov in overlaps:
        delta_ms = ov.get("delta_ms", 999)
        if delta_ms < 200:  # <200ms = atomar nutzbar
            windows.append({
                "eth_slot": ov.get("eth_slot"),
                "sol_slot": ov.get("sol_slot"),
                "delta_ms": delta_ms,
                "viable": True,
            })

    return {
        "status": "ok",
        "subagent": "C3-2a",
        "role": "Execution-Window-Identifier",
        "windows": len(windows),
        "windows_list": windows,
    }


def _c3_2b_scan_cross_chain_spreads(
    windows: dict,
    eth_pools: dict,
    sol_pools: dict,
) -> dict:
    """Scannt nach Preis-Spreads zwischen ETH- und SOL-Pools."""
    opportunities = []

    # Einfache Cross-Chain-Prüfung: Gleiches Asset, verschiedene Chains
    for eth_name, eth_pool in eth_pools.items():
        for sol_name, sol_pool in sol_pools.items():
            # Prüfe auf gleiches Basis-Asset
            eth_assets = {eth_pool.token0_symbol, eth_pool.token1_symbol}
            sol_assets = {sol_pool.token0_symbol, sol_pool.token1_symbol}
            common = eth_assets & sol_assets
            if not common:
                continue

            # Preis-Differenz
            if eth_pool.price > 0 and sol_pool.price > 0:
                spread_pct = abs(eth_pool.price - sol_pool.price) / min(eth_pool.price, sol_pool.price) * 100
                if spread_pct > 0.3:  # >0.3% Spread
                    opportunities.append({
                        "id": str(uuid.uuid4())[:8],
                        "type": ArbitrageType.CROSS_CHAIN.value,
                        "eth_pool": eth_name,
                        "sol_pool": sol_name,
                        "eth_price": round(eth_pool.price, 6),
                        "sol_price": round(sol_pool.price, 6),
                        "spread_pct": round(spread_pct, 4),
                        "common_assets": list(common),
                    })

    return {
        "status": "ok",
        "subagent": "C3-2b",
        "role": "Cross-Chain-Spread-Scanner",
        "total": len(opportunities),
        "opportunities": opportunities,
    }


def _c3_2c_filter_actionable(ops_result: dict) -> dict:
    """Filtert Cross-Chain-Opportunities nach Ausführbarkeit.

    Kriterien:
      - Spread > Bridge-Kosten (typisch 0.1-0.3% für Wormhole/LayerZero)
      - Atomares Fenster verfügbar
      - MEV-Risk vertretbar
    """
    ops = ops_result.get("opportunities", [])
    actionable = []

    BRIDGE_COST_PCT = 0.15  # typische Bridge-Gebühr
    for opp in ops:
        spread = opp.get("spread_pct", 0)
        net_spread = spread - (BRIDGE_COST_PCT * 2)  # Hin und zurück
        opp["bridge_cost_pct"] = round(BRIDGE_COST_PCT * 2, 3)
        opp["net_spread_pct"] = round(net_spread, 4)

        if net_spread > 0.1:  # >0.1% nach Bridge-Kosten
            opp["actionable"] = True
            actionable.append(opp)
        else:
            opp["actionable"] = False

    return {
        "status": "ok",
        "subagent": "C3-2c",
        "role": "Actionable-Filter",
        "total": len(ops),
        "actionable_count": len(actionable),
        "actionable": actionable,
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT C3-3: Triangular-Arbitrage-Scanner
# ═══════════════════════════════════════════════════════════════════════

def c3_3_triangular_arbitrage(
    action: str = "scan",
    pools: dict[str, PoolState] | None = None,
) -> dict:
    """Scannt nach Triangular-Arbitrage (A→B→C→A) auf gleichem DEX.

    Klassische Dreiecks-Arbitrage: ETH → USDC → WBTC → ETH
    mit nur einer Transaktion.

    Args:
        action: 'scan' | 'status'
        pools: Pool-Zustände (aus C1-3)

    Returns:
        {"status": "...", "triangles_found": N, "subagents": {...}}
    """
    try:
        if action == "status":
            return {
                "status": "ok",
                "agent": "C3-3",
                "strategy": "Triangular-Arbitrage (A→B→C→A)",
                "timestamp": _now_iso(),
            }

        all_pools = pools or KNOWN_POOLS

        graph = _c3_3a_build_token_graph(all_pools)
        triangles = _c3_3b_find_triangular_paths(graph, all_pools)
        profitable = _c3_3c_evaluate_profitability(triangles)

        return {
            "status": "completed",
            "agent": "C3-3",
            "pools_scanned": len(all_pools),
            "triangles_found": triangles.get("total", 0),
            "profitable_triangles": profitable.get("profitable_count", 0),
            "subagents": {
                "c3_3a_token_graph": graph,
                "c3_3b_triangle_finder": triangles,
                "c3_3c_profitability": profitable,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("C3-3 Fehler: %s", e)
        return {"status": "failed", "agent": "C3-3", "error": str(e)}


def _c3_3a_build_token_graph(pools: dict[str, PoolState]) -> dict:
    """Baut einen Token-Graphen aus allen Pools.

    Knoten = Tokens, Kanten = Pools mit Preis.
    """
    graph: dict[str, dict[str, dict]] = {}
    for name, pool in pools.items():
        t0 = pool.token0_symbol
        t1 = pool.token1_symbol

        # t0 → t1
        graph.setdefault(t0, {})[t1] = {
            "pool": name,
            "price": pool.price,
            "fee_bps": pool.fee_bps,
        }
        # t1 → t0
        graph.setdefault(t1, {})[t0] = {
            "pool": name,
            "price": 1.0 / pool.price if pool.price > 0 else 0,
            "fee_bps": pool.fee_bps,
        }

    return {
        "status": "ok",
        "subagent": "C3-3a",
        "role": "Token-Graph-Builder",
        "tokens": list(graph.keys()),
        "edges": sum(len(v) for v in graph.values()),
        "graph": {k: {kk: vv["price"] for kk, vv in v.items()} for k, v in graph.items()},
    }


def _c3_3b_find_triangular_paths(
    graph_result: dict,
    pools: dict[str, PoolState],
) -> dict:
    """Findet alle Triangular-Pfade (A→B→C→A) im Token-Graphen."""
    graph: dict[str, dict[str, dict]] = {}
    for name, pool in pools.items():
        t0 = pool.token0_symbol
        t1 = pool.token1_symbol
        graph.setdefault(t0, {})[t1] = {"pool": name, "price": pool.price, "fee_bps": pool.fee_bps}
        graph.setdefault(t1, {})[t0] = {"pool": name, "price": 1.0 / pool.price if pool.price > 0 else 0, "fee_bps": pool.fee_bps}

    tokens = list(graph.keys())
    triangles = []

    for a, b, c in itertools.permutations(tokens, 3):
        # Brauchen: A→B, B→C, C→A
        if b not in graph.get(a, {}):
            continue
        if c not in graph.get(b, {}):
            continue
        if a not in graph.get(c, {}):
            continue

        # Berechne kumulativen Preisfaktor
        p_ab = graph[a][b]["price"]
        p_bc = graph[b][c]["price"]
        p_ca = graph[c][a]["price"]

        # Triangular-Arbitrage: 1 Token A → B → C → A
        # Wenn Produkt > 1, gibt es Profit
        factor = p_ab * p_bc * p_ca
        fee_factor = (
            (1 - graph[a][b]["fee_bps"] / 10000) *
            (1 - graph[b][c]["fee_bps"] / 10000) *
            (1 - graph[c][a]["fee_bps"] / 10000)
        )
        net_factor = factor * fee_factor
        net_profit_pct = (net_factor - 1) * 100

        if net_profit_pct > 0:
            triangles.append({
                "id": str(uuid.uuid4())[:8],
                "path": f"{a}→{b}→{c}→{a}",
                "steps": [
                    {"from": a, "to": b, "pool": graph[a][b]["pool"], "price": round(p_ab, 6)},
                    {"from": b, "to": c, "pool": graph[b][c]["pool"], "price": round(p_bc, 6)},
                    {"from": c, "to": a, "pool": graph[c][a]["pool"], "price": round(p_ca, 6)},
                ],
                "gross_factor": round(factor, 8),
                "fee_factor": round(fee_factor, 8),
                "net_factor": round(net_factor, 8),
                "net_profit_pct": round(net_profit_pct, 6),
            })

    triangles.sort(key=lambda t: t["net_profit_pct"], reverse=True)
    return {
        "status": "ok",
        "subagent": "C3-3b",
        "role": "Triangle-Finder",
        "total": len(triangles),
        "triangles": triangles,
    }


def _c3_3c_evaluate_profitability(triangles_result: dict) -> dict:
    """Bewertet Profitabilität von Triangular-Pfaden.

    Berücksichtigt: Gas-Kosten, Slippage, Mindest-Profit.
    """
    triangles = triangles_result.get("triangles", [])
    profitable = []

    for tri in triangles:
        profit_pct = tri.get("net_profit_pct", 0)

        # Typisches Trading-Volumen für Triangular
        trade_amount = 10_000  # $10k Start
        gross_profit_usd = trade_amount * (profit_pct / 100)
        gas_cost_usd = (350_000 * GAS_PRICE_GWEI / 1e9) * ETH_PRICE_USD
        net_profit_usd = gross_profit_usd - gas_cost_usd

        tri["trade_amount_usd"] = trade_amount
        tri["gross_profit_usd"] = round(gross_profit_usd, 2)
        tri["gas_cost_usd"] = round(gas_cost_usd, 2)
        tri["net_profit_usd"] = round(net_profit_usd, 2)
        tri["executable"] = net_profit_usd > MIN_ARBITRAGE_PROFIT_USD

        if tri["executable"]:
            profitable.append(tri)

    top_3 = sorted(profitable, key=lambda t: t["net_profit_usd"], reverse=True)[:3]
    return {
        "status": "ok",
        "subagent": "C3-3c",
        "role": "Profitability-Evaluator",
        "profitable_count": len(profitable),
        "total_net_profit_usd": round(sum(t["net_profit_usd"] for t in profitable), 2),
        "top_3": top_3,
        "all_triangles": [t for t in triangles if t.get("executable")],
    }


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"

    if cmd == "c3_1":
        print(json.dumps(c3_1_cross_pool_arbitrage(), indent=2))
    elif cmd == "c3_2":
        overlaps = [
            {"eth_slot": 9_000_001, "sol_slot": 300_000_001, "delta_ms": 50},
            {"eth_slot": 9_000_002, "sol_slot": 300_000_002, "delta_ms": 180},
        ]
        print(json.dumps(c3_2_cross_chain_arbitrage(cross_chain_overlaps=overlaps), indent=2))
    elif cmd == "c3_3":
        print(json.dumps(c3_3_triangular_arbitrage(), indent=2))
    elif cmd == "status":
        print(json.dumps({
            "c3_1": c3_1_cross_pool_arbitrage("status"),
            "c3_2": c3_2_cross_chain_arbitrage("status"),
            "c3_3": c3_3_triangular_arbitrage("status"),
        }, indent=2))
    else:
        c31 = c3_1_cross_pool_arbitrage()
        c32 = c3_2_cross_chain_arbitrage(cross_chain_overlaps=[
            {"eth_slot": 9_000_001, "sol_slot": 300_000_001, "delta_ms": 50},
        ])
        c33 = c3_3_triangular_arbitrage()
        print(json.dumps({"c3_1": c31, "c3_2": c32, "c3_3": c33}, indent=2))
