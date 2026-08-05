"""
Agent X — Klasse D: Oracle Heartbeats Cluster D2 (Analytics).

Zustandsanalyse: Heartbeat-Timing, DeFi-Impact-Simulation,
Datenqualitätsprüfung.

Agenten:
  D2-1: Heartbeat-Timing-Analyst    — 3 Subagenten
  D2-2: DeFi-Impact-Simulator       — 3 Subagenten
  D2-3: Data-Quality- & Anomalie-Detektor — 3 Subagenten
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

from agent_x_klasse_d_oracle_models import (
    OracleProvider, UpdateTrigger, PriceFeed, OracleUpdateEvent,
    ImpactSimulation, HeartbeatSchedule, KNOWN_FEEDS,
    CHAINLINK_OFFCHAIN_API, PYTH_HERMES_API,
)

logger = logging.getLogger("oracle_d2_analytics")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════
# AGENT D2-1: Heartbeat-Timing-Analyst
# ═══════════════════════════════════════════════════════════════════════

def d2_1_heartbeat_timing(
    feeds: list[str] | None = None,
) -> dict:
    """Erstellt präzisen Zeitplan für alle erwarteten Oracle-Updates.

    Berechnet: nächster Heartbeat, Deviation-Band-Nähe, Update-Wahrscheinlichkeit.
    """
    try:
        target_feeds = feeds or list(KNOWN_FEEDS.keys())[:5]
        calendar = _d2_1a_build_heartbeat_calendar(target_feeds)
        deviation_band = _d2_1b_track_deviation_band(calendar)
        probability = _d2_1c_update_probability(deviation_band)

        # Nächsten Update-Zeitpunkt aus dem Kalender holen
        cal_schedules = calendar.get("schedules", [])
        next_update = min(
            (s["next_heartbeat_unix"] - time.time()
             for s in cal_schedules if s.get("next_heartbeat_unix", 0) > time.time()),
            default=0,
        )

        return {
            "status": "completed", "agent": "D2-1",
            "feeds_analyzed": len(target_feeds),
            "next_update_in_s": round(next_update, 1),
            "subagents": {
                "d2_1a_calendar": calendar,
                "d2_1b_deviation_band": deviation_band,
                "d2_1c_probability": probability,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("D2-1 Fehler: %s", e)
        return {"status": "failed", "agent": "D2-1", "error": str(e)}


def _d2_1a_build_heartbeat_calendar(feed_keys: list[str]) -> dict:
    """Baut einen Kalender aller nächsten Heartbeats."""
    now = time.time()
    schedules = []

    for key in feed_keys:
        feed = KNOWN_FEEDS.get(key)
        if not feed:
            continue
        secs_since = int(now - feed.last_onchain_timestamp) if feed.last_onchain_timestamp else 0
        next_hb = feed.last_onchain_timestamp + feed.heartbeat_seconds
        secs_until = max(0, int(next_hb - now))

        schedules.append(HeartbeatSchedule(
            asset_pair=feed.asset_pair,
            provider=feed.provider,
            heartbeat_seconds=feed.heartbeat_seconds,
            last_update_unix=feed.last_onchain_timestamp,
            next_heartbeat_unix=next_hb,
            deviation_buffer_pct=round(feed.deviation_threshold_pct - feed.deviation_from_onchain_pct, 4),
            deviation_approaching=feed.deviation_from_onchain_pct > feed.deviation_threshold_pct * 0.9,
        ).to_dict())

    # Sortiere nach Dringlichkeit
    schedules.sort(key=lambda s: s["seconds_until_next"])

    return {
        "status": "ok", "subagent": "D2-1a", "role": "Heartbeat-Kalender",
        "total_feeds": len(schedules),
        "next_heartbeat_in_s": schedules[0]["seconds_until_next"] if schedules else 0,
        "schedules": schedules,
    }


def _d2_1b_track_deviation_band(calendar_result: dict) -> dict:
    """Trackt, wie nah der Preis am Deviation-Trigger ist."""
    schedules = calendar_result.get("schedules", [])
    deviation_status = []

    for s in schedules:
        buffer = s.get("deviation_buffer_pct", 5.0)
        approaching = s.get("deviation_approaching", False)

        deviation_status.append({
            "feed": s["asset_pair"],
            "provider": s["provider"],
            "seconds_until_next": s.get("seconds_until_next", 0),
            "deviation_buffer_pct": buffer,
            "approaching_trigger": approaching,
            "expected_trigger": (
                "deviation" if approaching
                else "heartbeat" if s.get("seconds_until_next", 999) < 30
                else "none_imminent"
            ),
        })

    return {
        "status": "ok", "subagent": "D2-1b", "role": "Deviation-Band-Tracker",
        "feeds_approaching_trigger": sum(1 for d in deviation_status if d["approaching_trigger"]),
        "feeds": deviation_status,
    }


def _d2_1c_update_probability(deviation_result: dict) -> dict:
    """Modelliert Update-Wahrscheinlichkeit in den nächsten 5 Sekunden."""
    schedules = deviation_result.get("feeds", [])

    for s in schedules:
        # Probabilitäts-Modell:
        if s.get("approaching_trigger"):
            prob = 85  # Deviation-Trigger sehr wahrscheinlich
        elif s.get("seconds_until_next", 0) < 10:
            prob = 70  # Heartbeat in <10s
        elif s.get("seconds_until_next", 0) < 30:
            prob = 40
        elif s.get("seconds_until_next", 0) < 60:
            prob = 15
        else:
            prob = 5

        s["update_probability_5s_pct"] = prob

    return {
        "status": "ok", "subagent": "D2-1c", "role": "Push-Probability-Model",
        "schedules": schedules,
        "highest_probability_pct": max(
            (s.get("update_probability_5s_pct", 0) for s in schedules), default=0
        ),
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT D2-2: DeFi-Impact-Simulator
# ═══════════════════════════════════════════════════════════════════════

def d2_2_defi_impact_simulator(
    expected_price_changes: list[dict] | None = None,
    user_positions: list[dict] | None = None,
) -> dict:
    """Simuliert Auswirkungen eines Oracle-Updates BEVOR es on-chain ist.

    Berechnet: welche Positionen werden liquidierbar, welche Arbitrage-Chancen
    entstehen, wie verändert sich der TWAP.

    Args:
        expected_price_changes: [{"asset": "ETH/USD", "new_price": 3100.0, "old_price": 3200.0}]
        user_positions: Demo-User-Positionen

    Returns:
        {"status": "...", "positions_affected": N, "subagents": {...}}
    """
    try:
        changes = expected_price_changes or []
        positions = user_positions or _demo_positions()

        hf_impact = _d2_2a_simulate_hf_impact(changes, positions)
        liquidation_list = _d2_2b_build_liquidation_trigger_list(hf_impact)
        twap = _d2_2c_twap_impact(changes)

        return {
            "status": "completed", "agent": "D2-2",
            "positions_becoming_liquidatable": hf_impact.get("newly_liquidatable", 0),
            "arbitrage_profitable": twap.get("arbitrage_profitable", False),
            "subagents": {
                "d2_2a_hf_simulation": hf_impact,
                "d2_2b_liquidation_list": liquidation_list,
                "d2_2c_twap_impact": twap,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("D2-2 Fehler: %s", e)
        return {"status": "failed", "agent": "D2-2", "error": str(e)}


def _d2_2a_simulate_hf_impact(changes: list[dict], positions: list[dict]) -> dict:
    """Simuliert HF-Änderung für alle Positionen mit dem prognostizierten neuen Preis."""
    newly_liquidatable = []
    newly_critical = []
    total_collateral_at_risk = 0.0

    for pos in positions:
        # Finde relevanten Price Change
        asset = pos.get("asset", "ETH")
        change = next((c for c in changes if asset in c.get("asset", "")), None)
        if not change:
            continue

        old_collateral = pos.get("collateral_usd", 0)
        new_price = change.get("new_price", old_collateral)
        old_price = change.get("old_price", new_price)
        price_ratio = new_price / old_price if old_price > 0 else 1.0

        new_collateral = old_collateral * price_ratio
        debt = pos.get("debt_usd", 0)
        old_hf = pos.get("health_factor", 1.5)
        threshold = pos.get("liquidation_threshold", 0.8)
        new_hf = (new_collateral * threshold) / debt if debt > 0 else float("inf")

        pos["simulated_new_hf"] = round(new_hf, 4)
        pos["collateral_impact_usd"] = round(new_collateral - old_collateral, 2)

        if new_hf <= 1.0 and old_hf > 1.0:
            newly_liquidatable.append({
                "user": pos.get("user_address", ""),
                "old_hf": round(old_hf, 3),
                "new_hf": round(new_hf, 4),
                "debt_usd": debt,
                "collateral_impact_usd": pos["collateral_impact_usd"],
            })
        elif new_hf <= 1.05 and old_hf > 1.05:
            newly_critical.append({
                "user": pos.get("user_address", ""),
                "old_hf": round(old_hf, 3),
                "new_hf": round(new_hf, 4),
                "buffer_to_liquidation_pct": round((new_hf - 1.0) * 100, 2),
            })

        if new_hf <= 1.05:
            total_collateral_at_risk += new_collateral

    return {
        "status": "ok", "subagent": "D2-2a", "role": "HF-Simulation",
        "positions_checked": len(positions),
        "newly_liquidatable": len(newly_liquidatable),
        "newly_critical": len(newly_critical),
        "total_collateral_at_risk_usd": round(total_collateral_at_risk, 2),
        "liquidatable_users": newly_liquidatable,
        "critical_users": newly_critical,
    }


def _d2_2b_build_liquidation_trigger_list(hf_result: dict) -> dict:
    """Erstellt Liste von Wallets, die liquidiert WÜRDEN — vor der eigentlichen Liquidation."""
    liquidatable = hf_result.get("liquidatable_users", [])
    critical = hf_result.get("critical_users", [])

    return {
        "status": "ok", "subagent": "D2-2b", "role": "Liquidation-Trigger-List",
        "total_at_risk": len(liquidatable) + len(critical),
        "liquidatable_wallets": [u["user"] for u in liquidatable],
        "critical_wallets": [u["user"] for u in critical],
        "recommendation": (
            f"⚠️ {len(liquidatable)} Wallets werden liquidierbar — "
            "vor dem Update deleveragen!"
            if liquidatable
            else "Keine sofortigen Liquidationen erwartet"
        ),
    }


def _d2_2c_twap_impact(changes: list[dict]) -> dict:
    """Prüft, ob der neue Oracle-Preis außerhalb der aktuellen Uniswap-TWAP liegt."""
    arbitrage_opps = []
    for change in changes:
        new_price = change.get("new_price", 0)
        old_price = change.get("old_price", 0)
        # Geschätzter Uniswap-Spot-Preis (leicht hinter Oracle)
        uniswap_price = old_price + (new_price - old_price) * 0.3  # 30% des Weges
        spread = abs((new_price - uniswap_price) / uniswap_price * 100) if uniswap_price > 0 else 0

        if spread > 0.2:  # >0.2% Spread = Arbitrage möglich
            profit = abs(new_price - uniswap_price) * 10  # 10 ETH Trade
            gas_cost = 25  # $25 Gas
            arbitrage_opps.append({
                "asset": change.get("asset", "?"),
                "uniswap_price": round(uniswap_price, 2),
                "oracle_price": round(new_price, 2),
                "spread_pct": round(spread, 4),
                "profitable": profit > gas_cost,
                "estimated_profit_usd": round(profit - gas_cost, 2),
            })

    return {
        "status": "ok", "subagent": "D2-2c", "role": "TWAP-Impact",
        "arbitrage_opportunities": len(arbitrage_opps),
        "arbitrage_profitable": any(a["profitable"] for a in arbitrage_opps),
        "opportunities": arbitrage_opps,
    }


def _demo_positions() -> list[dict]:
    return [
        {"user_address": "0xAlice", "asset": "ETH", "collateral_usd": 50000,
         "debt_usd": 30000, "health_factor": 1.375, "liquidation_threshold": 0.825},
        {"user_address": "0xBob", "asset": "ETH", "collateral_usd": 10500,
         "debt_usd": 10000, "health_factor": 0.819, "liquidation_threshold": 0.78},
        {"user_address": "0xCarol", "asset": "BTC", "collateral_usd": 100000,
         "debt_usd": 75000, "health_factor": 1.04, "liquidation_threshold": 0.78},
    ]


# ═══════════════════════════════════════════════════════════════════════
# AGENT D2-3: Data-Quality- & Anomalie-Detektor
# ═══════════════════════════════════════════════════════════════════════

def d2_3_anomaly_detector(
    oracle_prices: dict[str, float] | None = None,
    uniswap_prices: dict[str, float] | None = None,
) -> dict:
    """Schützt vor manipulierten/fehlerhaften Oracle-Daten.

    Cross-Referenziert Chainlink vs. Pyth vs. Uniswap-Spot.
    """
    try:
        oracle = oracle_prices or {"ETH/USD_CL": 3245.67, "ETH/USD_PYTH": 3245.89}
        dex = uniswap_prices or {"ETH/USD": 3240.12}

        cross_ref = _d2_3a_cross_reference(oracle, dex)
        staleness = _d2_3b_check_staleness()
        breaker = _d2_3c_circuit_breaker(cross_ref, staleness)

        return {
            "status": "completed", "agent": "D2-3",
            "anomalies_found": cross_ref.get("anomaly_count", 0),
            "circuit_breaker_active": breaker.get("active", False),
            "subagents": {
                "d2_3a_cross_reference": cross_ref,
                "d2_3b_staleness": staleness,
                "d2_3c_circuit_breaker": breaker,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("D2-3 Fehler: %s", e)
        return {"status": "failed", "agent": "D2-3", "error": str(e)}


def _d2_3a_cross_reference(oracle: dict, dex: dict) -> dict:
    """Vergleicht Oracle-Preise mit DEX-Spot-Preisen. >2% Abweichung = Anomalie."""
    anomalies = []
    for oracle_key, oracle_price in oracle.items():
        asset = oracle_key.split("_")[0].replace("/USD", "")
        for dex_key, dex_price in dex.items():
            if asset in dex_key:
                spread = abs((oracle_price - dex_price) / dex_price * 100) if dex_price > 0 else 0
                if spread > 2.0:
                    anomalies.append({
                        "oracle_source": oracle_key,
                        "oracle_price": oracle_price,
                        "dex_price": dex_price,
                        "spread_pct": round(spread, 2),
                        "severity": "critical" if spread > 5 else "warning",
                    })

    return {
        "status": "ok", "subagent": "D2-3a", "role": "Cross-Referencer",
        "total_compared": len(oracle),
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
    }


def _d2_3b_check_staleness() -> dict:
    """Prüft, ob das letzte On-Chain-Update älter als der Heartbeat ist."""
    now = time.time()
    stale_feeds = []

    for key, feed in KNOWN_FEEDS.items():
        if feed.last_onchain_timestamp <= 0:
            continue
        age = now - feed.last_onchain_timestamp
        if age > feed.heartbeat_seconds * 1.5:  # >150% des Heartbeats
            stale_feeds.append({
                "feed": key,
                "age_seconds": int(age),
                "heartbeat_s": feed.heartbeat_seconds,
                "severity": "critical" if age > feed.heartbeat_seconds * 3 else "warning",
            })

    return {
        "status": "ok", "subagent": "D2-3b", "role": "Staleness-Checker",
        "stale_feeds": len(stale_feeds),
        "details": stale_feeds,
    }


def _d2_3c_circuit_breaker(cross_ref: dict, staleness: dict) -> dict:
    """Bei Anomalien: Signal an SymbolicsAgent — Oracle-Daten nicht vertrauen."""
    anomaly_count = cross_ref.get("anomaly_count", 0)
    stale_count = staleness.get("stale_feeds", 0)
    active = anomaly_count > 0 or stale_count > 0

    return {
        "status": "ok", "subagent": "D2-3c", "role": "Circuit-Breaker",
        "active": active,
        "reason": (
            f"{anomaly_count} Anomalie(n), {stale_count} Stale-Feed(s)"
            if active else "Keine Anomalien — Oracle-Daten vertrauenswürdig"
        ),
        "duration_s": 120 if active else 0,
        "message": (
            "⚠️ CIRCUIT BREAKER AKTIV: Oracle-Daten für 2 Minuten nicht vertrauen!"
            if active
            else "✅ Oracle-Daten vertrauenswürdig"
        ),
    }


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"

    if cmd == "d2_1":
        print(json.dumps(d2_1_heartbeat_timing(), indent=2))
    elif cmd == "d2_2":
        changes = [{"asset": "ETH/USD", "new_price": 3100.0, "old_price": 3200.0}]
        print(json.dumps(d2_2_defi_impact_simulator(expected_price_changes=changes), indent=2))
    elif cmd == "d2_3":
        print(json.dumps(d2_3_anomaly_detector(), indent=2))
    else:
        print(json.dumps({
            "d2_1": d2_1_heartbeat_timing(),
            "d2_2": d2_2_defi_impact_simulator(
                expected_price_changes=[{"asset": "ETH/USD", "new_price": 3100, "old_price": 3200}],
            ),
            "d2_3": d2_3_anomaly_detector(),
        }, indent=2))
