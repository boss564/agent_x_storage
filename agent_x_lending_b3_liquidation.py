"""
Agent X — Klasse B: Cluster B3 (Liquidations-Monitor).

Passiver und aktiver Monitor für Liquidations-Events.
Erkennt Kaskaden, feuert Stress-Signale an Klasse C und SymbolicsAgent.

Agenten:
  B3-1: Liquidation-Parser (Stream-Konsument)        — 3 Subagenten
  B3-2: Kaskaden-Detektor (Cascading Liquidations)   — 3 Subagenten
  B3-3: Marktstress-Signal (Bridge zu Klasse C)      — 3 Subagenten

Bridge:
  - B3-2 → C2 (Flash-Loan-Analyst): Kaskade = Arbitrage-Chance
  - B3-3 → SymbolicsAgent: Portfolio-weiter Stress-Alarm
"""

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from agent_x_lending_models import (
    Chain, RiskZone, LendingProtocol, LiquidationEvent,
)

logger = logging.getLogger("klasse_b3_liquidation")

# ─── Konfiguration ───────────────────────────────────────────────────

CASCADE_WINDOW_BLOCKS = int(os.getenv("CASCADE_WINDOW_BLOCKS", "3"))
CASCADE_THRESHOLD = int(os.getenv("CASCADE_THRESHOLD", "3"))  # >= N Liquidationen im Fenster = Kaskade
STRESS_VOLUME_THRESHOLD_USD = float(os.getenv("STRESS_VOLUME_USD", "500000"))  # 500k USD
LIQUIDATION_BONUS_DEFAULT = float(os.getenv("LIQUIDATION_BONUS_DEFAULT", "0.05"))  # 5%


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════
# AGENT B3-1: Liquidation-Parser
# ═══════════════════════════════════════════════════════════════════════

