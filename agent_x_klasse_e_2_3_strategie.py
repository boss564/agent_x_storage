"""
Agent X — Klasse E: Cluster E2 (Analytics) + E3 (Strategie).

E2: Parameter-Change-Simulator, Unlock-Pressure-Analyst, MEV-Prädiktor
E3: Countdown-Alarm, Hedge-Strategist, Vote-Agent

Strategische Langzeit-Agenten: Empfehlungen Tage bis Wochen im Voraus.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("klasse_e2_e3_strategie")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_unix() -> float:
    return time.time()


# ═══════════════════════════════════════════════════════════════════════
# AGENT E2-1: Parameter-Change-Simulator
# ═══════════════════════════════════════════════════════════════════════

def e2_1_parameter_simulator(
    pending_actions: list[dict] | None = None,
    user_positions: list[dict] | None = None,
) -> dict:
    """Simuliert, wie Governance-Änderungen DeFi-Protokolle beeinflussen.

    Args:
        pending_actions: Von E1-1c (Pending Timelock Actions)
        user_positions: Optionale User-Positionen für HF-Simulation

    Returns:
        {"status": "...", "affected_users": N, "subagents": {...}}
    """
    try:
        actions = pending_actions or []
        positions = user_positions or _demo_positions()

        interest = _e2_1a_simulate_interest_rate_change(actions, positions)
        collateral = _e2_1b_simulate_collateral_factor_change(actions, positions)
        apy_forecast = _e2_1c_forecast_pool_apy(interest, collateral)

        return {
            "status": "completed", "agent": "E2-1",
            "actions_simulated": len(actions),
            "users_affected": collateral.get("users_becoming_underwater", 0),
            "subagents": {
                "e2_1a_interest_rate": interest,
                "e2_1b_collateral_factor": collateral,
                "e2_1c_apy_forecast": apy_forecast,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("E2-1 Fehler: %s", e)
        return {"status": "failed", "error": str(e)}


def _e2_1a_simulate_interest_rate_change(actions: list[dict], positions: list[dict]) -> dict:
    """Simuliert Effekt von Zinsänderungen auf Borrow-Nachfrage."""
    interest_actions = [a for a in actions if "borrow" in a.get("action", "").lower() or "rate" in a.get("action", "").lower()]
    simulations = []

    for a in interest_actions:
        params = a.get("params", {})
        old_rate = float(str(params.get("old_rate", "3%")).replace("%", ""))
        new_rate = float(str(params.get("new_rate", "5%")).replace("%", ""))
        delta = new_rate - old_rate

        # Betroffene Borrower (geschätzt)
        affected = sum(1 for p in positions if p.get("debt_usd", 0) > 0)
        increased_cost = sum(p.get("debt_usd", 0) * (delta / 100) for p in positions if p.get("debt_usd", 0) > 0)

        simulations.append({
            "action": a.get("action", "?"),
            "rate_delta_pct": round(delta, 1),
            "affected_borrowers": affected,
            "total_increased_cost_usd_per_year": round(increased_cost, 2),
            "hf_impact": (
                "significant" if delta > 2
                else "moderate" if delta > 1
                else "minor"
            ),
        })

    return {
        "status": "ok", "subagent": "E2-1a", "role": "Interest-Rate-Simulator",
        "simulations": simulations,
    }


def _e2_1b_simulate_collateral_factor_change(actions: list[dict], positions: list[dict]) -> dict:
    """Simuliert: welche User geraten unter Wasser bei Collateral-Faktor-Änderung."""
    cf_actions = [a for a in actions if "collateral" in a.get("action", "").lower()]
    newly_underwater = []

    for a in cf_actions:
        params = a.get("params", {})
        old_cf = float(str(params.get("old_factor", "0.8")).replace("%", ""))
        if old_cf > 1:
            old_cf /= 100
        new_cf = float(str(params.get("new_factor", "0.7")).replace("%", ""))
        if new_cf > 1:
            new_cf /= 100

        for pos in positions:
            collat = pos.get("collateral_usd", 0)
            debt = pos.get("debt_usd", 0)
            if debt == 0:
                continue
            old_hf = (collat * old_cf) / debt
            new_hf = (collat * new_cf) / debt
            if old_hf > 1.0 and new_hf <= 1.0:
                newly_underwater.append({
                    "user": pos.get("user_address", ""),
                    "old_hf": round(old_hf, 3),
                    "new_hf": round(new_hf, 3),
                    "debt_usd": debt,
                })

    return {
        "status": "ok", "subagent": "E2-1b", "role": "Collateral-Factor-Simulator",
        "users_becoming_underwater": len(newly_underwater),
        "users": newly_underwater,
    }


def _e2_1c_forecast_pool_apy(interest_result: dict, collateral_result: dict) -> dict:
    """Prognostiziert Pool-APY-Änderungen und Kapitalflüsse."""
    sims = interest_result.get("simulations", [])
    apy_changes = []
    for s in sims:
        delta = s.get("rate_delta_pct", 0)
        # APY reagiert verzögert und gedämpft
        supply_change = -delta * 0.3  # Höhere Borrow-Rate → weniger Supply
        apy_changes.append({
            "rate_delta": delta,
            "estimated_supply_apy_change_pct": round(delta * 0.7, 2),
            "estimated_borrow_apy_change_pct": delta,
            "capital_flow": "outflow" if supply_change < -1 else "neutral" if abs(supply_change) < 1 else "inflow",
        })

    return {
        "status": "ok", "subagent": "E2-1c", "role": "Pool-APY-Forecaster",
        "apy_changes": apy_changes,
    }


def _demo_positions() -> list[dict]:
    return [
        {"user_address": "0xAlice", "collateral_usd": 50000, "debt_usd": 30000},
        {"user_address": "0xBob", "collateral_usd": 10500, "debt_usd": 10000},
        {"user_address": "0xCarol", "collateral_usd": 100000, "debt_usd": 75000},
    ]


# ═══════════════════════════════════════════════════════════════════════
# AGENT E2-2: Token-Unlock-Pressure-Analyst
# ═══════════════════════════════════════════════════════════════════════

def e2_2_unlock_pressure_analyst(
    unlock_data: list[dict] | None = None,
    market_caps: dict[str, float] | None = None,
) -> dict:
    """Berechnet Verkaufsdruck durch Token-Unlocks.

    Args:
        unlock_data: Von E1-2c (By-Token Unlocks)
        market_caps: Token → Market-Cap in USD

    Returns:
        {"status": "...", "highest_pressure_token": "X", "subagents": {...}}
    """
    try:
        by_token = unlock_data or []
        caps = market_caps or {"ARB": 1_200_000_000, "OP": 900_000_000, "PYTH": 400_000_000}

        supply = _e2_2a_calculate_liquid_supply(by_token, caps)
        dump = _e2_2b_estimate_daily_dump(supply)
        price_impact = _e2_2c_model_price_impact(dump)

        return {
            "status": "completed", "agent": "E2-2",
            "highest_pressure_token": price_impact.get("highest_impact_token", ""),
            "subagents": {
                "e2_2a_liquid_supply": supply,
                "e2_2b_daily_dump": dump,
                "e2_2c_price_impact": price_impact,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("E2-2 Fehler: %s", e)
        return {"status": "failed", "error": str(e)}


def _e2_2a_calculate_liquid_supply(by_token: list[dict], caps: dict) -> dict:
    """Berechnet zusätzliches Angebot durch Unlocks."""
    results = []
    for t in by_token:
        token = t.get("token", "?")
        total = t.get("total_upcoming", 0)
        next_amount = t.get("next_unlock_amount", 0)
        mc = caps.get(token, 1_000_000_000)
        # Preis aus Market-Cap schätzen (stark vereinfacht)
        est_circulating = mc / 0.5  # Annäherung
        supply_increase_pct = (total / est_circulating * 100) if est_circulating > 0 else 0

        results.append({
            "token": token,
            "total_upcoming_tokens": total,
            "estimated_circulating": est_circulating,
            "supply_increase_pct": round(supply_increase_pct, 2),
            "severity": "high" if supply_increase_pct > 5 else "moderate" if supply_increase_pct > 1 else "low",
        })

    return {
        "status": "ok", "subagent": "E2-2a", "role": "Liquid-Supply-Calculator",
        "results": results,
    }


def _e2_2b_estimate_daily_dump(supply_result: dict) -> dict:
    """Schätzt täglichen Verkaufsdruck (typisch 15-30% des Unlocks in 24h)."""
    results = supply_result.get("results", [])
    dump_estimates = []
    for r in results:
        next_amount = r.get("total_upcoming_tokens", 0)
        # Historisch: 15-25% wird in 24h verkauft
        dump_pct = 0.20
        daily_dump = next_amount * dump_pct
        est_price = 1.0  # Wird von Oracle geliefert
        daily_dump_usd = daily_dump * est_price

        dump_estimates.append({
            "token": r["token"],
            "estimated_24h_dump_tokens": round(daily_dump, 0),
            "estimated_24h_dump_usd": round(daily_dump_usd, 0),
            "dump_percentage_of_unlock": round(dump_pct * 100, 1),
        })

    return {
        "status": "ok", "subagent": "E2-2b", "role": "Daily-Dump-Volume",
        "estimates": dump_estimates,
    }


def _e2_2c_model_price_impact(dump_result: dict) -> dict:
    """Multipliziert Verkaufsdruck mit Liquiditätstiefe → geschätzte Preissenkung."""
    estimates = dump_result.get("estimates", [])
    impacts = []
    highest = ""

    for e in estimates:
        daily_dump_usd = e.get("estimated_24h_dump_usd", 0)
        # Liquiditätstiefe aus DEX-Daten (Klasse D)
        liquidity_1pct = 5_000_000  # $5M für 1% Impact
        price_impact = (daily_dump_usd / liquidity_1pct) if liquidity_1pct > 0 else 0

        impacts.append({
            "token": e["token"],
            "estimated_price_impact_pct": round(price_impact, 3),
            "severity": "high" if price_impact > 5 else "moderate" if price_impact > 1 else "low",
        })

    if impacts:
        impacts.sort(key=lambda i: i["estimated_price_impact_pct"], reverse=True)
        highest = impacts[0]["token"]

    return {
        "status": "ok", "subagent": "E2-2c", "role": "Price-Impact-Model",
        "highest_impact_token": highest,
        "impacts": impacts,
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT E2-3: MEV- & Stress-Prädiktor
# ═══════════════════════════════════════════════════════════════════════

def e2_3_stress_predictor(
    timelock_timeline: list[dict] | None = None,
    unlock_data: list[dict] | None = None,
) -> dict:
    """Sagt MEV- und Markt-Stress durch zukünftige Events voraus.

    Brücke zu Klasse B (Druckventile) und C (Lending).
    """
    try:
        timeline = timelock_timeline or []
        unlocks = unlock_data or []

        bribe = _e2_3a_forecast_bribe_spikes(timeline, unlocks)
        cascade = _e2_3b_predict_liquidation_cascade(timeline)
        fl_windows = _e2_3c_identify_flash_loan_windows(bribe, cascade)

        return {
            "status": "completed", "agent": "E2-3",
            "subagents": {
                "e2_3a_bribe_forecast": bribe,
                "e2_3b_cascade_risk": cascade,
                "e2_3c_flash_loan_windows": fl_windows,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("E2-3 Fehler: %s", e)
        return {"status": "failed", "error": str(e)}


def _e2_3a_forecast_bribe_spikes(timeline: list[dict], unlocks: list[dict]) -> dict:
    """Sagt MEV-Bribe-Spikes 24h vor großen Events voraus."""
    spikes = []
    for t in timeline:
        hours = t.get("hours_until_executable", 999)
        if hours < 48 and t.get("impact_score", 0) >= 6:
            spikes.append({
                "event": t.get("action", "?"),
                "hours_until": hours,
                "expected_bribe_multiplier": round(1 + (48 - hours) / 48 * 2, 1),
                "reason": f"MEV-Bots positionieren sich {hours:.0f}h vor {t.get('action','?')}",
            })

    return {
        "status": "ok", "subagent": "E2-3a", "role": "Bribe-Spike-Forecaster",
        "predicted_spikes": len(spikes), "spikes": spikes,
    }


def _e2_3b_predict_liquidation_cascade(timeline: list[dict]) -> dict:
    """Warnt vor Kombination von Zinserhöhung + Collateral-Senkung."""
    high_impact = [t for t in timeline if t.get("impact_score", 0) >= 7]
    risk = len(high_impact) > 0

    return {
        "status": "ok", "subagent": "E2-3b", "role": "Liquidation-Cascade-Risk",
        "cascade_risk_pct": min(90, len(high_impact) * 30),
        "high_risk_events": high_impact,
        "warning": (
            f"⚠️ {len(high_impact)} High-Impact-Events in den nächsten 72h — "
            "Liquidations-Kaskade möglich!" if risk
            else "Keine erhöhte Kaskaden-Gefahr"
        ),
    }


def _e2_3c_identify_flash_loan_windows(bribe_result: dict, cascade_result: dict) -> dict:
    """Identifiziert Flash-Loan-Fenster durch kombinierte Events."""
    windows = []
    if cascade_result.get("cascade_risk_pct", 0) > 50:
        windows.append({
            "type": "liquidation_arbitrage",
            "profit_potential": "HIGH",
            "window_hours": 48,
            "action": "Flash-Loan für Liquidation-Cascades vorbereiten",
        })

    return {
        "status": "ok", "subagent": "E2-3c", "role": "Flash-Loan-Opportunity-Window",
        "windows": windows,
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT E3-1: Timelock-Countdown-Alarm
# ═══════════════════════════════════════════════════════════════════════

def e3_1_countdown_alarm(
    pending_actions: list[dict] | None = None,
) -> dict:
    """Feuert mehrstufige Alarme 72/48/24/12h vor Timelock-Events.

    Returns:
        {"status": "...", "alerts_fired": N, "subagents": {...}}
    """
    try:
        actions = pending_actions or []
        multi = _e3_1a_multistage_alarm(actions)
        recommendations = _e3_1b_action_recommendation(actions)
        dashboard = _e3_1c_dashboard_update(multi, recommendations)

        return {
            "status": "completed", "agent": "E3-1",
            "alerts_fired": multi.get("alerts_fired", 0),
            "subagents": {
                "e3_1a_multistage": multi,
                "e3_1b_recommendations": recommendations,
                "e3_1c_dashboard": dashboard,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("E3-1 Fehler: %s", e)
        return {"status": "failed", "error": str(e)}


def _e3_1a_multistage_alarm(actions: list[dict]) -> dict:
    """12/24/48/72h-Mehrstufenalarme."""
    now = _now_unix()
    alerts = []
    thresholds = [(12, "CRITICAL"), (24, "HIGH"), (48, "MEDIUM"), (72, "INFO")]

    for a in actions:
        hours = a.get("hours_until_executable", 999)
        for thresh, level in thresholds:
            if hours <= thresh:
                alerts.append({
                    "action": a.get("action", "?"),
                    "timelock": a.get("timelock", "?"),
                    "hours_remaining": round(hours, 1),
                    "alert_level": level,
                    "message": (
                        f"{'🔴' if level == 'CRITICAL' else '🟠' if level == 'HIGH' else '🟡'}"
                        f" {a.get('action','?')} in {hours:.1f}h — "
                        f"{'SOFORT HANDELN!' if level == 'CRITICAL' else 'Vorbereiten.' if level == 'HIGH' else 'Monitoren.'}"
                    ),
                })
                break

    return {
        "status": "ok", "subagent": "E3-1a", "role": "Multistage-Alarm",
        "alerts_fired": len(alerts), "alerts": alerts,
    }


def _e3_1b_action_recommendation(actions: list[dict]) -> dict:
    """Konkrete Handlungsempfehlungen basierend auf Action-Typ."""
    recs = []
    for a in actions:
        action = a.get("action", "")
        if "borrow" in action.lower() or "rate" in action.lower():
            recs.append({
                "action": "Reduziere Borrow-Position um 20-30%",
                "reason": f"Zinserhöhung in {a.get('hours_until_executable',0):.0f}h",
                "deadline_h": a.get("hours_until_executable", 24),
            })
        elif "collateral" in action.lower():
            recs.append({
                "action": "Prüfe Collateral-Ratio — ggf. deleveragen",
                "reason": f"Collateral-Faktor-Änderung in {a.get('hours_until_executable',0):.0f}h",
                "deadline_h": a.get("hours_until_executable", 24),
            })

    return {
        "status": "ok", "subagent": "E3-1b", "role": "Action-Recommendation",
        "recommendations": recs,
    }


def _e3_1c_dashboard_update(multi: dict, recs: dict) -> dict:
    """Aktualisiert Future-Events-Tabelle für SymbolicsAgent."""
    return {
        "status": "ok", "subagent": "E3-1c", "role": "Dashboard-Update",
        "active_alerts": multi.get("alerts_fired", 0),
        "pending_recommendations": len(recs.get("recommendations", [])),
        "next_update_epoch_s": 12,
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT E3-2: Pre-Unlock-Hedge-Strategist
# ═══════════════════════════════════════════════════════════════════════

def e3_2_hedge_strategist(
    unlock_pressure: list[dict] | None = None,
    portfolio_tokens: list[str] | None = None,
) -> dict:
    """Entwickelt Hedging-Strategien für bevorstehende Token-Unlocks.

    Returns:
        {"status": "...", "signals": [...], "subagents": {...}}
    """
    try:
        pressure = unlock_pressure or []
        portfolio = portfolio_tokens or ["ETH", "ARB", "OP"]

        short = _e3_2a_generate_short_signals(pressure, portfolio)
        arb = _e3_2b_prepare_arbitrage(pressure)
        rebalance = _e3_2c_rebalance_portfolio(short, arb, portfolio)

        return {
            "status": "completed", "agent": "E3-2",
            "signals_generated": len(short.get("signals", [])),
            "subagents": {
                "e3_2a_short_signals": short,
                "e3_2b_arbitrage_prep": arb,
                "e3_2c_portfolio_rebalancer": rebalance,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("E3-2 Fehler: %s", e)
        return {"status": "failed", "error": str(e)}


def _e3_2a_generate_short_signals(pressure: list[dict], portfolio: list[str]) -> dict:
    """Short-Signal wenn großer Unlock + niedrige Liquidität."""
    signals = []
    for p in pressure:
        token = p.get("token", "")
        if token in portfolio and p.get("supply_increase_pct", 0) > 2:
            signals.append({
                "token": token,
                "direction": "SHORT",
                "confidence": "HIGH" if p.get("supply_increase_pct", 0) > 5 else "MEDIUM",
                "reason": f"{token}: {p['supply_increase_pct']:.1f}% Supply-Increase",
            })

    return {
        "status": "ok", "subagent": "E3-2a", "role": "Short-Signal-Generator",
        "signals": signals,
    }


def _e3_2b_prepare_arbitrage(pressure: list[dict]) -> dict:
    """Bereitet Arbitrage-Transaktionen für Unlock-Votalität vor."""
    return {
        "status": "ok", "subagent": "E3-2b", "role": "Arbitrage-Prepper",
        "opportunities": 0,
        "note": "Wird dynamisch bei Unlock-Event aktiviert",
    }


def _e3_2c_rebalance_portfolio(short: dict, arb: dict, portfolio: list[str]) -> dict:
    """Empfiehlt Portfolio-Rebalancing vor Unlocks."""
    signals = short.get("signals", [])
    swaps = []
    for s in signals:
        swaps.append({
            "from": s["token"],
            "to": "USDC",
            "reason": f"Hedge vor {s['token']}-Unlock ({s['confidence']} confidence)",
            "suggested_pct": 50 if s["confidence"] == "HIGH" else 25,
        })

    return {
        "status": "ok", "subagent": "E3-2c", "role": "Portfolio-Rebalancer",
        "suggested_swaps": swaps,
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT E3-3: Governance-Vote-Agent
# ═══════════════════════════════════════════════════════════════════════

def e3_3_vote_agent(
    proposals: list[dict] | None = None,
) -> dict:
    """Analysiert Proposals und empfiehlt Voting-Strategie.

    Returns:
        {"status": "...", "vote_recommendations": N, "subagents": {...}}
    """
    try:
        proposals = proposals or []

        recommend = _e3_3a_recommend_vote(proposals)
        delegates = _e3_3b_track_delegations(proposals)
        predict = _e3_3c_predict_outcome(proposals)

        return {
            "status": "completed", "agent": "E3-3",
            "vote_recommendations": len(recommend.get("recommendations", [])),
            "subagents": {
                "e3_3a_vote_recommender": recommend,
                "e3_3b_delegation_tracker": delegates,
                "e3_3c_outcome_predictor": predict,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("E3-3 Fehler: %s", e)
        return {"status": "failed", "error": str(e)}


def _e3_3a_recommend_vote(proposals: list[dict]) -> dict:
    """Empfiehlt For/Against basierend auf Simulationsergebnissen."""
    recs = []
    for p in proposals:
        impact = p.get("effective_impact_score", 5)
        rec = "AGAINST" if impact > 7 else "FOR" if impact < 4 else "ABSTAIN"
        recs.append({
            "proposal": p.get("id", "?"),
            "recommendation": rec,
            "reason": (
                "Hoher negativer Impact erwartet" if rec == "AGAINST"
                else "Niedriger Impact — unterstützen" if rec == "FOR"
                else "Unklar — abwarten"
            ),
        })

    return {
        "status": "ok", "subagent": "E3-3a", "role": "Vote-Recommender",
        "recommendations": recs,
    }


def _e3_3b_track_delegations(proposals: list[dict]) -> dict:
    """Trackt Voting-Patterns anderer Wallets."""
    return {
        "status": "ok", "subagent": "E3-3b", "role": "Delegation-Tracker",
        "tracked_wallets": 0,
        "note": "On-Chain-Delegation-Tracking via eth_call (Governance-Contracts)",
    }


def _e3_3c_predict_outcome(proposals: list[dict]) -> dict:
    """Sagt Proposal-Ausgang voraus."""
    for p in proposals:
        p["predicted_outcome"] = (
            "PASS" if p.get("estimated_pass_probability", 50) > 66
            else "FAIL" if p.get("estimated_pass_probability", 50) < 40
            else "UNCERTAIN"
        )

    return {
        "status": "ok", "subagent": "E3-3c", "role": "Outcome-Predictor",
        "predictions": [
            {"proposal": p.get("id", "?"), "outcome": p.get("predicted_outcome", "?")}
            for p in proposals
        ],
    }


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"

    demo_actions = [
        {"action": "setReserveBorrowRate", "timelock": "Aave_v3",
         "hours_until_executable": 23, "impact_score": 7,
         "params": {"new_rate": "5%", "old_rate": "3%"}},
        {"action": "setCollateralFactor", "timelock": "Compound",
         "hours_until_executable": 24, "impact_score": 8,
         "params": {"new_factor": "0.70", "old_factor": "0.80"}},
    ]

    if cmd == "e2_1":
        from e2_1_parameter_simulator import e2_1_parameter_simulator  # noqa
        print(json.dumps(e2_1_parameter_simulator(pending_actions=demo_actions), indent=2))
    elif cmd == "e3_1":
        print(json.dumps(e3_1_countdown_alarm(pending_actions=demo_actions), indent=2))
    else:
        print(json.dumps({
            "e2_1": e2_1_parameter_simulator(pending_actions=demo_actions),
            "e2_2": e2_2_unlock_pressure_analyst(),
            "e2_3": e2_3_stress_predictor(timelock_timeline=demo_actions),
            "e3_1": e3_1_countdown_alarm(pending_actions=demo_actions),
            "e3_2": e3_2_hedge_strategist(),
            "e3_3": e3_3_vote_agent(),
        }, indent=2))
