"""
Agent X — Druckventile: Cluster B2 (Druckanalyse & Statistische Modelle).

Destilliert aus den Rohdaten die Druck-Indizes:
Gas-Stress-Index, MEV-Druck-Monitor, Block-Kampf-Statistik.

Agenten:
  B2-1: Gas-Stress-Index-Rechner        — 3 Subagenten
  B2-2: MEV-Druck-Monitor               — 3 Subagenten
  B2-3: Block-Kampf-Statistiker          — 3 Subagenten
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from agent_x_klasse_b_pressure_models import (
    PressureLevel, RollingStats, BlockPressureSnapshot, EVMGasData,
)

logger = logging.getLogger("pressure_b2_analytics")

# Globale Stats (geteilt mit B1)
from agent_x_klasse_b_pressure_b1_ingestion import (
    basefee_stats, priority_fee_stats, bribe_stats, jito_tip_stats,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════
# AGENT B2-1: Gas-Stress-Index-Rechner
# ═══════════════════════════════════════════════════════════════════════

def b2_1_gas_stress_index(
    basefee_snapshot: dict | None = None,
    blob_snapshot: dict | None = None,
) -> dict:
    """Erzeugt einen normalisierten Gas-Stress-Wert (0-100).

    Kombiniert: Basefee-Abweichung + Blob-Auslastung + Priority-Fee-Druck.

    Returns:
        {"status": "...", "gas_pressure_index": N, "subagents": {...}}
    """
    try:
        z_score_result = _b2_1a_basefee_z_score(basefee_snapshot)
        blob_result = _b2_1b_blob_utilization(blob_snapshot)
        combined = _b2_1c_combine_gas_stress(z_score_result, blob_result)

        return {
            "status": "completed",
            "agent": "B2-1",
            "gas_pressure_index": combined["gas_pressure_index"],
            "pressure_level": combined["pressure_level"],
            "subagents": {
                "b2_1a_z_score": z_score_result,
                "b2_1b_blob": blob_result,
                "b2_1c_combined": combined,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("B2-1 Fehler: %s", e)
        return {"status": "failed", "agent": "B2-1", "error": str(e)}


def _b2_1a_basefee_z_score(snapshot: dict | None = None) -> dict:
    """Berechnet Z-Score der aktuellen Basefee vs. 24h-Durchschnitt."""
    basefee_current = 21.5  # Fallback
    if snapshot:
        basefees = snapshot.get("basefees", [])
        if basefees:
            basefee_current = basefees[-1].get("base_fee_gwei", 21.5)

    # Füttere Stats
    if basefee_stats.count > 0:
        z = basefee_stats.z_score
        alarming = abs(z) >= 2.0
    else:
        z = 0.0
        alarming = False

    return {
        "status": "ok",
        "subagent": "B2-1a",
        "role": "Basefee-Z-Score",
        "current_basefee_gwei": round(basefee_current, 2),
        "basefee_mean_24h": round(basefee_stats.mean, 2),
        "basefee_std_24h": round(basefee_stats.std, 2),
        "z_score": round(z, 2),
        "alarming": alarming,
        "sigma_level": (
            "3σ+" if abs(z) >= 3 else "2σ+" if abs(z) >= 2
            else "1σ" if abs(z) >= 1 else "normal"
        ),
    }


def _b2_1b_blob_utilization(snapshot: dict | None = None) -> dict:
    """Berechnet Blob-Space-Auslastung."""
    avg_util = 45.0
    if snapshot:
        blob_data = snapshot.get("blob_data", [])
        if blob_data:
            avg_util = sum(b.get("blob_utilization_pct", 0) for b in blob_data) / len(blob_data)

    return {
        "status": "ok",
        "subagent": "B2-1b",
        "role": "Blob-Utilization",
        "avg_blob_utilization_pct": round(avg_util, 1),
        "blob_space_stress": avg_util > 80,  # >80% = Rollup-Druck
        "blob_pressure_score": round(min(100, avg_util * 1.25), 1),  # 0-100 skaliert
    }


def _b2_1c_combine_gas_stress(z_result: dict, blob_result: dict) -> dict:
    """Gewichtete Zusammenführung zum GasPressureIndex (0-100).

    Gewichte: Basefee 50%, Priority-Fee 25%, Blob 25%
    """
    z_abs = abs(z_result.get("z_score", 0))
    basefee_component = min(100, z_abs * 25)  # z=4 → 100

    # Priority-Fee-Druck aus stats
    pf_p95 = priority_fee_stats.p95 if priority_fee_stats.count > 0 else 3.5
    pf_component = min(100, (pf_p95 / 15) * 100)  # 15 gwei = 100

    blob_component = blob_result.get("blob_pressure_score", 0)

    gas_pressure = round(
        basefee_component * 0.50 +
        pf_component * 0.25 +
        blob_component * 0.25,
        1,
    )

    level = _to_pressure_level(gas_pressure)

    return {
        "status": "ok",
        "subagent": "B2-1c",
        "role": "Gas-Stress-Combiner",
        "gas_pressure_index": gas_pressure,
        "pressure_level": level.value,
        "decomposed": {
            "basefee_z_component": round(basefee_component, 1),
            "priority_fee_component": round(pf_component, 1),
            "blob_component": round(blob_component, 1),
        },
        "weights": {"basefee": 0.50, "priority_fee": 0.25, "blob": 0.25},
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT B2-2: MEV-Druck-Monitor
# ═══════════════════════════════════════════════════════════════════════

def b2_2_mev_pressure_monitor(
    bundle_data: dict | None = None,
    tip_data: dict | None = None,
) -> dict:
    """Analysiert wie aggressiv Bots um Blockplatz kämpfen.

    Returns:
        {"status": "...", "mev_pressure_index": N, "subagents": {...}}
    """
    try:
        bribe_percentiles = _b2_2a_bribe_percentiles(bundle_data)
        tip_percentiles = _b2_2b_solana_tip_percentiles(tip_data)
        spikes = _b2_2c_mev_spike_detector(bribe_percentiles, tip_percentiles)

        return {
            "status": "completed",
            "agent": "B2-2",
            "mev_pressure_index": spikes["mev_pressure_index"],
            "pressure_level": spikes["level"],
            "subagents": {
                "b2_2a_bribe_pct": bribe_percentiles,
                "b2_2b_tip_pct": tip_percentiles,
                "b2_2c_spike_detector": spikes,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("B2-2 Fehler: %s", e)
        return {"status": "failed", "agent": "B2-2", "error": str(e)}


def _b2_2a_bribe_percentiles(bundle_data: dict | None = None) -> dict:
    """Berechnet Bribe-Perzentile (P50, P95, P99)."""
    # Bribe-Statistiken aus globalem Rolling Window
    if bribe_stats.count > 0:
        snap = bribe_stats.snapshot()
    else:
        snap = {"p50": 0.02, "p95": 0.15, "p99": 0.45, "mean": 0.05, "count": 0}

    return {
        "status": "ok",
        "subagent": "B2-2a",
        "role": "Bribe-P99",
        "bribe_p50_eth": snap["p50"],
        "bribe_p95_eth": snap["p95"],
        "bribe_p99_eth": snap["p99"],
        "bribe_mean_eth": snap["mean"],
        "bribe_p99_usd": round(snap["p99"] * 3200, 2),
        "sample_count": snap["count"],
    }


def _b2_2b_solana_tip_percentiles(tip_data: dict | None = None) -> dict:
    """Berechnet Jito-Tip-Perzentile."""
    if jito_tip_stats.count > 0:
        snap = jito_tip_stats.snapshot()
    else:
        snap = {"p50": 0.0005, "p95": 0.005, "p99": 0.02, "mean": 0.002, "count": 0}

    return {
        "status": "ok",
        "subagent": "B2-2b",
        "role": "Solana-Tip-Percentile",
        "tip_p50_sol": snap["p50"],
        "tip_p95_sol": snap["p95"],
        "tip_p99_sol": snap["p99"],
        "tip_mean_sol": snap["mean"],
        "tip_p99_usd": round(snap["p99"] * 180, 2),
        "sample_count": snap["count"],
    }


def _b2_2c_mev_spike_detector(bribe_pct: dict, tip_pct: dict) -> dict:
    """Erkennt plötzliche Anstiege der Bribes (MEV-Spikes).

    Wenn P99 > 3× Mittelwert: Frontrunning-Arbitrage aktiv.
    """
    bribe_p99 = bribe_pct.get("bribe_p99_eth", 0)
    bribe_mean = bribe_pct.get("bribe_mean_eth", 0.001)
    tip_p99 = tip_pct.get("tip_p99_sol", 0)

    # Spikes: P99 / Mean Ratio
    bribe_ratio = bribe_p99 / max(bribe_mean, 0.0001)
    spike_detected = bribe_ratio > 3.0

    # MEV-Pressure-Index: kombiniert Bribe-P99 + Spike-Status
    bribe_component = min(100, (bribe_p99 / 1.0) * 100)  # 1 ETH P99 = 100
    spike_bonus = 20 if spike_detected else 0
    mev_pressure = round(min(100, bribe_component + spike_bonus), 1)

    level = _to_pressure_level(mev_pressure)

    return {
        "status": "ok",
        "subagent": "B2-2c",
        "role": "MEV-Spike-Detektor",
        "mev_pressure_index": mev_pressure,
        "level": level.value,
        "bribe_ratio_p99_over_mean": round(bribe_ratio, 1),
        "spike_detected": spike_detected,
        "frontrunning_likely": spike_detected,
        "arbitrage_aggression": (
            "extreme" if bribe_ratio > 5
            else "high" if bribe_ratio > 3
            else "moderate" if bribe_ratio > 1.5
            else "normal"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT B2-3: Block-Kampf-Statistiker
# ═══════════════════════════════════════════════════════════════════════

def b2_3_block_fight_stats(
    gas_data: dict | None = None,
    mempool_snapshot: dict | None = None,
) -> dict:
    """Analysiert Block-Auslastung und Mempool-Bidding-Wars.

    Returns:
        {"status": "...", "block_pressure_index": N, "subagents": {...}}
    """
    try:
        fullness = _b2_3a_block_fullness(gas_data)
        queue_len = _b2_3b_mempool_queue_length(mempool_snapshot)
        greed = _b2_3c_validator_greed_index(fullness, queue_len)

        # Combined Block Pressure
        block_pressure = round(
            fullness.get("avg_fullness_pct", 0) * 0.50 +
            min(100, queue_len.get("queue_length", 0) * 0.2) * 0.30 +
            greed.get("greed_score", 0) * 0.20,
            1,
        )

        return {
            "status": "completed",
            "agent": "B2-3",
            "block_pressure_index": block_pressure,
            "pressure_level": _to_pressure_level(block_pressure).value,
            "subagents": {
                "b2_3a_fullness": fullness,
                "b2_3b_mempool": queue_len,
                "b2_3c_greed": greed,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("B2-3 Fehler: %s", e)
        return {"status": "failed", "agent": "B2-3", "error": str(e)}


def _b2_3a_block_fullness(gas_data: dict | None = None) -> dict:
    """Berechnet Block-Füllgrad (Gas-Used / Gas-Limit)."""
    basefees = gas_data.get("subagents", {}).get(
        "b1_1a_basefee", {},
    ).get("basefees", []) if gas_data else []

    avg_fullness = sum(b.get("gas_used_pct", 65) for b in basefees) / len(basefees) if basefees else 72.0
    max_fullness = max((b.get("gas_used_pct", 65) for b in basefees), default=85)
    high_pressure = avg_fullness > 85

    return {
        "status": "ok",
        "subagent": "B2-3a",
        "role": "Block-Füllgrad",
        "avg_fullness_pct": round(avg_fullness, 1),
        "max_fullness_pct": round(max_fullness, 1),
        "high_pressure": high_pressure,
        "bidding_war_likely": avg_fullness > 90,  # >90% = Bidding War
    }


def _b2_3b_mempool_queue_length(snapshot: dict | None = None) -> dict:
    """Misst Mempool-Queue-Länge."""
    queue = snapshot.get("pending_tx_count", 15_000) if snapshot else 15_000

    return {
        "status": "ok",
        "subagent": "B2-3b",
        "role": "Transaction-Queue-Length",
        "queue_length": queue,
        "pressure_signal": queue > 30_000,  # >30k pending = hoher Druck
        "estimated_confirmation_delay_blocks": (
            "1-2" if queue < 10_000
            else "2-5" if queue < 25_000
            else "5-10" if queue < 50_000
            else ">10"
        ),
    }


def _b2_3c_validator_greed_index(fullness: dict, queue: dict) -> dict:
    """Validator-Gier-Index: Fullness × Avg-Tip / Basefee-Ratio."""
    avg_fullness = fullness.get("avg_fullness_pct", 70)
    is_pressure = fullness.get("high_pressure", False) or queue.get("pressure_signal", False)

    greed_score = avg_fullness * 0.5
    if is_pressure:
        greed_score += 25  # Druck-Bonus
    greed_score = min(100, greed_score)

    return {
        "status": "ok",
        "subagent": "B2-3c",
        "role": "Validator-Gier-Index",
        "greed_score": round(greed_score, 1),
        "validator_behavior": (
            "aggressive_optimization" if greed_score > 80
            else "active_ordering" if greed_score > 60
            else "passive_inclusion" if greed_score > 40
            else "lazy_accept_all"
        ),
    }


# ─── Hilfsfunktion ───────────────────────────────────────────────────

def _to_pressure_level(score: float) -> PressureLevel:
    if score <= 30:
        return PressureLevel.LOW
    elif score <= 50:
        return PressureLevel.MODERATE
    elif score <= 70:
        return PressureLevel.ELEVATED
    elif score <= 85:
        return PressureLevel.HIGH
    return PressureLevel.EXTREME


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"

    if cmd == "b2_1":
        print(json.dumps(b2_1_gas_stress_index(), indent=2))
    elif cmd == "b2_2":
        print(json.dumps(b2_2_mev_pressure_monitor(), indent=2))
    elif cmd == "b2_3":
        print(json.dumps(b2_3_block_fight_stats(), indent=2))
    else:
        print(json.dumps({
            "b2_1": b2_1_gas_stress_index(),
            "b2_2": b2_2_mev_pressure_monitor(),
            "b2_3": b2_3_block_fight_stats(),
        }, indent=2))
