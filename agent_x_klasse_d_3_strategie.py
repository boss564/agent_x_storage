"""
Agent X — Klasse D: Oracle Heartbeats Cluster D3 (Strategie).

Strategische Outputs: Pre-Update-Alarme, Arbitrage-Frontrunning,
dynamische Slippage-Anpassung.

Agenten:
  D3-1: Pre-Update-Alarm-System         — 3 Subagenten
  D3-2: Arbitrage-Frontrunner-Detector   — 3 Subagenten
  D3-3: Slippage- & Gesundheits-Adaptor — 3 Subagenten

Bridge zu Klasse A (Konsensus): Timing für Block-Platzierung
Bridge zu Klasse B (Druckventile): Optimaler Bribe für Priorisierung
Bridge zu Klasse C/D (DeFi): Flash-Loan-Vorbereitung, HF-Schutz
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

from agent_x_klasse_d_oracle_models import (
    OracleProvider, UpdateTrigger, PriceFeed, PreUpdateAlert,
    ImpactSimulation, HeartbeatSchedule, KNOWN_FEEDS,
)

logger = logging.getLogger("oracle_d3_strategie")

CRITICAL_HF = float(os.getenv("CRITICAL_HF", "1.05"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════
# AGENT D3-1: Pre-Update-Alarm-System (DER TAKTGEBER)
# ═══════════════════════════════════════════════════════════════════════

def d3_1_pre_update_alarm(
    feeds_monitored: list[str] | None = None,
    deviation_warnings: list[dict] | None = None,
    heartbeat_schedules: list[dict] | None = None,
) -> dict:
    """Feuert exakt 2 Sekunden vor erwartetem On-Chain-Update High-Priority-Alert.

    Args:
        feeds_monitored: Welche Feeds überwachen?
        deviation_warnings: Von D1-3c (Early Warnings)
        heartbeat_schedules: Von D2-1a (Heartbeat-Kalender)

    Returns:
        {"status": "...", "alerts_fired": N, "subagents": {...}}
    """
    try:
        warnings = deviation_warnings or []
        schedules = heartbeat_schedules or []

        countdown = _d3_1a_run_countdown(schedules, warnings)
        mempool_scan = _d3_1b_scan_mempool_for_oracle_tx()
        dispatch = _d3_1c_dispatch_alerts(countdown, mempool_scan)

        return {
            "status": "completed", "agent": "D3-1",
            "alerts_fired": dispatch.get("alerts_fired", 0),
            "subagents": {
                "d3_1a_countdown": countdown,
                "d3_1b_mempool_spy": mempool_scan,
                "d3_1c_dispatcher": dispatch,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("D3-1 Fehler: %s", e)
        return {"status": "failed", "agent": "D3-1", "error": str(e)}


def _d3_1a_run_countdown(schedules: list[dict], warnings: list[dict]) -> dict:
    """Zählt Sekunden bis zum nächsten Heartbeat oder Deviation-Trigger."""
    now = time.time()
    countdowns = []

    # Priorität 1: Deviation-Warnungen (0.45%+)
    for w in warnings:
        countdowns.append({
            "feed": w.get("feed", "?"),
            "trigger": "deviation",
            "deviation_pct": w.get("deviation_pct", 0),
            "countdown_s": 2,  # Deviation-Trigger: ~2s bis On-Chain-Tx
            "severity": w.get("severity", "warning"),
            "alert_now": w.get("severity") == "critical",
        })

    # Priorität 2: Heartbeats
    for s in schedules:
        secs = s.get("seconds_until_next", 3600)
        if secs < 10:  # Nur wenn <10s bis Heartbeat
            countdowns.append({
                "feed": s["asset_pair"],
                "trigger": "heartbeat",
                "countdown_s": max(0, secs - 2),  # 2s Vorlauf
                "alert_now": secs <= 2,
            })

    countdowns.sort(key=lambda c: c["countdown_s"])

    return {
        "status": "ok", "subagent": "D3-1a", "role": "Countdown-Timer",
        "active_countdowns": len(countdowns),
        "next_alert_in_s": countdowns[0]["countdown_s"] if countdowns else 999,
        "alerts_due_now": [c for c in countdowns if c.get("alert_now")],
        "countdowns": countdowns,
    }


def _d3_1b_scan_mempool_for_oracle_tx() -> dict:
    """Scannt Mempool auf Chainlink-transmit() oder Pyth-updatePriceFeeds()."""
    # Im Produktivbetrieb: eth_subscribe("newPendingTransactions")
    # mit Filter auf Oracle-Contract-Adressen
    oracle_txs_found = []

    # Demo: simulierte Mempool-TXs
    cl_feeds = [f for f in KNOWN_FEEDS.values() if f.provider == OracleProvider.CHAINLINK]
    for feed in cl_feeds[:2]:
        if feed.deviation_from_onchain_pct > 0.5:
            oracle_txs_found.append({
                "tx_hash": f"0xmempool_{feed.asset_pair.replace('/', '_')}",
                "contract": feed.contract_address,
                "method": "transmit",
                "feed": feed.asset_pair,
                "detected_at_unix": time.time(),
            })

    return {
        "status": "ok", "subagent": "D3-1b", "role": "Mempool-Spy",
        "oracle_txs_found": len(oracle_txs_found),
        "transactions": oracle_txs_found,
        "message": (
            f"⚠️ {len(oracle_txs_found)} Oracle-TX(s) im Mempool — Update steht bevor!"
            if oracle_txs_found
            else "Keine Oracle-TXs im Mempool"
        ),
    }


def _d3_1c_dispatch_alerts(countdown: dict, mempool: dict) -> dict:
    """Sendet Alerts an Klasse-C-Agenten: 'ETH-Update in 3s — Slippage anpassen!'"""
    alerts = []

    # Alert-Typ 1: Countdown-Alerts
    for cd in countdown.get("alerts_due_now", []):
        alerts.append(PreUpdateAlert(
            alert_id="", asset_pair=cd["feed"],
            provider=OracleProvider.CHAINLINK,
            expected_trigger=UpdateTrigger.DEVIATION if cd["trigger"] == "deviation" else UpdateTrigger.HEARTBEAT,
            expected_price=0,  # Kommt von D1-3
            confidence_pct=85 if cd["trigger"] == "deviation" else 70,
            seconds_until_update=cd["countdown_s"],
            priority="CRITICAL" if cd["trigger"] == "deviation" else "HIGH",
        ).to_dict())

    # Alert-Typ 2: Mempool-TXs gefunden (Fallback)
    for tx in mempool.get("transactions", []):
        alerts.append(PreUpdateAlert(
            alert_id="", asset_pair=tx.get("feed", "?"),
            provider=OracleProvider.CHAINLINK,
            expected_trigger=UpdateTrigger.DEVIATION,
            expected_price=0,
            confidence_pct=95,  # Sehr sicher — TX schon im Mempool
            seconds_until_update=6,  # ~1 Block
            priority="CRITICAL",
        ).to_dict())

    return {
        "status": "ok", "subagent": "D3-1c", "role": "Action-Dispatch",
        "alerts_fired": len(alerts),
        "alerts": alerts,
        "message": (
            f"⚠️ {len(alerts)} Pre-Update-Alarme gefeuert — "
            "DeFi-Parameter anpassen!"
            if alerts else "Keine Alarme — keine Updates erwartet"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT D3-2: Arbitrage-Frontrunner-Detector
# ═══════════════════════════════════════════════════════════════════════

def d3_2_arbitrage_frontrunner(
    expected_price_changes: list[dict] | None = None,
    flash_loan_available: bool = True,
    gas_pressure_index: float = 50.0,
    mev_pressure_index: float = 50.0,
) -> dict:
    """Bereitet Flash-Loan-Arbitrage VOR dem Oracle-Update vor.

    Args:
        expected_price_changes: Prognostizierte Preisänderungen
        flash_loan_available: Flash-Loan von Klasse-C verfügbar?
        gas_pressure_index: Von Klasse B (Druckventile)
        mev_pressure_index: Von Klasse B

    Returns:
        {"status": "...", "recommended_trades": [...], "subagents": {...}}
    """
    try:
        changes = expected_price_changes or []

        spread_analysis = _d3_2a_analyze_pre_update_spread(changes)
        flash_sim = _d3_2b_simulate_flash_loan(
            spread_analysis, flash_loan_available, gas_pressure_index,
        )
        profit_estimate = _d3_2c_estimate_profit(flash_sim, mev_pressure_index)

        return {
            "status": "completed", "agent": "D3-2",
            "recommended_trades": profit_estimate.get("viable_trades", 0),
            "total_estimated_profit_usd": profit_estimate.get("total_profit_usd", 0),
            "subagents": {
                "d3_2a_spread_analysis": spread_analysis,
                "d3_2b_flash_sim": flash_sim,
                "d3_2c_profit_estimate": profit_estimate,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("D3-2 Fehler: %s", e)
        return {"status": "failed", "agent": "D3-2", "error": str(e)}


def _d3_2a_analyze_pre_update_spread(changes: list[dict]) -> dict:
    """Berechnet Spread zwischen aktuellen DEX-Preisen und erwartetem Oracle-Preis."""
    spreads = []
    for change in changes:
        new = change.get("new_price", 0)
        old = change.get("old_price", new)
        # DEX hinkt ~30% hinterher
        dex_price = old + (new - old) * 0.3
        spread = abs((new - dex_price) / dex_price * 100) if dex_price > 0 else 0

        spreads.append({
            "asset": change.get("asset", "?"),
            "dex_spot_price": round(dex_price, 2),
            "expected_oracle_price": round(new, 2),
            "pre_update_spread_pct": round(spread, 4),
            "opportunity": spread > 0.15,  # >0.15% lohnt sich
        })

    return {
        "status": "ok", "subagent": "D3-2a", "role": "Pre-Update-DEX-Spread",
        "spreads": spreads,
        "opportunity_count": sum(1 for s in spreads if s["opportunity"]),
    }


def _d3_2b_simulate_flash_loan(
    spread_result: dict, fl_available: bool, gas_idx: float,
) -> dict:
    """Simuliert Flash-Loan-basierte Arbitrage im Oracle-Update-Block."""
    if not fl_available:
        return {
            "status": "ok", "subagent": "D3-2b", "role": "Flash-Loan-Sim",
            "feasible": False, "note": "Flash-Loan nicht verfügbar",
            "simulations": [],
        }

    sims = []
    for spread in spread_result.get("spreads", []):
        if not spread["opportunity"]:
            continue
        new_price = spread["expected_oracle_price"]
        dex_price = spread["dex_spot_price"]
        trade_size = 100_000  # $100k Flash-Loan
        spread_abs = abs(new_price - dex_price) / dex_price

        gross = trade_size * spread_abs
        fl_fee = trade_size * 0.0009  # 0.09% Aave
        gas_units = 350_000
        gas_price_gwei = 25 + (gas_idx - 50) * 0.5
        gas_cost = gas_units * gas_price_gwei * 1e-9 * 3200

        sims.append({
            "asset": spread["asset"],
            "trade_size_usd": trade_size,
            "gross_profit_usd": round(gross, 2),
            "flash_loan_fee_usd": round(fl_fee, 2),
            "gas_cost_usd": round(gas_cost, 2),
            "net_profit_usd": round(gross - fl_fee - gas_cost, 2),
            "feasible": gross > fl_fee + gas_cost,
        })

    return {
        "status": "ok", "subagent": "D3-2b", "role": "Flash-Loan-Sim",
        "feasible": any(s["feasible"] for s in sims),
        "simulations": sims,
    }


def _d3_2c_estimate_profit(flash_result: dict, mev_idx: float) -> dict:
    """Finale Profit-Schätzung mit MEV-Risiko-Abzug."""
    sims = flash_result.get("simulations", [])
    viable = [s for s in sims if s["feasible"]]

    # MEV-Risiko: >60 MEV-Pressure → 20% Abzug
    mev_discount = 0.20 if mev_idx > 60 else 0.10 if mev_idx > 40 else 0.0

    for trade in viable:
        trade["mev_discount_pct"] = round(mev_discount * 100, 1)
        trade["adjusted_profit_usd"] = round(
            trade["net_profit_usd"] * (1 - mev_discount), 2
        )

    total = sum(t.get("adjusted_profit_usd", t.get("net_profit_usd", 0)) for t in viable)

    return {
        "status": "ok", "subagent": "D3-2c", "role": "Profit-Estimator",
        "viable_trades": len(viable),
        "total_profit_usd": round(total, 2),
        "mev_discount_applied_pct": round(mev_discount * 100, 1),
        "trades": viable,
        "recommendation": (
            f"GO: {len(viable)} Trades, ${total:.0f} Profit (nach {mev_discount*100:.0f}% MEV-Abzug)"
            if viable and total > 20
            else "NO-GO: Profit zu gering oder MEV zu hoch"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT D3-3: Slippage- & Gesundheits-Adaptor
# ═══════════════════════════════════════════════════════════════════════

def d3_3_slippage_adaptor(
    expected_updates: list[dict] | None = None,
    current_slippage_pct: float = 0.5,
    user_positions: list[dict] | None = None,
) -> dict:
    """Passt DeFi-Parameter dynamisch an erwartete Oracle-Updates an.

    Args:
        expected_updates: Bevorstehende Updates (von D3-1)
        current_slippage_pct: Aktuelle Slippage-Toleranz
        user_positions: Positionen für Collateral-Swap-Check

    Returns:
        {"status": "...", "adjusted_slippage_pct": N, "subagents": {...}}
    """
    try:
        updates = expected_updates or []
        positions = user_positions or []

        slippage = _d3_3a_dynamic_slippage_setter(updates, current_slippage_pct)
        collateral = _d3_3b_collateral_swapper(updates, positions)
        validator = _d3_3c_post_update_validator(updates)

        return {
            "status": "completed", "agent": "D3-3",
            "adjusted_slippage_pct": slippage["adjusted_slippage_pct"],
            "collateral_swap_recommended": collateral.get("swap_recommended", False),
            "subagents": {
                "d3_3a_slippage": slippage,
                "d3_3b_collateral": collateral,
                "d3_3c_validator": validator,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("D3-3 Fehler: %s", e)
        return {"status": "failed", "agent": "D3-3", "error": str(e)}


def _d3_3a_dynamic_slippage_setter(updates: list[dict], current_slippage: float) -> dict:
    """Erhöht Slippage-Toleranz wenn Oracle-Update innerhalb 10s erwartet wird."""
    now = time.time()
    adjusted = current_slippage

    for update in updates:
        secs = update.get("seconds_until_update", 999)
        if secs < 10:
            # Erhöhe Slippage proportional zur Dringlichkeit
            factor = 1 + (10 - secs) / 10 * 2  # 1.0x → 3.0x
            adjusted = max(adjusted, current_slippage * factor)

    adjusted = min(5.0, round(adjusted, 2))  # Max 5%

    return {
        "status": "ok", "subagent": "D3-3a", "role": "Dynamic-Slippage-Setter",
        "current_slippage_pct": current_slippage,
        "adjusted_slippage_pct": adjusted,
        "increase_reason": (
            f"Oracle-Update in <10s — Slippage auf {adjusted}% erhöht (Revert-Schutz)"
            if adjusted > current_slippage
            else "Keine Anpassung nötig"
        ),
    }


def _d3_3b_collateral_swapper(updates: list[dict], positions: list[dict]) -> dict:
    """Empfiehlt Collateral-Swap wenn Oracle-Update das Collateral abwerten würde."""
    swap_recommended = False
    swap_actions = []

    for update in updates:
        asset = update.get("asset_pair", update.get("feed", ""))
        if "ETH" in asset:
            for pos in positions:
                if pos.get("asset") in ("ETH", "wstETH") and pos.get("health_factor", 2) < 1.5:
                    swap_actions.append({
                        "user": pos.get("user_address", ""),
                        "from_asset": pos.get("asset", "ETH"),
                        "to_asset": "USDC",
                        "reason": f"ETH-Update erwartet — HF {pos.get('health_factor', 1.5):.3f} "
                                  "könnte kritisch werden",
                        "urgency": "high" if pos.get("health_factor", 2) < 1.1 else "medium",
                    })
                    swap_recommended = True

    return {
        "status": "ok", "subagent": "D3-3b", "role": "Collateral-Swapper",
        "swap_recommended": swap_recommended,
        "swap_actions": swap_actions,
    }


def _d3_3c_post_update_validator(updates: list[dict]) -> dict:
    """Validiert nach dem On-Chain-Update: War die Vorhersage korrekt?

    Feedback-Loop für zukünftige Vorhersagen.
    """
    return {
        "status": "ok", "subagent": "D3-3c", "role": "Post-Update-Validator",
        "pending_validations": len(updates),
        "feedback_loop_active": True,
        "note": "Wird nach dem nächsten On-Chain-Update ausgeführt",
    }


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"

    if cmd == "d3_1":
        print(json.dumps(d3_1_pre_update_alarm(
            deviation_warnings=[
                {"feed": "ETH/USD", "deviation_pct": 0.48, "severity": "warning"},
            ],
        ), indent=2))
    elif cmd == "d3_2":
        changes = [{"asset": "ETH/USD", "new_price": 3100.0, "old_price": 3200.0}]
        print(json.dumps(d3_2_arbitrage_frontrunner(
            expected_price_changes=changes, gas_pressure_index=45.0,
        ), indent=2))
    elif cmd == "d3_3":
        print(json.dumps(d3_3_slippage_adaptor(
            expected_updates=[
                {"feed": "ETH/USD", "seconds_until_update": 5},
            ],
        ), indent=2))
    elif cmd == "status":
        print(json.dumps({
            "d3_1": d3_1_pre_update_alarm(),
            "d3_2": d3_2_arbitrage_frontrunner(
                expected_price_changes=[{"asset": "ETH/USD", "new_price": 3100, "old_price": 3200}],
            ),
            "d3_3": d3_3_slippage_adaptor(),
        }, indent=2))
    else:
        print(json.dumps({
            "d3_1": d3_1_pre_update_alarm(
                deviation_warnings=[{"feed": "ETH/USD", "deviation_pct": 0.48, "severity": "warning"}],
            ),
            "d3_2": d3_2_arbitrage_frontrunner(
                expected_price_changes=[{"asset": "ETH/USD", "new_price": 3100, "old_price": 3200}],
            ),
            "d3_3": d3_3_slippage_adaptor(
                expected_updates=[{"feed": "ETH/USD", "seconds_until_update": 5}],
            ),
        }, indent=2))
