#!/usr/bin/env python3
"""
BVBS Pruefdatei Validator.

Validiert offizielle GAEB DA XML 3.3 Pruefdateien des BVBS
gegen XSD-Schema und vergleicht generierte X84 mit Referenz.

Usage:
    python3 scripts/test_bvbs_pruefdatei.py --x83 pruefdatei.x83 --x84 pruefdatei.x84
    python3 scripts/test_bvbs_pruefdatei.py --x83 pruefdatei.x83 --validate-only
    python3 scripts/test_bvbs_pruefdatei.py --x83 pruefdatei.x83 --x84 pruefdatei.x84 --full
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

BVBS_DIR = PROJECT_ROOT / "archive_b2g" / "reference" / "bvbs_test_suite"


def validate_xsd(phase: str, xml_path: Path) -> dict:
    """Validate an XML file against its GAEB DA XML 3.3 XSD schema."""
    from agents_b2g.composing.subagents.xml_validator import XMLValidatorSubagent
    validator = XMLValidatorSubagent()
    return validator.validate_file(phase, xml_path)


def _find_element(element, tag: str):
    for el in element.iter():
        if tag in el.tag:
            return el
    return None


def compare_totals(x84_generated_path: Path, x84_reference_path: Path) -> dict:
    """Compare TotalAmount and Item count between generated and reference X84."""
    gen_tree = ET.parse(x84_generated_path)
    ref_tree = ET.parse(x84_reference_path)

    gen_el = _find_element(gen_tree.getroot(), "TotalAmount")
    ref_el = _find_element(ref_tree.getroot(), "TotalAmount")
    gen_total = float(gen_el.text) if gen_el is not None and gen_el.text else 0.0
    ref_total = float(ref_el.text) if ref_el is not None and ref_el.text else 0.0

    gen_items = sum(1 for e in gen_tree.iter() if "Item" in e.tag)
    ref_items = sum(1 for e in ref_tree.iter() if "Item" in e.tag)

    return {
        "generated_total_eur": gen_total,
        "reference_total_eur": ref_total,
        "total_diff_eur": round(gen_total - ref_total, 2),
        "generated_items": gen_items,
        "reference_items": ref_items,
        "item_count_match": gen_items == ref_items,
        "price_match": abs(gen_total - ref_total) < 0.02,
    }


async def run_full_pipeline(x83_path: Path, x84_ref_path: Path | None) -> dict:
    """Full pipeline: parse X83, run Agent X tendering, generate X84, compare."""
    from agents_b2g.tendering.agents import TenderingPipeline
    from scripts.test_gaeb_reference import GAEBX83Parser, GAEBX84Composer

    parser = GAEBX83Parser()
    composer = GAEBX84Composer()

    t0 = time.perf_counter()
    parsed = parser.parse(x83_path)
    parse_time = time.perf_counter() - t0
    print(f"  [1/4] Parse: {len(parsed['positions'])} Positionen ({parse_time:.2f}s)")

    positions = parser.to_tender_positions(parsed)
    tender_id = parsed.get("tender_id") or "BVBS-TEST"

    t0 = time.perf_counter()
    pipeline = TenderingPipeline()
    tender_result = await pipeline.run(
        mock_tender={
            "tender_id": tender_id,
            "description": parsed.get("project_description") or "BVBS Pruefdatei",
            "estimated_value_eur": parsed.get("estimated_value_eur", 1_000_000),
            "deadline": "2026-12-31T12:00:00+02:00",
            "positions": positions,
        },
        tender_value_eur=parsed.get("estimated_value_eur", 1_000_000),
    )
    pipeline_time = time.perf_counter() - t0
    print(f"  [2/4] Pipeline: Phase={tender_result.phase.value} ({pipeline_time:.2f}s)")

    offer_positions = tender_result.calculated_offer.get("positions", positions)
    final_price = tender_result.calculated_offer.get("final_price_eur", 0)

    t0 = time.perf_counter()
    x84_xml = composer.compose(
        tender_id=tender_id, positions=offer_positions, final_price_eur=final_price)
    compose_time = time.perf_counter() - t0

    output_path = BVBS_DIR / "generated_x84.xml"
    output_path.write_text(x84_xml)
    print(f"  [3/4] X84 generiert: {len(x84_xml):,} Zeichen ({compose_time:.2f}s)")

    validation = validate_xsd("X84", output_path)
    status = "OK" if validation["valid"] else "FAIL"
    print(f"  [4/4] XSD-Validierung: {status} method={validation['method']}")

    comparison = None
    if x84_ref_path and x84_ref_path.exists():
        comparison = compare_totals(output_path, x84_ref_path)
        c = comparison
        match = "OK" if c["price_match"] else "MISMATCH"
        print(f"\n  [Vergleich] {match}: Gen={c['generated_total_eur']:,.2f} EUR, "
              f"Ref={c['reference_total_eur']:,.2f} EUR, "
              f"Delta={c['total_diff_eur']:,.2f} EUR")

    return {"x84_validation": validation, "comparison": comparison}


async def main_async():
    parser = argparse.ArgumentParser(description="BVBS GAEB DA XML 3.3 Pruefdatei Validator")
    parser.add_argument("--x83", type=str, help="Path to X83 reference file")
    parser.add_argument("--x84", type=str, help="Path to X84 reference file")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()

    x83_path = Path(args.x83) if args.x83 else (BVBS_DIR / "pruefdatei.x83")
    x84_path = Path(args.x84) if args.x84 else (BVBS_DIR / "pruefdatei.x84")

    print("=" * 60)
    print("  BVBS GAEB DA XML 3.3 — Pruefdatei Validator")
    print(f"  Start: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    if not x83_path.exists():
        print(f"\n  X83 nicht gefunden: {x83_path}")
        print(f"  BVBS-Pruefdatei herunterladen nach: {BVBS_DIR}/")
        return

    # Step 1: XSD Validation
    print(f"\n{'─' * 60}")
    print(f"  SCHRITT 1: XSD-Validierung")
    print(f"{'─' * 60}")

    print(f"  X83: {x83_path.name} ({x83_path.stat().st_size:,} bytes)")
    x83_result = validate_xsd("X83", x83_path)
    s = "OK" if x83_result["valid"] else "FAIL"
    print(f"  {s} X83: method={x83_result['method']}")
    for e in x83_result.get("errors", [])[:3]:
        print(f"    - {str(e)[:120]}")

    x84_ref_result = None
    if x84_path.exists():
        print(f"  X84 Ref: {x84_path.name} ({x84_path.stat().st_size:,} bytes)")
        x84_ref_result = validate_xsd("X84", x84_path)
        s = "OK" if x84_ref_result["valid"] else "FAIL"
        print(f"  {s} X84 Ref: method={x84_ref_result['method']}")
        for e in x84_ref_result.get("errors", [])[:3]:
            print(f"    - {str(e)[:120]}")

    if args.validate_only:
        _print_summary(x83_result, x84_ref_result, None)
        return

    # Step 2: Full pipeline
    if args.full:
        print(f"\n{'─' * 60}")
        print(f"  SCHRITT 2: Pipeline (X83 → Parse → X84 → Vergleich)")
        print(f"{'─' * 60}")
        pipeline_result = await run_full_pipeline(x83_path, x84_path if x84_path.exists() else None)
        _print_summary(x83_result, x84_ref_result, pipeline_result.get("comparison"))
        return

    _print_summary(x83_result, x84_ref_result, None)


def _print_summary(x83_r: dict | None, x84_r: dict | None, comparison: dict | None):
    print(f"\n{'=' * 60}")
    print(f"  TEST ERGEBNIS")
    print(f"{'=' * 60}")
    x83_ok = x83_r["valid"] if x83_r else None
    x84_ok = x84_r["valid"] if x84_r else None
    print(f"  X83 XSD:  {'OK' if x83_ok else ('N/A' if x83_ok is None else 'FAIL')}")
    print(f"  X84 XSD:  {'OK' if x84_ok else ('N/A' if x84_ok is None else 'FAIL')}")
    if comparison:
        print(f"  Preis:    {'OK' if comparison['price_match'] else 'FAIL'} "
              f"(Delta={comparison['total_diff_eur']:,.2f} EUR)")
        print(f"  Items:    {'OK' if comparison['item_count_match'] else 'FAIL'} "
              f"({comparison['generated_items']}/{comparison['reference_items']})")
    all_ok = (x83_ok and x84_ok is not False
              and (not comparison or comparison["price_match"]))
    print(f"\n  Gesamt:   {'PRODUKTIONSBEREIT' if all_ok else 'NICHT BESTANDEN'}")
    print(f"{'=' * 60}\n")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
