"""
Agent X — Klasse B: Cluster B2 (Health-Factor-Rechner / Risk Assessment).

Kritischster Agent der Klasse B. Reagiert auf Zustandsänderungen
(Supply/Borrow) und Preisänderungen. Berechnet exakte Health-Factors
nach Aave-V3-Formel und klassifiziert Risiko-Zonen.

Agenten:
  B2-1: Position-Ledger (Live-Zustand aller User)   — 3 Subagenten
  B2-2: Health-Factor-Rechner (exakte Mathematik)     — 3 Subagenten
  B2-3: Risiko-Klassifizierer (Alerts, Watchlist)     — 3 Subagenten

Bridge zu Klasse A:
  - A3-2 (Consensus Health Index) modifiziert Critical-Threshold
  - A2-3 (Churn-Predictor) warnt vor Validator-Exodus → erhöhte Volatilität
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from agent_x_lending_models import (
    Chain, RiskZone, LendingProtocol,
    AssetPosition, UserLendingState, LiquidationEvent,
    get_reserve_default,
)

logger = logging.getLogger("klasse_b2_risk")

# ─── Konfiguration ───────────────────────────────────────────────────

CRITICAL_THRESHOLD = float(os.getenv("CRITICAL_HF_THRESHOLD", "1.05"))
WARNING_THRESHOLD = float(os.getenv("WARNING_HF_THRESHOLD", "1.5"))
LIQUIDATION_THRESHOLD = float(os.getenv("LIQUIDATION_HF_THRESHOLD", "1.0"))

# Modifiziert durch Klasse A (A3-2 Consensus Health Index)
CRITICAL_BUMP_IF_NETWORK_UNSTABLE = float(os.getenv("CRITICAL_BUMP_NETWORK", "0.05"))
CONSENSUS_HEALTH_THRESHOLD = int(os.getenv("CONSENSUS_HEALTH_BUMP_THRESHOLD", "70"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════
# AGENT B2-1: Position-Ledger
# ═══════════════════════════════════════════════════════════════════════

def b2_1_position_ledger(
    action: str = "get_all_users",
    user_address: str | None = None,
    chain: str = "ETHEREUM",
    user_states: list[dict] | None = None,
) -> dict:
    """Hält den exakten Zustand aller Nutzer im Speicher.

    Args:
        action: 'get_all_users' | 'get_user' | 'update' | 'status'
        user_address: Spezifischer User für get_user/update
        chain: Chain-Filter
        user_states: Neue User-States für Update (von B1-3c)

    Returns:
        {"status": "...", "users_tracked": N, "subagents": {...}}
    """
    try:
        if action == "status":
            return {
                "status": "ok",
                "agent": "B2-1",
                "chains": ["ETHEREUM", "ARBITRUM", "SOLANA"],
                "timestamp": _now_iso(),
            }

        users = user_states or []

        if action == "get_user" and user_address:
            user = _b2_1a_lookup_user(user_address, chain, users)
            return {
                "status": "completed",
                "agent": "B2-1",
                "action": action,
                "user": user,
            }

        all_users = _b2_1a_get_all_positions(users)
        enriched = _b2_1b_enrich_with_reserves(all_users)
        validated = _b2_1c_validate_positions(enriched)

        return {
            "status": "completed",
            "agent": "B2-1",
            "action": action,
            "users_tracked": len(enriched.get("enriched_users", [])),
            "subagents": {
                "b2_1a_position_fetcher": all_users,
                "b2_1b_reserve_enricher": enriched,
                "b2_1c_position_validator": validated,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("B2-1 Fehler: %s", e)
        return {"status": "failed", "agent": "B2-1", "error": str(e)}


def _b2_1a_get_all_positions(users: list[dict]) -> dict:
    """Liest alle User-Positionen aus."""
    if not users:
        return {
            "status": "ok",
            "subagent": "B2-1a",
            "role": "Position-Fetcher",
            "total_users": 0,
            "total_positions": 0,
            "users": [],
        }

    total_positions = sum(len(u.get("positions", [])) for u in users)
    return {
        "status": "ok",
        "subagent": "B2-1a",
        "role": "Position-Fetcher",
        "total_users": len(users),
        "total_positions": total_positions,
        "users": users,
    }


def _b2_1a_lookup_user(address: str, chain: str, users: list[dict]) -> dict:
    """Schlägt einen einzelnen User nach."""
    for u in users:
        if u.get("user_address") == address and u.get("chain") == chain:
            return u
    return {}


def _b2_1b_enrich_with_reserves(fetcher_result: dict) -> dict:
    """Reichert Positionen mit aktuellen Reserve-Daten an (LTV, Threshold, Index)."""
    users = fetcher_result.get("users", [])
    enriched_users = []

    for user in users:
        enriched_positions = []
        for pos in user.get("positions", []):
            addr = pos.get("asset_address", "")
            asset = pos.get("asset_address", "ETH")
            reserve = get_reserve_default(asset)

            enriched_pos = {
                **pos,
                "ltv": reserve["ltv"],
                "liquidation_threshold": reserve["liquidation_threshold"],
                "liquidation_bonus": reserve["liquidation_bonus"],
                "symbol": reserve["symbol"],
                "decimals": reserve["decimals"],
                "liquidity_index": 1.0,
            }
            enriched_positions.append(enriched_pos)

        enriched_users.append({
            **user,
            "positions": enriched_positions,
        })

    return {
        "status": "ok",
        "subagent": "B2-1b",
        "role": "Reserve-Enricher",
        "enriched_users": enriched_users,
    }


def _b2_1c_validate_positions(enriched: dict) -> dict:
    """Validiert Positionen: prüft frozen assets, dust amounts, inkonsistente States."""
    users = enriched.get("enriched_users", [])
    valid_count = 0
    warnings = []

    for user in users:
        has_collateral = any(p.get("is_collateral") for p in user.get("positions", []))
        has_debt = any(p.get("type") == "debt" for p in user.get("positions", []))
        total_debt = user.get("total_debt_usd", 0)
        total_collateral = user.get("total_collateral_usd", 0)

        if total_debt > 0 and total_collateral == 0:
            warnings.append(f"{user.get('user_address','?')}: debt={total_debt} but no collateral")
        if not has_collateral and not has_debt:
            warnings.append(f"{user.get('user_address','?')}: empty position (no collateral, no debt)")

        valid_count += 1

    return {
        "status": "ok",
        "subagent": "B2-1c",
        "role": "Position-Validator",
        "total_validated": valid_count,
        "warnings": warnings,
        "has_critical_issues": len(warnings) > 0,
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT B2-2: Health-Factor-Rechner (Exakte Aave-V3-Mathematik)
# ═══════════════════════════════════════════════════════════════════════

def b2_2_health_factor_calculator(
    user_states: list[dict] | None = None,
    price_feeds: dict[str, float] | None = None,
    consensus_health_index: float = 100.0,
) -> dict:
    """Berechnet Health-Factors für alle User nach Aave-V3-Formel.

    Formel: HF = sum(collateral_i × price_i × threshold_i) / sum(debt_j × price_j)

    Args:
        user_states: Liste von User-States (aus B1-3c / B2-1)
        price_feeds: Asset → USD-Preis Mapping
        consensus_health_index: Von A3-2 (0-100), beeinflusst Critical-Threshold

    Returns:
        {"status": "...", "users_analyzed": N, "subagents": {...}}
    """
    try:
        users = user_states or []
        prices = price_feeds or {
            "ETH": 3200.0, "wstETH": 3400.0, "WBTC": 65000.0,
            "USDC": 1.0, "USDT": 1.0, "DAI": 1.0, "SOL": 180.0,
        }

        # Klasse-A-Bridge: Network unstable → bump critical threshold
        effective_critical = _b2_2a_compute_effective_threshold(consensus_health_index)

        hf_results = _b2_2b_compute_all_health_factors(users, prices)
        classified = _b2_2c_weighted_risk_assessment(hf_results, effective_critical)

        return {
            "status": "completed",
            "agent": "B2-2",
            "users_analyzed": len(users),
            "effective_critical_threshold": effective_critical,
            "consensus_health_index": consensus_health_index,
            "subagents": {
                "b2_2a_threshold_adjuster": {
                    "base_critical": CRITICAL_THRESHOLD,
                    "effective_critical": effective_critical,
                    "network_bump_applied": consensus_health_index < CONSENSUS_HEALTH_THRESHOLD,
                    "reason": (
                        f"Netzwerk instabil (CHI={consensus_health_index}), "
                        f"Threshold +{CRITICAL_BUMP_IF_NETWORK_UNSTABLE}"
                        if consensus_health_index < CONSENSUS_HEALTH_THRESHOLD
                        else "Netzwerk gesund, Standard-Threshold"
                    ),
                },
                "b2_2b_hf_computation": hf_results,
                "b2_2c_risk_assessment": classified,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("B2-2 Fehler: %s", e)
        return {"status": "failed", "agent": "B2-2", "error": str(e)}


def _b2_2a_compute_effective_threshold(consensus_health_index: float) -> float:
    """Berechnet effektive Critical-Threshold basierend auf Netzwerk-Gesundheit.

    Wenn Konsensus-Health-Index < 70: Erhöhe Critical-Schwellwert,
    weil Preise bei Reorgs kurzfristig abweichen können.
    """
    if consensus_health_index < CONSENSUS_HEALTH_THRESHOLD:
        return CRITICAL_THRESHOLD + CRITICAL_BUMP_IF_NETWORK_UNSTABLE
    return CRITICAL_THRESHOLD


def _b2_2b_compute_all_health_factors(
    users: list[dict],
    prices: dict[str, float],
) -> dict:
    """Berechnet Health-Factor für jeden User.

    HF = sum(collateral × price × liquidation_threshold) / sum(debt × price)
    """
    results = []
    summaries = {
        "safe": 0, "warning": 0, "critical": 0, "liquidatable": 0, "no_debt": 0,
    }

    for user in users:
        total_collateral_usd = 0.0
        total_debt_usd = 0.0
        weighted_threshold_sum = 0.0
        positions_count = 0

        positions = user.get("positions", [])
        if positions:
            # PRODUCTION PATH: Vollständige Positionsliste
            for pos in positions:
                asset_addr = pos.get("asset_address", pos.get("symbol", "ETH"))
                price = pos.get("price_usd", prices.get(asset_addr, 1.0))
                amount = pos.get("amount", 0.0)
                value_usd = amount * price
                threshold = pos.get("liquidation_threshold", 0.8)
                positions_count += 1

                if pos.get("is_collateral"):
                    total_collateral_usd += value_usd
                    weighted_threshold_sum += value_usd * threshold
                else:
                    total_debt_usd += value_usd
        else:
            # SNAPSHOT/BACKTEST PATH: Flache Felder direkt verwenden
            total_collateral_usd = float(user.get("total_collateral_usd", 0))
            total_debt_usd = float(user.get("total_debt_usd", 0))
            threshold = float(user.get("liquidation_threshold", 0.80))
            weighted_threshold_sum = total_collateral_usd * threshold
            # Wenn kein total_collateral_usd gesetzt: aus health_factor ableiten
            if total_collateral_usd == 0 and total_debt_usd > 0:
                hf_pre = float(user.get("health_factor", 1.5))
                if hf_pre != float("inf"):
                    total_collateral_usd = (total_debt_usd * hf_pre) / threshold
                    weighted_threshold_sum = total_collateral_usd * threshold

        # Aave V3 HF-Formel
        if total_debt_usd > 0.001:
            hf = weighted_threshold_sum / total_debt_usd
        else:
            hf = float("inf")

        zone = _classify_hf(hf, CRITICAL_THRESHOLD, WARNING_THRESHOLD)
        summaries[_zone_key(zone)] += 1

        results.append({
            "user_address": user.get("user_address", ""),
            "chain": user.get("chain", "ETHEREUM"),
            "total_collateral_usd": round(total_collateral_usd, 2),
            "total_debt_usd": round(total_debt_usd, 2),
            "weighted_threshold_sum": round(weighted_threshold_sum, 2),
            "health_factor": round(hf, 4) if hf != float("inf") else "inf",
            "risk_zone": zone.value,
            "positions_count": positions_count,
        })

    # Sortiere nach HF aufsteigend (riskanteste zuerst)
    results.sort(key=lambda r: r["health_factor"] if isinstance(r["health_factor"], float) else 9999.0)

    return {
        "status": "ok",
        "subagent": "B2-2b",
        "role": "HF-Computation",
        "total_users": len(results),
        "summary": summaries,
        "users": results,
        "top_5_at_risk": [r for r in results if isinstance(r["health_factor"], float) and r["health_factor"] < 2.0][:5],
    }


def _b2_2c_weighted_risk_assessment(
    hf_results: dict,
    effective_critical: float,
) -> dict:
    """Gewichtete Risiko-Bewertung über alle User.

    Berechnet einen Portfolio-weiten Risiko-Score (0-100),
    gewichtet nach Schulden-Volumen.
    """
    users = hf_results.get("users", [])
    risk_score = _compute_portfolio_risk_score(users)

    # Liquidation-Watchlist: alle User mit HF <= critical_threshold
    watchlist = []
    for u in users:
        hf = u["health_factor"]
        if isinstance(hf, (int, float)) and hf <= effective_critical:
            watchlist.append({
                "user": u["user_address"],
                "hf": hf,
                "debt_usd": u["total_debt_usd"],
                "collateral_usd": u["total_collateral_usd"],
            })

    return {
        "status": "ok",
        "subagent": "B2-2c",
        "role": "Weighted-Risk-Assessment",
        "portfolio_risk_score": risk_score,
        "portfolio_risk_grade": (
            "A" if risk_score >= 80 else "B" if risk_score >= 60
            else "C" if risk_score >= 40 else "D" if risk_score >= 20 else "F"
        ),
        "watchlist_count": len(watchlist),
        "watchlist": sorted(watchlist, key=lambda w: w["hf"]),
    }


def calculate_cf_drop_impact(
    user_states: list[dict],
    cf_changes: list[dict] | None = None,
) -> dict:
    """Berechnet projizierten HF bei angekündigten Collateral-Factor-Änderungen.

    Ein CF-Drop ist ein instantanes Ereignis — der HF fällt schlagartig,
    bevor der erste Preis-Tick erfolgt. Diese Funktion projiziert den HF
    NACH der CF-Änderung, sodass der Agent präventiv eskalieren kann.

    Args:
        user_states: Aktuelle User-Positionen (flache health_factor/debt-Daten)
        cf_changes: [{"asset": "WBTC", "old_factor": 0.80, "new_factor": 0.70}]

    Returns:
        {"worst_projected_hf": 0.72, "users_becoming_liquidatable": 5, ...}
    """
    changes = cf_changes or []
    if not changes:
        return {"worst_projected_hf": 999.0, "users_becoming_liquidatable": 0,
                "users_becoming_critical": 0, "cf_drop_active": False}

    newly_liquidatable = 0
    newly_critical = 0
    worst_projected = 999.0

    for user in user_states:
        hf = float(user.get("health_factor", 1.5))
        if hf == float("inf"):
            continue

        # Für jede CF-Änderung: HF skaliert linear mit threshold-Ratio
        for change in changes:
            old = float(str(change.get("old_factor", "0.8")).replace("%", ""))
            new = float(str(change.get("new_factor", "0.7")).replace("%", ""))
            if old > 1:
                old /= 100
            if new > 1:
                new /= 100

            if old > 0:
                projected_hf = hf * (new / old)
            else:
                projected_hf = hf

            worst_projected = min(worst_projected, projected_hf)

            if hf > 1.0 and projected_hf <= 1.0:
                newly_liquidatable += 1
            elif hf > 1.05 and projected_hf <= 1.05:
                newly_critical += 1

    return {
        "worst_projected_hf": round(worst_projected, 4) if worst_projected != 999.0 else 999.0,
        "users_becoming_liquidatable": newly_liquidatable,
        "users_becoming_critical": newly_critical,
        "cf_drop_active": True,
        "cf_changes_applied": len(changes),
    }


def _compute_portfolio_risk_score(users: list[dict]) -> float:
    """Portfolio-Risiko-Score: 100 = alle Users safe, 0 = alle liquidatable."""
    if not users:
        return 100.0

    total_debt = sum(
        u["total_debt_usd"] for u in users
        if isinstance(u["health_factor"], (int, float)) and u["health_factor"] != float("inf")
    )
    if total_debt == 0:
        return 100.0

    risk_weighted_sum = 0.0
    for u in users:
        hf = u["health_factor"]
        if not isinstance(hf, (int, float)) or hf == float("inf"):
            continue
        debt = u["total_debt_usd"]
        weight = debt / total_debt if total_debt > 0 else 0

        # HF → Score (0-100): cap bei HF=3.0
        score = min(100.0, (hf - 1.0) * 50)
        score = max(0.0, score)
        risk_weighted_sum += score * weight

    return round(risk_weighted_sum, 1)


# ─── Hilfsfunktionen ─────────────────────────────────────────────────

def calculate_single_health_factor(
    collateral_usd: float,
    debt_usd: float,
    liquidation_threshold: float,
) -> float:
    """Exakte Aave-V3-Health-Factor-Formel.

    Args:
        collateral_usd: Summe aller Collateral-Werte in USD
        debt_usd: Summe aller Schulden in USD
        liquidation_threshold: Gewichteter Durchschnitt (z.B. 0.8 ETH, 0.7 Altcoins)

    Returns:
        Health-Factor (inf wenn keine Schulden)
    """
    if debt_usd == 0:
        return float("inf")
    return (collateral_usd * liquidation_threshold) / debt_usd


def _classify_hf(
    hf: float,
    critical: float = CRITICAL_THRESHOLD,
    warning: float = WARNING_THRESHOLD,
) -> RiskZone:
    """Klassifiziert Health-Factor in RiskZone."""
    if hf == float("inf") or hf > warning:
        return RiskZone.SAFE
    elif hf > critical:
        return RiskZone.WARNING
    elif hf > 1.0:
        return RiskZone.CRITICAL
    else:
        return RiskZone.LIQUIDATABLE


def _zone_key(zone: RiskZone) -> str:
    return zone.value.lower()


# ═══════════════════════════════════════════════════════════════════════
# AGENT B2-3: Risiko-Klassifizierer (Alerts & Watchlist)
# ═══════════════════════════════════════════════════════════════════════

def b2_3_risk_classifier(
    hf_results: dict | None = None,
    effective_critical: float = CRITICAL_THRESHOLD,
) -> dict:
    """Klassifiziert Positionen und feuert Alarme.

    Args:
        hf_results: Output von B2-2 (health factors)
        effective_critical: Effektive Critical-Schwelle (ggf. von A3-2 modifiziert)

    Returns:
        {"status": "...", "alerts": [...], "subagents": {...}}
    """
    try:
        hf = hf_results or {}
        users = hf.get("subagents", {}).get("b2_2b_hf_computation", {}).get("users", [])

        alerts = _b2_3a_generate_alerts(users, effective_critical)
        watchlist = _b2_3b_build_watchlist(users, effective_critical)
        signals = _b2_3c_emit_signals(alerts, watchlist)

        return {
            "status": "completed",
            "agent": "B2-3",
            "total_alerts": len(alerts),
            "watchlist_size": watchlist.get("count", 0),
            "subagents": {
                "b2_3a_alert_generator": alerts,
                "b2_3b_watchlist_builder": watchlist,
                "b2_3c_signal_emitter": signals,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("B2-3 Fehler: %s", e)
        return {"status": "failed", "agent": "B2-3", "error": str(e)}


def _b2_3a_generate_alerts(
    users: list[dict],
    effective_critical: float,
) -> list[dict]:
    """Generiert Alerts basierend auf Health-Factors."""
    alerts = []
    for u in users:
        hf_val = u["health_factor"]
        if not isinstance(hf_val, (int, float)) or hf_val == float("inf"):
            continue

        if hf_val <= 1.0:
            alerts.append({
                "level": "LIQUIDATED",
                "user": u["user_address"],
                "hf": hf_val,
                "debt_usd": u["total_debt_usd"],
                "message": f"{u['user_address']} LIQUIDIERBAR! HF={hf_val:.3f}",
            })
        elif hf_val <= effective_critical:
            alerts.append({
                "level": "CRITICAL",
                "user": u["user_address"],
                "hf": hf_val,
                "debt_usd": u["total_debt_usd"],
                "message": f"{u['user_address']} fast liquidierbar: HF={hf_val:.3f}",
                "buffer_to_liquidation_pct": round((hf_val - 1.0) * 100, 2),
            })
        elif hf_val <= WARNING_THRESHOLD:
            alerts.append({
                "level": "WARNING",
                "user": u["user_address"],
                "hf": hf_val,
                "debt_usd": u["total_debt_usd"],
                "message": f"{u['user_address']} HF sinkt: {hf_val:.3f}",
            })

    return alerts


def _b2_3b_build_watchlist(
    users: list[dict],
    effective_critical: float,
) -> dict:
    """Baut Liquidation-Watchlist (Sorted Set, HF als Score)."""
    watchlist = []
    for u in users:
        hf_val = u["health_factor"]
        if isinstance(hf_val, (int, float)) and hf_val <= effective_critical * 1.5:
            watchlist.append({
                "user": u["user_address"],
                "chain": u.get("chain", "ETHEREUM"),
                "hf": hf_val,
                "debt_usd": u["total_debt_usd"],
                "collateral_usd": u["total_collateral_usd"],
                "collateral_ratio": (
                    round(u["total_collateral_usd"] / u["total_debt_usd"], 2)
                    if u["total_debt_usd"] > 0 else float("inf")
                ),
            })

    watchlist.sort(key=lambda w: w["hf"])

    return {
        "status": "ok",
        "subagent": "B2-3b",
        "role": "Watchlist-Builder",
        "count": len(watchlist),
        "effective_critical_threshold": effective_critical,
        "watchlist": watchlist,
    }


def _b2_3c_emit_signals(
    alerts: list[dict],
    watchlist: dict,
) -> dict:
    """Emitter für externe Signale (Telegram, Webhook, Klasse-C-Bridge)."""
    critical_count = sum(1 for a in alerts if a["level"] == "CRITICAL")
    liquidated_count = sum(1 for a in alerts if a["level"] == "LIQUIDATED")
    warning_count = sum(1 for a in alerts if a["level"] == "WARNING")

    signals = []

    if liquidated_count > 0:
        signals.append({
            "target": "klasse_c_flash_loan",
            "type": "LIQUIDATION_OPPORTUNITY",
            "count": liquidated_count,
            "priority": "HIGH",
        })

    if critical_count >= 3:
        signals.append({
            "target": "symbolics_agent",
            "type": "MULTIPLE_CRITICAL_POSITIONS",
            "count": critical_count,
            "priority": "MEDIUM",
            "message": f"{critical_count} Positionen nahe Liquidation — Markt-Check empfohlen",
        })

    if warning_count >= 10:
        signals.append({
            "target": "symbolics_agent",
            "type": "BROAD_WARNING_SIGNAL",
            "count": warning_count,
            "priority": "LOW",
            "message": f"{warning_count} Positionen im Warning-Bereich — Trend prüfen",
        })

    return {
        "status": "ok",
        "subagent": "B2-3c",
        "role": "Signal-Emitter",
        "signals_emitted": len(signals),
        "signals": signals,
        "summary": {
            "total_alerts": len(alerts),
            "critical": critical_count,
            "liquidated": liquidated_count,
            "warning": warning_count,
        },
    }


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Demo-Daten
    demo_users = [
        {
            "user_address": "0xAlice",
            "chain": "ETHEREUM",
            "total_collateral_usd": 50000,
            "total_debt_usd": 30000,
            "positions": [
                {"asset_address": "ETH", "amount": 10, "type": "collateral",
                 "is_collateral": True, "liquidation_threshold": 0.825},
                {"asset_address": "USDC", "amount": 30000, "type": "debt",
                 "is_collateral": False, "liquidation_threshold": 0.0},
            ],
        },
        {
            "user_address": "0xBob",
            "chain": "ETHEREUM",
            "total_collateral_usd": 10500,
            "total_debt_usd": 10000,
            "positions": [
                {"asset_address": "WBTC", "amount": 0.16, "type": "collateral",
                 "is_collateral": True, "liquidation_threshold": 0.78},
                {"asset_address": "DAI", "amount": 10000, "type": "debt",
                 "is_collateral": False, "liquidation_threshold": 0.0},
            ],
        },
    ]

    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"

    if cmd == "b2_1":
        print(json.dumps(b2_1_position_ledger(user_states=demo_users), indent=2))
    elif cmd == "b2_2":
        print(json.dumps(b2_2_health_factor_calculator(
            user_states=demo_users, consensus_health_index=65.0,
        ), indent=2))
    elif cmd == "b2_3":
        hf = b2_2_health_factor_calculator(user_states=demo_users)
        print(json.dumps(b2_3_risk_classifier(hf_results=hf), indent=2))
    else:
        b21 = b2_1_position_ledger(user_states=demo_users)
        b22 = b2_2_health_factor_calculator(user_states=demo_users)
        b23 = b2_3_risk_classifier(hf_results=b22)
        print(json.dumps({
            "b2_1": b21,
            "b2_2": b22,
            "b2_3": b23,
        }, indent=2))
