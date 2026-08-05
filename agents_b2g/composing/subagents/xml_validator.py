"""
Subagent: XML Schema Validator for GAEB DA XML 3.3 and XRechnung 3.0.

Validates generated XML against official XSD schemas from GAEB.de / KoSIT
before upload to e-procurement platforms or tax authorities.

Supports:
  - GAEB DA XML 3.3: X83 (Angebotsaufforderung), X84 (Angebotsabgabe),
    X86 (Auftragserteilung), X89 (Rechnung)
  - XRechnung 3.0 (placeholder — KoSIT schema)

Usage:
    # Phase-specific validation (auto-discovers XSD from reference dir):
    validator = XMLValidatorSubagent()
    result = validator.validate("X84", xml_string)

    # With custom unified schema path (single XSD from GAEB.de):
    validator = XMLValidatorSubagent("archive_b2g/reference/schemas/gaeb_da_xml_3.3.xsd")
    result = validator.validate_gaeb_xml(xml_string)

    # Validate file on disk:
    result = validator.validate_file("X83", Path("tender.x83"))

    # Raise on failure (for pre-upload checks):
    validator.validate_or_raise("X84", xml_string)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("XMLValidatorSubagent")


class XMLValidatorSubagent:
    """Validates GAEB DA XML 3.3 and XRechnung 3.0 against official XSD schemas."""

    # Schema paths relative to project root (phase-specific schemas)
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
    _SCHEMA_DIR = _PROJECT_ROOT / "archive_b2g" / "reference" / "gaeb_test_suite" / "schemas"

    _SCHEMA_FILES = {
        "X83": "GAEB_DA_XML_83_3.3_2021-05.xsd",
        "X84": "GAEB_DA_XML_84_3.3_2021-05.xsd",
        "X86": "GAEB_DA_XML_86_3.3_2021-05.xsd",
        "X89": "GAEB_DA_XML_89_3.3_2021-05.xsd",
    }

    def __init__(self, custom_schema_path: str | Path | None = None):
        self._schemas: dict[str, Any] = {}
        self._custom_schema: Any = None
        self._custom_schema_path = Path(custom_schema_path) if custom_schema_path else None
        self._xsd_available = self._check_xmlschema()

        if self._custom_schema_path:
            self._load_custom_schema()
        else:
            self._preload_schemas()

    # ============================================================
    # Schema loading
    # ============================================================

    @staticmethod
    def _check_xmlschema() -> bool:
        try:
            import xmlschema  # noqa: F401
            return True
        except ImportError:
            logger.warning("xmlschema nicht installiert - Fallback auf Regel-Pruefung")
            return False

    def _load_custom_schema(self) -> None:
        """Load a single unified XSD schema from a custom path."""
        if not self._xsd_available or not self._custom_schema_path:
            return
        from xmlschema import XMLSchema

        if self._custom_schema_path.exists():
            try:
                self._custom_schema = XMLSchema(str(self._custom_schema_path))
                logger.info(f"Custom XSD geladen: {self._custom_schema_path}")
            except Exception as exc:
                logger.warning(f"Custom XSD Ladefehler: {exc}")

    def _preload_schemas(self) -> None:
        """Preload all available GAEB schemas from the reference directory."""
        if not self._xsd_available:
            return
        from xmlschema import XMLSchema

        for phase, filename in self._SCHEMA_FILES.items():
            schema_path = self._SCHEMA_DIR / filename
            if schema_path.exists():
                try:
                    self._schemas[phase] = XMLSchema(str(schema_path))
                    logger.info(f"XSD {phase} geladen: {schema_path.name}")
                except Exception as exc:
                    logger.warning(f"XSD {phase} Ladefehler: {exc}")
                    self._schemas[phase] = None
            else:
                logger.info(f"XSD {phase} nicht lokal: {schema_path}")
                self._schemas[phase] = None

    # ============================================================
    # Validation methods
    # ============================================================

    def validate(self, phase: str, xml_string: str) -> dict:
        """
        Validate XML against GAEB DA XML 3.3 phase-specific schema.

        Args:
            phase: GAEB phase ('X83', 'X84', 'X86', 'X89')
            xml_string: The XML content to validate

        Returns:
            dict with keys: valid (bool), errors (list[str]), phase (str), method (str)
        """
        if phase not in self._SCHEMA_FILES:
            return {"valid": False, "errors": [f"Unbekannte GAEB-Phase: {phase}"],
                    "phase": phase, "method": "unknown"}

        schema = self._schemas.get(phase)

        if schema is not None:
            try:
                schema.validate(xml_string)
                return {"valid": True, "errors": [], "phase": phase, "method": "xsd"}
            except Exception as exc:
                return {"valid": False, "errors": [str(exc)], "phase": phase, "method": "xsd"}

        return self._validate_rules(phase, xml_string)

    def validate_gaeb_xml(self, xml_string: str) -> dict:
        """
        Validate GAEB XML against a single unified schema (custom_schema_path).
        Use this when you have one combined XSD from GAEB.de.
        """
        if self._custom_schema is not None:
            try:
                self._custom_schema.validate(xml_string)
                return {"valid": True, "errors": [], "phase": "auto", "method": "xsd"}
            except Exception as exc:
                return {"valid": False, "errors": [str(exc)], "phase": "auto", "method": "xsd"}

        # Auto-detect phase from XML content and validate
        for phase in ("X83", "X84", "X86", "X89"):
            dp = phase.lstrip("X")
            if f"<DP>{dp}</DP>" in xml_string or f"DP>{dp}<" in xml_string:
                return self.validate(phase, xml_string)

        return {"valid": False, "errors": ["Could not detect GAEB phase from XML"],
                "phase": "unknown", "method": "auto-detect"}

    def validate_file(self, phase: str, file_path: Path) -> dict:
        """Validate an XML file on disk."""
        if not file_path.exists():
            return {"valid": False, "errors": [f"File not found: {file_path}"],
                    "phase": phase, "method": "file", "file": str(file_path)}
        xml_string = file_path.read_text(encoding="utf-8")
        result = self.validate(phase, xml_string)
        result["file"] = str(file_path)
        return result

    def validate_or_raise(self, phase: str, xml_string: str) -> str:
        """
        Validate and return XML if valid, raise if invalid.
        Use this before uploading to e-procurement platforms.
        """
        result = self.validate(phase, xml_string)
        if not result["valid"]:
            error_list = "\n  - ".join(result["errors"])
            raise ValueError(
                f"GAEB DA XML 3.3 {phase} Validierung fehlgeschlagen:\n"
                f"  Methode: {result['method']}\n"
                f"  Fehler:\n  - {error_list}"
            )
        return xml_string

    # ============================================================
    # Fallback: rule-based validation (no XSD available)
    # ============================================================

    def _validate_rules(self, phase: str, xml_string: str) -> dict:
        """Fallback rule-based structural validation."""
        errors = []
        dp_number = phase.lstrip("X")

        if "GAEB" not in xml_string:
            errors.append("Missing GAEB root element")
        if f"<DP>{dp_number}</DP>" not in xml_string and f"DP>{dp_number}<" not in xml_string:
            errors.append(f"Missing DP={dp_number} (GAEB DA XML 3.3 phase {phase})")
        if "3.3" not in xml_string:
            errors.append("Missing Version=3.3")
        if "VersDate" not in xml_string:
            errors.append("Missing VersDate (e.g. 2021-05)")

        if phase == "X84":
            if "TotalAmount" not in xml_string:
                errors.append("X84: Missing TotalAmount")
            if "Item" not in xml_string:
                errors.append("X84: No Item elements")
            if "UP" not in xml_string:
                errors.append("X84: Missing unit prices (UP)")
        elif phase == "X83":
            if "EstValue" not in xml_string and "Qty" not in xml_string:
                errors.append("X83: Missing quantities")
        elif phase == "X89":
            if "Invoice" not in xml_string and "Rechnung" not in xml_string:
                errors.append("X89: Missing invoice data")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "phase": phase,
            "method": "rule-based (xsd not available)",
        }

    # ============================================================
    # Properties
    # ============================================================

    @property
    def available_schemas(self) -> list[str]:
        """List phases with XSD schemas successfully loaded."""
        names = [p for p, s in self._schemas.items() if s is not None]
        if self._custom_schema is not None and self._custom_schema_path:
            names.append(f"custom:{self._custom_schema_path.name}")
        return names

    @property
    def schema_dir(self) -> str:
        return str(self._SCHEMA_DIR)
