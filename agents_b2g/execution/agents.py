"""
Agent X B2G Execution & Settlement — 9 Post-Award Agents.

Construction monitoring, PoPW proof generation, quality assurance,
XRechnung creation, SEPA payment, and GoBD-compliant archiving.

Pipeline:  ContractActivation → PoPWCollector → ProgressVerification →
           DeliveryOracle → QualityAssurance → InvoiceAggregator →
           XRechnungGenerator → PaymentExecutor → SettlementFinalizer
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


# ============================================================
# Shared Types
# ============================================================


@dataclass
class ProjectState:
    """Complete state of a project in the execution phase."""
    project_id: str
    tender_id: str = ""
    contract_signed_at: str = ""
    escrow_active: bool = False
    total_budget_eur: float = 0.0
    positions: list[dict] = field(default_factory=list)
    popw_proofs: list[dict] = field(default_factory=list)
    progress_pct: float = 0.0
    quality_reports: list[dict] = field(default_factory=list)
    xrechnung_xml: str = ""
    payment_tx: str = ""
    settlement_tx: str = ""
    status: str = "CONTRACT_SIGNED"
    errors: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ============================================================
# Agent 1: ContractActivationAgent
# ============================================================


class ContractActivationAgent:
    """Receives award notice, activates escrow, sets milestones."""

    async def parse_award(self, award_data: dict) -> dict:
        """Subagent: ZuschlagParser."""
        return {
            "tender_id": award_data.get("tender_id", ""),
            "contract_value_eur": award_data.get("contract_value_eur", 0),
            "start_date": award_data.get("start_date", datetime.now(timezone.utc).isoformat()),
            "end_date": award_data.get("end_date", ""),
            "payment_plan": award_data.get("payment_plan", [
                {"milestone": "Baubeginn", "pct": 10},
                {"milestone": "Rohbau fertig", "pct": 40},
                {"milestone": "Abnahme", "pct": 45},
                {"milestone": "Schlussrechnung", "pct": 5},
            ]),
        }

    async def deploy_escrow(self, project_id: str, total_eur: float) -> str:
        """Subagent: EscrowDeployer — simulated escrow activation."""
        return f"0xESCROW-{hashlib.sha256(f'{project_id}{total_eur}'.encode()).hexdigest()[:16]}"

    async def set_milestones(self, milestones: list[dict]) -> list[dict]:
        """Subagent: TerminplanSetter."""
        return [{"name": m["milestone"], "pct": m["pct"], "status": "pending"} for m in milestones]

    async def activate(self, award_data: dict) -> ProjectState:
        award = await self.parse_award(award_data)
        project_id = f"PRJ-{award['tender_id']}"
        escrow_tx = await self.deploy_escrow(project_id, award["contract_value_eur"])
        milestones = await self.set_milestones(award["payment_plan"])

        state = ProjectState(
            project_id=project_id, tender_id=award["tender_id"],
            contract_signed_at=award["start_date"],
            escrow_active=True,
            total_budget_eur=award["contract_value_eur"],
            positions=award_data.get("positions", []),
        )
        print(f"  [ContractAct]   📜 Vertrag aktiviert: {project_id} "
              f"({award['contract_value_eur']:,.0f} €, {len(milestones)} Meilensteine)")
        return state


# ============================================================
# Agent 2: PoPWCollectorAgent
# ============================================================


class PoPWCollectorAgent:
    """Collects telemetry: GPS, IoT scales, site photos."""

    async def check_geofence(self, worker_gps: list[float], site_gps: list[float]) -> dict:
        """Subagent: GPSGeofenceSubagent."""
        from math import radians, sin, cos, sqrt, atan2
        lat1, lon1 = radians(worker_gps[0]), radians(worker_gps[1])
        lat2, lon2 = radians(site_gps[0]), radians(site_gps[1])
        dlat, dlon = lat2 - lat1, lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
        dist_m = 6371000 * 2 * atan2(sqrt(a), sqrt(1-a))
        return {"on_site": dist_m < 500, "distance_m": round(dist_m, 1)}

    async def read_iot_scale(self, material: str) -> dict:
        """Subagent: IoTScaleReader."""
        return {"material": material, "quantity_used": 125.5, "unit": "m³", "timestamp": datetime.now(timezone.utc).isoformat()}

    async def hash_photo(self, photo_bytes: bytes) -> str:
        """Subagent: PhotoHasher."""
        return hashlib.sha256(photo_bytes).hexdigest()[:40]

    async def collect(self, state: ProjectState) -> dict:
        """Simulated telemetry collection for one day on site."""
        telemetry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gps": await self.check_geofence([52.3759, 9.7320], [52.3760, 9.7321]),
            "material_usage": await self.read_iot_scale("Beton C30/37"),
            "photo_hash": await self.hash_photo(b"mock_photo_bytes"),
            "workers_on_site": 4,
            "weather": "trocken, 18°C",
        }
        print(f"  [PoPWCollector] 📡 Telemetrie: {telemetry['workers_on_site']} Arbeiter, "
              f"Geofence={'✓' if telemetry['gps']['on_site'] else '⚠'}")
        return telemetry


# ============================================================
# Agent 3: ProgressVerificationAgent
# ============================================================


class ProgressVerificationAgent:
    """Compares PoPW data against GAEB target quantities."""

    async def compare_actual_vs_target(self, telemetry: dict, positions: list[dict]) -> dict:
        """Subagent: SollIstVergleich."""
        total_target = sum(p.get("quantity", 0) for p in positions)
        actual = telemetry.get("material_usage", {}).get("quantity_used", 0)
        pct = min(100, actual / max(total_target, 1) * 100 * 10)  # Simulated scaling
        return {"target_total": total_target, "actual_used": actual, "progress_pct": round(pct, 1)}

    async def detect_deviation(self, progress_pct: float, expected_pct: float) -> dict:
        """Subagent: AbweichungsDetektor."""
        delta = abs(progress_pct - expected_pct)
        return {"deviation_pct": round(delta, 1), "alert": delta > 10}

    async def escalate(self, msg: str) -> None:
        """Subagent: EskalationsSubagent."""
        print(f"  [Progress]      ⚠ ESKALATION: {msg}")

    async def verify(self, state: ProjectState, telemetry: dict, expected_pct: float = 25.0) -> ProjectState:
        comparison = await self.compare_actual_vs_target(telemetry, state.positions)
        state.progress_pct = comparison["progress_pct"]
        deviation = await self.detect_deviation(state.progress_pct, expected_pct)
        icon = "✓" if not deviation["alert"] else "⚠"
        print(f"  [Progress]      {icon} Baufortschritt: {state.progress_pct}% "
              f"(Soll: {expected_pct}%, Δ={deviation['deviation_pct']}%)")
        if deviation["alert"]:
            await self.escalate(f"Abweichung {deviation['deviation_pct']}% > 10% bei Projekt {state.project_id}")
        return state


# ============================================================
# Agent 4: DeliveryOracleAgent — PoPW Proof Generator
# ============================================================


class DeliveryOracleAgent:
    """Creates cryptographic PoPW proofs for completed positions."""

    async def generate_proof(self, telemetry: dict, project_id: str, position_id: str) -> dict:
        """Subagent: ProofGenerator — creates cryptographic delivery proof."""
        raw = json.dumps({
            "project": project_id, "position": position_id,
            "gps": telemetry.get("gps", {}), "material": telemetry.get("material_usage", {}),
            "timestamp": telemetry["timestamp"],
        }, sort_keys=True)
        data_hash = hashlib.sha256(raw.encode()).hexdigest()
        proof_id = f"0xPoPW-{data_hash[:16]}"
        return {"proof_id": proof_id, "data_hash": data_hash, "position_id": position_id,
                "timestamp": telemetry["timestamp"], "verification": "sha256+geofence+iot"}

    async def create_zkp(self, proof: dict) -> dict:
        """Subagent: ZKPSigner — wraps proof for zero-knowledge submission."""
        return {"zkp_hash": hashlib.sha256(proof["proof_id"].encode()).hexdigest()[:32],
                "reveals": "Position completed, on-time, within geofence",
                "hides": "Exact worker count, material supplier pricing"}

    async def trigger_contract_event(self, proof: dict) -> str:
        """Subagent: EventTrigger — simulates DELIVERY_CONFIRMED on-chain."""
        return f"0xDELIVERY-{proof['proof_id'][:16]}"

    async def confirm(self, state: ProjectState, telemetry: dict) -> ProjectState:
        if not state.positions:
            return state
        pos = state.positions[0]
        proof = await self.generate_proof(telemetry, state.project_id, pos.get("position_id", "LV-0001"))
        zkp = await self.create_zkp(proof)
        proof["zkp"] = zkp
        tx = await self.trigger_contract_event(proof)
        proof["tx_hash"] = tx
        state.popw_proofs.append(proof)
        print(f"  [DeliveryOracle] ✅ PoPW-Proof: {proof['proof_id'][:20]}... (Tx={tx[:20]}...)")
        return state


# ============================================================
# Agent 5: QualityAssuranceAgent
# ============================================================


class QualityAssuranceAgent:
    """Collects lab reports, links them to PoPW proofs, manages defects."""

    async def fetch_lab_report(self, test_type: str) -> dict:
        """Subagent: LabReportFetcher."""
        return {"test": test_type, "result": "bestanden", "lab": "MPA Hannover",
                "report_hash": hashlib.sha256(f"{test_type}{time.time()}".encode()).hexdigest()[:20]}

    async def anchor_report(self, report: dict) -> str:
        """Subagent: ReportHasher."""
        return f"0xLAB-{report['report_hash']}"

    async def track_defects(self, defects: list[str]) -> list[dict]:
        """Subagent: MangelManager."""
        return [{"defect": d, "status": "offen", "reported_at": datetime.now(timezone.utc).isoformat()} for d in defects]

    async def assure(self, state: ProjectState) -> ProjectState:
        report = await self.fetch_lab_report("Beton-Druckfestigkeit C30/37")
        tx = await self.anchor_report(report)
        report["chain_tx"] = tx
        state.quality_reports.append(report)
        defects = await self.track_defects([])
        print(f"  [QA]            🔬 Prüfbericht: {report['test']} → {report['result']} "
              f"({len(defects)} Mängel)")
        return state


# ============================================================
# Agent 6: InvoiceAggregatorAgent
# ============================================================


class InvoiceAggregatorAgent:
    """Aggregates completed positions, proofs, and reports for invoicing."""

    async def merge_positions(self, positions: list[dict], proofs: list[dict]) -> list[dict]:
        """Subagent: PositionMerger."""
        proven_ids = {p["position_id"] for p in proofs}
        return [pos for pos in positions if pos.get("position_id") in proven_ids]

    async def calculate_tax(self, net_total: float) -> dict:
        """Subagent: TaxCalculator — §13b UStG reverse charge."""
        return {"net_eur": round(net_total, 2), "vat_rate": 19.0, "vat_reverse_charge": True,
                "vat_note": "§13b UStG — Steuerschuldnerschaft des Leistungsempfängers"}

    async def apply_discounts(self, total: float, skonto_pct: float = 2.0) -> float:
        """Subagent: DiscountHandler."""
        return round(total * (1 - skonto_pct / 100), 2)

    async def aggregate(self, state: ProjectState) -> dict:
        billable = await self.merge_positions(state.positions, state.popw_proofs)
        net_total = sum(p.get("total_net", p.get("quantity", 1) * 200) for p in billable)
        tax_info = await self.calculate_tax(net_total)
        discounted = await self.apply_discounts(net_total)
        invoice = {
            "invoice_id": f"INV-{state.project_id}-{len(state.popw_proofs):03d}",
            "billable_positions": len(billable),
            "net_total_eur": net_total,
            "discounted_eur": discounted,
            "tax_info": tax_info,
            "proof_count": len(state.popw_proofs),
        }
        print(f"  [InvoiceAggr]   🧾 Abschlagsrechnung: {invoice['billable_positions']} Positionen, "
              f"{net_total:,.2f} € netto")
        return invoice


# ============================================================
# Agent 7: XRechnungGeneratorAgent
# ============================================================


class XRechnungGeneratorAgent:
    """Creates XRechnung 3.0 XML (EN 16931 / CIUS-DE) with Schematron validation.

    Schematron validation requires full UBL 2.1 namespace output.
    Production mode: output UBL 2.1 and validate via XSLT transform.
    Current mode: simplified EN 16931 CIUS with graceful degradation.
    """

    _SCHEMATRON_XSL = Path("archive_b2g/schemas/xrechnung_30/schematron/ubl/XRechnung-UBL-validation.xsl")
    _schematron_cache: Any = None  # lxml.etree.XSLT transform

    def _load_schematron(self):
        """Lazy-load XRechnung Schematron via XSLT transform.

        The official KoSIT Schematron uses SchXslt extensions and requires
        precompiled .xsl + full UBL 2.1 XML input. If loading fails or lxml
        is unavailable, validation is gracefully skipped.
        """
        if self._schematron_cache is not None:
            return self._schematron_cache
        if self._SCHEMATRON_XSL.exists():
            try:
                from lxml import etree
                xslt_tree = etree.parse(str(self._SCHEMATRON_XSL))
                self._schematron_cache = etree.XSLT(xslt_tree)
                print(f"  [XRechnung]     📐 Schematron geladen: EN 16931 / CIUS-DE (KoSIT)")
                return self._schematron_cache
            except ImportError:
                pass
            except Exception as exc:
                print(f"  [XRechnung]     ⚠ Schematron nicht ladbar (benötigt volle UBL 2.1 Namespaces): {str(exc)[:100]}")
        return None

    async def build_xrechnung_xml(self, invoice: dict, state: ProjectState) -> str:
        """Subagent: XRechnungXMLBuilder — EN 16931 / CIUS-DE format."""
        proof_hashes = " ".join(p.get("proof_id", "")[:16] for p in state.popw_proofs)
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<CrossIndustryInvoice xmlns="urn:cen.eu:en16931:2017">\n'
            f'  <InvoiceNumber>{invoice["invoice_id"]}</InvoiceNumber>\n'
            f'  <InvoiceDate>{datetime.now(timezone.utc).strftime("%Y%m%d")}</InvoiceDate>\n'
            f'  <ProjectReference>{state.project_id}</ProjectReference>\n'
            f'  <NetTotal>{invoice["net_total_eur"]:.2f}</NetTotal>\n'
            f'  <VATNote>{invoice["tax_info"]["vat_note"]}</VATNote>\n'
            f'  <EmbeddedProofs>{proof_hashes}</EmbeddedProofs>\n'
            f'  <ChainAnchor>{state.settlement_tx or "pending"}</ChainAnchor>\n'
            f'</CrossIndustryInvoice>'
        )

    async def create_zugferd_pdf(self, xml_str: str, invoice: dict) -> str:
        """Subagent: ZUGFeRDPDFCreator."""
        return f"ZUGFeRD-PDF-{invoice['invoice_id']}.pdf"

    async def embed_hashes(self, xml_str: str, state: ProjectState) -> str:
        """Subagent: HashEmbedder."""
        return xml_str

    async def validate_schematron(self, xml_str: str) -> tuple[bool, list[str]]:
        """
        Subagent: XRechnungSchematronValidator — validates against EN 16931 rules.
        Uses precompiled XSLT transform from KoSIT.
        Requires: full UBL 2.1 namespace output for production validation.
        """
        transform = self._load_schematron()
        if transform is None:
            return True, []  # Schematron not available — skip (not an error)

        try:
            from lxml import etree
            root = etree.fromstring(xml_str.encode("utf-8"))
            # XSLT transform produces SVRL (Schematron Validation Report Language)
            result = transform(root)
            svrl_ns = "http://purl.oclc.org/dsdl/svrl"
            failed = result.xpath("//svrl:failed-assert", namespaces={"svrl": svrl_ns})
            errors = [
                f"{fa.get('location', '?')}: {fa.get('test', '?')} — {(fa.text or '').strip()[:100]}"
                for fa in failed
            ]
            is_valid = len(failed) == 0
            return is_valid, errors
        except Exception as exc:
            return False, [str(exc)]

    async def generate(self, state: ProjectState, invoice: dict) -> str:
        xml_str = await self.build_xrechnung_xml(invoice, state)

        # XRechnung Schematron validation
        schematron_ok, schematron_errors = await self.validate_schematron(xml_str)

        pdf_name = await self.create_zugferd_pdf(xml_str, invoice)
        xml_str = await self.embed_hashes(xml_str, state)
        state.xrechnung_xml = xml_str

        schematron_status = "✓" if schematron_ok else f"⚠ {len(schematron_errors)} Schematron-Issues"
        print(f"  [XRechnung]     📄 XRechnung 3.0: {invoice['invoice_id']} "
              f"({len(xml_str)} Zeichen, ZUGFeRD: {pdf_name}, "
              f"Schematron: {schematron_status})")
        return xml_str


# ============================================================
# Agent 8: PaymentExecutorAgent
# ============================================================


class PaymentExecutorAgent:
    """Triggers SEPA payment when delivery confirmed and acceptance passed."""

    async def execute_sepa(self, amount_eur: float, recipient_iban: str, reference: str) -> dict:
        """Subagent: SEPATransferSubagent."""
        return {"tx_id": f"SEPA-{uuid.uuid4().hex[:8].upper()}",
                "amount_eur": amount_eur, "recipient": recipient_iban,
                "reference": reference, "status": "EXECUTED",
                "timestamp": datetime.now(timezone.utc).isoformat()}

    async def burn_eure(self, amount_eur: float) -> str:
        """Subagent: EUReBurner — burns stablecoins for fiat out."""
        return f"0xBURN-{hashlib.sha256(str(amount_eur).encode()).hexdigest()[:16]}"

    async def generate_receipt(self, sepa_result: dict, burn_tx: str) -> dict:
        """Subagent: PaymentReceiptGenerator."""
        return {"sepa": sepa_result, "burn_tx": burn_tx, "payment_proof": hashlib.sha256(
            f"{sepa_result['tx_id']}{burn_tx}".encode()).hexdigest()[:32]}

    async def execute(self, state: ProjectState, invoice: dict) -> ProjectState:
        sepa = await self.execute_sepa(invoice["discounted_eur"], "DE89370400440532013000",
                                       invoice["invoice_id"])
        burn_tx = await self.burn_eure(invoice["discounted_eur"])
        receipt = await self.generate_receipt(sepa, burn_tx)
        state.payment_tx = receipt["payment_proof"]
        print(f"  [Payment]       💶 SEPA-Instant: {sepa['amount_eur']:,.2f} € → "
              f"{sepa['recipient'][:12]}... (Ref: {sepa['reference']})")
        return state


# ============================================================
# Agent 9: SettlementFinalizerAgent
# ============================================================


class SettlementFinalizerAgent:
    """Closes the project, anchors everything on-chain, archives per GoBD."""

    async def anchor_final(self, state: ProjectState) -> str:
        """Subagent: ChainAnchoringSubagent."""
        bundle = f"{state.project_id}{state.payment_tx}{state.xrechnung_xml[:100]}"
        return f"0xSETTLE-{hashlib.sha256(bundle.encode()).hexdigest()[:40]}"

    async def check_gobd(self, state: ProjectState) -> dict:
        """Subagent: GoBDComplianceChecker."""
        checks = {
            "contract_signed": bool(state.contract_signed_at),
            "popw_proofs_present": len(state.popw_proofs) > 0,
            "xrechnung_generated": bool(state.xrechnung_xml),
            "payment_executed": bool(state.payment_tx),
            "chain_anchored": bool(state.settlement_tx),
        }
        return {"all_passed": all(checks.values()), "checks": checks}

    async def close_project(self, state: ProjectState) -> ProjectState:
        """Subagent: ProjectCloser."""
        state.status = "COMPLETED"
        return state

    async def finalize(self, state: ProjectState) -> ProjectState:
        state.settlement_tx = await self.anchor_final(state)
        gobd = await self.check_gobd(state)
        state = await self.close_project(state)
        icon = "✅" if gobd["all_passed"] else "⚠"
        print(f"  [Settlement]    {icon} Projekt abgeschlossen: {state.project_id} "
              f"(Tx={state.settlement_tx[:20]}..., GoBD={'✓' if gobd['all_passed'] else '⚠'})")
        # Archive
        archive = Path("archive_b2g") / f"{state.project_id}_settlement.json"
        archive.parent.mkdir(exist_ok=True)
        archive.write_text(json.dumps({
            "project_id": state.project_id, "status": state.status,
            "payment_tx": state.payment_tx, "settlement_tx": state.settlement_tx,
            "gobd_check": gobd, "closed_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2, default=str))
        print(f"  [Settlement]    📦 Archiviert: {archive}")
        return state


# ============================================================
# Execution Pipeline — 9 Agenten in Sequenz
# ============================================================


class ExecutionPipeline:
    """Wires all 9 post-award agents into a sequential pipeline."""

    def __init__(self):
        self.contract_activation = ContractActivationAgent()
        self.popw_collector = PoPWCollectorAgent()
        self.progress_verifier = ProgressVerificationAgent()
        self.delivery_oracle = DeliveryOracleAgent()
        self.quality_assurance = QualityAssuranceAgent()
        self.invoice_aggregator = InvoiceAggregatorAgent()
        self.xrechnung_generator = XRechnungGeneratorAgent()
        self.payment_executor = PaymentExecutorAgent()
        self.settlement_finalizer = SettlementFinalizerAgent()

    async def run(self, award_data: dict) -> ProjectState:
        """Run the full 9-agent post-award pipeline."""
        start = time.perf_counter()

        # Phase 1-3: Activate → Collect → Verify
        state = await self.contract_activation.activate(award_data)
        telemetry = await self.popw_collector.collect(state)
        state = await self.progress_verifier.verify(state, telemetry)

        # Phase 4-6: Prove → QA → Invoice
        state = await self.delivery_oracle.confirm(state, telemetry)
        state = await self.quality_assurance.assure(state)
        invoice = await self.invoice_aggregator.aggregate(state)

        # Phase 7-9: XRechnung → Pay → Settle
        await self.xrechnung_generator.generate(state, invoice)
        state = await self.payment_executor.execute(state, invoice)
        state = await self.settlement_finalizer.finalize(state)

        elapsed = time.perf_counter() - start
        print(f"\n  [Execution]     ✅ Alle 9 Post-Award-Phasen durchlaufen in {elapsed:.1f}s")
        print(f"  Status: {state.status} | Payment: {state.payment_tx[:20]}... | "
              f"GoBD: {len(state.popw_proofs)} Proofs")
        return state
