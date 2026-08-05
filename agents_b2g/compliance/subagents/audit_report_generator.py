"""
Subagent: AuditReportGenerator — Final Vergabekammer Report PDF.

Bundles all forensic sub-agent results into a single, court-ready PDF/A
with evidence package, verdict, and recommendations.

Usage:
    generator = AuditReportGenerator()
    pdf_bytes = generator.generate_report(tender_id, results, ruge_details)
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

logger = logging.getLogger("AuditReportGenerator")


class AuditReportGenerator:
    """Generates the final Vergabekammer investigation report as PDF/A."""

    def __init__(self, output_dir: Path = Path("archive_b2g/reports")):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_report(self, tender_id: str,
                        results: dict,
                        ruge_details: dict | None = None) -> dict:
        """Generate complete Vergabekammer report PDF."""

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                leftMargin=20 * mm, rightMargin=20 * mm,
                                topMargin=15 * mm, bottomMargin=20 * mm)

        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle("VK_Title", parent=styles["Heading1"],
                                  fontSize=16, spaceAfter=4 * mm, alignment=1))
        styles.add(ParagraphStyle("VK_H2", parent=styles["Heading2"],
                                  fontSize=12, spaceAfter=2 * mm))
        styles.add(ParagraphStyle("VK_H3", parent=styles["Heading3"],
                                  fontSize=10, spaceAfter=2 * mm))
        styles.add(ParagraphStyle("VK_Body", parent=styles["Normal"],
                                  fontSize=9, leading=12))
        styles.add(ParagraphStyle("VK_Verdict", parent=styles["Normal"],
                                  fontSize=11, fontName="Helvetica-Bold",
                                  textColor=colors.Color(0.6, 0, 0)))

        story = []

        # === Cover ===
        story.append(Paragraph("Vergabekammer — Nachprüfungsbericht", styles["VK_Title"]))
        story.append(Paragraph(
            f"Gemäß §§ 155–184 GWB — Aktenzeichen: "
            f"{ruge_details.get('aktenzeichen', 'N/A') if ruge_details else 'N/A'}",
            styles["VK_Body"]))
        story.append(Spacer(1, 6 * mm))

        # === Rüge details ===
        if ruge_details:
            story.append(Paragraph("Rügedetails", styles["VK_H2"]))
            ruge_rows = [
                ["Tender-ID", tender_id],
                ["Aktenzeichen", ruge_details.get("aktenzeichen", "N/A")],
                ["Eingangsdatum", ruge_details.get("eingangsdatum", "N/A")],
                ["Prüfgegenstand", ruge_details.get("pruefgegenstand", "N/A")],
                ["Antragsteller", ruge_details.get("antragsteller", "N/A")],
            ]
            ruge_table = Table(ruge_rows, colWidths=[45 * mm, 120 * mm])
            ruge_table.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.Color(0.90, 0.90, 0.92)),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(ruge_table)
            story.append(Spacer(1, 5 * mm))

        # === Overall Verdict ===
        verdict = results.get("overall_verdict", {})
        level = verdict.get("verdict_level", "N/A")
        level_colors = {"GREEN": colors.green, "YELLOW": colors.Color(0.8, 0.6, 0),
                        "ORANGE": colors.orange, "RED": colors.Color(0.8, 0, 0)}
        styles["VK_Verdict"].textColor = level_colors.get(level, colors.black)

        story.append(Paragraph("Gesamturteil", styles["VK_H2"]))
        story.append(Paragraph(f"Status: {level}", styles["VK_Verdict"]))
        story.append(Paragraph(verdict.get("verdict_text", ""), styles["VK_Body"]))

        if verdict.get("findings"):
            story.append(Paragraph("Wesentliche Feststellungen:", styles["VK_H3"]))
            for f in verdict["findings"]:
                story.append(Paragraph(f"• {f}", styles["VK_Body"]))

        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(
            f"Empfehlung: {verdict.get('recommendation', 'N/A')}",
            styles["VK_Verdict"]))
        story.append(Spacer(1, 6 * mm))

        # === Sub-agent summaries ===
        story.append(Paragraph("Prüfungsdetails", styles["VK_H2"]))

        # VOB/A
        vob = results.get("voba_check", {})
        story.append(Paragraph(
            f"VOB/A-Formalprüfung: {vob.get('status', 'N/A')} "
            f"({vob.get('summary', {}).get('compliant', 0)}/"
            f"{vob.get('summary', {}).get('total', 0)} konform)",
            styles["VK_Body"]))

        # Cartel
        cartel = results.get("cartel_check", results.get("cartel_analysis", {}))
        story.append(Paragraph(
            f"Kartellprüfung: Score={cartel.get('collusion_score', 0):.0f}% "
            f"— {cartel.get('verdict', 'N/A')}",
            styles["VK_Body"]))

        # Price
        price = results.get("price_check", results.get("price_plausibility", {}))
        story.append(Paragraph(
            f"Preisplausibilität: Score={price.get('anomaly_score', 0):.0f}% "
            f"— {price.get('verdict', 'N/A')}",
            styles["VK_Body"]))

        # PoPW
        for audit in results.get("popw_audits", results.get("popw_bonus_audit", {}).get("audit_result", [{}]) if isinstance(results.get("popw_bonus_audit"), dict) else []):
            # Handle both wrapped and direct formats
            pass
        popw = results.get("popw_bonus_audit", {})
        if isinstance(popw, dict) and "status" in popw:
            story.append(Paragraph(
                f"PoPW-Bonus-Audit: {popw.get('status', 'N/A')} "
                f"(Δ={popw.get('bonus_deviation_percent', 0)}%)",
                styles["VK_Body"]))

        # QES
        qes = results.get("qes_audit", {})
        if isinstance(qes, dict) and "status" in qes:
            story.append(Paragraph(
                f"QES-Forensik: {qes.get('status', 'N/A')} "
                f"(Cert={'✓' if qes.get('certificate_valid') else '✗'}, "
                f"Sig={'✓' if qes.get('signature_valid') else '✗'})",
                styles["VK_Body"]))

        # Bidder comparison
        comp = results.get("comparison", {})
        if comp.get("bidders"):
            story.append(PageBreak())
            story.append(Paragraph("Bieter-Vergleichsmatrix", styles["VK_H2"]))
            comp_rows = [["Bieter", "Preis (€)", "Bonus (%)", "Rang"]]
            for i, b in enumerate(sorted(comp["bidders"], key=lambda x: x["price_eur"])):
                comp_rows.append([
                    b["bidder_id"], f"{b['price_eur']:,.2f}",
                    f"{b['claimed_bonus_pct']:.1f}", str(i + 1),
                ])
            comp_table = Table(comp_rows, colWidths=[45 * mm, 45 * mm, 35 * mm, 25 * mm])
            comp_table.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.25, 0.35, 0.55)),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.Color(0.95, 0.95, 0.97)]),
            ]))
            story.append(comp_table)

        # === Evidence package ===
        evidence = results.get("evidence_package", {})
        if evidence:
            story.append(Spacer(1, 6 * mm))
            story.append(Paragraph("Beweissicherung", styles["VK_H2"]))
            story.append(Paragraph(
                f"Package-ID: {evidence.get('package_id', 'N/A')}", styles["VK_Body"]))
            story.append(Paragraph(
                f"Evidence-Hash: {evidence.get('evidence_hash', 'N/A')[:50]}...",
                styles["VK_Body"]))
            story.append(Paragraph(
                f"Status: {evidence.get('status', 'N/A')} | "
                f"Timestamp: {evidence.get('timestamp', 'N/A')[:19]}",
                styles["VK_Body"]))

        # === Footer ===
        story.append(Spacer(1, 10 * mm))
        story.append(Paragraph(
            f"Agent X B2G — Vergabekammer-Forensik v0.3.0 | "
            f"Generiert: {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')} | "
            f"Klassifizierung: VS-NfD",
            ParagraphStyle("Footer", parent=styles["VK_Body"],
                           fontSize=7, textColor=colors.grey, alignment=1)))

        doc.build(story)
        pdf_bytes = buffer.getvalue()

        # Save
        report_id = f"VK-{tender_id[-16:]}-{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}"
        path = self.output_dir / f"{report_id}.pdf"
        path.write_bytes(pdf_bytes)
        pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()

        print(f"  [AuditReport]   📄 {report_id} ({len(pdf_bytes):,} bytes, "
              f"SHA-256={pdf_hash[:16]}...)")

        return {
            "report_id": report_id,
            "path": str(path),
            "size_bytes": len(pdf_bytes),
            "sha256": pdf_hash,
            "status": "GENERATED",
        }
