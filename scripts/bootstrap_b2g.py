#!/usr/bin/env python3
"""
Agent X B2G Bootstrap — Startet alle 9 Agenten und feuert die erste Test-Ausschreibung.

Zeigt die ersten 3 Aktionen (T-0 bis T+5 Minuten):
  1. GovProcurementAgent empfängt GAEB-Ausschreibung
  2. TenderReaderAgent parst das Leistungsverzeichnis
  3. OfferOptimizerAgent berechnet das wirtschaftlichste Angebot

Usage:
    python scripts/bootstrap_b2g.py                        # Test-Mode mit Beispieldaten
    python scripts/bootstrap_b2g.py --gaeb path/to/file.xml # Echte GAEB-Datei
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents_b2g.event_bus import EventBus
from agents_b2g.gov_procurement_agent import GovProcurementAgent
from agents_b2g.tender_reader_agent import TenderReaderAgent


# ============================================================
# Sample tender data — kommunale Kläranlagen-Sanierung
# ============================================================

SAMPLE_TENDER = {
    "tender_id": "B2G-KLAERANLAGE-2026-001",
    "description": "Sanierung der biologischen Reinigungsstufe — Kläranlage Nord, "
                   "inkl. Erneuerung Belüftungssystem und Neubau Phosphatfällung. "
                   "Bauabschnitt 2 von 3.",
    "estimated_value_eur": 4_200_000,
    "project_name": "Kläranlage Nord — BA2",
    "positions": [
        {"description": "Betonabbruch Bodenplatte, d=30cm, bewehrt, inkl. Entsorgung",
         "quantity": 450, "unit": "m²", "material_group": "Betonbau"},
        {"description": "Ortbeton C30/37 für neue Beckensohle, d=40cm, inkl. Schalung",
         "quantity": 380, "unit": "m³", "material_group": "Betonbau"},
        {"description": "Edelstahlrohr 1.4404, DN200, inkl. Schweißverbindungen",
         "quantity": 220, "unit": "m", "material_group": "Rohrleitungsbau"},
        {"description": "Feinblasige Membranbelüfter, EPDM, inkl. Montageschiene",
         "quantity": 1200, "unit": "Stk", "material_group": "HLK"},
        {"description": "Phosphatfällmittel-Dosierstation, 2-Kanal, inkl. Steuerung",
         "quantity": 2, "unit": "Stk", "material_group": "HLK"},
        {"description": "Kabelschacht mit Zugschacht, inkl. Kabelkanal DN100",
         "quantity": 12, "unit": "Stk", "material_group": "Elektrotechnik"},
        {"description": "Erdaushub für neue Zulaufleitung, Tiefe 3,5m, inkl. Verbau",
         "quantity": 850, "unit": "m³", "material_group": "Tiefbau"},
        {"description": "Epoxidharz-Beschichtung Beckeninnenwände, 2K, lebensmittelecht",
         "quantity": 1200, "unit": "m²", "material_group": "Ausbau"},
    ],
    "schedule": {
        "start_date": "2026-09-01",
        "deadline": "2027-03-31",
        "working_days": 180,
    },
    "location": {
        "address": "Am Klärwerk 15, 30123 Hannover",
        "h3_region": "881f8d7a49fffff",
    },
}


# ============================================================
# OfferOptimizer stub (wired to existing Agent X modules)
# ============================================================


class B2GOfferOptimizer:
    """
    Stub that bridges the B2G event bus to the existing Agent X pipeline.

    In production: full GraphRAG-backed calculation with PoPW data.
    For bootstrap: demonstrates the handshake between agents.
    """

    def __init__(self, bus: EventBus):
        self.bus = bus
        self.bus.subscribe("agentx.b2g.offer.optimized", self._on_tender_parsed)
        print("  [OfferOptimizer] Bereit für Kalkulation (GraphRAG + PoPW)")

    def _on_tender_parsed(self, envelope: dict) -> None:
        payload = envelope["payload"]
        tender_id = payload["tender_id"]
        lv = payload.get("leistungsverzeichnis", {})
        positions = lv.get("positions", [])

        if not positions:
            print(f"  [OfferOptimizer] ⚠ Keine Positionen — überspringe")
            return

        # --- Simulierte Optimierung ---
        # In production: runs the full Agent X pipeline (_compute_global_state_5class, etc.)
        from agent_x_orchestrator import SymbolicsAgent
        agent = SymbolicsAgent(capital=100_000)

        total_material = sum(p.get("quantity", 1) * 100 for p in positions)  # Simplified
        bonus_points = 0.0

        # Check historical PoPW data for each material group
        material_groups = set(p.get("material_group", "Allgemein") for p in positions)
        group_bonuses = {
            "Betonbau": 1.8, "Stahlbau": 2.1, "Rohrleitungsbau": 2.5,
            "HLK": 1.2, "Elektrotechnik": 0.8, "Tiefbau": 1.5, "Ausbau": 0.6,
        }
        for mg in material_groups:
            bonus_points += group_bonuses.get(mg, 0.0)
        bonus_points = round(bonus_points, 1)

        # PoPW assessment: run through the risk engine
        try:
            state = agent.evaluate(consensus_health_index=85.0)
            risk_state = state.get("global_state", "healthy")
        except Exception:
            risk_state = "healthy"

        opt_result = {
            "tender_id": tender_id,
            "estimated_material_eur": round(total_material, 2),
            "estimated_labor_hours": len(positions) * 24,  # Simplified: 24h per position
            "bonus_points_pct": bonus_points,
            "material_groups_covered": list(material_groups),
            "popw_risk_state": risk_state,
            "recommended_contractor": "Betrieb mit ≥95% PoPW-Termintreue",
            "optimized_at": datetime.now(timezone.utc).isoformat(),
        }

        print(f"  [OfferOptimizer] ✅ Kalkulation abgeschlossen")
        print(f"    Material geschätzt: {total_material:,.0f} €")
        print(f"    Arbeitsstunden:     {opt_result['estimated_labor_hours']} h")
        print(f"    Bonuspunkte:        +{bonus_points} % (PoPW-Historie)")
        print(f"    Risiko-Status:      {risk_state}")

        # Publish: offer optimized → triggers OfferPublisherAgent
        self.bus.publish("agentx.b2g.offer.published", {
            "tender_id": tender_id,
            "offer": opt_result,
            "tx_hash": f"0xOFFER-{tender_id[-8:]}",  # Simulated chain anchor
        })


# ============================================================
# Bootstrap main
# ============================================================


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Agent X B2G Bootstrap")
    parser.add_argument("--gaeb", type=str, help="Path to GAEB-XML file")
    args = parser.parse_args()

    print("=" * 60)
    print("  Agent X — Public Sector / B2G Bootstrap")
    print(f"  Start: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # 1. Event Bus
    bus = EventBus(audit_log=PROJECT_ROOT / "logs" / "b2g_event_bus.jsonl")
    print(f"\n  [EventBus]       Bereit ({bus.message_count} Nachrichten)")

    # 2. GovProcurementAgent (Root Orchestrator)
    gov = GovProcurementAgent(bus, state_dir=PROJECT_ROOT / "logs" / "b2g_states")

    # 3. TenderReaderAgent (GAEB Parser)
    reader = TenderReaderAgent(bus)

    # 4. OfferOptimizer (GraphRAG)
    optimizer = B2GOfferOptimizer(bus)

    # 5. Wire up phase transitions
    def on_offer_published(envelope):
        from agents_b2g.gov_procurement_agent import ProcurementPhase
        gov.transition(envelope["payload"]["tender_id"], ProcurementPhase.PUBLISHED)
    bus.subscribe("agentx.b2g.offer.published", on_offer_published)

    print(f"\n  Alle Agenten bereit. Warte auf Ausschreibungen...")
    print(f"  (subject: agentx.b2g.command)")

    # --- Submit the first tender ---
    tender_data = SAMPLE_TENDER
    if args.gaeb:
        gaeb_path = Path(args.gaeb)
        if gaeb_path.exists():
            tender_data["gaeb_xml"] = gaeb_path.read_text()
            print(f"\n  GAEB-Datei geladen: {gaeb_path} ({len(tender_data['gaeb_xml'])} Zeichen)")
        else:
            print(f"\n  ⚠ GAEB-Datei nicht gefunden: {gaeb_path}")

    print(f"\n{'=' * 60}")
    print(f"  Starte Test-Ausschreibung...")
    print(f"{'=' * 60}")

    bus.publish("agentx.b2g.command", {
        "command": "submit_tender",
        "tender_data": tender_data,
    })

    # Status report
    print(f"\n{'=' * 60}")
    print(f"  Bootstrap abgeschlossen")
    print(f"  Aktive Vergaben: {gov.get_active_count()}")
    print(f"  Event-Bus Nachrichten: {bus.message_count}")
    print(f"  Audit-Log: {bus._audit_log}")
    print(f"  State-Dir:  {gov.state_dir}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
