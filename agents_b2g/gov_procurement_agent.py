"""
Agent 1 — GovProcurementAgent (Root Orchestrator, B2G Edition).

Receives public tenders (GAEB-XML), checks formal eligibility (prequalification),
and delegates tasks to sub-agents. Maintains the global procurement state.

Lifecycle:  TENDER_RECEIVED → PARSED → OPTIMIZED → PUBLISHED →
            CONTRACT_SIGNED → ESCROW_FUNDED → DELIVERY_CONFIRMED →
            INVOICE_GENERATED → CHAIN_ANCHORED → COMPLETED
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from agents_b2g.event_bus import EventBus


class ProcurementPhase(str, Enum):
    TENDER_RECEIVED = "TENDER_RECEIVED"
    PARSED = "PARSED"
    OPTIMIZED = "OPTIMIZED"
    PUBLISHED = "PUBLISHED"
    CONTRACT_SIGNED = "CONTRACT_SIGNED"
    ESCROW_FUNDED = "ESCROW_FUNDED"
    DELIVERY_CONFIRMED = "DELIVERY_CONFIRMED"
    INVOICE_GENERATED = "INVOICE_GENERATED"
    CHAIN_ANCHORED = "CHAIN_ANCHORED"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"


class GovProcurementAgent:
    """
    Root orchestrator for public-sector procurement.

    Validates incoming tenders against BHO/VOB/A thresholds,
    routes them through the 9-agent pipeline, and maintains
    the authoritative procurement state log.
    """

    # BHO § 55: Schwellenwerte für Vergabearten
    THRESHOLD_DIRECT = 1_000       # Direktauftrag bis 1.000 €
    THRESHOLD_NEGOTIATED = 100_000 # Freihändige Vergabe bis 100.000 €
    THRESHOLD_EU_TENDER = 5_382_000 # EU-weite Ausschreibung ab 5,382 Mio €

    def __init__(self, event_bus: EventBus, state_dir: Path | None = None):
        self.bus = event_bus
        self.state_dir = state_dir or Path("logs/b2g_states")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._active_procurements: dict[str, dict[str, Any]] = {}
        self._phase = ProcurementPhase.TENDER_RECEIVED

        # Register command handler
        self.bus.subscribe("agentx.b2g.command", self._handle_command)

        print(f"  [GovProcurement]  Initialisiert. "
              f"Schwellenwerte: Direkt={self.THRESHOLD_DIRECT:,}€, "
              f"Verhandelt={self.THRESHOLD_NEGOTIATED:,}€, "
              f"EU={self.THRESHOLD_EU_TENDER:,}€")

    # ------------------------------------------------------------------
    # Command handler — entry point for new tenders
    # ------------------------------------------------------------------

    def _handle_command(self, envelope: dict) -> None:
        """Process incoming command from the event bus."""
        payload = envelope["payload"]
        cmd = payload.get("command", "")

        if cmd == "submit_tender":
            self.receive_tender(payload.get("tender_data", {}))
        elif cmd == "status":
            self._publish_status(payload.get("tender_id", ""))
        else:
            print(f"  [GovProcurement]  Unbekanntes Kommando: {cmd}")

    def receive_tender(self, tender_data: dict) -> str:
        """
        Receive a new public tender. Validates formal eligibility,
        generates a tender ID, and publishes the tender.parsed event.
        """
        tender_id = tender_data.get("tender_id",
                                     f"B2G-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}")
        estimated_value = float(tender_data.get("estimated_value_eur", 0))

        # BHO § 55: Vergabeart bestimmen
        if estimated_value <= self.THRESHOLD_DIRECT:
            vergabeart = "Direktauftrag"
        elif estimated_value <= self.THRESHOLD_NEGOTIATED:
            vergabeart = "Freihändige Vergabe"
        elif estimated_value <= self.THRESHOLD_EU_TENDER:
            vergabeart = "Nationale Ausschreibung"
        else:
            vergabeart = "EU-weite Ausschreibung"

        print(f"\n{'=' * 60}")
        print(f"  [GovProcurement]  NEUE AUSSCHREIBUNG EMPFANGEN")
        print(f"  Tender-ID:    {tender_id}")
        print(f"  Auftragswert: {estimated_value:,.2f} €")
        print(f"  Vergabeart:   {vergabeart} (VOB/A)")
        print(f"  Beschreibung: {tender_data.get('description', 'N/A')[:80]}")
        print(f"{'=' * 60}")

        # Store state
        state = {
            "tender_id": tender_id,
            "phase": ProcurementPhase.TENDER_RECEIVED.value,
            "received_at": datetime.now(timezone.utc).isoformat(),
            "estimated_value_eur": estimated_value,
            "vergabeart": vergabeart,
            "tender_data": tender_data,
        }
        self._active_procurements[tender_id] = state
        self._persist_state(tender_id, state)

        # Publish: tender received → triggers TenderReaderAgent
        self.bus.publish("agentx.b2g.tender.parsed", {
            "tender_id": tender_id,
            "vergabeart": vergabeart,
            "estimated_value_eur": estimated_value,
            "raw_data": tender_data,
        })

        return tender_id

    # ------------------------------------------------------------------
    # Phase transitions (called by sub-agents via event bus)
    # ------------------------------------------------------------------

    def transition(self, tender_id: str, new_phase: ProcurementPhase,
                   metadata: dict | None = None) -> None:
        """Advance a procurement to the next phase."""
        if tender_id not in self._active_procurements:
            print(f"  [GovProcurement]  ⚠ Unbekannte Tender-ID: {tender_id}")
            return

        old = self._active_procurements[tender_id]["phase"]
        self._active_procurements[tender_id]["phase"] = new_phase.value
        if metadata:
            self._active_procurements[tender_id].update(metadata)

        self._persist_state(tender_id, self._active_procurements[tender_id])

        phase_icons = {
            "PARSED": "📄", "OPTIMIZED": "✅", "PUBLISHED": "📨",
            "CONTRACT_SIGNED": "✍️", "ESCROW_FUNDED": "💰",
            "DELIVERY_CONFIRMED": "🚚", "INVOICE_GENERATED": "🧾",
            "CHAIN_ANCHORED": "🔗", "COMPLETED": "🏁",
        }
        icon = phase_icons.get(new_phase.value, "→")
        print(f"  [GovProcurement]  {icon} {old} → {new_phase.value}")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def _publish_status(self, tender_id: str) -> None:
        state = self._active_procurements.get(tender_id, {})
        print(f"  [GovProcurement]  Status {tender_id}: {state.get('phase', 'UNKNOWN')}")

    def get_active_count(self) -> int:
        return len(self._active_procurements)

    def _persist_state(self, tender_id: str, state: dict) -> None:
        path = self.state_dir / f"{tender_id}.json"
        path.write_text(json.dumps(state, indent=2, default=str))
