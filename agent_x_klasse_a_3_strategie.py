"""
Agent X — Klasse A: Cluster A3 (Strategische Outputs für SymbolicsAgent).

Schnittstelle zu SymbolicsAgent und DeFi-Agenten (Klasse B & C).
Timing, Health-Score und Order-Routing.

Agenten:
  A3-1: Proposer- & Leader-Schedule-Forecaster  — 3 Subagenten
  A3-2: Netzwerk-Gesundheits- & Stress-Klassifizierer — 3 Subagenten
  A3-3: Deterministic Order-Routing-Optimizer   — 3 Subagenten
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("klasse_a3_strategie")

# ─── Konfiguration ───────────────────────────────────────────────────

SLOT_DURATION_ETH = 12.0    # Sekunden pro ETH-Slot
SLOT_DURATION_SOL = 0.4     # Sekunden pro Solana-Slot
PREDICT_AHEAD_ETH = 64      # Slots vorausberechnen (~12.8 min)
PREDICT_AHEAD_SOL = 100     # Slots vorausberechnen (~40s)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_unix() -> float:
    return datetime.now(timezone.utc).timestamp()


# ═══════════════════════════════════════════════════════════════════════
# AGENT A3-1: Proposer- & Leader-Schedule-Forecaster
# ═══════════════════════════════════════════════════════════════════════

def a3_1_proposer_forecaster(
    current_eth_slot: int = 0,
    current_sol_slot: int = 0,
    eth_schedule: list[dict] | None = None,
    sol_schedule: list[dict] | None = None,
) -> dict:
    """Beantwortet: Wer produziert den nächsten Block auf ETH / Solana?

    Speist direkt in:
      - C2 (Arbitrage): Exakte Slot-Zeiten für optimalen Tx-Broadcast
    """
    try:
        now_unix = _now_unix()

        eth_timing = _a3_1a_eth_block_timing(current_eth_slot, now_unix)
        sol_mapper = _a3_1b_solana_leader_mapper(current_sol_slot, sol_schedule or [])
        cross_chain = _a3_1c_cross_chain_overlap(
            eth_timing.get("next_slots", []),
            sol_mapper.get("next_slots", []),
        )

        return {
            "status": "completed",
            "agent": "A3-1",
            "subagents": {
                "a3_1a_eth_timing": eth_timing,
                "a3_1b_sol_leader": sol_mapper,
                "a3_1c_cross_chain": cross_chain,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("A3-1 Fehler: %s", e)
        return {"status": "failed", "agent": "A3-1", "error": str(e)}


def _a3_1a_eth_block_timing(current_slot: int, now_unix: float) -> dict:
    """Berechnet exakte UNIX-Timestamps der nächsten 64 ETH-Slots (~12.8 min).

    Ausgabe fließt in:
      - C2 (Arbitrage-Agent): Optimaler Broadcast-Zeitpunkt
    """
    next_slots = []
    for i in range(PREDICT_AHEAD_ETH):
        slot = current_slot + i
        ts = now_unix + (i * SLOT_DURATION_ETH)
        next_slots.append({
            "slot": slot,
            "unix_timestamp": round(ts, 3),
            "iso_time": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
            "offset_ms": round(i * SLOT_DURATION_ETH * 1000),
        })

    return {
        "status": "ok",
        "subagent": "A3-1a",
        "role": "ETH-Block-Timing-Predictor",
        "current_slot": current_slot,
        "slots_predicted": PREDICT_AHEAD_ETH,
        "prediction_horizon_seconds": round(PREDICT_AHEAD_ETH * SLOT_DURATION_ETH, 1),
        "next_slot_at": next_slots[0]["iso_time"] if next_slots else None,
        "next_slot_unix": next_slots[0]["unix_timestamp"] if next_slots else None,
        "next_slots": next_slots,
    }


def _a3_1b_solana_leader_mapper(
    current_sol_slot: int,
    sol_schedule: list[dict],
) -> dict:
    """Ordnet aktuelle und nächste 100 Solana-Slots den Validator-Pubkeys zu."""
    next_slots = []
    if sol_schedule:
        # Aus Schedule die nächsten Slots filtern
        start = current_sol_slot
        for entry in sol_schedule:
            if entry.get("slot", 0) >= start:
                next_slots.append(entry)
            if len(next_slots) >= PREDICT_AHEAD_SOL:
                break

    # Falls kein Schedule: Platzhalter
    if not next_slots:
        now_unix = _now_unix()
        for i in range(PREDICT_AHEAD_SOL):
            slot = current_sol_slot + i
            ts = now_unix + (i * SLOT_DURATION_SOL)
            next_slots.append({
                "slot": slot,
                "leader_pubkey": "unknown",  # im Produktivbetrieb aus Schedule
                "unix_timestamp": round(ts, 3),
                "offset_ms": round(i * SLOT_DURATION_SOL * 1000),
            })

    return {
        "status": "ok",
        "subagent": "A3-1b",
        "role": "Solana-Leader-Mapper",
        "current_sol_slot": current_sol_slot,
        "slots_mapped": len(next_slots),
        "unique_leaders": len({s.get("leader_pubkey") for s in next_slots}),
        "next_slots": next_slots,
    }


def _a3_1c_cross_chain_overlap(
    eth_slots: list[dict],
    sol_slots: list[dict],
) -> dict:
    """Findet Zeitfenster, in denen ETH- und Solana-Blöcke gleichzeitig produziert werden.

    Perfekt für atomare Cross-Chain-Arbitrage.
    """
    overlaps = []
    tolerance_ms = 200  # 200ms Fenster für "gleichzeitig"

    if eth_slots and sol_slots:
        eth_idx, sol_idx = 0, 0
        while eth_idx < len(eth_slots) and sol_idx < len(sol_slots):
            eth_ts = eth_slots[eth_idx].get("unix_timestamp", 0)
            sol_ts = sol_slots[sol_idx].get("unix_timestamp", 0)
            diff_ms = abs(eth_ts - sol_ts) * 1000

            if diff_ms < tolerance_ms:
                overlaps.append({
                    "eth_slot": eth_slots[eth_idx].get("slot"),
                    "sol_slot": sol_slots[sol_idx].get("slot"),
                    "eth_timestamp": eth_ts,
                    "sol_timestamp": sol_ts,
                    "delta_ms": round(diff_ms, 1),
                })

            if eth_ts < sol_ts:
                eth_idx += 1
            else:
                sol_idx += 1

    return {
        "status": "ok",
        "subagent": "A3-1c",
        "role": "Cross-Chain-Overlap-Detector",
        "overlaps_found": len(overlaps),
        "tolerance_ms": tolerance_ms,
        "overlaps": overlaps,
        "cross_chain_opportunity": len(overlaps) > 0,
        "recommendation": (
            f"{len(overlaps)} atomare Cross-Chain-Fenster gefunden — Arbitrage möglich"
            if overlaps else "Keine Überlappung — sequenzielle Ausführung empfohlen"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT A3-2: Netzwerk-Gesundheits- & Stress-Klassifizierer
# ═══════════════════════════════════════════════════════════════════════

def a3_2_health_classifier(
    exit_queue_length: int = 0,
    participation_rate: float = 0.95,
    finality_status: str = "on_time",
    reorg_depth: int = 0,
) -> dict:
    """Fasst alle Klasse-A-Metriken zum Consensus Health Index (0–100) zusammen.

    Unter 60 Punkten → DeFi-Agenten drosseln oder pausieren.
    """
    try:
        churn_score = _a3_2a_churn_stress(exit_queue_length)
        participation_score = _a3_2b_participation_grade(participation_rate)
        finality_score = _a3_2c_finality_risk(finality_status, reorg_depth)

        # Gewichteter Health-Index
        health_index = round(
            churn_score["score"] * 0.30 +
            participation_score["score"] * 0.40 +
            finality_score["score"] * 0.30,
            1,
        )

        # Ableitung von Handlungsempfehlungen
        if health_index >= 80:
            state = "healthy"
            recommendation = "Alle DeFi-Operationen freigegeben"
        elif health_index >= 60:
            state = "caution"
            recommendation = "Flash-Loans mit erhöhtem Slippage ausführen"
        elif health_index >= 40:
            state = "stressed"
            recommendation = "Nur einfache Swaps, keine Flash-Loans, Lending-Positionen prüfen"
        elif health_index >= 20:
            state = "degraded"
            recommendation = "Nur Read-Operationen, keine Transaktionen senden"
        else:
            state = "critical"
            recommendation = "ALLE DeFi-Operationen pausieren — Netzwerk instabil"

        return {
            "status": "completed",
            "agent": "A3-2",
            "consensus_health_index": health_index,
            "network_state": state,
            "recommendation": recommendation,
            "subagents": {
                "a3_2a_churn": churn_score,
                "a3_2b_participation": participation_score,
                "a3_2c_finality": finality_score,
            },
            "weights": {"churn": 0.30, "participation": 0.40, "finality": 0.30},
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("A3-2 Fehler: %s", e)
        return {"status": "failed", "agent": "A3-2", "error": str(e)}


def _a3_2a_churn_stress(exit_queue_length: int) -> dict:
    """Bewertet Exit-Druck: hohe Punktzahl = wenig Stress (Exit-Queue klein)."""
    if exit_queue_length <= 10:
        score = 100.0
        level = "minimal"
    elif exit_queue_length <= 50:
        score = 85.0
        level = "low"
    elif exit_queue_length <= 200:
        score = 65.0
        level = "moderate"
    elif exit_queue_length <= 1000:
        score = 40.0
        level = "elevated"
    elif exit_queue_length <= 5000:
        score = 20.0
        level = "high"
    else:
        score = 5.0
        level = "extreme"

    return {
        "status": "ok",
        "subagent": "A3-2a",
        "role": "Validator-Churn-Stress",
        "exit_queue_length": exit_queue_length,
        "score": score,
        "level": level,
        "contribution": round(score * 0.30, 1),
    }


def _a3_2b_participation_grade(participation_rate: float) -> dict:
    """Notet Partizipationsrate. Normal > 95%. Alles darunter = Warnsignal."""
    rate_pct = participation_rate * 100 if participation_rate <= 1 else participation_rate

    if rate_pct >= 98:
        score = 100.0
        grade = "excellent"
    elif rate_pct >= 95:
        score = 85.0
        grade = "normal"
    elif rate_pct >= 90:
        score = 60.0
        grade = "below_average"
    elif rate_pct >= 80:
        score = 35.0
        grade = "poor"
    elif rate_pct >= 66:
        score = 15.0
        grade = "dangerous"
    else:
        score = 0.0
        grade = "chain_stall_risk"

    return {
        "status": "ok",
        "subagent": "A3-2b",
        "role": "Network-Participation-Grade",
        "participation_rate_pct": round(rate_pct, 2),
        "score": score,
        "grade": grade,
        "warning_triggered": rate_pct < 95.0,
        "contribution": round(score * 0.40, 1),
    }


def _a3_2c_finality_risk(finality_status: str, reorg_depth: int) -> dict:
    """Berechnet Wahrscheinlichkeit nicht-finalisierter Epoche."""
    status_scores = {
        "on_time": 100.0,
        "slight_delay": 75.0,
        "moderate_delay": 45.0,
        "severe_delay": 15.0,
    }
    base_score = status_scores.get(finality_status, 50.0)

    # Reorg-Abzug: je tiefer, desto schlechter
    reorg_penalty = min(reorg_depth * 10, 40)
    score = max(0.0, base_score - reorg_penalty)

    if score >= 90:
        risk = "minimal"
    elif score >= 60:
        risk = "low"
    elif score >= 30:
        risk = "moderate"
    else:
        risk = "high"

    return {
        "status": "ok",
        "subagent": "A3-2c",
        "role": "Finality-Risk-Score",
        "finality_status": finality_status,
        "reorg_depth": reorg_depth,
        "reorg_penalty": reorg_penalty,
        "score": score,
        "risk_level": risk,
        "contribution": round(score * 0.30, 1),
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT A3-3: Deterministic Order-Routing-Optimizer
# ═══════════════════════════════════════════════════════════════════════

def a3_3_order_routing_optimizer(
    eth_slots: list[dict] | None = None,
    sol_slots: list[dict] | None = None,
    trusted_validators: list[str] | None = None,
    health_index: float = 85.0,
) -> dict:
    """Nutzt Leader-Schedules zur Minimierung von Frontrunning/Sandwiching.

    Gibt konkrete Sendeempfehlung: „Sende Tx in genau X Sekunden (Slot Y).“
    """
    try:
        trusted = set(trusted_validators or [])
        eth_slots_list = eth_slots or []
        sol_slots_list = sol_slots or []

        slot_finder = _a3_3a_lowest_latency_slot(eth_slots_list, sol_slots_list, trusted, health_index)
        builder = _a3_3b_builder_broker(slot_finder)
        dispatcher = _a3_3c_tx_dispatch_optimizer(slot_finder, builder)

        return {
            "status": "completed",
            "agent": "A3-3",
            "subagents": {
                "a3_3a_slot_finder": slot_finder,
                "a3_3b_builder": builder,
                "a3_3c_dispatcher": dispatcher,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("A3-3 Fehler: %s", e)
        return {"status": "failed", "agent": "A3-3", "error": str(e)}


def _a3_3a_lowest_latency_slot(
    eth_slots: list[dict],
    sol_slots: list[dict],
    trusted_validators: set[str],
    health_index: float,
) -> dict:
    """Sucht den nächsten Slot mit vertrauenswürdigem/MEV-neutralem Validator.

    Bevorzugt Slots von bekannten, nicht-MEV-extrahierenden Validatoren.
    """
    best_eth = None
    best_sol = None
    reason = None

    # ETH: nächsten vertrauenswürdigen Slot finden
    for s in eth_slots[:10]:  # nur die nächsten 10 prüfen
        proposer = str(s.get("proposer_index", ""))
        if trusted_validators and proposer in trusted_validators:
            best_eth = s
            reason = f"Vertrauenswürdiger ETH-Validator {proposer} in {s.get('offset_ms', 0)}ms"
            break

    if not best_eth and eth_slots:
        best_eth = eth_slots[0]
        reason = "Kein bevorzugter Validator verfügbar — nächsten Slot nehmen"

    # Solana: nächsten vertrauenswürdigen Leader finden
    for s in sol_slots[:10]:
        leader = str(s.get("leader_pubkey", ""))
        if trusted_validators and leader in trusted_validators:
            best_sol = s
            if not best_eth:
                reason = f"Vertrauenswürdiger Solana-Leader {leader[:12]}..."
            break

    if not best_sol and sol_slots:
        best_sol = sol_slots[0]

    # Wenn Health-Index < 60: nur vertrauenswürdige Validatoren
    restricted = health_index < 60

    return {
        "status": "ok",
        "subagent": "A3-3a",
        "role": "Lowest-Latency-Slot-Finder",
        "best_eth_slot": best_eth,
        "best_sol_slot": best_sol,
        "reason": reason,
        "restricted_mode": restricted,
        "health_index": health_index,
        "trusted_validators_count": len(trusted_validators),
    }


def _a3_3b_builder_broker(slot_finder: dict) -> dict:
    """Stellt Verbindung zu MEV-Buildern nur zu optimalen Zeitpunkten her.

    Bei vertrauenswürdigem Validator: kein Builder nötig (private Tx reicht).
    Bei unbekanntem Validator: MEV-Builder für Schutz nutzen.
    """
    best_eth = slot_finder.get("best_eth_slot")
    reason = slot_finder.get("reason", "")

    use_builder = True
    if reason and "Vertrauenswürdiger" in reason:
        use_builder = False  # privater Tx-Pool reicht

    return {
        "status": "ok",
        "subagent": "A3-3b",
        "role": "Builder-Connection-Broker",
        "use_mev_builder": use_builder,
        "builder_needed": use_builder,
        "optimal_connection_window_s": 2.0 if best_eth else 0,
        "recommended_builders": (
            ["flashbots", "beaverbuild"] if use_builder
            else ["direct_node"]  # privater Tx-Pool
        ),
    }


def _a3_3c_tx_dispatch_optimizer(
    slot_finder: dict,
    builder_broker: dict,
) -> dict:
    """Gibt konkrete Sendeempfehlung aus.

    „Sende Uniswap-Swap-Tx in genau 6 Sekunden (Slot 18.456.789),
     damit Leader X sie priorisiert.“
    """
    best_eth = slot_finder.get("best_eth_slot") or {}
    best_sol = slot_finder.get("best_sol_slot") or {}
    use_builder = builder_broker.get("use_mev_builder", True)
    restricted = slot_finder.get("restricted_mode", False)

    eth_slot = best_eth.get("slot", "N/A")
    eth_offset_ms = best_eth.get("offset_ms", 0)
    sol_slot = best_sol.get("slot", "N/A")

    if restricted:
        instruction = (
            "HEALTH-KRITISCH: Nur vertrauenswürdige Validatoren nutzen. "
            "Keine Arbitrage ohne validierte Route."
        )
    elif use_builder:
        instruction = (
            f"Sende ETH-Tx in {eth_offset_ms}ms (Slot {eth_slot}) via Flashbots/Beaver. "
            f"Solana-Tx parallel in Slot {sol_slot} platzieren."
        )
    else:
        instruction = (
            f"Sende ETH-Tx direkt an vertrauenswürdigen Validator in {eth_offset_ms}ms "
            f"(Slot {eth_slot}). Kein MEV-Builder nötig — Sandwich-Risk minimal."
        )

    return {
        "status": "ok",
        "subagent": "A3-3c",
        "role": "Tx-Dispatch-Optimizer",
        "eth_target_slot": eth_slot,
        "sol_target_slot": sol_slot,
        "eth_offset_ms": eth_offset_ms,
        "dispatch_instruction": instruction,
        "urgent": eth_offset_ms < 4000,  # < 4s = sofort handeln
    }


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"

    if cmd == "a3_1":
        print(json.dumps(a3_1_proposer_forecaster(
            current_eth_slot=9_000_000,
            current_sol_slot=300_000_000,
        ), indent=2))
    elif cmd == "a3_2":
        print(json.dumps(a3_2_health_classifier(
            exit_queue_length=42,
            participation_rate=0.97,
            finality_status="on_time",
        ), indent=2))
    elif cmd == "a3_3":
        print(json.dumps(a3_3_order_routing_optimizer(
            eth_slots=[
                {"slot": 9_000_001, "proposer_index": "12345", "unix_timestamp": _now_unix() + 12, "offset_ms": 12000},
            ],
            trusted_validators=["12345"],
        ), indent=2))
    else:
        print(json.dumps({
            "a3_1": a3_1_proposer_forecaster(
                current_eth_slot=9_000_000,
                current_sol_slot=300_000_000,
            ),
            "a3_2": a3_2_health_classifier(),
            "a3_3": a3_3_order_routing_optimizer(),
        }, indent=2))
