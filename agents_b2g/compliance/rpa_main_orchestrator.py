"""
Agent 1 (RPA Wave): RPAMainOrchestrator — Root Agent for Rechnungsprüfungsamt.

Orchestrates the 8-step audit pipeline and produces the final discharge report:
  GoBD Integrity → Ledger (BHO) → Hash (Chain) → XRechnung → PoPW →
  VOB/B Compliance → Tax → PDF/A-3 Report

Usage:
    orch = RPAMainOrchestrator()
    result = orch.conduct_audit("TED-2026-0815-KLAERANLAGE-NORD")
    # result["overall_status"]["verdict"]: ENTLASTET / VORBEHALT / ENTLASTUNG_VERWEIGERT
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents_b2g.compliance.subagents.gobd_integrity_checker import GoBDIntegrityChecker
from agents_b2g.compliance.subagents.ledger_exporter_subagent import LedgerExporterSubagent
from agents_b2g.compliance.subagents.hash_verifier_subagent import HashVerifierSubagent
from agents_b2g.compliance.subagents.xrechnung_audit_checker import XRechnungAuditChecker
from agents_b2g.compliance.subagents.vobb_payment_compliance_checker import (
    VOBBPaymentComplianceChecker)
from agents_b2g.compliance.subagents.tax_compliance_auditor import TaxComplianceAuditor
from agents_b2g.compliance.subagents.pdf_audit_composer import PDFAuditComposer
from agents_b2g.compliance.subagents.popw_evidence_auditor import PoPWEvidenceAuditor

logger = logging.getLogger("RPAMainOrchestrator")


class RPAMainOrchestrator:
    """Root agent for the Rechnungsprüfungsamt audit pipeline."""

    def __init__(self, archive_base_dir: str = "archive_b2g",
                 chain_adapter: Any = None,
                 output_dir: str = "archive_b2g/rpa_reports"):
        self.archive_dir = Path(archive_base_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.gobd_checker = GoBDIntegrityChecker(str(archive_base_dir))
        self.ledger_exporter = LedgerExporterSubagent(archive_dir=str(archive_base_dir))
        self.hash_verifier = HashVerifierSubagent(archive_dir=str(archive_base_dir),
                                                  chain_adapter=chain_adapter)
        self.xrechnung_checker = XRechnungAuditChecker(str(archive_base_dir))
        self.vobb_checker = VOBBPaymentComplianceChecker(archive_dir=str(archive_base_dir))
        self.tax_checker = TaxComplianceAuditor(archive_dir=str(archive_base_dir))
        self.pdf_composer = PDFAuditComposer(str(output_dir))
        self.popw_auditor = PoPWEvidenceAuditor(archive_dir=str(archive_base_dir))

    # ============================================================
    # Main audit
    # ============================================================

    def conduct_audit(self, tender_id: str,
                      pruefungszeitraum: str | None = None,
                      rpa_beauftragter: str = "Rechnungsprüfungsamt",
                      options: dict | None = None) -> dict[str, Any]:
        """Complete RPA audit from GoBD integrity to final discharge report."""

        start = time.perf_counter()
        options = options or {}

        logger.info(f"RPA audit: {tender_id}")

        results: dict[str, Any] = {
            "tender_id": tender_id,
            "rpa_beauftragter": rpa_beauftragter,
            "pruefungszeitraum": pruefungszeitraum,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "AUDIT_RUNNING",
            "checks": {},
            "overall_status": None,
            "report_path": None,
            "errors": [],
        }

        # == Step 1: GoBD Integrity ==
        gobd = self.gobd_checker.check_integrity(tender_id)
        results["checks"]["gobd_integrity"] = gobd
        if gobd.get("overall_status") == "FAILED":
            return self._halt(results, "GoBD-Integritätsverletzung!")

        # == Step 2: BHO Ledger ==
        ledger = self.ledger_exporter.export_ledger(tender_id)
        results["checks"]["ledger"] = ledger
        if ledger.get("status") != "LEDGER_EXPORTED":
            return self._halt(results, "Ledger-Export fehlgeschlagen", ledger)
        if not ledger.get("ledger", {}).get("bho_compliant"):
            return self._halt(results, "BHO Zero-Sum verletzt!", ledger)

        # == Step 3: Chain Hash Verification ==
        chain = self.hash_verifier.verify_anchors(tender_id)
        results["checks"]["chain_anchors"] = chain
        if chain.get("overall_status") == "FAILED":
            return self._halt(results, "On-Chain-Hashes stimmen nicht überein!", chain)
        if chain.get("overall_status") == "UNTESTED":
            results["checks"]["chain_anchors"]["note"] = "Chain-Adapter nicht verfügbar — Mock-Mode"

        # == Step 4: XRechnung Audit ==
        xrechnung = self.xrechnung_checker.check_invoices(tender_id)
        results["checks"]["xrechnung"] = xrechnung
        if xrechnung.get("status") == "FAILED":
            return self._halt(results, "XRechnung-Compliance verletzt!", xrechnung)

        # == Step 5: PoPW Evidence ==
        popw = self.popw_auditor.audit_evidence(tender_id)
        results["checks"]["popw_evidence"] = popw
        if popw.get("status") == "FAILED":
            return self._halt(results, "PoPW-Evidence unzureichend!", popw)
        if popw.get("status") == "UNTESTED":
            results["checks"]["popw_evidence"]["note"] = "Keine Telemetrie-Daten im Archiv — Mock-Mode"

        # == Step 6: VOB/B Payment Compliance ==
        vobb = self.vobb_checker.check_payments(tender_id)
        results["checks"]["vobb_compliance"] = vobb
        if vobb.get("status") == "FAILED":
            return self._halt(results, "VOB/B-Zahlungsvorschriften verletzt!", vobb)

        # == Step 7: Tax Compliance ==
        tax = self.tax_checker.audit_tax_compliance(tender_id)
        results["checks"]["tax_compliance"] = tax
        if tax.get("status") == "FAILED":
            return self._halt(results, "Steuerrechtliche Unregelmäßigkeiten!", tax)

        # == Step 8: Overall verdict ==
        results["overall_status"] = self._verdict(results["checks"])

        # == Step 9: Generate report ==
        elapsed = time.perf_counter() - start
        results["completed_at"] = datetime.now(timezone.utc).isoformat()
        results["duration_s"] = round(elapsed, 2)

        report = self.pdf_composer.generate_report(tender_id, results, rpa_beauftragter)
        results["report_path"] = report.get("path")
        results["pdf_hash"] = report.get("sha256")
        verdict = results["overall_status"]
        print(f"\n  [RPA-Orchestrator] 🏛️ Audit complete in {elapsed:.1f}s")
        print(f"    GoBD={gobd.get('overall_status', '?')} | "
              f"BHO Δ={ledger['ledger'].get('delta_eur', '?'):.2f} € | "
              f"Chain={chain.get('overall_status', '?')}")
        print(f"    Verdict: {verdict['verdict']} ({verdict['level']}) — "
              f"{verdict['recommendation']}")

        results["status"] = "AUDIT_COMPLETE"

        # Archive
        self._archive(tender_id, results)

        return results

    # ============================================================
    # Placeholder checks (extensible)
    # ============================================================

    @staticmethod
    def _check_popw(tender_id: str) -> dict:
        return {"status": "PLACEHOLDER", "tender_id": tender_id,
                "note": "PoPW telemetry evidence — TelemetryPipeline covers IoT/GPS/ZK proofs"}

    @staticmethod
    def _check_tax(tender_id: str) -> dict:
        return {"status": "PLACEHOLDER", "tender_id": tender_id,
                "note": "§13b UStG reverse charge — TreasuryPipeline covers tax compliance"}

    # ============================================================
    # Verdict engine
    # ============================================================

    def _verdict(self, checks: dict) -> dict:
        failed = []
        warnings = []
        for name, result in checks.items():
            if not isinstance(result, dict):
                continue
            status = result.get("status") or result.get("overall_status", "?")
            if status in ("FAILED", "ERROR", "HALTED"):
                failed.append(name)
            elif status in ("WARNING", "PLACEHOLDER"):
                warnings.append(name)

        if not failed and not warnings:
            return {"verdict": "ENTLASTET", "level": "GREEN",
                    "message": "Alle Prüfungen bestanden — uneingeschränkte Entlastung.",
                    "recommendation": "Entlastung erteilen."}
        elif not failed:
            return {"verdict": "ENTLASTET_MIT_HINWEIS", "level": "YELLOW",
                    "message": f"{len(warnings)} Warnungen: {', '.join(warnings[:3])}",
                    "recommendation": "Entlastung mit Hinweisen erteilen."}
        elif len(failed) <= 2:
            return {"verdict": "VORBEHALT", "level": "ORANGE",
                    "message": f"{len(failed)} Prüfungen fehlgeschlagen: {', '.join(failed)}",
                    "recommendation": "Entlastung unter Vorbehalt, Nachprüfung in 3 Monaten."}
        else:
            return {"verdict": "ENTLASTUNG_VERWEIGERT", "level": "RED",
                    "message": f"{len(failed)} Prüfungen fehlgeschlagen!",
                    "recommendation": "Entlastung verweigern. Fachaufsicht einschalten."}

    # ============================================================
    # Report + Archive
    # ============================================================

    def _generate_report(self, tender_id: str, results: dict,
                         beauftragter: str) -> dict:
        """Generate RPA audit report as structured JSON (PDF via AuditReportGenerator)."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_id = f"RPA_Audit_{tender_id[-16:]}_{ts}"
        path = self.output_dir / f"{report_id}.json"
        report = {
            "report_id": report_id,
            "tender_id": tender_id,
            "beauftragter": beauftragter,
            "verdict": results["overall_status"],
            "checks_summary": {
                k: (v.get("status") or v.get("overall_status", "?"))
                for k, v in results["checks"].items()
            },
            "generated_at": results["completed_at"],
        }
        path.write_text(json.dumps(report, indent=2, default=str, ensure_ascii=False))
        import hashlib
        return {"path": str(path), "hash": hashlib.sha256(path.read_bytes()).hexdigest()[:16]}

    def _archive(self, tender_id: str, results: dict) -> None:
        archive_dir = self.archive_dir / tender_id / "rpa_audits"
        archive_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = archive_dir / f"rpa_audit_{ts}.json"
        save = {k: v for k, v in results.items() if k != "report_pdf_bytes"}
        path.write_text(json.dumps(save, indent=2, default=str, ensure_ascii=False))
        logger.info(f"RPA audit archived: {path}")

    def _halt(self, results: dict, reason: str, detail: Any = None) -> dict:
        results["status"] = "AUDIT_HALTED"
        results["halt_reason"] = reason
        results["overall_status"] = {
            "verdict": "HALTED", "level": "RED",
            "message": reason,
            "recommendation": "Prüfung manuell durchführen.",
        }
        logger.error(f"RPA HALT: {reason}")
        return results
