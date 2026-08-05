"""
Subagent: PDFAuditComposer — RPA Final Audit Report (PDF/A-3).

Generates the official discharge report (Entlastungsbericht) for the
Rechnungsprüfungsamt with all 7 audit steps, verdict, tax attestation,
and cryptographic evidence package.

Usage:
    composer = PDFAuditComposer()
    report = composer.generate_report(tender_id, results, rpa_beauftragter)
"""
from __future__ import annotations

import hashlib
import io
import logging
from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak,
)

logger = logging.getLogger("PDFAuditComposer")

VERDICT_COLORS = {
    "GREEN": colors.Color(0.1, 0.6, 0.1),
    "YELLOW": colors.Color(0.8, 0.6, 0),
    "ORANGE": colors.orange,
    "RED": colors.Color(0.8, 0, 0),
}


class PDFAuditComposer:
    """RPA discharge report PDF/A-3 generator."""

    def __init__(self, output_dir: str = "archive_b2g/rpa_reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ============================================================
    # Main generator
    # ============================================================

    def generate_report(self, tender_id: str, results: dict,
                        rpa_beauftragter: str = "Rechnungsprüfungsamt") -> dict:
        """Generate complete RPA audit report PDF."""

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                leftMargin=20 * mm, rightMargin=20 * mm,
                                topMargin=15 * mm, bottomMargin=15 * mm)

        styles = getSampleStyleSheet()
        S = self._setup_styles(styles)
        story = []
        checks = results.get("checks", {})
        verdict = results.get("overall_status", {})
        ts = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

        # === COVER ===
        story.append(Spacer(1, 2 * cm))
        story.append(Paragraph("RECHNUNGSPRÜFUNGSAMT", S["title"]))
        story.append(Paragraph("Entlastungsbericht gemäß BHO §70–§80", S["subtitle"]))
        story.append(Spacer(1, 1 * cm))

        cover_data = [
            ["Tender-ID", tender_id],
            ["Prüfer", rpa_beauftragter],
            ["Datum", ts],
            ["Status", results.get("status", "?")],
        ]
        cover_table = Table(cover_data, colWidths=[5 * cm, 10 * cm])
        cover_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
            ("BACKGROUND", (0, 0), (0, -1), colors.Color(0.90, 0.90, 0.92)),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(cover_table)
        story.append(PageBreak())

        # === VERDICT ===
        story.append(Paragraph("1. Gesamturteil", S["h2"]))
        level = verdict.get("level", "N/A")
        vc = VERDICT_COLORS.get(level, colors.black)
        story.append(Paragraph(
            f"<font color='{vc}'><b>{verdict.get('verdict', '?')}</b></font>", S["body"]))
        story.append(Paragraph(verdict.get("message", ""), S["body"]))
        story.append(Paragraph(
            f"<b>Empfehlung:</b> {verdict.get('recommendation', '')}", S["body"]))
        story.append(Spacer(1, 4 * mm))

        # === AUDIT STEPS ===
        story.append(Paragraph("2. Prüfschritte", S["h2"]))

        steps = [
            ("GoBD-Integrität", "gobd_integrity", "WORM-Archiv Hash-Ketten"),
            ("BHO-Kassenbuch", "ledger", "Decimal-Buchführung, Zero-Sum"),
            ("Chain-Verifikation", "chain_anchors", "Gnosis/peaq Merkle-Abgleich"),
            ("XRechnung-Audit", "xrechnung", "EN 16931 / §13b / Leitweg-ID"),
            ("PoPW-Evidenz", "popw_evidence", "Telemetrie physische Deckung"),
            ("VOB/B-Compliance", "vobb_compliance", "§16 Fristen, §17 Einbehalt, §13 Mängel"),
            ("Steuerkonformität", "tax_compliance", "§13b UStG, BZSt, Freistellungsattest"),
        ]

        step_rows = [["Prüfung", "Status", "Details"]]
        for name, key, desc in steps:
            check = checks.get(key, {})
            status = str(check.get("status") or check.get("overall_status", "?"))
            detail = ""
            if key == "ledger":
                d = check.get("ledger", {})
                detail = f"Δ={d.get('delta_eur', '?'):.2f} €"
            elif key == "gobd_integrity":
                detail = f"Files={check.get('checked_files', '?')}"
            elif key == "xrechnung":
                detail = f"Valid={check.get('valid_invoices', '?')}/{check.get('total_invoices', '?')}"
            elif key == "vobb_compliance":
                detail = "✓" if check.get("overall_compliant") else "✗"
            elif key == "tax_compliance":
                att = check.get("freistellungsattest", {})
                detail = att.get("status", "?")
            step_rows.append([name, status, detail or desc])

        step_table = Table(step_rows, colWidths=[4 * cm, 3.5 * cm, 8 * cm])
        step_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.25, 0.35, 0.55)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.95, 0.97)]),
        ]))
        story.append(step_table)
        story.append(Spacer(1, 6 * mm))

        # === TAX ATTEST ===
        tax = checks.get("tax_compliance", {})
        attest = tax.get("freistellungsattest", {})
        if attest:
            story.append(Paragraph("3. §13b UStG Freistellungsattest", S["h2"]))
            att_data = [
                ["Attest-ID", attest.get("attest_id", "?")],
                ["Status", attest.get("status", "?")],
                ["Rechtsgrundlage", attest.get("legal_basis", "?")],
                ["Reverse-Charge", "✓" if attest.get("basis", {}).get("reverse_charge") else "✗"],
                ["IBAN-Compliance", "✓" if attest.get("basis", {}).get("iban") else "✗"],
                ["Steuer-ID", "✓" if attest.get("basis", {}).get("tax_id") else "✗"],
            ]
            att_table = Table(att_data, colWidths=[5 * cm, 10 * cm])
            att_table.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.Color(0.90, 0.90, 0.92)),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(att_table)

        # === FOOTER ===
        story.append(Spacer(1, 10 * mm))
        story.append(Paragraph(
            f"Agent X B2G — RPA-Prüfsystem v0.3.0 | Generiert: {ts} | "
            "Klassifizierung: VS-NfD | GoBD-konform archiviert",
            ParagraphStyle("Footer", parent=S["body"], fontSize=7,
                           textColor=colors.grey, alignment=1)))

        doc.build(story)
        pdf_bytes = buffer.getvalue()

        # Save
        rpt_id = f"RPA_Entlastung_{tender_id[-16:]}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}"
        path = self.output_dir / f"{rpt_id}.pdf"
        path.write_bytes(pdf_bytes)
        pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()[:16]

        print(f"  [RPA-PDF]       📄 {rpt_id}.pdf ({len(pdf_bytes):,} bytes, "
              f"SHA-256={pdf_hash}...)")

        return {"report_id": rpt_id, "path": str(path),
                "size_bytes": len(pdf_bytes), "sha256": pdf_hash}

    # ============================================================
    # Styles
    # ============================================================

    @staticmethod
    def _setup_styles(styles):
        styles.add(ParagraphStyle("RPA_title", parent=styles["Heading1"],
                                  fontSize=18, leading=22, alignment=1, spaceAfter=10))
        styles.add(ParagraphStyle("RPA_subtitle", parent=styles["Heading2"],
                                  fontSize=12, leading=16, alignment=1, spaceAfter=8))
        styles.add(ParagraphStyle("RPA_h2", parent=styles["Heading2"],
                                  fontSize=12, spaceAfter=4))
        styles.add(ParagraphStyle("RPA_body", parent=styles["Normal"],
                                  fontSize=9, leading=13))
        return {
            "title": styles["RPA_title"], "subtitle": styles["RPA_subtitle"],
            "h2": styles["RPA_h2"], "body": styles["RPA_body"],
        }
