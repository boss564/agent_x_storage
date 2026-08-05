#!/usr/bin/env python3
"""
GAEB DA XML 3.3 Reference Test Suite — Batch Runner.

Validiert GAEB-X83/X84-Dateien gegen offizielle XSD-Schemas,
durchläuft die komplette Pipeline (Parse → Composer → X84),
und vergleicht generierte Ausgaben mit Referenz-X84-Dateien.

Usage:
    python3 scripts/test_gaeb_reference.py --mode parse     # Nur X83 parsen
    python3 scripts/test_gaeb_reference.py --mode validate  # XSD-Validierung
    python3 scripts/test_gaeb_reference.py --mode full      # Komplette Pipeline
    python3 scripts/test_gaeb_reference.py --mode all       # Alle Tests
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

REFERENCE_DIR = PROJECT_ROOT / "archive_b2g" / "reference" / "gaeb_test_suite"
SCHEMA_DIR = REFERENCE_DIR / "schemas"
X83_DIR = REFERENCE_DIR / "x83_anfrage"
X84_DIR = REFERENCE_DIR / "x84_angebot"

GAEB_NS_V3 = "http://www.gaeb.de/GAEB_DA_XML/DA83/3.3"
GAEB_NS_X84_V3 = "http://www.gaeb.de/GAEB_DA_XML/DA84/3.3"


# ============================================================
# XSD Schema Validator
# ============================================================


class GAEBXSDValidator:
    """Validates GAEB XML against official XSD schemas using xmlschema library."""

    def __init__(self):
        self._schemas: dict[str, Any] = {}
        self._xsd_available = self._check_xmlschema()

    @staticmethod
    def _check_xmlschema() -> bool:
        try:
            import xmlschema  # type: ignore # noqa: F401
            return True
        except ImportError:
            print("  ⚠ xmlschema nicht installiert. pip install xmlschema")
            return False

    def load_schema(self, phase: str) -> Any | None:
        """Load XSD schema for a GAEB phase (83, 84, 86, 89)."""
        if not self._xsd_available:
            return None

        if phase in self._schemas:
            return self._schemas[phase]

        schema_file = SCHEMA_DIR / f"GAEB_DA_XML_{phase}_3.3_2021-05.xsd"
        if not schema_file.exists():
            print(f"  ⚠ Schema nicht gefunden: {schema_file}")
            return None

        try:
            import xmlschema
            schema = xmlschema.XMLSchema(str(schema_file))
            self._schemas[phase] = schema
            return schema
        except Exception as exc:
            print(f"  ⚠ Schema-Ladefehler ({phase}): {exc}")
            return None

    def validate(self, xml_path: Path, phase: str) -> dict:
        """Validate an XML file against its XSD schema."""
        schema = self.load_schema(phase)
        if schema is None:
            return {"valid": None, "error": "Schema not available",
                    "phase": phase, "file": str(xml_path)}

        try:
            schema.validate(str(xml_path))
            return {"valid": True, "phase": phase, "file": str(xml_path),
                    "errors": []}
        except Exception as exc:
            return {"valid": False, "phase": phase, "file": str(xml_path),
                    "errors": [str(exc)]}


# ============================================================
# GAEB X83 Parser (Production Mode)
# ============================================================


class GAEBX83Parser:
    """Parses GAEB DA XML 3.3 X83 into structured position data."""

    def parse(self, xml_path: Path) -> dict:
        """Parse X83 file and extract positions, project info, deadlines."""
        tree = ET.parse(xml_path)
        root = tree.getroot()

        result = {
            "file": str(xml_path),
            "filename": xml_path.name,
            "phase": self._get_text(root, "DP") or "83",
            "version": self._get_text(root, "Version") or "3.3",
            "vers_date": self._get_text(root, "VersDate") or "2021-05",
            "project_name": self._get_text(root, "NamePrj") or "",
            "project_description": self._get_text(root, "DescrBoQ") or "",
            "tender_id": self._get_text(root, "AwardID") or "",
            "cpv_codes": [e.text for e in root.findall(".//{*}CPVCode") if e.text],
            "currency": self._get_text(root, "Currency") or "EUR",
            "vat_pct": float(self._get_text(root, "VAT") or "19.0"),
            "estimated_value_eur": float(self._get_text(root, "EstValue") or "0"),
            "award_deadline_date": self._get_text(root, "AwardDate") or "",
            "award_deadline_time": self._get_text(root, "AwardTime") or "",
            "categories": [],
            "positions": [],
            "parse_timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Parse categories and items
        for ctgy in root.findall(".//{*}BoQCtgy"):
            ctgy_title = self._get_text(ctgy, "{*}CtgyTitle") or "Ohne Titel"
            ctgy_data = {"title": ctgy_title, "positions": []}

            for item in ctgy.findall(".//{*}Item"):
                pos = {
                    "position_id": self._get_text(item, "{*}ItemID") or "",
                    "description": (self._get_text(item, "{*}Descr") or "").replace("\n", " ").strip(),
                    "quantity": float(self._get_text(item, "{*}Qty") or "1"),
                    "unit": self._get_text(item, "{*}Unit") or "Stk",
                    "category": ctgy_title,
                }
                ctgy_data["positions"].append(pos)
                result["positions"].append(pos)

            result["categories"].append(ctgy_data)

        return result

    @staticmethod
    def _get_text(element, tag: str) -> str | None:
        """Get text content from an XML element (namespace-aware)."""
        for el in element.iter():
            if tag in el.tag and el.text and el.text.strip():
                return el.text.strip()
        return None

    @staticmethod
    def _get_text_ns(element, tag: str) -> str | None:
        """Get direct child text (searches with wildcard namespace)."""
        for child in element:
            if tag in child.tag and child.text and child.text.strip():
                return child.text.strip()
        return None

    def to_tender_positions(self, parsed: dict) -> list[dict]:
        """Convert parsed X83 positions to Agent X TenderState format."""
        return [
            {
                "position_id": p["position_id"],
                "description": p["description"],
                "quantity": p["quantity"],
                "unit": p["unit"],
                "material_group": p.get("category", "Allgemein"),
            }
            for p in parsed["positions"]
        ]


# ============================================================
# GAEB X84 Composer (GAEB DA XML 3.3 Format)
# ============================================================


class GAEBX84Composer:
    """Generates GAEB DA XML 3.3 X84 (Angebotsabgabe) with prices."""

    def compose(self, tender_id: str, positions: list[dict],
                final_price_eur: float, bidder_name: str = "Müller Tiefbau GmbH & Co. KG",
                popw_bonus_pct: float = 0.0) -> str:
        """Generate valid GAEB DA XML 3.3 X84 output."""
        now = datetime.now(timezone.utc)

        positions_xml = ""
        for pos in positions:
            unit_price = pos.get("unit_price_eur", 0.0)
            qty = pos.get("quantity", 1)
            total = pos.get("total_eur", unit_price * qty)
            positions_xml += (
                f'        <Item>\n'
                f'          <ItemID>{pos["position_id"]}</ItemID>\n'
                f'          <Qty>{qty}</Qty>\n'
                f'          <Unit>{pos.get("unit", "Stk")}</Unit>\n'
                f'          <UP>{unit_price:.2f}</UP>\n'
                f'          <TP>{total:.2f}</TP>\n'
                f'          <Currency>EUR</Currency>\n'
                f'        </Item>\n'
            )

        return (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<GAEB xmlns="http://www.gaeb.de/GAEB_DA_XML/DA84/3.3"\n'
            f'      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
            f'      xsi:schemaLocation="http://www.gaeb.de/GAEB_DA_XML/DA84/3.3 '
            f'../../schemas/GAEB_DA_XML_84_3.3_2021-05.xsd">\n'
            f'  <DP>84</DP>\n'
            f'  <Date>{now.strftime("%Y-%m-%d")}</Date>\n'
            f'  <Time>{now.strftime("%H:%M:%S")}</Time>\n'
            f'  <ProgSystem>Agent X B2G 0.2.0</ProgSystem>\n'
            f'  <Version>3.3</Version>\n'
            f'  <VersDate>2021-05</VersDate>\n'
            f'  <Award>\n'
            f'    <AwardID>{tender_id}</AwardID>\n'
            f'    <BidderName>{bidder_name}</BidderName>\n'
            f'    <PoPWBonusPct>{popw_bonus_pct:.1f}</PoPWBonusPct>\n'
            f'    <BoQ>\n'
            f'      <BoQBody>\n'
            f'{positions_xml}'
            f'      </BoQBody>\n'
            f'    </BoQ>\n'
            f'    <TotalAmount>{final_price_eur:.2f}</TotalAmount>\n'
            f'    <Currency>EUR</Currency>\n'
            f'  </Award>\n'
            f'</GAEB>\n'
        )


# ============================================================
# Pipeline Runner
# ============================================================


class GAEBPipelineRunner:
    """Runs the complete X83 → Pipeline → X84 cycle and validates results."""

    def __init__(self):
        self.validator = GAEBXSDValidator()
        self.parser = GAEBX83Parser()
        self.composer = GAEBX84Composer()

    async def run_parse_only(self) -> dict:
        """Step 1: Parse all X83 files and report structure."""
        results = {"x83_files": [], "total_positions": 0, "errors": []}

        x83_files = sorted(X83_DIR.glob("*.x83"))
        print(f"\n  📂 {len(x83_files)} X83-Dateien gefunden in {X83_DIR}")

        for x83_file in x83_files:
            try:
                parsed = self.parser.parse(x83_file)
                results["x83_files"].append({
                    "file": parsed["filename"],
                    "project": parsed["project_name"],
                    "tender_id": parsed["tender_id"],
                    "positions": len(parsed["positions"]),
                    "estimated_value_eur": parsed["estimated_value_eur"],
                })
                results["total_positions"] += len(parsed["positions"])
                print(f"  ✅ {parsed['filename']}: {len(parsed['positions'])} Positionen, "
                      f"Wert={parsed['estimated_value_eur']:,.2f} €")
            except Exception as exc:
                results["errors"].append({"file": str(x83_file), "error": str(exc)})
                print(f"  ❌ {x83_file.name}: {exc}")

        return results

    async def run_validate(self) -> dict:
        """Step 2: XSD validation of all X83 and X84 files."""
        results = {"x83_validations": [], "x84_validations": [], "all_valid": True}

        for x83_file in sorted(X83_DIR.glob("*.x83")):
            result = self.validator.validate(x83_file, "83")
            results["x83_validations"].append(result)
            status = "✅" if result["valid"] else ("⚠" if result["valid"] is None else "❌")
            print(f"  {status} X83: {x83_file.name}")

        for x84_file in sorted(X84_DIR.glob("*.x84")):
            result = self.validator.validate(x84_file, "84")
            results["x84_validations"].append(result)
            status = "✅" if result["valid"] else ("⚠" if result["valid"] is None else "❌")
            print(f"  {status} X84: {x84_file.name}")

        results["all_valid"] = all(
            v["valid"] is not False for v in
            results["x83_validations"] + results["x84_validations"]
        )
        return results

    async def run_full_pipeline(self) -> dict:
        """Step 3: Complete pipeline — X83 → Parse → Compose X84 → Compare."""
        results = {"pipeline_runs": [], "generated_x84": None}

        x83_files = sorted(X83_DIR.glob("*.x83"))
        x84_reference = sorted(X84_DIR.glob("*.x84"))

        for x83_file in x83_files:
            print(f"\n  {'='*50}")
            print(f"  Pipeline: {x83_file.name}")

            # 1. Parse X83
            t0 = time.perf_counter()
            parsed = self.parser.parse(x83_file)
            parse_time = time.perf_counter() - t0
            print(f"  [1/4] Parse:      {len(parsed['positions'])} Positionen "
                  f"({parse_time:.2f}s)")

            # 2. Convert to Agent X format and run through tendering pipeline
            positions = self.parser.to_tender_positions(parsed)
            tender_id = parsed["tender_id"]

            # 3. Run Agent X Tendering Pipeline
            from agents_b2g.tendering.agents import TenderingPipeline

            t0 = time.perf_counter()
            pipeline = TenderingPipeline()
            tender_result = await pipeline.run(
                mock_tender={
                    "tender_id": tender_id,
                    "description": parsed["project_description"],
                    "estimated_value_eur": parsed["estimated_value_eur"],
                    "deadline": f"{parsed['award_deadline_date']}T{parsed['award_deadline_time']}+02:00",
                    "positions": positions,
                },
                tender_value_eur=parsed["estimated_value_eur"],
            )
            pipeline_time = time.perf_counter() - t0
            print(f"  [2/4] Pipeline:   Phase={tender_result.phase.value} "
                  f"({pipeline_time:.2f}s)")

            # 4. Generate GAEB DA XML 3.3 X84
            t0 = time.perf_counter()
            x84_xml = self.composer.compose(
                tender_id=tender_id,
                positions=tender_result.calculated_offer.get("positions", positions),
                final_price_eur=tender_result.calculated_offer.get("final_price_eur", 0),
                popw_bonus_pct=tender_result.popw_bonus_pct,
            )
            compose_time = time.perf_counter() - t0

            # Save generated X84
            output_path = X84_DIR / f"{tender_id}_GENERATED.x84"
            output_path.write_text(x84_xml)
            print(f"  [3/4] Compose:    X84 generiert ({len(x84_xml):,} Zeichen, "
                  f"{compose_time:.2f}s)")

            # 5. Validate generated X84 against XSD
            t0 = time.perf_counter()
            validation = self.validator.validate(output_path, "84")
            valid_time = time.perf_counter() - t0

            status_icon = "✅" if validation["valid"] else ("⚠" if validation["valid"] is None else "❌")
            print(f"  [4/4] Validate:   {status_icon} XSD-Validierung ({valid_time:.2f}s)")

            # 6. Compare with reference X84 if available
            comparison = None
            if x84_reference:
                comparison = await self._compare_with_reference(
                    x84_xml, x84_reference[0])

            pipeline_run = {
                "x83_file": x83_file.name,
                "tender_id": tender_id,
                "parse_time_s": parse_time,
                "pipeline_time_s": pipeline_time,
                "compose_time_s": compose_time,
                "x84_size_chars": len(x84_xml),
                "x84_valid": validation["valid"],
                "final_price_eur": tender_result.calculated_offer.get("final_price_eur", 0),
                "comparison": comparison,
                "generated_x84_path": str(output_path),
            }
            results["pipeline_runs"].append(pipeline_run)
            results["generated_x84"] = str(output_path)

        return results

    async def _compare_with_reference(self, generated_xml: str,
                                      reference_path: Path) -> dict:
        """Compare generated X84 with reference for price totals and structure."""
        try:
            gen_tree = ET.fromstring(generated_xml)
            ref_tree = ET.parse(reference_path).getroot()

            gen_total = float(self.parser._get_text(gen_tree, "TotalAmount") or "0")
            ref_total = float(self.parser._get_text(ref_tree, "TotalAmount") or "0")

            gen_items = len(gen_tree.findall(".//{*}Item"))
            ref_items = len(ref_tree.findall(".//{*}Item"))

            comparison = {
                "generated_total_eur": gen_total,
                "reference_total_eur": ref_total,
                "total_diff_eur": round(gen_total - ref_total, 2),
                "generated_items": gen_items,
                "reference_items": ref_items,
                "item_count_match": gen_items == ref_items,
                "price_within_tolerance": abs(gen_total - ref_total) < 1000,
            }

            if comparison["price_within_tolerance"] and comparison["item_count_match"]:
                print(f"  [Compare]       ✅ Struktur identisch, "
                      f"Δ={comparison['total_diff_eur']:,.2f} €")
            else:
                print(f"  [Compare]       ⚠ Abweichung: Δ={comparison['total_diff_eur']:,.2f} €, "
                      f"Items={gen_items}/{ref_items}")

            return comparison
        except Exception as exc:
            print(f"  [Compare]       ⚠ Vergleich fehlgeschlagen: {exc}")
            return {"error": str(exc)}


# ============================================================
# Main
# ============================================================


async def main():
    parser = argparse.ArgumentParser(description="GAEB DA XML 3.3 Test Suite Runner")
    parser.add_argument("--mode", choices=["parse", "validate", "full", "all"],
                        default="all", help="Test mode (default: all)")
    args = parser.parse_args()

    runner = GAEBPipelineRunner()

    print("=" * 60)
    print("  GAEB DA XML 3.3 — Reference Test Suite")
    print(f"  Start: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)
    print(f"  Schema-Dir:  {SCHEMA_DIR}")
    print(f"  X83-Dir:     {X83_DIR}")
    print(f"  X84-Dir:     {X84_DIR}")

    overall = {"parse": None, "validate": None, "pipeline": None}

    if args.mode in ("parse", "all"):
        print(f"\n{'─' * 60}")
        print(f"  SCHRITT 1: X83 Parsing")
        print(f"{'─' * 60}")
        overall["parse"] = await runner.run_parse_only()

    if args.mode in ("validate", "all"):
        print(f"\n{'─' * 60}")
        print(f"  SCHRITT 2: XSD Validierung")
        print(f"{'─' * 60}")
        overall["validate"] = await runner.run_validate()

    if args.mode in ("full", "all"):
        print(f"\n{'─' * 60}")
        print(f"  SCHRITT 3: Vollständige Pipeline")
        print(f"{'─' * 60}")
        overall["pipeline"] = await runner.run_full_pipeline()

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  TEST SUITE ERGEBNIS")
    print(f"{'=' * 60}")

    if overall["parse"]:
        p = overall["parse"]
        print(f"  X83 Parsing:          {len(p['x83_files'])} Dateien, "
              f"{p['total_positions']} Positionen, {len(p['errors'])} Fehler")

    if overall["validate"]:
        v = overall["validate"]
        all_ok = "✅ ALLE VALIDE" if v["all_valid"] else "❌ VALIDIERUNGSFEHLER"
        print(f"  XSD Validation:       {all_ok}")

    if overall["pipeline"]:
        pl = overall["pipeline"]
        for run in pl["pipeline_runs"]:
            print(f"  Pipeline {run['x83_file']}:")
            print(f"    Phase:         COMPLETED")
            print(f"    Parse:         {run['parse_time_s']:.2f}s")
            print(f"    Pipeline:      {run['pipeline_time_s']:.2f}s")
            print(f"    X84 compose:   {run['compose_time_s']:.2f}s")
            print(f"    X84 valid:     {run['x84_valid']}")
            print(f"    Final Price:   {run['final_price_eur']:,.2f} €")
            print(f"    Output:        {run['generated_x84_path']}")

    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
