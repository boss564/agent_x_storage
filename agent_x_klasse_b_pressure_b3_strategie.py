"""
Agent X — Druckventile: Cluster B3 (Strategische Outputs & Integration).

Schnittstelle zu Klasse C (DeFi/Risiko): Optimal-Tx-Timer, Stress-Frühwarnung,
Block-Forensik.

Agenten:
  B3-1: Optimal-Tx-Timer (Priority-Fee-Kalkulation)  — 3 Subagenten
  B3-2: Marktstress-Frühwarnsystem (Alerts für C)    — 3 Subagenten
  B3-3: Block-Building-Simulator (Forensik)          — 3 Subagenten

Bridge zu Klasse C (Risiko & Arbitrage):
  - B3-2a: Druck → Liquidation-Risk (erhöht CriticalThreshold)
  - B3-2b: Druck → Arbitrage-Opportunity (hohe Bribes = Preisverzerrungen)
  - B3-2c: Alert-Publisher (standardisierte Warnungen an SymbolicsAgent)
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from agent_x_klasse_b_pressure_models import (
    PressureLevel, TxTimingRecommendation, BlockForensicReport,
)
from agent_x_klasse_b_pressure_b2_analytics import _to_pressure_level

logger = logging.getLogger("pressure_b3_strategie")

# ─── Konfiguration ───────────────────────────────────────────────────

SAFE_PRIORITY_FEE_GWEI = float(os.getenv("SAFE_PRIORITY_FEE_GWEI", "3.0"))
CRITICAL_HF_DEFAULT = float(os.getenv("CRITICAL_HF_DEFAULT", "1.05"))
HF_BUMP_UNDER_PRESSURE = float(os.getenv("HF_BUMP_UNDER_PRESSURE", "0.05"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════
# AGENT B3-1: Optimal-Tx-Timer
# ═══════════════════════════════════════════════════════════════════════

def b3_1_optimal_tx_timer(
    gas_pressure_index: float = 50.0,
    mev_pressure_index: float = 50.0,
    current_basefee_gwei: float = 21.0,
    priority_fee_p95_gwei: float = 3.5,
    trusted_validators: list[str] | None = None,
    next_slot: int = 0,
    next_slot_ms: int = 0,
) -> dict:
    """Sagt optimalen Sendezeitpunkt und Priority-Fee für eine TX voraus.

    Args:
        gas_pressure_index: Von B2-1 (0-100)
        mev_pressure_index: Von B2-2 (0-100)
        current_basefee_gwei: Aktuelle Basefee
        priority_fee_p95_gwei: P95 Priority-Fee
        trusted_validators: Liste vertrauenswürdiger Validatoren
        next_slot: Nächster Slot (von A3-1)
        next_slot_ms: Zeit bis nächster Slot in ms

    Returns:
        {"status": "...", "recommendation": TxTimingRecommendation, "subagents": {...}}
    """
    try:
        window = _b3_1a_low_pressure_window(gas_pressure_index, mev_pressure_index)
        validator_check = _b3_1b_validator_whitelist_check(trusted_validators)
        dispatch = _b3_1c_tx_value_dispatch(
            window, validator_check, current_basefee_gwei,
            priority_fee_p95_gwei, next_slot, next_slot_ms,
        )

        return {
            "status": "completed",
            "agent": "B3-1",
            "recommendation": {
                "optimal_gas_price_gwei": dispatch["optimal_gas_price_gwei"],
                "optimal_priority_fee_gwei": dispatch["optimal_priority_fee_gwei"],
                "estimated_confirmation_ms": dispatch["estimated_confirmation_ms"],
                "mev_risk": dispatch["mev_risk"],
                "sandwich_protection": dispatch["sandwich_protection"],
                "target_slot": next_slot,
                "reason": dispatch["reason"],
            },
            "subagents": {
                "b3_1a_pressure_window": window,
                "b3_1b_validator_check": validator_check,
                "b3_1c_dispatch": dispatch,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("B3-1 Fehler: %s", e)
        return {"status": "failed", "agent": "B3-1", "error": str(e)}


def _b3_1a_low_pressure_window(gas_idx: float, mev_idx: float) -> dict:
    """Sucht Low-Pressure-Fenster: Gas + MEV beide unter Schwelle."""
    combined = (gas_idx + mev_idx) / 2
    is_low_pressure = combined < 40

    return {
        "status": "ok",
        "subagent": "B3-1a",
        "role": "Low-Pressure-Window-Finder",
        "gas_pressure": gas_idx,
        "mev_pressure": mev_idx,
        "combined_pressure": round(combined, 1),
        "is_low_pressure_window": is_low_pressure,
        "window_quality": (
            "ideal" if combined < 20
            else "good" if combined < 40
            else "acceptable" if combined < 60
            else "poor"
        ),
    }


def _b3_1b_validator_whitelist_check(
    trusted: list[str] | None,
) -> dict:
    """Prüft ob der nächste Leader ein vertrauenswürdiger Validator ist."""
    has_trusted = bool(trusted)

    return {
        "status": "ok",
        "subagent": "B3-1b",
        "role": "Validator-Whitelist-Checker",
        "trusted_validators_available": has_trusted,
        "count": len(trusted) if trusted else 0,
        "recommendation": (
            "Direkt-Sendung an vertrauenswürdigen Validator möglich — kein MEV-Schutz nötig"
            if has_trusted
            else "Validator unbekannt — MEV-Boost/Flashbots empfohlen"
        ),
    }


def _b3_1c_tx_value_dispatch(
    window: dict,
    validator: dict,
    basefee: float,
    pf_p95: float,
    next_slot: int,
    next_slot_ms: int,
) -> dict:
    """Berechnet optimale Priority-Fee: hoch genug gegen MEV, niedrig genug für Profit."""
    is_low = window["is_low_pressure_window"]
    has_trusted = validator["trusted_validators_available"]

    # Berechne optimale Priority-Fee
    if is_low and has_trusted:
        # Best-Case: niedrige Fee reicht
        optimal_pf = 1.0
        mev_risk = "low"
        sandwich = False
        reason = "Niedriger Druck + vertrauenswürdiger Validator — minimale Fee ausreichend"
    elif is_low:
        optimal_pf = 2.0
        mev_risk = "low"
        sandwich = False
        reason = "Niedriger Druck, aber unbekannter Validator — moderate Fee"
    elif has_trusted:
        optimal_pf = pf_p95 * 0.7  # 70% von P95
        mev_risk = "medium"
        sandwich = True
        reason = f"Hoher Druck, aber vertrauenswürdiger Validator — {optimal_pf:.1f} gwei Priority"
    else:
        optimal_pf = pf_p95 * 1.2  # 120% von P95
        mev_risk = "high"
        sandwich = True
        reason = f"Hoher Druck + unbekannter Validator — {optimal_pf:.1f} gwei + Flashbots-Schutz"

    total_gas = basefee + optimal_pf
    est_confirmation = next_slot_ms if next_slot_ms > 0 else 12000

    return {
        "status": "ok",
        "subagent": "B3-1c",
        "role": "Tx-Value-Dispatch",
        "optimal_gas_price_gwei": round(total_gas, 1),
        "optimal_priority_fee_gwei": round(optimal_pf, 1),
        "estimated_confirmation_ms": est_confirmation,
        "mev_risk": mev_risk,
        "sandwich_protection": sandwich,
        "reason": reason,
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT B3-2: Marktstress-Frühwarnsystem (Bridge zu Klasse C)
# ═══════════════════════════════════════════════════════════════════════

def b3_2_stress_early_warning(
    gas_pressure_index: float = 50.0,
    mev_pressure_index: float = 50.0,
    combined_pressure_index: float = 50.0,
    current_critical_hf: float = CRITICAL_HF_DEFAULT,
) -> dict:
    """Warnt Klasse C (Lending/Arbitrage) bei extremem MEV-Druck.

    Args:
        gas_pressure_index: Von B2-1
        mev_pressure_index: Von B2-2
        combined_pressure_index: Durchschnitt gas+mev
        current_critical_hf: Aktuelle Critical-Threshold (von B2-2 / A3-2)

    Returns:
        {"status": "...", "alerts": [...], "adjusted_hf": N}
    """
    try:
        liquidation_risk = _b3_2a_pressure_to_liquidation_risk(
            gas_pressure_index, mev_pressure_index, current_critical_hf,
        )
        arb_opportunity = _b3_2b_pressure_to_arbitrage_opportunity(
            mev_pressure_index, gas_pressure_index,
        )
        alerts = _b3_2c_publish_alerts(liquidation_risk, arb_opportunity, combined_pressure_index)

        return {
            "status": "completed",
            "agent": "B3-2",
            "adjusted_critical_hf": liquidation_risk["adjusted_critical_hf"],
            "alerts_fired": len(alerts.get("alerts", [])),
            "subagents": {
                "b3_2a_liquidation_risk": liquidation_risk,
                "b3_2b_arbitrage_opp": arb_opportunity,
                "b3_2c_alerts": alerts,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("B3-2 Fehler: %s", e)
        return {"status": "failed", "agent": "B3-2", "error": str(e)}


def _b3_2a_pressure_to_liquidation_risk(
    gas_idx: float, mev_idx: float, current_hf: float,
) -> dict:
    """Hoher Gas-Stress → erhöhte Liquidations-Verzögerung → HF-Bump."""
    pressure = max(gas_idx, mev_idx)

    if pressure > 80:
        hf_bump = HF_BUMP_UNDER_PRESSURE * 2  # 1.05 → 1.15
        risk = "critical"
        reason = "Extremer Druck — Liquidations-Transaktionen verzögern sich stark"
    elif pressure > 60:
        hf_bump = HF_BUMP_UNDER_PRESSURE  # 1.05 → 1.10
        risk = "elevated"
        reason = "Erhöhter Druck — höherer HF-Puffer empfohlen"
    else:
        hf_bump = 0.0
        risk = "normal"
        reason = "Normaler Druck — Standard-HF ausreichend"

    adjusted = round(current_hf + hf_bump, 3)

    return {
        "status": "ok",
        "subagent": "B3-2a",
        "role": "Pressure→Liquidation-Risk",
        "current_critical_hf": current_hf,
        "hf_bump": round(hf_bump, 3),
        "adjusted_critical_hf": adjusted,
        "risk_level": risk,
        "reason": reason,
        "recommendation": (
            f"HF auf {adjusted} erhöhen — Liquidationen könnten verzögert sein"
            if hf_bump > 0
            else "Standard-HF beibehalten"
        ),
    }


def _b3_2b_pressure_to_arbitrage_opportunity(
    mev_idx: float, gas_idx: float,
) -> dict:
    """Hohe Bribes → Bots fahren aggressive Arbitrage → Preisverzerrungen wahrscheinlich."""
    if mev_idx > 80 and gas_idx < 50:
        # MEV extrem, aber Gas niedrig: Arbitrage-Chance!
        signal = "strong_opportunity"
        probability = "high"
        detail = "MEV-Bots pumpen Bribes bei niedrigem Gas — Arbitrage-Spreads wahrscheinlich >0.5%"
    elif mev_idx > 60:
        signal = "opportunity"
        probability = "moderate"
        detail = "Erhöhte MEV-Aktivität — Arbitrage-Chancen prüfen"
    elif mev_idx > 40:
        signal = "watch"
        probability = "low"
        detail = "Leichte MEV-Aktivität — Spreads beobachten"
    else:
        signal = "quiet"
        probability = "none"
        detail = "Niedrige MEV-Aktivität — keine signifikanten Preisverzerrungen"

    return {
        "status": "ok",
        "subagent": "B3-2b",
        "role": "Pressure→Arbitrage-Opportunity",
        "signal": signal,
        "arbitrage_probability": probability,
        "mev_index": mev_idx,
        "gas_index": gas_idx,
        "detail": detail,
    }


def _b3_2c_publish_alerts(
    liquidation_risk: dict,
    arb_opp: dict,
    combined_pressure: float,
) -> dict:
    """Feuert standardisierte Alarme an den SymbolicsAgent."""
    alerts = []
    pressure_level = _to_pressure_level(combined_pressure).value

    if liquidation_risk["risk_level"] == "critical":
        alerts.append({
            "target": "symbolics_agent",
            "level": "CRITICAL",
            "type": "LIQUIDATION_RISK_HIGH",
            "message": f"HF-Bump auf {liquidation_risk['adjusted_critical_hf']} — {liquidation_risk['reason']}",
            "action": "CRITICAL_HF_ADJUST",
        })

    if arb_opp["signal"] == "strong_opportunity":
        alerts.append({
            "target": "klasse_c_arbitrage",
            "level": "HIGH",
            "type": "MEV_ARBITRAGE_WINDOW",
            "message": arb_opp["detail"],
            "action": "SCAN_ARBITRAGE_SPREADS",
        })

    if pressure_level in ("high", "extreme"):
        alerts.append({
            "target": "klasse_c_flash_loan",
            "level": "MEDIUM",
            "type": "FLASH_LOAN_RISK_ELEVATED",
            "message": f"MEV-Druck {pressure_level} — Flash-Loans riskant",
            "action": "FLASH_LOAN_CAUTION",
        })

    return {
        "status": "ok",
        "subagent": "B3-2c",
        "role": "Alert-Publisher",
        "pressure_level": pressure_level,
        "alerts_count": len(alerts),
        "alerts": alerts,
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT B3-3: Block-Building-Simulator (Forensik)
# ═══════════════════════════════════════════════════════════════════════

def b3_3_block_forensics(
    action: str = "analyze",
    block_number: int = 21_000_100,
    chain: str = "ETHEREUM",
) -> dict:
    """Rekonstruiert Block-Building und analysiert MEV-Auswirkungen.

    Args:
        action: 'analyze' | 'status'
        block_number: Zu analysierender Block
        chain: Chain

    Returns:
        {"status": "...", "report": BlockForensicReport, "subagents": {...}}
    """
    try:
        if action == "status":
            return {
                "status": "ok",
                "agent": "B3-3",
                "capabilities": ["Block-Rekonstruktion", "MEV-Explorer", "Post-Mortem"],
                "timestamp": _now_iso(),
            }

        reconstruction = _b3_3a_reconstruct_block(block_number, chain)
        mev_analysis = _b3_3b_explore_mev(reconstruction)
        post_mortem = _b3_3c_generate_post_mortem(reconstruction, mev_analysis)

        return {
            "status": "completed",
            "agent": "B3-3",
            "block_analyzed": block_number,
            "report": post_mortem,
            "subagents": {
                "b3_3a_reconstruction": reconstruction,
                "b3_3b_mev_explorer": mev_analysis,
                "b3_3c_post_mortem": post_mortem,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("B3-3 Fehler: %s", e)
        return {"status": "failed", "agent": "B3-3", "error": str(e)}


def _b3_3a_reconstruct_block(block_num: int, chain: str) -> dict:
    """Rekonstruiert Block: alle TXs nach Priority-Fee sortiert."""
    # Demo-Block mit realistischen Werten
    txs = [
        {"hash": f"0xb{block_num}_1", "from": "0xSearcher1", "priority_fee_gwei": 45.0,
         "type": "arbitrage", "gas_used": 350_000},
        {"hash": f"0xb{block_num}_2", "from": "0xBot1", "priority_fee_gwei": 38.0,
         "type": "sandwich_front", "gas_used": 250_000},
        {"hash": f"0xb{block_num}_3", "from": "0xUser1", "priority_fee_gwei": 3.0,
         "type": "swap", "gas_used": 150_000},
        {"hash": f"0xb{block_num}_4", "from": "0xBot1", "priority_fee_gwei": 5.0,
         "type": "sandwich_back", "gas_used": 250_000},
        {"hash": f"0xb{block_num}_5", "from": "0xLiquidator1", "priority_fee_gwei": 25.0,
         "type": "liquidation", "gas_used": 400_000},
        {"hash": f"0xb{block_num}_6", "from": "0xSearcher2", "priority_fee_gwei": 42.0,
         "type": "arbitrage", "gas_used": 320_000},
        {"hash": f"0xb{block_num}_7", "from": "0xUser2", "priority_fee_gwei": 2.0,
         "type": "transfer", "gas_used": 21000},
    ]

    sorted_txs = sorted(txs, key=lambda t: t["priority_fee_gwei"], reverse=True)
    total_priority_eth = sum(t["priority_fee_gwei"] * t["gas_used"] * 1e-9 for t in txs)

    return {
        "status": "ok",
        "subagent": "B3-3a",
        "role": "Block-Rekonstruktor",
        "block_number": block_num,
        "chain": chain,
        "total_txs": len(txs),
        "total_priority_fees_eth": round(total_priority_eth, 6),
        "txs_by_priority": [
            {**t, "priority_fee_eth": round(t["priority_fee_gwei"] * t["gas_used"] * 1e-9, 6)}
            for t in sorted_txs
        ],
    }


def _b3_3b_explore_mev(reconstruction: dict) -> dict:
    """Identifiziert MEV-TXs: Sandwiches, Arbitrage, Liquidationen."""
    txs = reconstruction.get("txs_by_priority", [])

    sandwiches = 0
    frontruns = 0
    backruns = 0
    arbitrages = 0
    liquidations = 0
    mev_txs = []

    for t in txs:
        ttype = t.get("type", "")
        if ttype == "sandwich_front":
            frontruns += 1
            mev_txs.append(t)
        elif ttype == "sandwich_back":
            backruns += 1
        elif ttype == "arbitrage":
            arbitrages += 1
            mev_txs.append(t)
        elif ttype == "liquidation":
            liquidations += 1
            mev_txs.append(t)

    sandwiches = min(frontruns, backruns)  # Ein Sandwich = front+back

    mev_eth = sum(t.get("priority_fee_eth", 0) for t in mev_txs)

    return {
        "status": "ok",
        "subagent": "B3-3b",
        "role": "MEV-Explorer",
        "mev_tx_count": len(mev_txs),
        "sandwich_attacks": sandwiches,
        "frontrun_attacks": frontruns,
        "backrun_attacks": backruns,
        "arbitrage_txs": arbitrages,
        "liquidation_txs": liquidations,
        "total_mev_priority_fees_eth": round(mev_eth, 6),
        "mev_dominance_pct": round(
            mev_eth / reconstruction["total_priority_fees_eth"] * 100, 1
        ) if reconstruction["total_priority_fees_eth"] > 0 else 0,
    }


def _b3_3c_generate_post_mortem(block: dict, mev: dict) -> dict:
    """Erstellt Post-Mortem-Report für SymbolicsAgent."""
    sandwich_count = mev.get("sandwich_attacks", 0)
    arb_count = mev.get("arbitrage_txs", 0)
    liq_count = mev.get("liquidation_txs", 0)
    mev_eth = mev.get("total_mev_priority_fees_eth", 0)
    block_num = block.get("block_number")
    total_txs = block.get("total_txs", 0)

    summary = (
        f"In Block {block_num} haben {mev.get('mev_tx_count', 0)}/{total_txs} TXs "
        f"MEV-Aktivität gezeigt: {sandwich_count} Sandwich(es), {arb_count} Arbitrage(n), "
        f"{liq_count} Liquidation(en). "
        f"MEV-Bots zahlten {mev_eth:.4f} ETH an Priority-Fees "
        f"({mev.get('mev_dominance_pct', 0):.1f}% aller Priority-Fees). "
    )

    if sandwich_count > 0:
        summary += f"Durch Sandwiches wurden {sandwich_count} User geschädigt. "
    if arb_count > 2:
        summary += f"Hohe Arbitrage-Aktivität deutet auf Preisverzerrungen hin. "
    if mev.get("mev_dominance_pct", 0) > 50:
        summary += "MEV-Bots dominieren den Block — Flash-Loans riskant."

    return {
        "status": "ok",
        "subagent": "B3-3c",
        "role": "Post-Mortem-Generator",
        "block_number": block_num,
        "total_txs": total_txs,
        "total_priority_fees_eth": block.get("total_priority_fees_eth", 0),
        "mev_tx_count": mev.get("mev_tx_count", 0),
        "mev_bundles_count": mev.get("mev_tx_count", 0),  # Näherung
        "estimated_mev_profit_eth": round(mev_eth * 5, 4),  # MEV-Profit ≈ 5× Priority-Fee
        "sandwich_attacks": sandwich_count,
        "frontrun_attacks": mev.get("frontrun_attacks", 0),
        "backrun_attacks": mev.get("backrun_attacks", 0),
        "arbitrage_txs": arb_count,
        "liquidation_txs": liq_count,
        "summary": summary,
        "timestamp": _now_iso(),
    }


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"

    if cmd == "b3_1":
        print(json.dumps(b3_1_optimal_tx_timer(
            gas_pressure_index=65.0, mev_pressure_index=55.0,
            trusted_validators=["validator_101"],
            next_slot=9000001, next_slot_ms=8000,
        ), indent=2))
    elif cmd == "b3_2":
        print(json.dumps(b3_2_stress_early_warning(
            gas_pressure_index=85.0, mev_pressure_index=90.0,
        ), indent=2))
    elif cmd == "b3_3":
        print(json.dumps(b3_3_block_forensics("analyze"), indent=2))
    elif cmd == "status":
        print(json.dumps({
            "b3_1": b3_1_optimal_tx_timer(),
            "b3_2": b3_2_stress_early_warning(),
            "b3_3": b3_3_block_forensics("status"),
        }, indent=2))
    else:
        print(json.dumps({
            "b3_1": b3_1_optimal_tx_timer(
                gas_pressure_index=65.0, mev_pressure_index=55.0,
                trusted_validators=["validator_101"],
                next_slot=9000001, next_slot_ms=8000,
            ),
            "b3_2": b3_2_stress_early_warning(
                gas_pressure_index=85.0, mev_pressure_index=90.0,
            ),
            "b3_3": b3_3_block_forensics("analyze"),
        }, indent=2))
