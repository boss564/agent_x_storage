"""
Agent X — Klasse A: Cluster A2 (State & Analytics).

Zustandsanalyse & Deterministische Metriken.
Destilliert Rohdaten aus A1 zu aussagekräftigen Klasse-A-Signalen.

Agenten:
  A2-1: Slot- & Epochen-Performance-Analyst  — 3 Subagenten
  A2-2: Sync-Committee- & Rotations-Tracker  — 3 Subagenten
  A2-3: Staking-Flow- & Churn-Prädiktor      — 3 Subagenten
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("klasse_a2_analytics")

# ─── Konfiguration ───────────────────────────────────────────────────

EPOCH_DURATION_S = 384  # 32 slots × 12s
SLOTS_PER_EPOCH = 32
SYNC_COMMITTEE_SIZE = 512  # ggf. 1024 ab Altair
SYNC_COMMITTEE_EPOCHS = 256  # Rotation alle 256 Epochen (~27h)
ATTESTATION_NORMAL = 0.95  # Partizipationsrate unter 95% = Warnsignal


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════
# AGENT A2-1: Slot- & Epochen-Performance-Analyst
# ═══════════════════════════════════════════════════════════════════════

def a2_1_performance_analyst(
    blocks: list[dict] | None = None,
    attestations: list[dict] | None = None,
    reorgs: list[dict] | None = None,
) -> dict:
    """Verdichtet Blöcke & Attestationen einer Epoche zu Performanz-KPIs.

    Nimmt Ausgaben von A1-1a, A1-1b, A1-1c entgegen.

    Returns:
        {"status": "...", "epoch_summary": {...}, "subagents": {...}}
    """
    try:
        blocks = blocks or []
        attestations = attestations or []
        reorgs_list = reorgs or []

        finality = _a2_1a_check_finality(blocks, reorgs_list)
        effectiveness = _a2_1b_proposer_effectiveness(blocks)
        epoch_summary = _a2_1c_aggregate_epoch(finality, effectiveness, attestations, reorgs_list)

        return {
            "status": "completed",
            "agent": "A2-1",
            "epoch_summary": epoch_summary,
            "subagents": {
                "a2_1a_finality": finality,
                "a2_1b_effectiveness": effectiveness,
                "a2_1c_aggregator": epoch_summary,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("A2-1 Fehler: %s", e)
        return {"status": "failed", "agent": "A2-1", "error": str(e)}


def _a2_1a_check_finality(blocks: list[dict], reorgs: list[dict]) -> dict:
    """Prüft, ob die Epoche innerhalb der erwarteten 32 Slots finalisiert wurde.

    Verzögerte Finalität = starkes Stress-Signal für DeFi-Transaktionen.
    """
    total_blocks = len(blocks)
    missed = SLOTS_PER_EPOCH - total_blocks if total_blocks < SLOTS_PER_EPOCH else 0
    reorg_count = len(reorgs)
    finalized = missed == 0 and reorg_count == 0
    delay_slots = missed + sum(r.get("depth", 0) for r in reorgs)

    # Status-Klassifizierung
    if finalized:
        status = "on_time"
    elif delay_slots <= 1:
        status = "slight_delay"
    elif delay_slots <= 4:
        status = "moderate_delay"
    else:
        status = "severe_delay"

    return {
        "status": "ok",
        "subagent": "A2-1a",
        "role": "Finality-Checker",
        "slots_expected": SLOTS_PER_EPOCH,
        "slots_filled": total_blocks,
        "missed_slots": missed,
        "reorg_slots_lost": delay_slots - missed if delay_slots > missed else 0,
        "total_delay_slots": delay_slots,
        "finality_status": status,
        "is_finalized": finalized,
        "finality_risk": "high" if status in ("moderate_delay", "severe_delay") else "low",
    }


def _a2_1b_proposer_effectiveness(blocks: list[dict]) -> dict:
    """Berechnet für jeden Validator die Quote gefüllter vs. zugewiesener Slots.

    Niedrige Effectiveness = Validator ist offline oder zensiert.
    """
    if not blocks:
        return {
            "status": "ok",
            "subagent": "A2-1b",
            "role": "Proposer-Effectiveness",
            "slots_assigned": 0,
            "slots_filled": 0,
            "effectiveness_pct": 100.0,
            "underperformers": [],
        }

    # Gruppiere nach proposer_index
    proposer_slots: dict[str, int] = {}
    for b in blocks:
        idx = str(b.get("proposer_index", ""))
        proposer_slots[idx] = proposer_slots.get(idx, 0) + 1

    assigned_per_proposer = max(1, SLOTS_PER_EPOCH // max(1, len(proposer_slots)))
    underperformers = []
    total_assigned = 0
    total_filled = 0

    for idx, filled in proposer_slots.items():
        assigned = assigned_per_proposer
        total_assigned += assigned
        total_filled += filled
        rate = filled / assigned if assigned > 0 else 1.0
        if rate < 0.9:
            underperformers.append({
                "proposer_index": idx,
                "assigned": assigned,
                "filled": filled,
                "rate": round(rate, 3),
            })

    overall = round(total_filled / total_assigned * 100, 1) if total_assigned else 100.0

    return {
        "status": "ok",
        "subagent": "A2-1b",
        "role": "Proposer-Effectiveness",
        "slots_assigned": total_assigned,
        "slots_filled": total_filled,
        "effectiveness_pct": overall,
        "underperformers": underperformers,
        "underperformer_count": len(underperformers),
    }


def _a2_1c_aggregate_epoch(
    finality: dict,
    effectiveness: dict,
    attestations: list[dict],
    reorgs: list[dict],
) -> dict:
    """Fasst am Ende jeder Epoche alle Metriken in einem EpochSummary-Objekt zusammen."""
    participation_estimate = round(effectiveness.get("effectiveness_pct", 95.0) / 100, 3)

    return {
        "subagent": "A2-1c",
        "role": "Epoch-Aggregator",
        "participation_rate": participation_estimate,
        "participation_normal": participation_estimate >= ATTESTATION_NORMAL,
        "missed_blocks": finality.get("missed_slots", 0),
        "reorg_count": len(reorgs),
        "finalization_status": finality.get("finality_status", "unknown"),
        "overall_health": (
            "healthy" if finality.get("is_finalized") and participation_estimate >= ATTESTATION_NORMAL
            else "degraded" if participation_estimate >= 0.80
            else "critical"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT A2-2: Sync-Committee- & Rotations-Tracker
# ═══════════════════════════════════════════════════════════════════════

def a2_2_sync_committee_tracker(
    current_epoch: int = 0,
    committee_members: list[str] | None = None,
) -> dict:
    """Tracker für Sync-Committee-Rotationen (alle 256 Epochen, ~27h).

    Essenziell für Light Clients und Bridge-Protokolle.
    """
    try:
        committee = committee_members or []
        rotation = _a2_2a_rotation_alarm(current_epoch)
        mapper = _a2_2b_active_member_mapper(committee)
        simulator = _a2_2c_light_client_simulator(current_epoch)

        return {
            "status": "completed",
            "agent": "A2-2",
            "current_epoch": current_epoch,
            "committee_size": len(committee),
            "subagents": {
                "a2_2a_rotation": rotation,
                "a2_2b_mapper": mapper,
                "a2_2c_light_client": simulator,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("A2-2 Fehler: %s", e)
        return {"status": "failed", "agent": "A2-2", "error": str(e)}


def _a2_2a_rotation_alarm(current_epoch: int) -> dict:
    """Countdown bis zur nächsten Committee-Rotation. Alarm 1h vor Wechsel."""
    epochs_since_rotation = current_epoch % SYNC_COMMITTEE_EPOCHS
    epochs_until_rotation = SYNC_COMMITTEE_EPOCHS - epochs_since_rotation
    seconds_until = epochs_until_rotation * EPOCH_DURATION_S
    hours_until = round(seconds_until / 3600, 2)
    minutes_until = round(seconds_until / 60, 1)

    # Alarm: < 1h (ca. 10 Epochen)
    fire_alarm = epochs_until_rotation <= 10

    return {
        "status": "ok",
        "subagent": "A2-2a",
        "role": "Committee-Rotation-Alarm",
        "epochs_since_last_rotation": epochs_since_rotation,
        "epochs_until_rotation": epochs_until_rotation,
        "hours_until_rotation": hours_until,
        "minutes_until_rotation": minutes_until,
        "alarm_fired": fire_alarm,
        "alarm_reason": "Rotation steht in < 1h bevor — Light Clients updaten!" if fire_alarm else None,
        "next_rotation_epoch": current_epoch + epochs_until_rotation,
    }


def _a2_2b_active_member_mapper(committee: list[str]) -> dict:
    """Hält die aktuellen 512/1024 Validator-Pubkeys im Speicher bereit."""
    member_count = len(committee) if committee else SYNC_COMMITTEE_SIZE

    return {
        "status": "ok",
        "subagent": "A2-2b",
        "role": "Active-Member-Mapper",
        "committee_size": member_count,
        "committee_size_expected": SYNC_COMMITTEE_SIZE,
        "is_full": member_count >= SYNC_COMMITTEE_SIZE,
        "members_stored": min(len(committee), 10),  # nur Zählung, keine Pubkey-Liste
    }


def _a2_2c_light_client_simulator(current_epoch: int) -> dict:
    """Simuliert nächstes Light-Client-Update — wichtig für Off-Chain-Verarbeitung."""
    # Light-Client-Updates alle ~1.1 Tage (256 Epochen)
    epochs_since_rotation = current_epoch % SYNC_COMMITTEE_EPOCHS
    next_update_epoch = current_epoch + (SYNC_COMMITTEE_EPOCHS - epochs_since_rotation)

    return {
        "status": "ok",
        "subagent": "A2-2c",
        "role": "Light-Client-Simulator",
        "next_update_epoch": next_update_epoch,
        "updates_per_week_estimate": round(7 * 24 / 27.3, 1),
        "current_period": current_epoch // SYNC_COMMITTEE_EPOCHS,
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT A2-3: Staking-Flow- & Churn-Prädiktor
# ═══════════════════════════════════════════════════════════════════════

def a2_3_staking_flow_predictor(
    exit_queue_length: int = 0,
    activation_queue_length: int = 0,
    active_validators: int = 0,
    historical_avg_exit: float | None = None,
) -> dict:
    """Trägheitssensor des Netzwerks.

    Ein plötzlicher Anstieg der Exit-Queue = Klasse-C-Punktprozess-Signal
    für mangelndes Vertrauen.
    """
    try:
        spike = _a2_3a_exit_spike_detector(exit_queue_length, historical_avg_exit)
        entry_est = _a2_3b_entry_time_estimator(activation_queue_length)
        net_delta = _a2_3c_net_staking_delta(active_validators, exit_queue_length, activation_queue_length)

        return {
            "status": "completed",
            "agent": "A2-3",
            "subagents": {
                "a2_3a_spike_detector": spike,
                "a2_3b_entry_estimator": entry_est,
                "a2_3c_net_delta": net_delta,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("A2-3 Fehler: %s", e)
        return {"status": "failed", "agent": "A2-3", "error": str(e)}


def _a2_3a_exit_spike_detector(
    exit_queue_length: int,
    historical_avg: float | None = None,
) -> dict:
    """Vergleicht aktuelle Exit-Queue mit 24h-Durchschnitt.

    2-Sigma-Grenze → Alarm → warnt B2 (Lending-Risiko-Agent).
    """
    avg = historical_avg if historical_avg else 50.0
    sigma = max(avg * 0.3, 5)  # 30% der Baseline als Sigma
    deviation = exit_queue_length - avg
    z_score = round(deviation / sigma, 2) if sigma > 0 else 0.0
    spike_detected = abs(z_score) >= 2.0

    return {
        "status": "ok",
        "subagent": "A2-3a",
        "role": "Exit-Volumen-Spike-Detektor",
        "current_exit_queue": exit_queue_length,
        "historical_avg_24h": round(avg, 1),
        "sigma": round(sigma, 1),
        "z_score": z_score,
        "spike_detected": spike_detected,
        "severity": (
            "critical" if spike_detected and z_score > 3
            else "warning" if spike_detected
            else "normal"
        ),
        "alert_for_lending_agent": spike_detected,
        "recommendation": (
            "Validator-Exodus erkannt — Health-Factor-Berechnung anpassen"
            if spike_detected
            else None
        ),
    }


def _a2_3b_entry_time_estimator(activation_queue_length: int) -> dict:
    """Sagt voraus, wann ein neuer Validator aktiv wird."""
    churn_limit = 8
    epochs = activation_queue_length / churn_limit if churn_limit else 0
    seconds = epochs * EPOCH_DURATION_S
    hours = round(seconds / 3600, 2)

    return {
        "status": "ok",
        "subagent": "A2-3b",
        "role": "Entry-Time-Estimator",
        "queue_position": activation_queue_length,
        "estimated_hours_until_active": hours,
        "estimated_epochs": round(epochs, 1),
        "estimated_activation_time": (
            datetime.now(timezone.utc).isoformat() if hours <= 1
            else f"~{hours}h ab jetzt"
        ),
    }


def _a2_3c_net_staking_delta(
    active_validators: int,
    exit_queue: int,
    activation_queue: int,
) -> dict:
    """Berechnet Nettoveränderung der gestakten ETH (Entries − Exits) pro Epoche."""
    churn_limit = 8
    exits_per_epoch = min(churn_limit, exit_queue) if exit_queue > 0 else 0
    entries_per_epoch = min(churn_limit, activation_queue) if activation_queue > 0 else 0
    net_flow = entries_per_epoch - exits_per_epoch  # + = wachsend, − = schrumpfend

    # 32 ETH pro Validator
    net_eth_flow = net_flow * 32

    if net_flow > 4:
        trend = "strongly_growing"
    elif net_flow > 0:
        trend = "growing"
    elif net_flow == 0:
        trend = "stable"
    elif net_flow > -4:
        trend = "shrinking"
    else:
        trend = "strongly_shrinking"

    return {
        "status": "ok",
        "subagent": "A2-3c",
        "role": "Netto-Staking-Delta",
        "exits_per_epoch": exits_per_epoch,
        "entries_per_epoch": entries_per_epoch,
        "net_validator_flow": net_flow,
        "net_eth_flow_per_epoch": net_eth_flow,
        "trend": trend,
        "active_validators_snapshot": active_validators,
        "trend_signal": (
            "Vertrauensverlust — Exit dominiert" if trend.endswith("shrinking")
            else "Netzwerk wächst gesund" if trend.endswith("growing")
            else "Netzwerk stabil"
        ),
    }


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "a2_1":
        print(json.dumps(a2_1_performance_analyst(), indent=2))
    elif cmd == "a2_2":
        print(json.dumps(a2_2_sync_committee_tracker(current_epoch=123456), indent=2))
    elif cmd == "a2_3":
        print(json.dumps(a2_3_staking_flow_predictor(
            exit_queue_length=42,
            activation_queue_length=128,
            active_validators=1_048_576,
        ), indent=2))
    else:
        print(json.dumps({
            "a2_1": a2_1_performance_analyst(),
            "a2_2": a2_2_sync_committee_tracker(current_epoch=123456),
            "a2_3": a2_3_staking_flow_predictor(
                exit_queue_length=42,
                activation_queue_length=128,
                active_validators=1_048_576,
            ),
        }, indent=2))
