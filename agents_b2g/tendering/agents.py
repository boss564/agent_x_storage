"""
Agent X B2G Tendering Engine — 9 Agents with Subagents.

Async pipeline for public procurement: from TED monitoring to bid submission.
Each agent has dedicated subagents (internal async methods) for heavy lifting.

Architecture:
  TenderMonitor → TenderParser → EligibilityChecker → CHIRiskAnalyzer →
  PoPWIndexer → OfferCalculator → TenderComposer → DeadlineManager →
  BidSubmittal (→ MultiChainAnchor)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


# ============================================================
# Shared Types
# ============================================================


class TenderPhase(str, Enum):
    MONITORED = "monitored"
    PARSED = "parsed"
    ELIGIBILITY_CHECKED = "eligibility_checked"
    RISK_ANALYZED = "risk_analyzed"
    POPW_INDEXED = "popw_indexed"
    CALCULATED = "calculated"
    COMPOSED = "composed"
    SUBMITTED = "submitted"
    REJECTED = "rejected"


@dataclass
class TenderState:
    """Complete state of a tender through the pipeline."""
    tender_id: str
    phase: TenderPhase = TenderPhase.MONITORED
    raw_gaeb: str = ""
    lv_positions: list[dict] = field(default_factory=list)
    eligibility: dict = field(default_factory=dict)
    chi_score: float = 100.0
    chi_breakdown: dict = field(default_factory=dict)
    popw_bonus_pct: float = 0.0
    popw_certificates: list[dict] = field(default_factory=list)
    calculated_offer: dict = field(default_factory=dict)
    gaeb_output: str = ""
    deadline: datetime | None = None
    submission_tx: str = ""
    errors: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ============================================================
# Agent 1: TenderMonitorAgent — Scanner
# ============================================================


class TenderMonitorAgent:
    """
    Monitors e-procurement platforms 24/7 for new tenders matching
    predefined CPV codes and keywords. Subagents handle RSS, TED XML,
    and keyword filtering.
    """

    CPV_CODES = ["45000000", "45100000", "45200000", "45300000"]  # Bauarbeiten
    KEYWORDS = ["Kläranlage", "Tiefbau", "Brücke", "Kanal", "Rohrleitung",
                "Betonbau", "Straßenbau", "Hochbau"]

    def __init__(self):
        self._monitored: list[dict] = []

    async def scan_ted(self, mock_data: dict | None = None) -> list[dict]:
        """Subagent: TED XML Downloader — scans for new tenders."""
        if mock_data:
            return [mock_data]
        return []  # Production: HTTP fetch from TED API

    async def filter_by_keywords(self, tenders: list[dict]) -> list[dict]:
        """Subagent: KeywordMatcher — filters by CPV + description."""
        matches = []
        for t in tenders:
            desc = t.get("description", "") + " " + " ".join(t.get("cpv_codes", []))
            if any(kw.lower() in desc.lower() for kw in self.KEYWORDS):
                matches.append(t)
        return matches

    async def monitor(self, mock_tender: dict | None = None) -> list[TenderState]:
        """Main entry: scan platforms and return matching tenders."""
        tenders = await self.scan_ted(mock_tender)
        matches = await self.filter_by_keywords(tenders)

        states = []
        for t in matches:
            state = TenderState(
                tender_id=t.get("tender_id", f"TED-{hash(t.get('description',''))%100000:05d}"),
                phase=TenderPhase.MONITORED,
                raw_gaeb=t.get("gaeb_xml", ""),
                deadline=self._parse_deadline(t.get("deadline", "")),
            )
            self._monitored.append({"tender_id": state.tender_id, "found_at": datetime.now(timezone.utc).isoformat()})
            states.append(state)
            print(f"  [TenderMonitor] 🔍 Neue Ausschreibung: {state.tender_id} — "
                  f"{t.get('description', 'N/A')[:70]}...")

        return states

    def _parse_deadline(self, s: str) -> datetime | None:
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return datetime.now(timezone.utc) + timedelta(days=28)  # Default: 4 weeks


# ============================================================
# Agent 2: TenderParserAgent — GAEB Dekonstrukteur
# ============================================================


class TenderParserAgent:
    """
    Parses GAEB-X83/X84 XML into structured JSON Bill of Quantities.
    Subagents: GAEB XML Validator, PDF Annex Scraper, LV Structure Mapper.
    """

    async def validate_gaeb(self, xml_string: str) -> tuple[bool, list[str]]:
        """Subagent: GAEBXMLValidator — schema check."""
        if not xml_string:
            return True, []  # No XML = test mode
        errors = []
        if "<GAEB" not in xml_string and "<gaeb" not in xml_string:
            errors.append("Missing GAEB root element")
        return len(errors) == 0, errors

    async def map_lv_structure(self, positions: list[dict]) -> list[dict]:
        """Subagent: LVStructureMapper — builds position tree with hierarchy."""
        enriched = []
        for i, pos in enumerate(positions):
            enriched.append({
                "position_id": pos.get("position_id", f"LV-{i+1:04d}"),
                "description": pos.get("description", ""),
                "quantity": float(pos.get("quantity", 1)),
                "unit": pos.get("unit", "Stk"),
                "material_group": pos.get("material_group", "Allgemein"),
                "parent_id": pos.get("parent_id", None),
                "is_optional": pos.get("is_optional", False),
                "is_side_offer": pos.get("is_side_offer", False),
            })
        return enriched

    async def scrape_annex_pdfs(self, pdf_urls: list[str]) -> list[dict]:
        """Subagent: PDFAnnexScraper — extracts hidden positions from plans."""
        return []  # Production: PDF text extraction

    async def parse(self, state: TenderState) -> TenderState:
        """Main entry: parse GAEB into structured LV."""
        xml = state.raw_gaeb
        valid, errors = await self.validate_gaeb(xml)
        if not valid:
            state.errors.extend(errors)
            return state

        # In test mode, positions come from the mock data
        # In production, positions come from GAEB XML parsing
        state.lv_positions = await self.map_lv_structure(state.lv_positions)

        # Check for hidden positions in annex PDFs
        hidden = await self.scrape_annex_pdfs([])
        state.lv_positions.extend(hidden)

        state.phase = TenderPhase.PARSED
        print(f"  [TenderParser]  📄 {len(state.lv_positions)} Positionen extrahiert"
              + (f" (+{len(hidden)} aus Anhängen)" if hidden else ""))
        return state


# ============================================================
# Agent 3: EligibilityCheckerAgent — Formalprüfer
# ============================================================


class EligibilityCheckerAgent:
    """
    Checks whether the company meets the tender's minimum criteria.
    Subagents: ReferenceMatcher, ComplianceRuleEngine (VOB/A §6).
    """

    # Simulated company profile
    COMPANY_PROFILE = {
        "name": "Müller Tiefbau GmbH & Co. KG",
        "annual_revenue_3y_avg_eur": 8_500_000,
        "employees": 85,
        "references": [
            {"project": "Kläranlage Süd — BA3", "value_eur": 3_200_000, "year": 2024},
            {"project": "Regenrückhaltebecken Ost", "value_eur": 2_800_000, "year": 2023},
            {"project": "Kanalnetz Sanierung Nord", "value_eur": 5_100_000, "year": 2025},
        ],
    }

    async def check_references(self, required_value_eur: float) -> dict:
        """Subagent: ReferenceMatcher — checks if references meet threshold."""
        matching = [r for r in self.COMPANY_PROFILE["references"]
                    if r["value_eur"] >= required_value_eur * 0.7]
        return {
            "passed": len(matching) >= 1,
            "matching_count": len(matching),
            "best_reference": matching[0] if matching else None,
        }

    async def check_compliance(self, tender_value_eur: float) -> dict:
        """Subagent: ComplianceRuleEngine — VOB/A §6 checks."""
        profile = self.COMPANY_PROFILE
        issues = []

        # VOB/A §6a: Mindestumsatz (typisch: 1,5× Jahreswert)
        min_revenue = tender_value_eur * 1.5
        if profile["annual_revenue_3y_avg_eur"] < min_revenue:
            issues.append(f"Umsatz {profile['annual_revenue_3y_avg_eur']:,.0f}€ unter "
                          f"geforderten {min_revenue:,.0f}€")

        # VOB/A §6b: Mindestmitarbeiter
        if profile["employees"] < 15:
            issues.append(f"Nur {profile['employees']} Mitarbeiter")

        return {"passed": len(issues) == 0, "issues": issues}

    async def check(self, state: TenderState, tender_value_eur: float) -> TenderState:
        """Main entry: run all eligibility checks."""
        ref_result = await self.check_references(tender_value_eur)
        comp_result = await self.check_compliance(tender_value_eur)

        state.eligibility = {
            "references_ok": ref_result["passed"],
            "compliance_ok": comp_result["passed"],
            "overall_passed": ref_result["passed"] and comp_result["passed"],
            "reference_count": ref_result["matching_count"],
            "compliance_issues": comp_result["issues"],
        }

        if state.eligibility["overall_passed"]:
            state.phase = TenderPhase.ELIGIBILITY_CHECKED
            print(f"  [Eligibility]   ✅ Formalprüfung bestanden "
                  f"({ref_result['matching_count']} Referenzen)")
        else:
            state.phase = TenderPhase.REJECTED
            state.errors.append(f"Eignung nicht gegeben: {comp_result['issues']}")
            print(f"  [Eligibility]   ❌ Formalprüfung NICHT bestanden: {comp_result['issues']}")

        return state


# ============================================================
# Agent 4: CHIRiskAnalyzerAgent — Projekt-Risikoscope
# ============================================================


class CHIRiskAnalyzerAgent:
    """
    Computes the Construction Hazard Index (CHI) for the tender.
    Subagents: MaterialPriceOracle, LogisticHeatmap, WeatherHistoricalDB.
    """

    async def fetch_material_prices(self, positions: list[dict]) -> dict:
        """Subagent: MaterialPriceOracle — current construction price index."""
        # Simplified: use static reference prices
        ref_prices = {
            "Betonbau": 185.0, "Stahlbau": 3200.0, "Rohrleitungsbau": 95.0,
            "HLK": 450.0, "Elektrotechnik": 280.0, "Tiefbau": 65.0,
            "Ausbau": 120.0, "Allgemein": 200.0,
        }
        prices = {}
        for pos in positions:
            mg = pos.get("material_group", "Allgemein")
            prices[pos.get("position_id", "?")] = ref_prices.get(mg, 200.0)
        return prices

    async def assess_logistics(self, h3_region: str) -> dict:
        """Subagent: LogisticHeatmap — transportation and access scoring."""
        # Simplified: urban = good, rural = penalty
        scores = {"881f8d7a49fffff": 0.95, "881f8d7a4bfffff": 0.90,
                  "881f8d7a4d7ffff": 0.82, "881f8d7a4e3ffff": 0.70}
        score = scores.get(h3_region, 0.85)
        return {"accessibility_score": score, "estimated_extra_transport_pct": round((1-score)*100, 1)}

    async def seasonal_risk(self, deadline: datetime | None) -> dict:
        """Subagent: WeatherHistoricalDB — weather risk by season."""
        if deadline is None:
            return {"season": "unknown", "weather_risk": "medium", "risk_penalty_pct": 5.0}
        month = deadline.month
        if month in (12, 1, 2):
            return {"season": "winter", "weather_risk": "high", "risk_penalty_pct": 12.0}
        elif month in (6, 7, 8):
            return {"season": "summer", "weather_risk": "low", "risk_penalty_pct": 2.0}
        else:
            return {"season": "transition", "weather_risk": "medium", "risk_penalty_pct": 5.0}

    async def analyze(self, state: TenderState, h3_region: str = "") -> TenderState:
        """Main entry: compute CHI and risk breakdown."""
        positions = state.lv_positions
        material_prices = await self.fetch_material_prices(positions)
        logistics = await self.assess_logistics(h3_region)
        weather = await self.seasonal_risk(state.deadline)

        # Base CHI from position count and material diversity
        material_groups = len(set(p.get("material_group", "Allgemein") for p in positions))
        base_chi = max(60, 100 - len(positions) * 2)  # More positions = more complex

        # Penalties
        logistics_penalty = (1 - logistics["accessibility_score"]) * 20
        weather_penalty = weather["risk_penalty_pct"] * 0.5
        chi = max(0, min(100, base_chi - logistics_penalty - weather_penalty))

        state.chi_score = round(chi, 1)
        state.chi_breakdown = {
            "base_chi": base_chi,
            "position_count": len(positions),
            "material_groups": material_groups,
            "logistics_penalty": round(logistics_penalty, 1),
            "weather_penalty": round(weather_penalty, 1),
            "material_price_index": round(sum(material_prices.values()) / max(len(material_prices), 1), 1),
            "logistics": logistics,
            "weather": weather,
        }
        state.phase = TenderPhase.RISK_ANALYZED
        print(f"  [CHI-Risk]      ⚠ CHI={chi:.0f} (Basis={base_chi}, "
              f"Logistik={logistics_penalty:.0f}, Wetter={weather_penalty:.0f})")
        return state


# ============================================================
# Agent 5: PoPWIndexerAgent — Bonussammler
# ============================================================


class PoPWIndexerAgent:
    """
    Searches the blockchain for completed PoPW projects to generate bonus certificates.
    Subagents: ChainQuerySubagent, QualityScoreAggregator, ZKPGenerator.
    """

    async def query_chain(self, company_id: str) -> list[dict]:
        """Subagent: ChainQuerySubagent — reads completed escrow projects."""
        # Simulated — in production queries MultiChainAnchorAgent
        return [
            {"project": "Kanalisation Abschnitt 4", "completed": "2025-11-15",
             "on_time": True, "quality_score": 0.98},
            {"project": "Brückenpfeiler B7", "completed": "2025-08-02",
             "on_time": True, "quality_score": 0.95},
            {"project": "Straßenbau L412", "completed": "2025-04-20",
             "on_time": False, "quality_score": 0.88},
        ]

    async def aggregate_scores(self, projects: list[dict]) -> dict:
        """Subagent: QualityScoreAggregator — computes on-time % and avg quality."""
        on_time = sum(1 for p in projects if p["on_time"])
        avg_quality = sum(p["quality_score"] for p in projects) / max(len(projects), 1)
        return {
            "total_projects": len(projects),
            "on_time_count": on_time,
            "on_time_pct": round(on_time / max(len(projects), 1) * 100, 1),
            "avg_quality": round(avg_quality, 3),
            "bonus_eligible": on_time >= 2 and avg_quality >= 0.85,
        }

    async def generate_zkp(self, scores: dict) -> dict:
        """Subagent: ZKPGenerator — creates zero-knowledge proof for the authority."""
        # Simplified: hash of the scores as a "proof"
        proof_seed = json.dumps(scores, sort_keys=True)
        return {
            "zkp_hash": hashlib.sha256(proof_seed.encode()).hexdigest()[:40],
            "proves": "Termintreue ≥ 66% UND Durchschnittsqualität ≥ 0.85",
            "reveals_nothing": "Keine Einzelprojektdaten offengelegt",
        }

    async def index(self, state: TenderState, company_id: str = "mueller_tiefbau") -> TenderState:
        """Main entry: compute PoPW bonus from on-chain history."""
        projects = await self.query_chain(company_id)
        scores = await self.aggregate_scores(projects)

        if scores["bonus_eligible"]:
            state.popw_bonus_pct = round(
                1.0 + scores["on_time_pct"] / 100 * 0.05 + scores["avg_quality"] * 2.0, 1
            )
        else:
            state.popw_bonus_pct = 0.0

        zkp = await self.generate_zkp(scores)
        state.popw_certificates = [zkp]

        state.phase = TenderPhase.POPW_INDEXED
        print(f"  [PoPW-Index]    🏆 {scores['total_projects']} Projekte, "
              f"Termintreue={scores['on_time_pct']}%, Bonus=+{state.popw_bonus_pct}%"
              + (f" (ZKP: {zkp['zkp_hash'][:12]}...)" if scores["bonus_eligible"] else ""))
        return state


# ============================================================
# Agent 6: OfferCalculatorAgent — Kalkulator
# ============================================================


class OfferCalculatorAgent:
    """
    Calculates the final bid price per LV position using CHI data and PoPW bonuses.
    Subagents: UnitPriceEstimator, WasteOptimizer, SurplusMarginEngine.
    """

    async def estimate_unit_prices(self, positions: list[dict]) -> dict:
        """Subagent: UnitPriceEstimator — BKI standard prices per material group."""
        bki_prices = {
            "Betonbau": 185.0, "Stahlbau": 3200.0, "Rohrleitungsbau": 95.0,
            "HLK": 450.0, "Elektrotechnik": 280.0, "Tiefbau": 65.0,
            "Ausbau": 120.0, "Allgemein": 200.0,
        }
        return {p["position_id"]: bki_prices.get(p.get("material_group", "Allgemein"), 200.0)
                for p in positions}

    async def optimize_waste(self, positions: list[dict], chi: float) -> dict:
        """Subagent: WasteOptimizer — reduces material waste using historical data."""
        # Higher CHI = more efficient (experienced contractor)
        base_waste_pct = 8.0
        optimized_waste = base_waste_pct * (1.0 - (chi - 50) / 100)
        return {"base_waste_pct": base_waste_pct, "optimized_waste_pct": round(optimized_waste, 1),
                "savings_pct": round(base_waste_pct - optimized_waste, 1)}

    async def compute_margin(self, subtotal: float, risk_state: str, popw_bonus: float) -> dict:
        """Subagent: SurplusMarginEngine — profit margin based on risk."""
        base_margin = 12.0
        risk_adj = {"healthy": 1.0, "caution": 1.3, "stressed": 1.6, "critical": 2.0}
        margin = base_margin * risk_adj.get(risk_state, 1.0) + popw_bonus
        return {"base_margin_pct": base_margin, "risk_adjusted_margin_pct": round(margin, 1),
                "popw_reduction": popw_bonus}

    async def calculate(self, state: TenderState) -> TenderState:
        """Main entry: compute per-position and total bid price."""
        positions = state.lv_positions
        unit_prices = await self.estimate_unit_prices(positions)
        waste = await self.optimize_waste(positions, state.chi_score)

        # Compute per-position totals
        position_totals = []
        total_material = 0.0
        for pos in positions:
            pid = pos["position_id"]
            up = unit_prices.get(pid, 200.0)
            qty = pos["quantity"]
            material_cost = up * qty
            waste_cost = material_cost * waste["optimized_waste_pct"] / 100
            labor_cost = qty * 0.5 * 65.0  # Simplified: 0.5h per unit at 65€/h
            pos_total = material_cost + waste_cost + labor_cost
            position_totals.append({
                "position_id": pid, "unit_price_eur": round(up, 2),
                "quantity": qty, "material_eur": round(material_cost, 2),
                "waste_eur": round(waste_cost, 2), "labor_eur": round(labor_cost, 2),
                "total_eur": round(pos_total, 2),
            })
            total_material += pos_total

        # Apply margin
        risk_state = "healthy" if state.chi_score >= 80 else "caution" if state.chi_score >= 60 else "stressed"
        margin_info = await self.compute_margin(total_material, risk_state, state.popw_bonus_pct)
        margin_eur = total_material * margin_info["risk_adjusted_margin_pct"] / 100
        final_price = total_material + margin_eur

        state.calculated_offer = {
            "positions": position_totals,
            "subtotal_eur": round(total_material, 2),
            "waste_pct_used": waste["optimized_waste_pct"],
            "margin_pct": margin_info["risk_adjusted_margin_pct"],
            "margin_eur": round(margin_eur, 2),
            "final_price_eur": round(final_price, 2),
        }
        state.phase = TenderPhase.CALCULATED
        print(f"  [Calculator]    💰 Angebotspreis: {final_price:,.2f} € "
              f"(Marge={margin_info['risk_adjusted_margin_pct']}%, "
              f"Verschnitt={waste['optimized_waste_pct']}%)")
        return state


# ============================================================
# Agent 7: TenderComposerAgent — GAEB-X84 Export
# ============================================================


class TenderComposerAgent:
    """
    Converts calculated prices + formal documents back into GAEB-X84 format.
    Subagents: GAEBX84Serializer, DocgenSubagent, EESerializer.
    """

    async def serialize_to_x84(self, state: TenderState) -> str:
        """Subagent: GAEBX84Serializer — writes GAEB DA XML 3.3 X84 (Angebotsabgabe)."""
        positions_xml = ""
        for pos in state.calculated_offer.get("positions", []):
            unit_price = pos.get("unit_price_eur", 0)
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

        now = datetime.now(timezone.utc)
        gaeb_xml = (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<GAEB xmlns="http://www.gaeb.de/GAEB_DA_XML/DA84/3.3"\n'
            f'      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
            f'  <DP>84</DP>\n'
            f'  <Date>{now.strftime("%Y-%m-%d")}</Date>\n'
            f'  <Time>{now.strftime("%H:%M:%S")}</Time>\n'
            f'  <ProgSystem>Agent X B2G 0.2.0</ProgSystem>\n'
            f'  <Version>3.3</Version>\n'
            f'  <VersDate>2021-05</VersDate>\n'
            f'  <Award>\n'
            f'    <AwardID>{state.tender_id}</AwardID>\n'
            f'    <BoQ>\n'
            f'      <BoQBody>\n'
            f'{positions_xml}'
            f'      </BoQBody>\n'
            f'    </BoQ>\n'
            f'    <TotalAmount>{state.calculated_offer.get("final_price_eur", 0):.2f}</TotalAmount>\n'
            f'    <Currency>EUR</Currency>\n'
            f'  </Award>\n'
            f'</GAEB>\n'
        )
        return gaeb_xml

    async def generate_deckblatt(self, state: TenderState) -> str:
        """Subagent: DocgenSubagent — creates cover sheet with PoPW certificates."""
        return (
            f"ANGEBOT — {state.tender_id}\n"
            f"Datum: {datetime.now(timezone.utc).strftime('%d.%m.%Y')}\n"
            f"Bieter: Müller Tiefbau GmbH & Co. KG\n"
            f"PoPW-Bonus: +{state.popw_bonus_pct}%\n"
            f"ZKP-Nachweis: {state.popw_certificates[0]['zkp_hash'][:16] if state.popw_certificates else 'N/A'}...\n"
        )

    async def generate_vhb_pdf(self, state: TenderState) -> Path:
        """Subagent: VHBFormGenerator — creates VHB-221 + VHB-222 PDF."""
        from agents_b2g.tendering.subagents.vhb_pdf_generator import VHBPDFGenerator
        generator = VHBPDFGenerator()
        return generator.generate_221(state)

    async def compose(self, state: TenderState) -> TenderState:
        """Main entry: produce final GAEB-X84 + Deckblatt + VHB-221/222 PDF."""
        state.gaeb_output = await self.serialize_to_x84(state)
        deckblatt = await self.generate_deckblatt(state)
        vhb_pdf_path = await self.generate_vhb_pdf(state)
        state.phase = TenderPhase.COMPOSED
        print(f"  [Composer]      📨 GAEB-X84 ({len(state.gaeb_output)} Zeichen)"
              + (f" + Deckblatt" if deckblatt else "")
              + f" + VHB-PDF: {vhb_pdf_path.name}")
        return state


# ============================================================
# Agent 8: DeadlineManagerAgent — Fristenwächter
# ============================================================


class DeadlineManagerAgent:
    """
    Manages the countdown to bid submission. Orchestrates parallel work
    and escalates when deadlines approach.
    Subagents: CountdownTimer, TaskOrchestrator, EscalationMailer.
    """

    def __init__(self):
        self._timers: dict[str, dict] = {}

    async def start_countdown(self, tender_id: str, deadline: datetime | None) -> dict:
        """Subagent: CountdownTimer — starts countdown to submission."""
        if deadline is None:
            deadline = datetime.now(timezone.utc) + timedelta(days=28)
        remaining = deadline - datetime.now(timezone.utc)
        hours = max(0, remaining.total_seconds() / 3600)
        urgency = "critical" if hours < 24 else "high" if hours < 72 else "normal"
        timer = {"tender_id": tender_id, "deadline": deadline.isoformat(),
                 "remaining_hours": round(hours, 1), "urgency": urgency}
        self._timers[tender_id] = timer
        return timer

    async def check_escalation(self, timer: dict) -> str | None:
        """Subagent: EscalationMailer — warns when <2h remain."""
        if timer["remaining_hours"] < 2:
            return f"⚠ ESKALATION: Nur noch {timer['remaining_hours']:.1f}h für {timer['tender_id']}!"
        return None

    async def monitor_deadline(self, state: TenderState) -> TenderState:
        """Main entry: check deadline and escalate if needed."""
        timer = await self.start_countdown(state.tender_id, state.deadline)
        escalation = await self.check_escalation(timer)

        urgency_icon = {"normal": "✓", "high": "⚠", "critical": "⛔"}
        icon = urgency_icon.get(timer["urgency"], "?")
        print(f"  [Deadline]      {icon} Frist: {timer['remaining_hours']:.0f}h verbleibend "
              f"({timer['urgency'].upper()})")

        if escalation:
            state.errors.append(escalation)
            print(f"  [Deadline]      {escalation}")

        return state


# ============================================================
# Agent 9: BidSubmittalAgent — Absender & Notar
# ============================================================


class BidSubmittalAgent:
    """
    Submits the final bid to the e-procurement platform and notarizes
    the submission hash on-chain via MultiChainAnchorAgent.
    Subagents: PlatformAuthenticator, LargeFileUploader, ReceiptValidator.
    """

    async def authenticate(self, platform: str) -> str:
        """Subagent: PlatformAuthenticator — logs into e-procurement platform."""
        return f"session-{hash(platform) % 100000:05d}"

    async def upload(self, gaeb_xml: str, session_token: str) -> dict:
        """Subagent: LargeFileUploader — chunked upload of GAEB file."""
        # Simulated upload
        receipt = {
            "upload_id": f"UPL-{hash(gaeb_xml) % 1000000:06d}",
            "status": "received",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "file_size_bytes": len(gaeb_xml),
        }
        return receipt

    async def validate_receipt(self, receipt: dict) -> bool:
        """Subagent: ReceiptValidator — checks platform confirmation."""
        return receipt.get("status") == "received"

    async def submit(self, state: TenderState, platform: str = "dtloe") -> TenderState:
        """Main entry: upload bid and notarize on-chain."""
        if not state.gaeb_output:
            state.errors.append("Kein GAEB-X84 zum Einreichen")
            return state

        session = await self.authenticate(platform)
        receipt = await self.upload(state.gaeb_output, session)
        is_valid = await self.validate_receipt(receipt)

        if is_valid:
            submission_hash = hashlib.sha256(
                (state.gaeb_output + receipt["timestamp"]).encode()
            ).hexdigest()[:64]
            state.submission_tx = f"0x{submission_hash}"
            state.phase = TenderPhase.SUBMITTED
            print(f"  [BidSubmittal]  🔗 Angebot eingereicht! "
                  f"Tx=0x{submission_hash[:16]}... (Plattform: {platform})")
        else:
            state.errors.append(f"Upload fehlgeschlagen: {receipt}")

        return state


# ============================================================
# Pipeline Orchestrator — runs all 9 agents in sequence
# ============================================================


class TenderingPipeline:
    """
    Wires all 9 tendering agents into a sequential pipeline.

    Usage:
        pipeline = TenderingPipeline()
        result = await pipeline.run(mock_tender_data, h3_region="881f8d7a49fffff")
    """

    def __init__(self):
        self.monitor = TenderMonitorAgent()
        self.parser = TenderParserAgent()
        self.eligibility = EligibilityCheckerAgent()
        self.chi_risk = CHIRiskAnalyzerAgent()
        self.popw = PoPWIndexerAgent()
        self.calculator = OfferCalculatorAgent()
        self.composer = TenderComposerAgent()
        self.deadline = DeadlineManagerAgent()
        self.submittal = BidSubmittalAgent()

    async def run(
        self,
        mock_tender: dict,
        tender_value_eur: float = 0,
        h3_region: str = "",
    ) -> TenderState:
        """Run the full 9-agent pipeline on a single tender."""
        start = time.perf_counter()

        # Phase 1-3: Scan → Parse → Check
        states = await self.monitor.monitor(mock_tender)
        if not states:
            print("  [Pipeline] Keine Ausschreibungen gefunden.")
            return TenderState(tender_id="NONE", phase=TenderPhase.REJECTED)

        state = states[0]

        # Inject LV if provided in mock data
        if "positions" in mock_tender:
            state.lv_positions = mock_tender["positions"]

        state = await self.parser.parse(state)
        state = await self.eligibility.check(state, tender_value_eur or mock_tender.get("estimated_value_eur", 4_200_000))
        if state.phase == TenderPhase.REJECTED:
            return state

        # Phase 4-6: Risk → PoPW → Calculate
        state = await self.chi_risk.analyze(state, h3_region)
        state = await self.popw.index(state)
        state = await self.calculator.calculate(state)

        # Phase 7-9: Compose → Deadline → Submit
        state = await self.composer.compose(state)
        state = await self.deadline.monitor_deadline(state)
        state = await self.submittal.submit(state)

        elapsed = time.perf_counter() - start
        print(f"\n  [Pipeline] ✅ Alle 9 Phasen durchlaufen in {elapsed:.1f}s")
        print(f"  Finaler Preis: {state.calculated_offer.get('final_price_eur', 0):,.2f} €")
        print(f"  Submission Tx: {state.submission_tx[:24]}...")
        return state
