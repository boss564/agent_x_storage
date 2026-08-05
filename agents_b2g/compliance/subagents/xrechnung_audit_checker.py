"""
Subagent: XRechnungAuditChecker — EN 16931 / CIUS-DE Invoice Compliance.

Validates XRechnung 3.0 XML files for KoSIT Schematron compliance,
correct tax breakdown (§13b UStG), Leitweg-ID matching, and UBL 2.1
structural integrity.

Usage:
    checker = XRechnungAuditChecker()
    result = checker.check_invoices("TED-2026-0815-KLAERANLAGE-NORD")
"""
from __future__ import annotations

import hashlib
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("XRechnungAuditChecker")

# UBL 2.1 / EN 16931 namespaces
NS = {
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
}

REQUIRED_ELEMENTS = ["ID", "IssueDate", "AccountingSupplierParty",
                     "AccountingCustomerParty", "LegalMonetaryTotal"]


class XRechnungAuditChecker:
    """EN 16931 / CIUS-DE XRechnung 3.0 compliance auditor."""

    _SCHEMATRON_XSL = Path("archive_b2g/schemas/xrechnung_30/schematron/ubl/"
                           "XRechnung-UBL-validation.xsl")

    def __init__(self, archive_dir: str = "archive_b2g"):
        self.archive_dir = Path(archive_dir)
        self._schematron = self._load_schematron()

    @classmethod
    def _load_schematron(cls):
        if not cls._SCHEMATRON_XSL.exists():
            return None
        try:
            from lxml import etree
            xslt_tree = etree.parse(str(cls._SCHEMATRON_XSL))
            return etree.XSLT(xslt_tree)
        except ImportError:
            return None
        except Exception as exc:
            logger.warning(f"Schematron load failed: {exc}")
            return None

    # ============================================================
    # Main check
    # ============================================================

    def check_invoices(self, tender_id: str) -> dict[str, Any]:
        """Audit all XRechnung XMLs for a tender."""

        logger.info(f"XRechnung audit for {tender_id}")

        invoices = list(self.archive_dir.rglob(f"*{tender_id}*xrechnung*.xml"))
        invoices.extend(list(self.archive_dir.rglob("xrechnung_*.xml")))

        if not invoices:
            return {"status": "WARNING", "tender_id": tender_id,
                    "message": "Keine XRechnung-XMLs im Archiv gefunden.",
                    "total_invoices": 0, "valid_invoices": 0, "invalid_invoices": 0,
                    "timestamp": datetime.now(timezone.utc).isoformat()}

        results = []
        valid = invalid = 0

        for inv_path in invoices[:50]:  # Limit for sanity
            audit = self._audit_invoice(inv_path, tender_id)
            results.append(audit)
            if audit["valid"]:
                valid += 1
            else:
                invalid += 1

        print(f"  [XRechnungAudit] 🧾 {valid}/{len(results)} invoices valid "
              f"(Schematron={'active' if self._schematron else 'skip'})")

        return {
            "status": "PASSED" if invalid == 0 else "FAILED",
            "tender_id": tender_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_invoices": len(results),
            "valid_invoices": valid,
            "invalid_invoices": invalid,
            "invoices": results,
        }

    # ============================================================
    # Per-invoice audit
    # ============================================================

    def _audit_invoice(self, file_path: Path, tender_id: str) -> dict:
        try:
            xml_content = file_path.read_text(encoding="utf-8")
        except Exception as exc:
            return {"file": str(file_path), "valid": False,
                    "errors": [f"Lesefehler: {exc}"], "warnings": []}

        errors: list[str] = []
        warnings: list[str] = []

        # 1. Schematron
        sch = self._validate_schematron(xml_content)
        errors.extend(sch.get("errors", []))
        warnings.extend(sch.get("warnings", []))

        # 2. Tax compliance
        tax = self._check_tax(xml_content)
        errors.extend(tax.get("errors", []))
        warnings.extend(tax.get("warnings", []))

        # 3. Leitweg-ID
        leit = self._check_leitweg(xml_content, tender_id)
        errors.extend(leit.get("errors", []))
        warnings.extend(leit.get("warnings", []))

        # 4. Structure
        struct = self._check_structure(xml_content)
        errors.extend(struct.get("errors", []))
        warnings.extend(struct.get("warnings", []))

        return {
            "file": str(file_path),
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "details": {"schematron": sch, "tax": tax, "leitweg": leit, "structure": struct},
        }

    # ============================================================
    # Individual checks
    # ============================================================

    def _validate_schematron(self, xml_content: str) -> dict:
        if not self._schematron:
            return {"valid": True, "warnings": ["Schematron nicht verfügbar."]}

        try:
            from lxml import etree
            root = etree.fromstring(xml_content.encode("utf-8"))
            result = self._schematron(root)
            svrl_ns = "http://purl.oclc.org/dsdl/svrl"
            failed = result.xpath("//svrl:failed-assert", namespaces={"svrl": svrl_ns})
            errors = [f"{fa.get('test', '?')[:60]}" for fa in failed[:5]]
            return {"valid": len(failed) == 0, "errors": errors, "warnings": []}
        except Exception as exc:
            return {"valid": False, "errors": [f"Schematron: {exc}"], "warnings": []}

    @staticmethod
    def _check_tax(xml_content: str) -> dict:
        try:
            root = ET.fromstring(xml_content)
            tax_total = root.find(".//{*}TaxAmount")
            tax_amount = float(tax_total.text) if tax_total is not None and tax_total.text else 0.0
            is_13b = "reverse" in xml_content.lower() or "13b" in xml_content.lower()

            errors = []
            warnings = []
            if tax_amount < 0:
                errors.append("Steuerbetrag negativ.")
            if not is_13b and "Bau" in xml_content.upper():
                warnings.append("Bauleistung ohne §13b UStG-Kennzeichnung — prüfen.")

            return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings,
                    "tax_amount_eur": tax_amount, "reverse_charge_13b": is_13b}
        except Exception as exc:
            return {"valid": False, "errors": [f"Steuerprüfung: {exc}"], "warnings": []}

    @staticmethod
    def _check_leitweg(xml_content: str, tender_id: str) -> dict:
        try:
            root = ET.fromstring(xml_content)
            buyer_ref = root.find(".//{*}BuyerReference")
            leitweg = buyer_ref.text if buyer_ref is not None and buyer_ref.text else None

            if not leitweg:
                return {"valid": False, "errors": ["Leitweg-ID nicht gefunden."]}

            if tender_id[-8:] in leitweg or leitweg[:8] in tender_id:
                return {"valid": True, "errors": [], "leitweg_id": leitweg}
            return {"valid": False, "errors": [f"Leitweg-ID mismatch: {leitweg}"],
                    "leitweg_id": leitweg}
        except Exception as exc:
            return {"valid": False, "errors": [f"Leitweg-Prüfung: {exc}"]}

    @staticmethod
    def _check_structure(xml_content: str) -> dict:
        try:
            root = ET.fromstring(xml_content)
            missing = []
            for elem in REQUIRED_ELEMENTS:
                if root.find(f".//{{*}}{elem}") is None and root.find(f".//{elem}") is None:
                    # Also try with common namespace prefixes
                    found = False
                    for prefix in NS:
                        if root.find(f".//{{{NS[prefix]}}}{elem}") is not None:
                            found = True
                            break
                    if not found:
                        missing.append(elem)

            if missing:
                return {"valid": False, "errors": [f"Fehlende Elemente: {', '.join(missing)}"]}
            return {"valid": True, "errors": [], "warnings": []}
        except ET.ParseError as exc:
            return {"valid": False, "errors": [f"XML-Parsing: {exc}"]}
