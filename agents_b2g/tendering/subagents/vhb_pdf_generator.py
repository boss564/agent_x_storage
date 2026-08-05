"""
Subagent: VHB-221/222 PDF Generator.

Erzeugt VOB/A-konforme Angebots-PDFs mit Preisaufgliederung nach
VHB-Formblatt 221 (Erfassungsformblatt Preise) und 222 (Fortsetzung).

Integriert in den TenderComposerAgent: nach der X84-Serialisierung
wird automatisch ein unterschriftsreifes PDF-Angebot generiert.

Usage:
    generator = VHBPDFGenerator()
    pdf_path = generator.generate_221(state, output_dir=Path("output"))
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak,
)


# Mapping: BKI material groups → VHB cost categories
BKI_TO_VHB = {
    "Betonbau": ("Material", 0.30, "Lohn", 0.55, "Geräte", 0.15),
    "Stahlbau": ("Material", 0.50, "Lohn", 0.35, "Geräte", 0.15),
    "Rohrleitungsbau": ("Material", 0.40, "Lohn", 0.45, "Geräte", 0.15),
    "HLK": ("Material", 0.45, "Lohn", 0.40, "Geräte", 0.15),
    "Elektrotechnik": ("Material", 0.35, "Lohn", 0.50, "Geräte", 0.15),
    "Tiefbau": ("Geräte", 0.40, "Lohn", 0.40, "Material", 0.20),
    "Ausbau": ("Lohn", 0.55, "Material", 0.35, "Geräte", 0.10),
    "Allgemein": ("Nachunternehmer", 0.50, "Lohn", 0.30, "Material", 0.20),
}


class VHBPDFGenerator:
    """Generates VHB-221 (price breakdown) and VHB-222 (position detail) PDFs."""

    def __init__(self, output_dir: Path = Path("archive_b2g/offers")):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._styles = getSampleStyleSheet()
        self._setup_styles()

    def _setup_styles(self) -> None:
        """Custom styles for German construction forms."""
        self._styles.add(ParagraphStyle(
            "VHB_Title", parent=self._styles["Heading1"],
            fontSize=14, spaceAfter=4 * mm, alignment=1,
        ))
        self._styles.add(ParagraphStyle(
            "VHB_Subtitle", parent=self._styles["Heading2"],
            fontSize=10, spaceAfter=3 * mm, alignment=1,
        ))
        self._styles.add(ParagraphStyle(
            "VHB_FieldLabel", parent=self._styles["Normal"],
            fontSize=8, fontName="Helvetica-Bold",
        ))
        self._styles.add(ParagraphStyle(
            "VHB_FieldValue", parent=self._styles["Normal"],
            fontSize=8, fontName="Helvetica",
        ))
        self._styles.add(ParagraphStyle(
            "VHB_TableCell", parent=self._styles["Normal"],
            fontSize=7, leading=9,
        ))
        self._styles.add(ParagraphStyle(
            "VHB_TableHeader", parent=self._styles["Normal"],
            fontSize=7, fontName="Helvetica-Bold", leading=9, alignment=1,
        ))
        self._styles.add(ParagraphStyle(
            "VHB_Footer", parent=self._styles["Normal"],
            fontSize=7, alignment=1, textColor=colors.grey,
        ))

    # ============================================================
    # VHB 221: Erfassungsformblatt Preise (Cover Sheet)
    # ============================================================

    def generate_221(self, state: Any, bidder_name: str = "Müller Tiefbau GmbH & Co. KG",
                     bidder_address: str = "Baustraße 1, 30167 Hannover") -> Path:
        """
        Generate VHB Form 221 — price breakdown cover sheet.

        Shows: total bid price, breakdown by VHB cost category
        (Lohn/Material/Geräte/Nachunternehmer), PoPW bonus.
        """
        tender_id = getattr(state, "tender_id", "UNKNOWN")
        filename = f"VHB_221_{tender_id}.pdf"
        path = self.output_dir / filename

        doc = SimpleDocTemplate(
            str(path), pagesize=A4,
            leftMargin=20 * mm, rightMargin=20 * mm,
            topMargin=15 * mm, bottomMargin=20 * mm,
        )

        offer = getattr(state, "calculated_offer", {})
        positions = offer.get("positions", [])
        final_price = offer.get("final_price_eur", 0)
        popw_bonus = getattr(state, "popw_bonus_pct", 0.0)
        chi_score = getattr(state, "chi_score", 0)

        story = []

        # === Header ===
        story.append(Paragraph("VHB 221 — Erfassungsformblatt Preise", self._styles["VHB_Title"]))
        story.append(Paragraph(
            "VOB/A-konforme Angebotsabgabe gemäß Vergabehandbuch Bund",
            self._styles["VHB_Subtitle"],
        ))

        # Bidder info box
        info_data = [
            [Paragraph("<b>Bieter</b>", self._styles["VHB_FieldLabel"]),
             Paragraph(f"{bidder_name}<br/>{bidder_address}", self._styles["VHB_FieldValue"])],
            [Paragraph("<b>Projekt</b>", self._styles["VHB_FieldLabel"]),
             Paragraph(f"{tender_id}<br/>{getattr(state, 'tender_id', '')}", self._styles["VHB_FieldValue"])],
            [Paragraph("<b>Datum</b>", self._styles["VHB_FieldLabel"]),
             Paragraph(datetime.now(timezone.utc).strftime("%d.%m.%Y"), self._styles["VHB_FieldValue"])],
            [Paragraph("<b>Angebotssumme (netto)</b>", self._styles["VHB_FieldLabel"]),
             Paragraph(f"<b>{final_price:,.2f} €</b>", self._styles["VHB_FieldValue"])],
        ]
        info_table = Table(info_data, colWidths=[50 * mm, 110 * mm])
        info_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BACKGROUND", (0, 0), (0, -1), colors.Color(0.92, 0.92, 0.92)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 8 * mm))

        # === Price Breakdown by VHB Category ===
        story.append(Paragraph("Preisaufgliederung nach Kostengruppen", self._styles["VHB_Subtitle"]))

        # Aggregate by VHB category
        vhb_totals = self._compute_vhb_breakdown(positions)

        breakdown_header = ["Kostengruppe", "Betrag (€)", "Anteil (%)"]
        breakdown_rows = [breakdown_header]
        for category in ("Lohn", "Material", "Geräte", "Nachunternehmer"):
            amount = vhb_totals.get(category, 0)
            pct = round(amount / max(1, final_price) * 100, 1)
            breakdown_rows.append([category, f"{amount:,.2f}", f"{pct}%"])

        # CHI/PoPW info
        breakdown_rows.append([
            f"PoPW-Bonus (+{popw_bonus}%)",
            f"{final_price * popw_bonus / 100:,.2f}",
            f"{popw_bonus}%",
        ])
        breakdown_rows.append([
            "Gesamtsumme",
            f"<b>{final_price:,.2f}</b>",
            "100%",
        ])

        breakdown_table = Table(breakdown_rows, colWidths=[60 * mm, 50 * mm, 40 * mm])
        breakdown_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.25, 0.35, 0.55)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, -1), (-1, -1), colors.Color(0.90, 0.90, 0.92)),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(breakdown_table)
        story.append(Spacer(1, 5 * mm))

        # CHI / risk info
        risk_text = (
            f"Risikoklasse: CHI {chi_score} | "
            f"Preisbasis: BKI-Standardkostentabellen 2024 | "
            f"Ausführungsort: Kläranlage Nord, Hannover"
        )
        story.append(Paragraph(risk_text, self._styles["VHB_Footer"]))
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(
            f"Preise gelten bis 31.12.2026 (VOB/A §10). "
            f"Nebenangebote sind nur zulässig, wenn in der X84-Datei gekennzeichnet.",
            self._styles["VHB_Footer"],
        ))

        story.append(PageBreak())

        # === VHB 222: Per-Position Detail (continuation) ===
        story.append(Paragraph("VHB 222 — Preisaufgliederung (Fortsetzung)", self._styles["VHB_Title"]))
        story.append(Paragraph(
            f"Projekt: {tender_id} | Bieter: {bidder_name}",
            self._styles["VHB_Subtitle"],
        ))
        story.append(Spacer(1, 5 * mm))

        pos_header = ["Pos.-Nr.", "Beschreibung", "Menge", "EH", "EP (€)", "GP (€)", "Kostengruppe"]
        pos_rows = [pos_header]
        for pos in positions:
            pid = pos.get("position_id", "")
            desc = (pos.get("description", ""))[:50]
            qty = pos.get("quantity", 1)
            unit = pos.get("unit", "Stk")
            up = pos.get("unit_price_eur", 0)
            total = pos.get("total_eur", up * qty)
            mg = pos.get("material_group", "Allgemein")
            vhb_cat = self._vhb_category(mg)
            pos_rows.append([
                Paragraph(pid, self._styles["VHB_TableCell"]),
                Paragraph(desc, self._styles["VHB_TableCell"]),
                f"{qty:,.1f}",
                unit,
                f"{up:,.2f}",
                f"{total:,.2f}",
                vhb_cat,
            ])

        pos_table = Table(pos_rows, colWidths=[16 * mm, 60 * mm, 14 * mm, 10 * mm, 22 * mm, 22 * mm, 22 * mm])
        pos_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.25, 0.35, 0.55)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (2, 0), (5, -1), "RIGHT"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.95, 0.97)]),
        ]))
        story.append(pos_table)

        # Footer
        story.append(Spacer(1, 8 * mm))
        story.append(Paragraph(
            "Dieses Angebot wurde automatisiert durch Agent X B2G generiert. "
            "Preise basieren auf BKI-Standardkostentabellen. "
            f"Erstellt am {datetime.now(timezone.utc).strftime('%d.%m.%Y')} "
            f"um {datetime.now(timezone.utc).strftime('%H:%M')} UTC.",
            self._styles["VHB_Footer"],
        ))

        doc.build(story)
        print(f"  [VHB-Generator] 📋 {filename} ({len(positions)} Positionen, "
              f"{final_price:,.2f} €, CHI={chi_score})")
        return path

    # ============================================================
    # Helpers
    # ============================================================

    def _compute_vhb_breakdown(self, positions: list[dict]) -> dict[str, float]:
        """Aggregate position totals into VHB cost categories."""
        totals: dict[str, float] = {}
        for pos in positions:
            mg = pos.get("material_group", "Allgemein")
            total = pos.get("total_eur", pos.get("unit_price_eur", 0) * pos.get("quantity", 1))
            mapping = BKI_TO_VHB.get(mg, BKI_TO_VHB["Allgemein"])

            for i in range(0, len(mapping), 2):
                cat = mapping[i]
                pct = mapping[i + 1]
                totals[cat] = totals.get(cat, 0) + total * pct

        return {k: round(v, 2) for k, v in totals.items()}

    @staticmethod
    def _vhb_category(material_group: str) -> str:
        """Return primary VHB cost category for a material group."""
        mapping = BKI_TO_VHB.get(material_group, BKI_TO_VHB["Allgemein"])
        return mapping[0]  # Primary category
