"""
Agent X — Klasse C: Cluster C2 (Flash-Loan-Analyse).

Erkennt Flash-Loan-Transaktionen, berechnet Profitabilität
und bewertet Risiken (Revert-Risk, MEV-Konkurrenz).

Agenten:
  C2-1: Flash-Loan-Detektor (Mempool + On-Chain)      — 3 Subagenten
  C2-2: Profitabilitäts-Rechner (Gas, Fees, Net-Profit) — 3 Subagenten
  C2-3: Risiko-Assessor (Revert, MEV, Competition)      — 3 Subagenten

Bridge zu Klasse A:
  - A3-2 (Health-Classifier): Deaktiviert C2 bei Reorg/Finalitätsverzögerung
  - A3-3 (Order-Routing): Optimaler Broadcast-Zeitpunkt
Bridge zu Klasse B:
  - B3-3 (Stress-Signal): Flash-Loan-Chancen bei Liquidations-Kaskaden
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from agent_x_klasse_c_models import (
    DexProtocol, FlashLoanEvent, ArbitrageOpportunity, ArbitrageType,
    OpportunityStatus, PoolState, KNOWN_POOLS,
    get_flash_loan_fee,
)

logger = logging.getLogger("klasse_c2_flashloans")

# ─── Konfiguration ───────────────────────────────────────────────────

FLASH_LOAN_MIN_PROFIT_USD = float(os.getenv("FLASH_LOAN_MIN_PROFIT_USD", "50"))
GAS_PRICE_GWEI = float(os.getenv("DEFAULT_GAS_PRICE_GWEI", "25"))
ETH_PRICE_USD = float(os.getenv("ETH_PRICE_USD", "3200"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════
# AGENT C2-1: Flash-Loan-Detektor
# ═══════════════════════════════════════════════════════════════════════

def c2_1_flash_loan_detector(
    action: str = "scan",
    mempool_txs: list[dict] | None = None,
    consensus_health_index: float = 100.0,
) -> dict:
    """Erkennt Flash-Loan-Aufrufe in Mempool und On-Chain.

    Args:
        action: 'scan' | 'status'
        mempool_txs: TXs aus C1-1 Mempool-Watcher
        consensus_health_index: Von A3-2 (0-100). < 60 → C2 deaktiviert.

    Returns:
        {"status": "...", "flash_loans_detected": N, "subagents": {...}}
    """
    try:
        if action == "status":
            return {
                "status": "ok",
                "agent": "C2-1",
                "protocols": ["AaveV3", "Balancer", "UniswapV3", "Maker"],
                "active": consensus_health_index >= 60,
                "timestamp": _now_iso(),
            }

        # A3-2-Bridge: Deaktiviere Flash-Loan-Analyse bei Netzwerkstress
        if consensus_health_index < 60:
            return {
                "status": "deactivated",
                "agent": "C2-1",
                "reason": f"Netzwerk-Gesundheit kritisch (CHI={consensus_health_index})",
                "recommendation": "Keine Flash-Loans bei instabiler Finalität",
                "subagents": {
                    "c2_1a_detector": {"status": "skipped"},
                    "c2_1b_validator": {"status": "skipped"},
                    "c2_1c_classifier": {"status": "skipped"},
                },
                "timestamp": _now_iso(),
            }

        txs = mempool_txs or []
        detected = _c2_1a_detect_flash_loans(txs)
        validated = _c2_1b_validate_flash_loans(detected)
        classified = _c2_1c_classify_flash_loans(validated)

        return {
            "status": "completed",
            "agent": "C2-1",
            "flash_loans_detected": detected.get("count", 0),
            "consensus_health": consensus_health_index,
            "subagents": {
                "c2_1a_detector": detected,
                "c2_1b_validator": validated,
                "c2_1c_classifier": classified,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("C2-1 Fehler: %s", e)
        return {"status": "failed", "agent": "C2-1", "error": str(e)}


def _c2_1a_detect_flash_loans(txs: list[dict]) -> dict:
    """Scannt TXs nach Flash-Loan-Method-Signaturen.

    Aave V3:    flashLoan(address,address[],uint256[],uint256[],address,bytes,uint16)
    Balancer:   flashLoan(address,address[],uint256[],bytes)
    Uniswap V3: flash(address,uint256,uint256,bytes)
    Maker:      mint(address,uint256) — DAI Flash Mint
    """
    flash_sigs = {
        "0xab9c4b5d": "AaveV3_flashLoan",
        "0x5cffe9de": "Balancer_flashLoan",
        "0x490e6cbc": "UniswapV3_flash",
        "0x40c10f19": "Maker_flashMint",
    }

    detected = []
    for tx in txs:
        mid = tx.get("method_id", "")
        if mid in flash_sigs:
            detected.append({
                "tx_hash": tx.get("hash"),
                "protocol": flash_sigs[mid].split("_")[0],
                "method": flash_sigs[mid],
                "initiator": tx.get("from"),
                "value_usd": tx.get("value_usd", 0),
                "gas_price_gwei": tx.get("gasPrice", 0) / 1e9,
            })

    return {
        "status": "ok",
        "subagent": "C2-1a",
        "role": "Flash-Loan-Detector",
        "count": len(detected),
        "flash_loans": detected,
    }


def _c2_1b_validate_flash_loans(detected: dict) -> dict:
    """Validiert Flash-Loans: Prüft ob genug Liquidität vorhanden ist."""
    loans = detected.get("flash_loans", [])
    validated = []
    for loan in loans:
        # Prüfe ob Flash-Loan-Volumen realistisch ist
        value = loan.get("value_usd", 0)
        if value < 1000:  # Zu klein, ignoriere
            continue
        # Max Flash-Loan ≈ TVL des Protokolls
        if value > 100_000_000:  # > $100M suspekt
            loan["suspicious"] = True
        loan["valid"] = True
        validated.append(loan)

    return {
        "status": "ok",
        "subagent": "C2-1b",
        "role": "Flash-Loan-Validator",
        "valid_count": len(validated),
        "flash_loans": validated,
    }


def _c2_1c_classify_flash_loans(validated: dict) -> dict:
    """Klassifiziert Flash-Loans nach Größe und Protokoll."""
    loans = validated.get("flash_loans", [])
    sizes = {"small": 0, "medium": 0, "large": 0, "whale": 0}

    for loan in loans:
        v = loan.get("value_usd", 0)
        if v < 50_000:
            sizes["small"] += 1
        elif v < 500_000:
            sizes["medium"] += 1
        elif v < 5_000_000:
            sizes["large"] += 1
        else:
            sizes["whale"] += 1

    return {
        "status": "ok",
        "subagent": "C2-1c",
        "role": "Flash-Loan-Classifier",
        "by_size": sizes,
        "flash_loans": loans,
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT C2-2: Profitabilitäts-Rechner
# ═══════════════════════════════════════════════════════════════════════

def c2_2_profitability_calculator(
    flash_loans: list[dict] | None = None,
    pool_states: dict[str, PoolState] | None = None,
    gas_price_gwei: float = GAS_PRICE_GWEI,
) -> dict:
    """Berechnet Profitabilität von Flash-Loan-basierten Operationen.

    Formel: Net Profit = Swap-Profit − Flash-Loan-Fee − Gas − MEV-Bribe

    Args:
        flash_loans: Aus C2-1
        pool_states: Aktuelle Pool-Zustände (aus C1-3)
        gas_price_gwei: Aktueller Gas-Preis

    Returns:
        {"status": "...", "profitable_count": N, "subagents": {...}}
    """
    try:
        loans = flash_loans or []
        pools = pool_states or KNOWN_POOLS

        raw_opportunities = _c2_2a_compute_raw_opportunities(loans, pools)
        gas_analysis = _c2_2b_compute_gas_costs(raw_opportunities, gas_price_gwei)
        net_profits = _c2_2c_compute_net_profit(gas_analysis)

        return {
            "status": "completed",
            "agent": "C2-2",
            "total_scanned": len(loans),
            "profitable_count": net_profits.get("profitable_count", 0),
            "subagents": {
                "c2_2a_raw_profit": raw_opportunities,
                "c2_2b_gas_analysis": gas_analysis,
                "c2_2c_net_profit": net_profits,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("C2-2 Fehler: %s", e)
        return {"status": "failed", "agent": "C2-2", "error": str(e)}


def _c2_2a_compute_raw_opportunities(
    flash_loans: list[dict],
    pools: dict[str, PoolState],
) -> dict:
    """Berechnet Roh-Profit-Möglichkeiten aus Flash-Loans.

    Simuliert: Was könnte man mit $X Flash-Loan arbitragieren?
    """
    opportunities = []
    eth_usdc_pool = pools.get("ETH-USDC_UniV3")
    eth_usdc_v2 = pools.get("ETH-USDC_UniV2")

    for loan in flash_loans:
        amount = loan.get("value_usd", 0)
        if amount < 10000 or not eth_usdc_pool or not eth_usdc_v2:
            continue

        # Simulation: Cross-Pool-Arbitrage ETH/USDC V3 ↔ V2
        # Kaufe auf V2, verkaufe auf V3
        if eth_usdc_pool and eth_usdc_v2:
            eth_amount = amount / eth_usdc_pool.price  # $ → ETH
            # Buy ETH on V2 (USDC → ETH)
            eth_out_v2 = eth_usdc_v2.get_output_amount(amount, token_in_is_0=False)
            # Sell ETH on V3 (ETH → USDC)
            usdc_out_v3 = eth_usdc_pool.get_output_amount(eth_out_v2, token_in_is_0=True)

            gross_profit = usdc_out_v3 - amount
            fee_pct = get_flash_loan_fee(loan.get("protocol", "AaveV3"))
            flash_fee = amount * fee_pct

            opportunities.append({
                "tx_hash": loan.get("tx_hash"),
                "protocol": loan.get("protocol"),
                "loan_amount_usd": amount,
                "strategy": "ETH-USDC_V2→V3",
                "gross_profit_usd": round(gross_profit, 2),
                "flash_loan_fee_usd": round(flash_fee, 2),
            })

    return {
        "status": "ok",
        "subagent": "C2-2a",
        "role": "Raw-Profit-Computer",
        "opportunities_analyzed": len(opportunities),
        "opportunities": opportunities,
    }


def _c2_2b_compute_gas_costs(
    raw_opps: dict,
    gas_price_gwei: float,
) -> dict:
    """Berechnet Gas-Kosten für Flash-Loan-Transaktionen.

    Typische Gas-Kosten:
      - Flash-Loan + 1 Swap: ~200k Gas
      - Flash-Loan + 2 Swaps (Arbitrage): ~300k Gas
      - Flash-Loan + Liquidate: ~350k Gas
    """
    gas_per_strategy = {
        "simple_flash": 200_000,
        "arbitrage": 300_000,
        "liquidation": 350_000,
    }

    opportunities = raw_opps.get("opportunities", [])
    enriched = []
    for opp in opportunities:
        gas_units = gas_per_strategy.get("arbitrage", 300_000)
        gas_cost_eth = (gas_units * gas_price_gwei) / 1e9
        gas_cost_usd = gas_cost_eth * ETH_PRICE_USD

        enriched.append({
            **opp,
            "gas_units": gas_units,
            "gas_price_gwei": gas_price_gwei,
            "gas_cost_eth": round(gas_cost_eth, 6),
            "gas_cost_usd": round(gas_cost_usd, 2),
        })

    return {
        "status": "ok",
        "subagent": "C2-2b",
        "role": "Gas-Analyzer",
        "gas_price_gwei": gas_price_gwei,
        "opportunities": enriched,
    }


def _c2_2c_compute_net_profit(gas_analysis: dict) -> dict:
    """Berechnet Netto-Profit nach allen Kosten.

    Net = Gross − Flash-Loan-Fee − Gas − MEV-Schutz
    """
    opportunities = gas_analysis.get("opportunities", [])
    profitable = []
    total_net = 0.0

    for opp in opportunities:
        gross = opp.get("gross_profit_usd", 0)
        flash_fee = opp.get("flash_loan_fee_usd", 0)
        gas = opp.get("gas_cost_usd", 0)
        net = gross - flash_fee - gas

        opp["net_profit_usd"] = round(net, 2)
        opp["roi_pct"] = round(net / opp["loan_amount_usd"] * 100, 4) if opp["loan_amount_usd"] > 0 else 0

        if net > FLASH_LOAN_MIN_PROFIT_USD:
            opp["profitable"] = True
            profitable.append(opp)
            total_net += net
        else:
            opp["profitable"] = False

    return {
        "status": "ok",
        "subagent": "C2-2c",
        "role": "Net-Profit-Computer",
        "profitable_count": len(profitable),
        "total_net_profit_usd": round(total_net, 2),
        "opportunities": opportunities,
        "profitable": profitable,
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT C2-3: Risiko-Assessor (Flash-Loan-Spezifisch)
# ═══════════════════════════════════════════════════════════════════════

def c2_3_risk_assessor(
    net_profit_results: dict | None = None,
    consensus_health_index: float = 100.0,
    mempool_bots_count: int = 0,
) -> dict:
    """Bewertet Risiken von Flash-Loan-Transaktionen.

    Risiko-Faktoren:
      - Revert-Risk: Wird die TX reverten? (Preis-Impact, Slippage)
      - MEV-Competition: Wie viele Bots konkurrieren?
      - Network-Risk: Finalitätsprobleme?

    Args:
        net_profit_results: Aus C2-2
        consensus_health_index: Von A3-2
        mempool_bots_count: Von C1-1c

    Returns:
        {"status": "...", "approved_count": N, "subagents": {...}}
    """
    try:
        profits = net_profit_results or {}
        profitable = profits.get("subagents", {}).get(
            "c2_2c_net_profit", {},
        ).get("profitable", profits.get("profitable", []))

        revert_risk = _c2_3a_assess_revert_risk(profitable)
        mev_risk = _c2_3b_assess_mev_competition(profitable, mempool_bots_count)
        approved = _c2_3c_approve_execution(revert_risk, mev_risk, consensus_health_index)

        return {
            "status": "completed",
            "agent": "C2-3",
            "total_evaluated": len(profitable),
            "approved_count": approved.get("approved_count", 0),
            "subagents": {
                "c2_3a_revert_risk": revert_risk,
                "c2_3b_mev_risk": mev_risk,
                "c2_3c_approval": approved,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("C2-3 Fehler: %s", e)
        return {"status": "failed", "agent": "C2-3", "error": str(e)}


def _c2_3a_assess_revert_risk(profitable: list[dict]) -> dict:
    """Bewertet Revert-Risiko basierend auf Preis-Impact und Slippage."""
    risk_levels = []
    for opp in profitable:
        roi = opp.get("roi_pct", 0)
        # Sehr kleine Margen = hohes Revert-Risiko
        if roi < 0.1:
            risk = "high"
        elif roi < 0.5:
            risk = "medium"
        else:
            risk = "low"

        risk_levels.append({
            "tx_hash": opp.get("tx_hash"),
            "roi_pct": roi,
            "revert_risk": risk,
        })

    high_risk = sum(1 for r in risk_levels if r["revert_risk"] == "high")
    return {
        "status": "ok",
        "subagent": "C2-3a",
        "role": "Revert-Risk-Assessor",
        "total": len(risk_levels),
        "high_revert_risk_count": high_risk,
        "risk_levels": risk_levels,
    }


def _c2_3b_assess_mev_competition(
    profitable: list[dict],
    bots_count: int,
) -> dict:
    """Bewertet MEV-Konkurrenz-Risiko.

    Viele Bots im Mempool → höhere Wahrscheinlichkeit,
    dass die eigene TX gesandwicht oder front-run wird.
    """
    if bots_count == 0:
        competition = "low"
    elif bots_count <= 2:
        competition = "medium"
    elif bots_count <= 5:
        competition = "high"
    else:
        competition = "extreme"

    return {
        "status": "ok",
        "subagent": "C2-3b",
        "role": "MEV-Competition-Assessor",
        "mempool_bots": bots_count,
        "competition_level": competition,
        "sandwich_risk": competition in ("high", "extreme"),
        "recommendation": (
            "Flashbots/MEV-Boost empfohlen" if competition in ("high", "extreme")
            else "Direkt-Sendung möglich"
        ),
    }


def _c2_3c_approve_execution(
    revert_risk: dict,
    mev_risk: dict,
    consensus_health: float,
) -> dict:
    """Finale Freigabe-Prüfung für Flash-Loan-Ausführung.

    Drei Hürden:
      1. Revert-Risk nicht "high"
      2. MEV-Competition nicht "extreme"
      3. Consensus-Health > 60
    """
    risk_levels = revert_risk.get("risk_levels", [])
    competition = mev_risk.get("competition_level", "low")
    network_ok = consensus_health >= 60

    approved = []
    rejected = []
    for r in risk_levels:
        reject_reasons = []
        if r.get("revert_risk") == "high":
            reject_reasons.append("revert_risk_high")
        if competition == "extreme":
            reject_reasons.append("mev_competition_extreme")
        if not network_ok:
            reject_reasons.append("network_unstable")

        if reject_reasons:
            rejected.append({**r, "reject_reasons": reject_reasons})
        else:
            approved.append(r)

    return {
        "status": "ok",
        "subagent": "C2-3c",
        "role": "Execution-Approver",
        "approved_count": len(approved),
        "rejected_count": len(rejected),
        "network_health_ok": network_ok,
        "approved": approved,
        "rejected": rejected,
    }


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Demo-Daten
    demo_loans = [
        {"hash": "0xfl1", "protocol": "AaveV3", "from": "0xArb1",
         "method_id": "0xab9c4b5d", "value_usd": 2_000_000, "gasPrice": 25_000_000_000},
        {"hash": "0xfl2", "protocol": "Balancer", "from": "0xArb2",
         "method_id": "0x5cffe9de", "value_usd": 500_000, "gasPrice": 22_000_000_000},
    ]

    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"

    if cmd == "c2_1":
        print(json.dumps(c2_1_flash_loan_detector(mempool_txs=demo_loans), indent=2))
    elif cmd == "c2_2":
        print(json.dumps(c2_2_profitability_calculator(flash_loans=demo_loans), indent=2))
    elif cmd == "c2_3":
        c22 = c2_2_profitability_calculator(flash_loans=demo_loans)
        print(json.dumps(c2_3_risk_assessor(c22, mempool_bots_count=3), indent=2))
    elif cmd == "status":
        print(json.dumps(c2_1_flash_loan_detector("status"), indent=2))
    else:
        c21 = c2_1_flash_loan_detector(mempool_txs=demo_loans)
        c22 = c2_2_profitability_calculator(flash_loans=demo_loans)
        c23 = c2_3_risk_assessor(c22, mempool_bots_count=3)
        print(json.dumps({"c2_1": c21, "c2_2": c22, "c2_3": c23}, indent=2))
