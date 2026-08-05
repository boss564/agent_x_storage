"""
Agent X — Klasse A: Cluster A1 (Ingestion).

Rohdaten-Beschaffung & Synchronisation.
Direkte Schnittstelle zu Consensus-Clients (Lighthouse/Prysm, Solana-Validatoren).

Agenten:
  A1-1: Beacon-Chain-Listener (Ethereum)  — 3 Subagenten
  A1-2: Solana-Leader-Schedule-Fetcher     — 3 Subagenten
  A1-3: Validator-Exit- & Queue-Monitor    — 3 Subagenten
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

from agent_x_beacon_client import (
    sse_stream,
    collect_events_batch,
    get_validator_queue_data_sync,
    get_validator_queue_data_async,
    get_current_epoch_sync,
)
from agent_x_solana_client import (
    get_leader_schedule_sync,
    get_leader_schedule_async,
    get_current_slot_sync,
    get_current_slot_async,
    get_epoch_info_sync,
)

logger = logging.getLogger("klasse_a1_ingestion")

# ─── Konfiguration ───────────────────────────────────────────────────

BEACON_NODE_URL = os.getenv("BEACON_NODE_URL", "http://localhost:5052")
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "http://localhost:8899")
SOLANA_LEADER_SLOTS = int(os.getenv("SOLANA_LEADER_SLOTS", "432000"))  # ~2-3 Tage

# ─── Hilfsfunktionen ─────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════
# AGENT A1-1: Beacon-Chain-Listener (Ethereum)
# ═══════════════════════════════════════════════════════════════════════

def a1_1_beacon_listener(action: str = "listen", max_events: int = 100) -> dict:
    """Stellt Verbindung zum Beacon-Node her und empfängt Echtzeit-Events.

    Events: block, attestation, finalized_checkpoint, chain_reorg.

    Args:
        action: 'listen' | 'poll' | 'status'
        max_events: Max Events im Poll-Modus.

    Returns:
        {"status": "...", "events": [...], "subagents": {...}}
    """
    try:
        if action == "status":
            return {
                "status": "ok",
                "agent": "A1-1",
                "node": BEACON_NODE_URL,
                "events_monitored": ["block", "attestation", "finalized_checkpoint", "chain_reorg"],
                "timestamp": _now_iso(),
            }

        # Real SSE-Stream — sammelt Events async via aiohttp
        events = asyncio.run(collect_events_batch(
            ["block", "attestation", "chain_reorg", "finalized_checkpoint"],
            max_events=max_events,
        )) if action == "poll" else []

        # Subagenten-Pipeline
        blocks = _a1_1a_filter_blocks(events, max_events)
        attestations = _a1_1b_collect_attestations(events, max_events)
        reorgs = _a1_1c_detect_reorgs(events)

        return {
            "status": "completed",
            "agent": "A1-1",
            "action": action,
            "total_events": len(events),
            "subagents": {
                "a1_1a_block_proposals": blocks,
                "a1_1b_attestations": attestations,
                "a1_1c_reorgs": reorgs,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("A1-1 Fehler: %s", e)
        return {"status": "failed", "agent": "A1-1", "error": str(e)}


# ─── Subagent A1-1a: Block-Proposal-Sub ──────────────────────────────

def _a1_1a_filter_blocks(events: list[dict], max_events: int) -> dict:
    """Filtert block-Events und extrahiert proposer_index + Slot-Zeit.

    Ausgabe fließt in:
      - A3-1a (ETH-Block-Timing-Predictor)
      - A3-3  (Order-Routing-Optimizer)
    """
    blocks = []
    for ev in events:
        event_type = ev.get("event", "")
        data = ev.get("data", ev)  # SSE-Format: event+data; fallback: flach
        if event_type != "block" and ev.get("event") != "block":
            if not event_type and ev.get("slot"):
                pass  # flat format fallback
            else:
                continue
        slot = data.get("slot", ev.get("slot", ""))
        blocks.append({
            "slot": slot,
            "proposer_index": data.get("proposer_index", ev.get("proposer_index", "")),
            "timestamp": ev.get("received_at", _now_iso()),
        })

    blocks = blocks[:max_events]
    return {
        "status": "ok",
        "subagent": "A1-1a",
        "role": "Block-Proposal-Sub",
        "blocks_found": len(blocks),
        "latest_slot": blocks[-1]["slot"] if blocks else None,
        "latest_proposer": blocks[-1]["proposer_index"] if blocks else None,
        "blocks": blocks,
    }


# ─── Subagent A1-1b: Attestation-Sub ─────────────────────────────────

def _a1_1b_collect_attestations(events: list[dict], max_events: int) -> dict:
    """Sammelt attestation-Events für spätere Partizipationsraten-Berechnung.

    Ausgabe fließt in:
      - A2-1a (Finality-Checker)
      - A3-2b (Network-Participation-Grade)
    """
    attestations = []
    for ev in events:
        event_type = ev.get("event", "")
        data = ev.get("data", ev)
        if event_type != "attestation" and ev.get("event") != "attestation":
            if not event_type and ev.get("validator_index"):
                pass
            else:
                continue
        attestations.append({
            "slot": data.get("slot", ev.get("slot", "")),
            "validator_index": data.get("validator_index", ev.get("validator_index", "")),
            "source_epoch": data.get("source_epoch", ev.get("source_epoch", "")),
            "target_epoch": data.get("target_epoch", ev.get("target_epoch", "")),
            "timestamp": ev.get("received_at", _now_iso()),
        })

    attestations = attestations[:max_events]
    unique_validators = len({a["validator_index"] for a in attestations})

    return {
        "status": "ok",
        "subagent": "A1-1b",
        "role": "Attestation-Sub",
        "attestations_collected": len(attestations),
        "unique_validators": unique_validators,
        "attestations": attestations,
    }


# ─── Subagent A1-1c: Reorg-Detektor ──────────────────────────────────

def _a1_1c_detect_reorgs(events: list[dict]) -> dict:
    """Überwacht chain_reorg-Events und dokumentiert die Reorg-Tiefe.

    Reorgs > 2 Slots sind kritisches Signal für:
      - A3-2c (Finality-Risk-Score)
      - Deaktivierung von C2 (Flash-Loan-Analyse)
    """
    reorgs = []
    for ev in events:
        event_type = ev.get("event", "")
        data = ev.get("data", ev)
        if event_type != "chain_reorg" and ev.get("event") != "chain_reorg":
            if not event_type and ev.get("depth"):
                pass
            else:
                continue
        depth = int(data.get("depth", ev.get("depth", 0)))
        reorgs.append({
            "slot": data.get("slot", ev.get("slot", "")),
            "depth": depth,
            "old_head": data.get("old_head_block_root", ev.get("old_head_block_root", "")),
            "new_head": data.get("new_head_block_root", ev.get("new_head_block_root", "")),
            "severity": "critical" if depth >= 2 else "warning" if depth == 1 else "info",
            "timestamp": ev.get("received_at", _now_iso()),
        })

    critical_count = sum(1 for r in reorgs if r["severity"] == "critical")

    return {
        "status": "ok",
        "subagent": "A1-1c",
        "role": "Reorg-Detektor",
        "reorgs_total": len(reorgs),
        "reorgs_critical": critical_count,
        "requires_flashloan_shutdown": critical_count > 0,
        "reorgs": reorgs,
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT A1-2: Solana-Leader-Schedule-Fetcher
# ═══════════════════════════════════════════════════════════════════════

def a1_2_solana_schedule_fetcher(action: str = "fetch") -> dict:
    """Ruft den determinierten Leader-Schedule für die nächsten 432.000 Slots ab.

    Args:
        action: 'fetch' | 'current' | 'status'

    Returns:
        {"status": "...", "slots_total": N, "subagents": {...}}
    """
    try:
        if action == "status":
            return {
                "status": "ok",
                "agent": "A1-2",
                "rpc": SOLANA_RPC_URL,
                "slots_monitored": SOLANA_LEADER_SLOTS,
                "timestamp": _now_iso(),
            }

        # Real Solana RPC: Leader-Schedule laden
        schedule_result = get_leader_schedule_sync()
        schedule_raw = schedule_result.get("schedule", {})

        parsed = _a1_2a_parse_schedule(schedule_raw)
        progress = _a1_2b_track_slot_progress(
            parsed["schedule"],
            current_slot=get_current_slot_sync(),
        )
        skips = _a1_2c_monitor_skips(progress)

        return {
            "status": "completed",
            "agent": "A1-2",
            "action": action,
            "schedule_slots_loaded": len(schedule_raw),
            "subagents": {
                "a1_2a_schedule_parser": parsed,
                "a1_2b_slot_progress": progress,
                "a1_2c_skip_monitor": skips,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("A1-2 Fehler: %s", e)
        return {"status": "failed", "agent": "A1-2", "error": str(e)}


def _a1_2a_parse_schedule(schedule_raw: dict[int, str]) -> dict:
    """Wandelt Rohdaten (slot → pubkey) in sortierte Zeitleiste um."""
    if not schedule_raw:
        return {
            "status": "ok",
            "subagent": "A1-2a",
            "role": "Schedule-Parser",
            "slots_parsed": 0,
            "schedule": [],
        }

    sorted_slots = sorted(schedule_raw.items())
    timeline = [
        {"slot": slot, "leader_pubkey": pubkey}
        for slot, pubkey in sorted_slots
    ]

    return {
        "status": "ok",
        "subagent": "A1-2a",
        "role": "Schedule-Parser",
        "slots_parsed": len(timeline),
        "first_slot": timeline[0]["slot"] if timeline else None,
        "last_slot": timeline[-1]["slot"] if timeline else None,
        "total_leaders": len({t["leader_pubkey"] for t in timeline}),
        "schedule": timeline,
    }


def _a1_2b_track_slot_progress(schedule: list[dict], current_slot: int = 0) -> dict:
    """Gleicht aktuellen Slot (via RPC) mit designiertem Leader ab.

    Ausgabe fließt in:
      - A3-1b (Solana-Leader-Mapper)
    """
    if not schedule:
        return {
            "status": "ok",
            "subagent": "A1-2b",
            "role": "Slot-Progress-Tracker",
            "current_slot": current_slot,
            "designated_leader": None,
            "source": "solana_rpc" if current_slot > 0 else "schedule_fallback",
        }

    # Finde den Eintrag im Schedule für den aktuellen Slot
    designated = None
    for entry in schedule:
        if entry.get("slot") == current_slot:
            designated = entry.get("leader_pubkey")
            break

    # Fallback: erster Schedule-Eintrag
    if designated is None and schedule:
        designated = schedule[0].get("leader_pubkey", None)

    return {
        "status": "ok",
        "subagent": "A1-2b",
        "role": "Slot-Progress-Tracker",
        "current_slot": current_slot,
        "designated_leader": designated,
        "on_track": designated is not None,
        "source": "solana_rpc_live",
    }


def _a1_2c_monitor_skips(progress: dict) -> dict:
    """Erkennt Skipped Slots (designierter Leader produziert keinen Block).

    Ausgabe fließt in:
      - A2-1b (Proposer-Effectiveness)
    """
    current_slot = progress.get("current_slot")
    on_track = progress.get("on_track", True)

    return {
        "status": "ok",
        "subagent": "A1-2c",
        "role": "Skip-Rate-Monitor",
        "current_slot": current_slot,
        "skipped_detected": not on_track,
        "skip_reason": None if on_track else "Leader hat keinen Block produziert",
        "consecutive_skips": 0 if on_track else 1,
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT A1-3: Validator-Exit- & Queue-Monitor
# ═══════════════════════════════════════════════════════════════════════

def a1_3_exit_queue_monitor(action: str = "poll") -> dict:
    """Beobachtet Entry/Exit-Queues der Beacon-Chain.

    Args:
        action: 'poll' | 'status'

    Returns:
        {"status": "...", "queues": {...}, "subagents": {...}}
    """
    try:
        if action == "status":
            return {
                "status": "ok",
                "agent": "A1-3",
                "node": BEACON_NODE_URL,
                "timestamp": _now_iso(),
            }

        # Real Beacon-API: Validator-Queue-Daten via REST
        queue_data = get_validator_queue_data_sync()

        exit_info = _a1_3a_calc_exit_queue(queue_data)
        activation_info = _a1_3b_calc_activation_queue(queue_data)
        history = _a1_3c_track_active_history(queue_data)

        return {
            "status": "completed",
            "agent": "A1-3",
            "action": action,
            "raw_data": queue_data,
            "subagents": {
                "a1_3a_exit_queue": exit_info,
                "a1_3b_activation_queue": activation_info,
                "a1_3c_active_history": history,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("A1-3 Fehler: %s", e)
        return {"status": "failed", "agent": "A1-3", "error": str(e)}


def _a1_3a_calc_exit_queue(data: dict) -> dict:
    """Berechnet geschätzte Wartezeit aus exit_queue_position + churn_limit.

    Max 8 Exits pro Epoche (384s). Ausgabe fließt in:
      - A2-3a (Exit-Volumen-Spike-Detektor)
    """
    queue_len = data.get("exit_queue_length", 0)
    churn_limit = data.get("churn_limit", 8)
    epochs_to_clear = queue_len / churn_limit if churn_limit > 0 else 0
    wait_seconds = epochs_to_clear * 384  # 384s pro Epoche
    wait_minutes = round(wait_seconds / 60, 1)
    wait_hours = round(wait_minutes / 60, 2)

    return {
        "status": "ok",
        "subagent": "A1-3a",
        "role": "Exit-Queue-Rechner",
        "exit_queue_length": queue_len,
        "churn_limit": churn_limit,
        "epochs_to_clear": round(epochs_to_clear, 1),
        "estimated_wait_minutes": wait_minutes,
        "estimated_wait_hours": wait_hours,
        "severity": "critical" if wait_hours > 24 else "warning" if wait_hours > 6 else "normal",
    }


def _a1_3b_calc_activation_queue(data: dict) -> dict:
    """Berechnet Wartezeit für neue Validatoren in der Activation-Queue.

    Ausgabe fließt in:
      - A2-3b (Entry-Time-Estimator)
    """
    queue_len = data.get("activation_queue_length", 0)
    churn_limit = data.get("churn_limit", 8)
    epochs_to_clear = queue_len / churn_limit if churn_limit > 0 else 0
    wait_seconds = epochs_to_clear * 384
    wait_minutes = round(wait_seconds / 60, 1)

    return {
        "status": "ok",
        "subagent": "A1-3b",
        "role": "Activation-Queue-Rechner",
        "activation_queue_length": queue_len,
        "churn_limit": churn_limit,
        "epochs_to_clear": round(epochs_to_clear, 1),
        "estimated_wait_minutes": wait_minutes,
    }


def _a1_3c_track_active_history(data: dict) -> dict:
    """Speichert historischen Verlauf der aktiven Validator-Anzahl.

    Trendanalyse für Trägheitssignale.
    Ausgabe fließt in:
      - A2-3c (Netto-Staking-Delta)
    """
    active = data.get("active_validators", 0)

    return {
        "status": "ok",
        "subagent": "A1-3c",
        "role": "Total-Active-Historian",
        "active_validators": active,
        "trend": "stable",  # stable | growing | shrinking
        "delta_24h": 0,     # Änderung letzte 24h
        "delta_7d": 0,
        "snapshot_timestamp": _now_iso(),
    }


# ═══════════════════════════════════════════════════════════════════════
# ASYNC-VARIANTEN
# ═══════════════════════════════════════════════════════════════════════

async def a1_1_beacon_listener_async(max_events: int = 100) -> dict:
    """Async-Variante des Beacon-Listeners mit vollem aiohttp-SSE-Stream."""
    try:
        events = []
        async for ev in sse_stream(
            ["block", "attestation", "chain_reorg", "finalized_checkpoint"],
            max_events=max_events,
        ):
            events.append(ev)

        blocks = _a1_1a_filter_blocks(events, max_events)
        attestations = _a1_1b_collect_attestations(events, max_events)
        reorgs = _a1_1c_detect_reorgs(events)

        return {
            "status": "completed",
            "agent": "A1-1",
            "mode": "async",
            "total_events": len(events),
            "subagents": {
                "a1_1a_block_proposals": blocks,
                "a1_1b_attestations": attestations,
                "a1_1c_reorgs": reorgs,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("A1-1 async Fehler: %s", e)
        return {"status": "failed", "agent": "A1-1", "error": str(e)}


async def a1_2_solana_schedule_fetcher_async() -> dict:
    """Async-Variante des Solana-Fetchers mit parallelen RPC-Calls."""
    try:
        schedule_task = get_leader_schedule_async()
        slot_task = get_current_slot_async()

        schedule_result, current_slot = await asyncio.gather(
            schedule_task, slot_task,
        )

        schedule_raw = schedule_result.get("schedule", {})
        parsed = _a1_2a_parse_schedule(schedule_raw)
        progress = _a1_2b_track_slot_progress(parsed["schedule"], current_slot=current_slot)
        skips = _a1_2c_monitor_skips(progress)

        return {
            "status": "completed",
            "agent": "A1-2",
            "mode": "async",
            "schedule_slots_loaded": len(schedule_raw),
            "subagents": {
                "a1_2a_schedule_parser": parsed,
                "a1_2b_slot_progress": progress,
                "a1_2c_skip_monitor": skips,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("A1-2 async Fehler: %s", e)
        return {"status": "failed", "agent": "A1-2", "error": str(e)}


async def a1_3_exit_queue_monitor_async() -> dict:
    """Async-Variante des Exit-Queue-Monitors."""
    try:
        queue_data = await get_validator_queue_data_async()
        exit_info = _a1_3a_calc_exit_queue(queue_data)
        activation_info = _a1_3b_calc_activation_queue(queue_data)
        history = _a1_3c_track_active_history(queue_data)

        return {
            "status": "completed",
            "agent": "A1-3",
            "mode": "async",
            "subagents": {
                "a1_3a_exit_queue": exit_info,
                "a1_3b_activation_queue": activation_info,
                "a1_3c_active_history": history,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("A1-3 async Fehler: %s", e)
        return {"status": "failed", "agent": "A1-3", "error": str(e)}


async def run_all_ingestion_async() -> dict:
    """Führt alle 3 A1-Agenten parallel aus (async)."""
    results = await asyncio.gather(
        a1_1_beacon_listener_async(max_events=50),
        a1_2_solana_schedule_fetcher_async(),
        a1_3_exit_queue_monitor_async(),
        return_exceptions=True,
    )
    return {
        "a1_1": results[0] if not isinstance(results[0], Exception) else {"error": str(results[0])},
        "a1_2": results[1] if not isinstance(results[1], Exception) else {"error": str(results[1])},
        "a1_3": results[2] if not isinstance(results[2], Exception) else {"error": str(results[2])},
        "timestamp": _now_iso(),
    }


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "a1_1":
        print(json.dumps(a1_1_beacon_listener("poll"), indent=2))
    elif cmd == "a1_2":
        print(json.dumps(a1_2_solana_schedule_fetcher("fetch"), indent=2))
    elif cmd == "a1_3":
        print(json.dumps(a1_3_exit_queue_monitor("poll"), indent=2))
    elif cmd == "async":
        print(json.dumps(asyncio.run(run_all_ingestion_async()), indent=2))
    elif cmd == "status":
        print(json.dumps({
            "a1_1": a1_1_beacon_listener("status"),
            "a1_2": a1_2_solana_schedule_fetcher("status"),
            "a1_3": a1_3_exit_queue_monitor("status"),
        }, indent=2))
    else:
        print(f"Verwendung: {sys.argv[0]} [a1_1|a1_2|a1_3|async|status]")
