#!/usr/bin/env python3
"""
Agent X — B2G Tendering Orchestrator.
Bootstraps all 9 tendering agents and runs the full pipeline against
a sample public tender (Kläranlage Nord — BA2, 4.2 Mio €).

Usage:
    python orchestrator_b2g.py
    python orchestrator_b2g.py --tender sample_tender.json
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents_b2g.tendering.agents import TenderingPipeline

# ============================================================
# Sample Tender: Kläranlage Nord — BA2
# ============================================================

SAMPLE_TENDER = {
    "tender_id": "TED-2026-0815-KLAERANLAGE-NORD",
    "description": "Sanierung der biologischen Reinigungsstufe — Kläranlage Nord, "
                   "inkl. Erneuerung Belüftungssystem und Neubau Phosphatfällung. "
                   "Bauabschnitt 2 von 3. VOB/A nationale Ausschreibung.",
    "estimated_value_eur": 4_200_000,
    "deadline": "2026-09-15T12:00:00+02:00",
    "cpv_codes": ["45252100", "45252200", "45232410"],
    "positions": [
        {"position_id": "LV-0101", "description": "Betonabbruch Bodenplatte, d=30cm, bewehrt, inkl. Entsorgung",
         "quantity": 450, "unit": "m²", "material_group": "Betonbau"},
        {"position_id": "LV-0102", "description": "Ortbeton C30/37 für neue Beckensohle, d=40cm, inkl. Schalung",
         "quantity": 380, "unit": "m³", "material_group": "Betonbau"},
        {"position_id": "LV-0201", "description": "Edelstahlrohr 1.4404, DN200, inkl. Schweißverbindungen",
         "quantity": 220, "unit": "m", "material_group": "Rohrleitungsbau"},
        {"position_id": "LV-0301", "description": "Feinblasige Membranbelüfter, EPDM, inkl. Montageschiene",
         "quantity": 1200, "unit": "Stk", "material_group": "HLK"},
        {"position_id": "LV-0302", "description": "Phosphatfällmittel-Dosierstation, 2-Kanal, inkl. Steuerung",
         "quantity": 2, "unit": "Stk", "material_group": "HLK"},
        {"position_id": "LV-0401", "description": "Kabelschacht mit Zugschacht, inkl. Kabelkanal DN100",
         "quantity": 12, "unit": "Stk", "material_group": "Elektrotechnik"},
        {"position_id": "LV-0501", "description": "Erdaushub für neue Zulaufleitung, Tiefe 3,5m, inkl. Verbau",
         "quantity": 850, "unit": "m³", "material_group": "Tiefbau"},
        {"position_id": "LV-0601", "description": "Epoxidharz-Beschichtung Beckeninnenwände, 2K, lebensmittelecht",
         "quantity": 1200, "unit": "m²", "material_group": "Ausbau"},
    ],
}


async def main():
    print("=" * 60)
    print("  Agent X — B2G Tendering Pipeline")
    print(f"  Start: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # Initialize pipeline
    pipeline = TenderingPipeline()
    print(f"\n  9 Agenten initialisiert:")
    print(f"    1. TenderMonitorAgent     — Scanner (TED/RSS)")
    print(f"    2. TenderParserAgent      — GAEB-XML Parser")
    print(f"    3. EligibilityCheckerAgent — Formalprüfung (VOB/A §6)")
    print(f"    4. CHIRiskAnalyzerAgent   — Construction Hazard Index")
    print(f"    5. PoPWIndexerAgent       — Blockchain-Bonuszertifikate")
    print(f"    6. OfferCalculatorAgent   — Preiskalkulation")
    print(f"    7. TenderComposerAgent    — GAEB-X84 Export")
    print(f"    8. DeadlineManagerAgent   — Fristenwächter")
    print(f"    9. BidSubmittalAgent      — Abgabe + Chain-Notar")

    # Run pipeline
    print(f"\n{'=' * 60}")
    print(f"  Starte Pipeline: {SAMPLE_TENDER['tender_id']}")
    print(f"{'=' * 60}\n")

    result = await pipeline.run(
        mock_tender=SAMPLE_TENDER,
        tender_value_eur=SAMPLE_TENDER["estimated_value_eur"],
        h3_region="881f8d7a49fffff",  # Hannover
    )

    # Result summary
    print(f"\n{'=' * 60}")
    print(f"  PIPELINE RESULT")
    print(f"{'=' * 60}")
    print(f"  Tender:        {result.tender_id}")
    print(f"  Phase:         {result.phase.value}")
    print(f"  CHI:           {result.chi_score}")
    print(f"  PoPW-Bonus:    +{result.popw_bonus_pct}%")
    print(f"  Final Price:   {result.calculated_offer.get('final_price_eur', 0):,.2f} €")
    print(f"  Submission Tx: {result.submission_tx[:32]}...")
    if result.errors:
        print(f"  Errors:        {len(result.errors)}")
        for e in result.errors:
            print(f"    - {e}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
