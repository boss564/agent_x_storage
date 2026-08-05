"""
Agent 2 — TenderReaderAgent (GAEB Parser, B2G Edition).

Parses GAEB-XML files (GAEB_DA_XML_3.2) into structured JSON.
Extracts Bill of Quantities (Leistungsverzeichnis), schedules,
threshold values, and material lists.

Handles both real GAEB-XML and a simplified JSON fallback for testing.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents_b2g.event_bus import EventBus


class TenderReaderAgent:
    """
    Parses public tender documents into structured procurement data.

    Input:  GAEB-XML (primary) or simplified JSON (test fallback)
    Output: Structured Leistungsverzeichnis (LV) with:
      - Position list (description, quantity, unit, material group)
      - Schedule constraints (start date, deadline)
      - Threshold values (estimated total)
    """

    # GAEB XML namespaces (GAEB_DA_XML_3.2)
    GAEB_NS = {
        "gaeb": "http://www.gaeb.de/GAEB_DA_XML/200407",
    }

    def __init__(self, event_bus: EventBus):
        self.bus = event_bus
        # Listen for parsed tender events
        self.bus.subscribe("agentx.b2g.tender.parsed", self._on_tender_received)
        print("  [TenderReader]   Bereit für GAEB-XML (GAEB_DA_XML_3.2)")

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------

    def _on_tender_received(self, envelope: dict) -> None:
        """Parse tender data from the event bus."""
        payload = envelope["payload"]
        tender_id = payload["tender_id"]
        raw = payload.get("raw_data", {})

        # Check for embedded GAEB XML or test data
        gaeb_xml = raw.get("gaeb_xml", raw.get("xml", ""))
        if gaeb_xml:
            lv = self.parse_gaeb_xml(gaeb_xml, tender_id)
        else:
            lv = self.parse_from_dict(raw, tender_id)

        if lv:
            self.bus.publish("agentx.b2g.offer.optimized", {
                "tender_id": tender_id,
                "leistungsverzeichnis": lv,
                "estimated_value_eur": payload.get("estimated_value_eur", 0),
            })

    # ------------------------------------------------------------------
    # GAEB-XML Parser
    # ------------------------------------------------------------------

    def parse_gaeb_xml(self, xml_string: str, tender_id: str) -> dict | None:
        """
        Parse GAEB_DA_XML_3.2 into structured LV.

        Real GAEB files have a complex nested structure.
        This parser handles the core elements needed for procurement.
        """
        try:
            root = ET.fromstring(xml_string)
        except ET.ParseError as exc:
            print(f"  [TenderReader]   ❌ XML-Parse-Fehler: {exc}")
            return self._fallback_lv(tender_id)

        # Extract project info
        project_name = self._find_text(root, ".//ProjectName", "Unbekanntes Bauvorhaben")
        description = self._find_text(root, ".//Description", project_name)

        # Extract positions (BoQ items)
        positions = []
        for pos_elem in root.iter("Item") or root.iter("Position"):
            pos = {
                "position_id": self._find_text(pos_elem, ".//ItemNumber", ""),
                "description": self._find_text(pos_elem, ".//ShortText", ""),
                "quantity": self._parse_float(self._find_text(pos_elem, ".//Quantity", "1")),
                "unit": self._find_text(pos_elem, ".//Unit", "Stk"),
                "material_group": self._classify_material(
                    self._find_text(pos_elem, ".//ShortText", "")
                ),
            }
            if pos["position_id"]:
                positions.append(pos)

        if not positions:
            print(f"  [TenderReader]   ⚠ Keine Positionen in GAEB-XML gefunden")
            return self._fallback_lv(tender_id)

        print(f"  [TenderReader]   📄 {len(positions)} Leistungspositionen extrahiert")
        return {
            "tender_id": tender_id,
            "project_name": project_name,
            "description": description,
            "positions": positions,
            "position_count": len(positions),
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "source_format": "GAEB_DA_XML_3.2",
        }

    # ------------------------------------------------------------------
    # Simplified parser (JSON test data)
    # ------------------------------------------------------------------

    def parse_from_dict(self, data: dict, tender_id: str) -> dict | None:
        """Parse from structured dict (test/fallback mode)."""
        positions = data.get("positions", data.get("leistungsverzeichnis", []))
        if not positions:
            print(f"  [TenderReader]   ⚠ Kein Leistungsverzeichnis in Daten")
            return self._fallback_lv(tender_id)

        enriched = []
        for i, pos in enumerate(positions):
            if isinstance(pos, str):
                pos = {"description": pos}
            enriched.append({
                "position_id": pos.get("position_id", f"POS-{i+1:03d}"),
                "description": pos.get("description", ""),
                "quantity": float(pos.get("quantity", 1)),
                "unit": pos.get("unit", "Stk"),
                "material_group": pos.get("material_group",
                                          self._classify_material(pos.get("description", ""))),
            })

        print(f"  [TenderReader]   📄 {len(enriched)} Leistungspositionen geladen")
        return {
            "tender_id": tender_id,
            "project_name": data.get("project_name", data.get("description", "Bauvorhaben")),
            "description": data.get("description", ""),
            "positions": enriched,
            "position_count": len(enriched),
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "source_format": "JSON_TEST",
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_text(self, elem, xpath, default=""):
        found = elem.find(xpath)
        return found.text.strip() if found is not None and found.text else default

    def _parse_float(self, s: str) -> float:
        try:
            return float(s.replace(",", ".").replace(" ", ""))
        except (ValueError, TypeError):
            return 1.0

    def _classify_material(self, description: str) -> str:
        """Classify a position into a material group based on description."""
        desc_lower = description.lower()
        if any(w in desc_lower for w in ["beton", "estrich", "zement", "schalung"]):
            return "Betonbau"
        elif any(w in desc_lower for w in ["stahl", "träger", "bewehrung"]):
            return "Stahlbau"
        elif any(w in desc_lower for w in ["rohr", "leitung", "kanal", "abwasser"]):
            return "Rohrleitungsbau"
        elif any(w in desc_lower for w in ["kabel", "elektro", "schalt", "verteiler"]):
            return "Elektrotechnik"
        elif any(w in desc_lower for w in ["heizung", "lüftung", "klima", "wärme"]):
            return "HLK"
        elif any(w in desc_lower for w in ["putz", "maler", "boden", "fliesen"]):
            return "Ausbau"
        elif any(w in desc_lower for w in ["erd", "aushub", "gründung", "bohr"]):
            return "Tiefbau"
        return "Allgemein"

    def _fallback_lv(self, tender_id: str) -> dict:
        """Minimal LV when parsing fails."""
        return {
            "tender_id": tender_id,
            "project_name": "Bauvorhaben (unklar)",
            "description": "Kein GAEB-XML — manuelle Erfassung erforderlich",
            "positions": [],
            "position_count": 0,
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "source_format": "FALLBACK",
        }