def b3_1_liquidation_parser(
    raw_liquidations: list[dict] | None = None,
) -> dict:
    """Konsumiert Liquidations-Events aus B1-1 (EVM) und B1-2 (Solana).

    Parst Rohdaten in einheitliche LiquidationEvent-Objekte.

    Args:
        raw_liquidations: Liste roher Liquidation-Events

    Returns:
        {"status": "...", "liquidations_parsed": N, "subagents": {...}}
    """
    try:
        raw = raw_liquidations or []

        evm_parsed = _b3_1a_parse_evm_liquidations(raw)
        sol_parsed = _b3_1b_parse_solana_liquidations(raw)
        enriched = _b3_1c_enrich_liquidation_metrics(evm_parsed, sol_parsed)

        return {
            "status": "completed",
            "agent": "B3-1",
            "liquidations_parsed": enriched.get("total_parsed", 0),
            "subagents": {
                "b3_1a_evm_parser": evm_parsed,
                "b3_1b_solana_parser": sol_parsed,
                "b3_1c_metrics_enricher": enriched,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("B3-1 Fehler: %s", e)
        return {"status": "failed", "agent": "B3-1", "error": str(e)}


def _b3_1a_parse_evm_liquidations(events: list[dict]) -> dict:
    """Parst EVM-LiquidationCall-Events."""
    parsed = []
    for ev in events:
        etype = ev.get("_event_type", ev.get("type", ""))
        if "liquidation" not in etype.lower():
            continue

        collateral = ev.get("collateral_asset", "")
        debt_asset = ev.get("debt_asset", "")
        debt_covered = ev.get("debt_to_cover", ev.get("debt_covered", 0))
        collateral_taken = ev.get("liquidated_collateral", ev.get("collateral_taken", 0))

        if isinstance(debt_covered, (int, float)) and debt_covered > 1e12:
            debt_covered = debt_covered / 1e18
        if isinstance(collateral_taken, (int, float)) and collateral_taken > 1e12:
            collateral_taken = collateral_taken / 1e18

        parsed.append({
            "tx_hash": ev.get("tx_hash", ev.get("transactionHash", "")),
            "chain": "ETHEREUM",
            "protocol": "AaveV3",
            "block_number": ev.get("block_number", 0),
            "user_address": ev.get("user", ev.get("user_address", "")),
            "liquidator_address": ev.get("liquidator", ""),
            "collateral_asset": collateral,
            "debt_asset": debt_asset,
            "collateral_taken": collateral_taken,
            "debt_covered": debt_covered,
            "bonus_pct": LIQUIDATION_BONUS_DEFAULT,
            "timestamp": ev.get("timestamp", _now_iso()),
        })

    return {
        "status": "ok",
        "subagent": "B3-1a",
        "role": "EVM-Liquidation-Parser",
        "evm_liquidations": len(parsed),
        "liquidations": parsed,
    }


def _b3_1b_parse_solana_liquidations(events: list[dict]) -> dict:
    """Parst Solana-Liquidations-Events."""
    parsed = []
    for ev in events:
        etype = ev.get("_event_type", ev.get("type", ""))
        if "liquidate" not in etype.lower() and "liquidation" not in etype.lower():
            continue

        parsed.append({
            "tx_hash": ev.get("signature", ev.get("tx_hash", "")),
            "chain": "SOLANA",
            "protocol": "Solend",
            "block_number": 0,
            "slot": ev.get("slot", 0),
            "user_address": ev.get("user", ev.get("user_address", "")),
            "liquidator_address": ev.get("liquidator", ""),
            "collateral_asset": ev.get("collateral_asset", "SOL"),
            "debt_asset": ev.get("debt_asset", "USDC"),
            "collateral_taken": float(ev.get("collateral_taken", 0)),
            "debt_covered": float(ev.get("debt_covered", 0)),
            "bonus_pct": 0.05,  # Solend: 5%
            "timestamp": ev.get("timestamp", _now_iso()),
        })

    return {
        "status": "ok",
        "subagent": "B3-1b",
        "role": "Solana-Liquidation-Parser",
        "solana_liquidations": len(parsed),
        "liquidations": parsed,
    }


def _b3_1c_enrich_liquidation_metrics(
    evm_result: dict,
    sol_result: dict,
) -> dict:
    """Reichert Liquidation-Events mit USD-Werten und Metriken an."""
    all_liq = evm_result.get("liquidations", []) + sol_result.get("liquidations", [])

    # Approximiere USD-Werte
    for liq in all_liq:
        if liq.get("collateral_asset", "") in ("ETH", "wstETH"):
            price = 3200.0
        elif liq.get("collateral_asset", "") == "WBTC":
            price = 65000.0
        elif liq.get("collateral_asset", "") == "SOL":
            price = 180.0
        else:
            price = 1.0  # Stablecoin

        liq["collateral_usd"] = round(liq.get("collateral_taken", 0) * price, 2)
        liq["debt_usd"] = round(liq.get("debt_covered", 0), 2)  # debt ist in stablecoin

    total_collateral_usd = sum(l.get("collateral_usd", 0) for l in all_liq)
    total_debt_usd = sum(l.get("debt_usd", 0) for l in all_liq)

    return {
        "status": "ok",
        "subagent": "B3-1c",
        "role": "Metrics-Enricher",
        "total_parsed": len(all_liq),
        "total_collateral_usd": round(total_collateral_usd, 2),
        "total_debt_usd": round(total_debt_usd, 2),
        "avg_bonus_pct": round(
            sum(l.get("bonus_pct", 0) for l in all_liq) / len(all_liq) * 100, 1
        ) if all_liq else 0,
        "liquidations": all_liq,
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT B3-2: Kaskaden-Detektor (Cascading Liquidations)
# ═══════════════════════════════════════════════════════════════════════

def b3_2_cascade_detector(
    liquidations: list[dict] | None = None,
    window_blocks: int = CASCADE_WINDOW_BLOCKS,
    threshold: int = CASCADE_THRESHOLD,
) -> dict:
    """Erkennt Kaskaden: N+ Liquidationen innerhalb weniger Blöcke.

    Kaskade = Marktstress → Arbitrage-Chance für Flash-Loans.

    Args:
        liquidations: Liste aller Liquidation-Events (aus B3-1)
        window_blocks: Block-Fenster (default 3)
        threshold: Mindestanzahl pro Fenster (default 3)

    Returns:
        {"status": "...", "cascades_detected": N, "subagents": {...}}
    """
    try:
        liq_list = liquidations or []

        blocks = _b3_2a_group_by_block(liq_list)
        cascades = _b3_2b_detect_cascades(blocks, window_blocks, threshold)
        stress = _b3_2c_analyze_cascade_impact(cascades, liq_list)

        return {
            "status": "completed",
            "agent": "B3-2",
            "total_liquidations": len(liq_list),
            "cascades_detected": len(cascades.get("cascades", [])),
            "window_blocks": window_blocks,
            "cascade_threshold": threshold,
            "subagents": {
                "b3_2a_block_grouper": blocks,
                "b3_2b_cascade_scanner": cascades,
                "b3_2c_impact_analyzer": stress,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("B3-2 Fehler: %s", e)
        return {"status": "failed", "agent": "B3-2", "error": str(e)}


def _b3_2a_group_by_block(liquidations: list[dict]) -> dict:
    """Gruppiert Liquidationen nach Block-Nummer."""
    by_block: dict[int, list] = defaultdict(list)
    for liq in liquidations:
        block = liq.get("block_number", liq.get("slot", 0))
        by_block[block].append(liq)

    return {
        "status": "ok",
        "subagent": "B3-2a",
        "role": "Block-Grouper",
        "unique_blocks": len(by_block),
        "blocks_with_multiple": {
            str(b): len(ls) for b, ls in by_block.items() if len(ls) > 1
        },
        "max_per_block": max(len(ls) for ls in by_block.values()) if by_block else 0,
    }


def _b3_2b_detect_cascades(
    blocks: dict,
    window_blocks: int,
    threshold: int,
) -> dict:
    """Scannt in gleitendem Fenster nach Kaskaden.

    Eine Kaskade = sum(liquidations in [block_n, block_n + window]) >= threshold.
    """
    all_blocks = sorted(int(b) for b in blocks.get("unique_blocks", 0) and
                        blocks.get("blocks_with_multiple", {}).keys() or [])

    # Fallback: Berechne aus den Rohdaten
    if not all_blocks and "blocks_with_multiple" in blocks:
        all_blocks = sorted(int(k) for k in blocks.get("blocks_with_multiple", {}).keys())

    cascades = []
    for start_block in all_blocks:
        total_in_window = 0
        affected_blocks = []
        for b in range(start_block, start_block + window_blocks + 1):
            block_str = str(b)
            count = blocks.get("blocks_with_multiple", {}).get(block_str, 0)
            if count > 0:
                total_in_window += count
                affected_blocks.append(b)

        if total_in_window >= threshold:
            cascades.append({
                "start_block": start_block,
                "end_block": start_block + window_blocks,
                "affected_blocks": affected_blocks,
                "total_liquidations": total_in_window,
                "severity": (
                    "extreme" if total_in_window >= threshold * 3
                    else "high" if total_in_window >= threshold * 2
                    else "moderate"
                ),
            })

    return {
        "status": "ok",
        "subagent": "B3-2b",
        "role": "Cascade-Scanner",
        "cascades": cascades,
        "total_cascades": len(cascades),
        "max_cascade_size": max((c["total_liquidations"] for c in cascades), default=0),
    }


def _b3_2c_analyze_cascade_impact(
    cascades_result: dict,
    all_liquidations: list[dict],
) -> dict:
    """Analysiert den Impact von Kaskaden auf den Markt.

    Berechnet: total USD liquidiert, betroffene Assets, Arbitrage-Volumen.
    """
    cascades = cascades_result.get("cascades", [])
    if not cascades:
        return {
            "status": "ok",
            "subagent": "B3-2c",
            "role": "Impact-Analyzer",
            "total_cascade_volume_usd": 0,
            "affected_assets": [],
        }

    # Aggregiere betroffene Assets
    asset_impact: dict[str, float] = defaultdict(float)
    total_volume = 0.0
    for liq in all_liquidations:
        asset = liq.get("collateral_asset", "unknown")
        vol = liq.get("collateral_usd", 0)
        asset_impact[asset] += vol
        total_volume += vol

    most_affected = sorted(asset_impact.items(), key=lambda x: x[1], reverse=True)[:3]

    return {
        "status": "ok",
        "subagent": "B3-2c",
        "role": "Impact-Analyzer",
        "total_cascade_volume_usd": round(total_volume, 2),
        "affected_assets": [
            {"asset": a, "volume_usd": round(v, 2)} for a, v in most_affected
        ],
        "arbitrage_opportunity": total_volume > STRESS_VOLUME_THRESHOLD_USD,
        "recommendation": (
            f"Flash-Loan-Chance: {round(total_volume, 0)} USD in {len(cascades)} Kaskaden"
            if total_volume > STRESS_VOLUME_THRESHOLD_USD
            else "Keine signifikante Arbitrage-Chance"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT B3-3: Marktstress-Signal (Bridge zu Klasse C)
# ═══════════════════════════════════════════════════════════════════════

def b3_3_stress_signal(
    cascade_result: dict | None = None,
    health_factor_data: dict | None = None,
    consensus_health_index: float = 100.0,
) -> dict:
    """Emitter für Marktstress-Signale an SymbolicsAgent und Klasse C.

    Args:
        cascade_result: Output von B3-2 (Kaskaden)
        health_factor_data: Output von B2-2 (Health-Factors)
        consensus_health_index: Von A3-2 (0-100)

    Returns:
        {"status": "...", "signals_emitted": [...], "subagents": {...}}
    """
    try:
        cascades = cascade_result or {}
        hf_data = health_factor_data or {}

        state = _b3_3a_assess_market_state(cascades, hf_data, consensus_health_index)
        signals = _b3_3b_generate_stress_signals(state)
        actions = _b3_3c_recommend_actions(state, signals)

        return {
            "status": "completed",
            "agent": "B3-3",
            "signals_emitted": len(signals),
            "subagents": {
                "b3_3a_market_state": state,
                "b3_3b_stress_signals": signals,
                "b3_3c_recommended_actions": actions,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("B3-3 Fehler: %s", e)
        return {"status": "failed", "agent": "B3-3", "error": str(e)}


def _b3_3a_assess_market_state(
    cascades: dict,
    hf_data: dict,
    consensus_health: float,
) -> dict:
    """Bewertet den globalen Markt-Zustand aus B-Perspektive.

    Kombiniert: Cascade-Status + Portfolio-Risk + Network-Health.
    """
    cascade_count = cascades.get("cascades_detected", 0)
    cascade_volume = cascades.get("subagents", {}).get(
        "b3_2c_impact_analyzer", {},
    ).get("total_cascade_volume_usd", 0)

    portfolio_risk = hf_data.get("subagents", {}).get(
        "b2_2c_risk_assessment", {},
    ).get("portfolio_risk_score", 100)

    watchlist_count = hf_data.get("subagents", {}).get(
        "b2_2c_risk_assessment", {},
    ).get("watchlist_count", 0)

    # Gesamt-Stress-Level (0-100, 0 = maximaler Stress)
    stress = 100.0
    if cascade_count > 0:
        stress -= min(40, cascade_count * 10)
    if cascade_volume > STRESS_VOLUME_THRESHOLD_USD:
        stress -= 20
    if portfolio_risk < 60:
        stress -= 15
    if watchlist_count > 5:
        stress -= 10
    if consensus_health < 70:
        stress -= 15
    stress = max(0.0, stress)

    # Markt-Phase
    if stress >= 80:
        phase = "bull"
    elif stress >= 60:
        phase = "neutral"
    elif stress >= 40:
        phase = "correction"
    elif stress >= 20:
        phase = "crash"
    else:
        phase = "capitulation"

    return {
        "status": "ok",
        "subagent": "B3-3a",
        "role": "Market-State-Assessor",
        "market_stress_index": round(stress, 1),
        "market_phase": phase,
        "components": {
            "cascade_stress": cascade_count > 0,
            "volume_stress": cascade_volume > STRESS_VOLUME_THRESHOLD_USD,
            "portfolio_stress": portfolio_risk < 60,
            "watchlist_stress": watchlist_count > 5,
            "network_stress": consensus_health < 70,
        },
    }


def _b3_3b_generate_stress_signals(state: dict) -> list[dict]:
    """Generiert priorisierte Stress-Signale."""
    phase = state.get("market_phase", "neutral")
    stress = state.get("market_stress_index", 100)
    components = state.get("components", {})

    signals = []

    if components.get("cascade_stress"):
        signals.append({
            "target": "klasse_c_arbitrage",
            "level": "HIGH",
            "type": "CASCADE_LIQUIDATION",
            "message": f"Liquidations-Kaskade erkannt: {stress:.0f}/100 Stress-Index",
            "action": "Flash-Loan-Opportunitäten scannen",
        })

    if components.get("portfolio_stress"):
        watchlist = state.get("watchlist_count", 0)
        signals.append({
            "target": "symbolics_agent",
            "level": "MEDIUM",
            "type": "PORTFOLIO_DEGRADATION",
            "message": f"Portfolio-Risiko erhöht, {watchlist} Positionen nahe Liquidation",
            "action": "Positionen reduzieren oder absichern",
        })

    if phase in ("crash", "capitulation"):
        signals.append({
            "target": "symbolics_agent",
            "level": "CRITICAL",
            "type": "MARKET_CAPITULATION",
            "message": f"Marktphase: {phase} — Stress-Index: {stress:.0f}/100",
            "action": "ALLE DeFi-Operationen pausieren, nur Kapitalerhalt",
        })

    if components.get("network_stress"):
        signals.append({
            "target": "klasse_c_flash_loan",
            "level": "WARNING",
            "type": "NETWORK_INSTABILITY",
            "message": "Netzwerk-Gesundheit eingeschränkt — Flash-Loans riskant",
            "action": "Flash-Loan-Analyse temporär deaktivieren",
        })

    return signals


def _b3_3c_recommend_actions(state: dict, signals: list[dict]) -> dict:
    """Leitet konkrete Handlungsempfehlungen aus den Signalen ab."""
    phase = state.get("market_phase", "neutral")
    actions = []

    critical_signals = [s for s in signals if s.get("level") == "CRITICAL"]
    high_signals = [s for s in signals if s.get("level") == "HIGH"]

    if phase == "capitulation":
        actions.append({
            "priority": 1,
            "action": "SHUTDOWN_DEFI",
            "detail": "Alle Positionen schließen, Kapital in Stablecoins",
            "trigger": "Markt-Kapitulation",
        })
    elif phase == "crash":
        actions.append({
            "priority": 2,
            "action": "REDUCE_EXPOSURE",
            "detail": "Gefährdete Positionen deleverage, Stop-Loss setzen",
            "trigger": "Markt-Crash",
        })
    elif high_signals:
        actions.append({
            "priority": 3,
            "action": "SCAN_ARBITRAGE",
            "detail": "Flash-Loan-Arbitrage scannen, Liquidations-Boni einsammeln",
            "trigger": f"{len(high_signals)} HIGH-Signale",
        })

    if not actions:
        actions.append({
            "priority": 99,
            "action": "MONITOR",
            "detail": "Keine Aktion nötig — Normale Marktbedingungen",
            "trigger": "Standard",
        })

    return {
        "status": "ok",
        "subagent": "B3-3c",
        "role": "Action-Recommender",
        "total_actions": len(actions),
        "actions": actions,
    }


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Demo-Liquidationen
    demo_liq = [
        {"_event_type": "liquidation", "tx_hash": "0xaaa", "block_number": 19000001,
         "user": "0xVictim1", "liquidator": "0xBot1",
         "collateral_asset": "ETH", "debt_asset": "USDC",
         "debt_to_cover": 50_000_000000000000000000, "liquidated_collateral": 16_000000000000000000,
         "timestamp": _now_iso()},
        {"_event_type": "liquidation", "tx_hash": "0xbbb", "block_number": 19000001,
         "user": "0xVictim2", "liquidator": "0xBot2",
         "collateral_asset": "wstETH", "debt_asset": "DAI",
         "debt_to_cover": 30_000_000000000000000000, "liquidated_collateral": 9_000000000000000000,
         "timestamp": _now_iso()},
        {"_event_type": "liquidation", "tx_hash": "0xccc", "block_number": 19000002,
         "user": "0xVictim3", "liquidator": "0xBot1",
         "collateral_asset": "WBTC", "debt_asset": "USDC",
         "debt_to_cover": 80_000_000000, "liquidated_collateral": 1_30000000,
         "timestamp": _now_iso()},
        {"_event_type": "liquidation", "tx_hash": "0xddd", "block_number": 19000002,
         "user": "0xVictim4", "liquidator": "0xBot3",
         "collateral_asset": "ETH", "debt_asset": "USDT",
         "debt_to_cover": 20_000_000000000000000000, "liquidated_collateral": 6_500000000000000000,
         "timestamp": _now_iso()},
    ]

    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"

    if cmd == "b3_1":
        print(json.dumps(b3_1_liquidation_parser(raw_liquidations=demo_liq), indent=2))
    elif cmd == "b3_2":
        b31 = b3_1_liquidation_parser(raw_liquidations=demo_liq)
        all_liq = b31.get("subagents", {}).get("b3_1c_metrics_enricher", {}).get("liquidations", [])
        print(json.dumps(b3_2_cascade_detector(liquidations=all_liq), indent=2))
    elif cmd == "b3_3":
        b31 = b3_1_liquidation_parser(raw_liquidations=demo_liq)
        all_liq = b31.get("subagents", {}).get("b3_1c_metrics_enricher", {}).get("liquidations", [])
        b32 = b3_2_cascade_detector(liquidations=all_liq)
        print(json.dumps(b3_3_stress_signal(
            cascade_result=b32, consensus_health_index=55.0,
        ), indent=2))
    else:
        b31 = b3_1_liquidation_parser(raw_liquidations=demo_liq)
        all_liq = b31.get("subagents", {}).get("b3_1c_metrics_enricher", {}).get("liquidations", [])
        b32 = b3_2_cascade_detector(liquidations=all_liq)
        b33 = b3_3_stress_signal(cascade_result=b32, consensus_health_index=55.0)
        print(json.dumps({"b3_1": b31, "b3_2": b32, "b3_3": b33}, indent=2))
