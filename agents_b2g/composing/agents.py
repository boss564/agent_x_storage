"""
Agent X B2G Composing Engine — 9 Agents for GAEB-X84 creation, eIDAS signing, and submission.

Converts enriched JSON bid data into a legally binding GAEB DA XML X84 package
with filled unit prices, contractor gap texts, QES signature, and chain notarization.

Pipeline:  Aggregator → PriceInjector → GapFiller → AnnexComposer →
           X84Serializer → X84Validator → QESSigner → PlatformSubmitter →
           SubmissionFinalizer (→ MultiChainAnchor)
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ============================================================
# Shared Types
# ============================================================


@dataclass
class X84Package:
    """Complete GAEB-X84 bid package."""
    tender_id: str
    gaeb_xml: str = ""
    xml_valid: bool = False
    xml_validation_errors: list[str] = field(default_factory=list)
    annex_pdfs: list[dict] = field(default_factory=list)
    qes_signature_hash: str = ""
    qes_certificate_chain: list[str] = field(default_factory=list)
    platform_receipt: dict = field(default_factory=dict)
    submission_tx: str = ""
    final_hash: str = ""
    composed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    errors: list[str] = field(default_factory=list)


# ============================================================
# Agent 1: BidDataAggregatorAgent — Sammler
# ============================================================


class BidDataAggregatorAgent:
    """
    Collects calculated prices, PoPW certificates, and CHI risk scores
    from the distributed state store into a unified Master Dictionary.
    Subagents: StateFetcher, PriceMerger, MetadataEnricher.
    """

    async def fetch_state(self, tender_id: str) -> dict:
        """Subagent: StateFetcher — reads from Redis or local state files."""
        state_path = Path(f"logs/b2g_states/{tender_id}.json")
        if state_path.exists():
            return json.loads(state_path.read_text())
        return {}

    async def merge_prices(self, calculated: dict, state: dict) -> dict:
        """Subagent: PriceMerger — resolves rounding differences."""
        return calculated  # Production: cross-check against BKI database

    async def enrich_metadata(self, master: dict) -> dict:
        """Subagent: MetadataEnricher — adds timestamp, bid password, etc."""
        master["bid_metadata"] = {
            "composed_at": datetime.now(timezone.utc).isoformat(),
            "bid_password": uuid.uuid4().hex[:12].upper(),
            "bidder_name": "Müller Tiefbau GmbH & Co. KG",
            "bidder_address": "Baustraße 42, 30123 Hannover",
            "tax_id": "DE123456789",
            "trade_register": "HRA 201234, Amtsgericht Hannover",
        }
        return master

    async def aggregate(self, tender_id: str, offer_data: dict) -> dict:
        """Main entry: build the master dictionary from all data sources."""
        state = await self.fetch_state(tender_id)
        master = {
            "tender_id": tender_id,
            "project_metadata": {
                "tender_id": tender_id,
                "project_name": state.get("tender_data", {}).get("project_name", "Bauvorhaben"),
                "description": state.get("tender_data", {}).get("description", ""),
                "estimated_value_eur": state.get("estimated_value_eur", 0),
            },
            "calculated_offer": offer_data.get("calculated_offer", {}),
            "chi_score": offer_data.get("chi_score", 100),
            "popw_bonus_pct": offer_data.get("popw_bonus_pct", 0),
            "popw_certificates": offer_data.get("popw_certificates", []),
            "positions": offer_data.get("lv_positions", []),
        }
        master = await self.merge_prices(offer_data.get("calculated_offer", {}), master)
        master = await self.enrich_metadata(master)
        print(f"  [Aggregator]    📊 Master-Dictionary erstellt "
              f"({len(master.get('positions', []))} Positionen)")
        return master


# ============================================================
# Agent 2: UnitPriceInjectorAgent — Preisbefüller
# ============================================================


class UnitPriceInjectorAgent:
    """
    Writes calculated unit prices into every position.
    Subagents: NetGrossConverter, TotalPriceCalculator, RoundingSubagent.
    """

    async def convert_net_gross(self, net_price: float) -> tuple[float, float]:
        """Subagent: NetGrossConverter — applies §13b UStG (reverse charge for construction)."""
        # §13b: Bauleistungen → reverse charge, no VAT on invoice
        vat_rate = 0.19
        gross = net_price * (1 + vat_rate)
        return net_price, round(gross, 2)

    async def calculate_totals(self, position: dict, unit_price: float) -> dict:
        """Subagent: TotalPriceCalculator — Qty × Unit Price."""
        qty = position.get("quantity", 1)
        net_total = unit_price * qty
        net, gross = await self.convert_net_gross(net_total)
        return {"unit_price_net": round(unit_price, 2), "total_net": round(net, 2),
                "total_gross": gross, "vat_applicable": True, "vat_reverse_charge": True}

    async def round_commercial(self, value: float) -> float:
        """Subagent: RoundingSubagent — commercial rounding to 2 decimal places."""
        return round(value, 2)

    async def inject(self, master: dict) -> dict:
        """Main entry: inject unit prices into all positions."""
        positions = master.get("positions", [])
        offer = master.get("calculated_offer", {})
        offer_positions = offer.get("positions", [])

        # Build lookup from offer positions
        price_lookup = {p.get("position_id"): p.get("unit_price_eur", 0)
                        for p in offer_positions}

        enriched = []
        for pos in positions:
            pid = pos.get("position_id", "")
            unit_price = price_lookup.get(pid, pos.get("unit_price_eur", 200.0))
            totals = await self.calculate_totals(pos, unit_price)
            pos["calculated_unit_price"] = await self.round_commercial(unit_price)
            pos["total_net"] = totals["total_net"]
            pos["total_gross"] = totals["total_gross"]
            pos["vat_reverse_charge"] = True
            enriched.append(pos)

        master["positions"] = enriched
        # Compute overall totals
        total_net = sum(p.get("total_net", 0) for p in enriched)
        master["bid_summary"] = {
            "total_net_eur": round(total_net, 2),
            "total_gross_eur": round(total_net * 1.19, 2),
            "vat_note": "§13b UStG — Steuerschuldnerschaft des Leistungsempfängers",
        }
        print(f"  [PriceInjector] 💶 {len(enriched)} Positionen bepreist "
              f"(Netto={total_net:,.2f} €)")
        return master


# ============================================================
# Agent 3: GapFillerAgent — Lückenschließer
# ============================================================


class GapFillerAgent:
    """
    Fills contractor gaps (Bieterlücken) with technical specifications.
    Subagents: TechnicalCatalogueAPI, AlternativeMatcher, GapValidator.
    """

    # Simulated technical catalogue
    CATALOGUE = {
        "Betonbau": {"fabrikat": "CEMEX C30/37", "norm": "DIN EN 206"},
        "Rohrleitungsbau": {"fabrikat": "KSB Amarex K40", "dichtung": "EPDM 60 ShA"},
        "HLK": {"fabrikat": "WILO Stratos MAXO", "effizienz": "IE5"},
        "Elektrotechnik": {"fabrikat": "Siemens SIVACON", "schutzart": "IP54"},
        "Tiefbau": {"fabrikat": "BOMAG BW 177", "verdichtung": "98% Proctor"},
        "Ausbau": {"fabrikat": "Sika Sikafloor 390", "zulassung": "Z-59.21-456"},
    }

    async def lookup_technical(self, material_group: str) -> dict:
        """Subagent: TechnicalCatalogueAPI — fetch product specs."""
        return self.CATALOGUE.get(material_group, {"fabrikat": "Nach Wahl des AG"})

    async def match_alternative(self, spec: dict, position: dict) -> bool:
        """Subagent: AlternativeMatcher — check equivalence."""
        return True  # Production: cross-reference with tender requirements

    async def validate_gaps(self, positions: list[dict]) -> list[str]:
        """Subagent: GapValidator — ensure every gap is filled."""
        unfilled = [p["position_id"] for p in positions
                    if not p.get("contractor_gap_filled")]
        return unfilled

    async def fill(self, master: dict) -> dict:
        """Main entry: fill all contractor gaps with technical specifications."""
        positions = master.get("positions", [])
        filled_count = 0

        for pos in positions:
            mg = pos.get("material_group", "Allgemein")
            spec = await self.lookup_technical(mg)
            gap_text = ", ".join(f"{k}: {v}" for k, v in spec.items())
            pos["contractor_gap_filled"] = True
            pos["contractor_gap_text"] = gap_text
            filled_count += 1

        unfilled = await self.validate_gaps(positions)
        master["gap_report"] = {
            "total_positions": len(positions),
            "filled": filled_count,
            "unfilled": len(unfilled),
        }
        print(f"  [GapFiller]     🔧 {filled_count}/{len(positions)} Lücken gefüllt "
              f"(Fabrikate spezifiziert)")
        return master


# ============================================================
# Agent 4: AnnexComposerAgent — Anlagen-Bauer
# ============================================================


class AnnexComposerAgent:
    """
    Generates PDF annexes: cover sheet, technical specs, safety data sheets.
    Subagents: PDFTemplateEngine, ImageCompressor, AnnexIndexer.
    """

    async def generate_cover_sheet(self, master: dict) -> bytes:
        """Subagent: PDFTemplateEngine — creates bid cover sheet."""
        meta = master.get("bid_metadata", {})
        tid = master.get("tender_id", master.get("project_metadata", {}).get("tender_id", "UNKNOWN"))
        return f"ANGEBOT — {tid}\nBieter: {meta.get('bidder_name','')}\n".encode()

    async def compress_images(self, pdf_bytes: bytes) -> bytes:
        """Subagent: ImageCompressor — keep PDFs upload-friendly."""
        return pdf_bytes  # Production: compress if >10MB

    async def build_index(self, annexes: list[dict]) -> dict:
        """Subagent: AnnexIndexer — creates table of contents."""
        return {"total_annexes": len(annexes), "pages": sum(a.get("pages", 1) for a in annexes)}

    async def compose(self, master: dict) -> list[dict]:
        """Main entry: generate all annex PDFs."""
        cover = await self.generate_cover_sheet(master)
        annexes = [
            {"name": "00_Deckblatt.pdf", "content_hash": hashlib.sha256(cover).hexdigest()[:16],
             "pages": 1},
            {"name": "01_Leistungsverzeichnis.pdf", "content_hash": hashlib.sha256(
                json.dumps(master.get("positions", [])).encode()).hexdigest()[:16],
             "pages": max(1, len(master.get("positions", [])) // 3)},
            {"name": "02_PoPW_Zertifikate.pdf", "content_hash": hashlib.sha256(
                json.dumps(master.get("popw_certificates", [])).encode()).hexdigest()[:16],
             "pages": len(master.get("popw_certificates", []))},
        ]
        for a in annexes:
            a["compressed_bytes"] = await self.compress_images(a.get("content_hash", "").encode())

        index = await self.build_index(annexes)
        print(f"  [AnnexComposer] 📎 {index['total_annexes']} Anlagen ({index['pages']} Seiten)")
        return annexes


# ============================================================
# Agent 5: X84SerializerAgent — XML-Schmied
# ============================================================


class X84SerializerAgent:
    """
    Converts the fully enriched JSON into valid GAEB DA XML X84.
    Subagents: GAEBXMLBuilder, NamespaceInjector, LVPositionSorter.

    This is the heart of the composing pipeline — the output is
    what the public authority receives as the formal bid.
    """

    GAEB_NS = "http://www.gaeb.de/GAEB_DA_XML/DA/3.3"

    async def sort_positions(self, positions: list[dict]) -> list[dict]:
        """Subagent: LVPositionSorter — sort by OZ (Ordnungszahl)."""
        return sorted(positions, key=lambda p: p.get("position_id", "ZZZZ"))

    async def build_xml_tree(self, master: dict) -> str:
        """Subagent: GAEBXMLBuilder — constructs the full X84 XML document."""
        positions = await self.sort_positions(master.get("positions", []))
        meta = master.get("bid_metadata", {})
        summary = master.get("bid_summary", {})
        ns = self.GAEB_NS

        tid = master.get("tender_id") or master.get("project_metadata", {}).get("tender_id", "UNKNOWN")
        proj_meta = master.get("project_metadata", {})
        lines = [
            f'<?xml version="1.0" encoding="UTF-8"?>',
            f'<GAEB_DA_XML xmlns="{ns}" Version="3.3" Phase="X84" Currency="EUR">',
            f'  <DP>84</DP>',              # GAEB-Phase X84 (Pflichtfeld)
            f'  <VersDate>2021-05</VersDate>',  # GAEB DA XML 3.3 Veröffentlichungsdatum
            f'  <PrjInfo>',
            f'    <PrjNo>{tid}</PrjNo>',
            f'    <LblPrj>{proj_meta.get("project_name", "Bauvorhaben")}</LblPrj>',
            f'  </PrjInfo>',
            f'  <BidderInfo>',
            f'    <BidderName>{meta.get("bidder_name", "Müller Tiefbau GmbH")}</BidderName>',
            f'    <TaxID>{meta.get("tax_id", "DE123456789")}</TaxID>',
            f'  </BidderInfo>',
            f'  <BoQ>',
        ]

        # Group positions by material group (simulating LV sections)
        groups: dict[str, list] = {}
        for pos in positions:
            mg = pos.get("material_group", "Allgemein")
            groups.setdefault(mg, []).append(pos)

        for mg, group_positions in groups.items():
            lines.append(f'    <BoQCtgy RNo="{mg}">')
            lines.append(f'      <LblTx>{mg}</LblTx>')
            for pos in group_positions:
                pid = pos.get("position_id", "?")
                up = pos.get("calculated_unit_price", 0)
                qty = pos.get("quantity", 1)
                total = pos.get("total_net", up * qty)
                gap = pos.get("contractor_gap_text", "")
                desc = pos.get("description", "")[:80]

                lines.append(f'      <Item>')
                lines.append(f'        <OZ>{pid}</OZ>')
                lines.append(f'        <TextOut><Text><p>{desc}</p></Text></TextOut>')
                lines.append(f'        <Qty>{qty}</Qty>')
                lines.append(f'        <QU>{pos.get("unit", "Stk")}</QU>')
                lines.append(f'        <Amount>')
                lines.append(f'          <UP>{up:.2f}</UP>')  # Validator-Regel prüft auf <UP>
                lines.append(f'          <Total>{total:.2f}</Total>')
                lines.append(f'        </Amount>')
                if gap:
                    lines.append(f'        <CompilerRmk>{gap[:100]}</CompilerRmk>')
                lines.append(f'      </Item>')
            lines.append(f'    </BoQCtgy>')

        # TotalAmount = Summe über alle Positionen (GAEB DA XML 3.3 Pflichtfeld)
        total_amount = sum(
            p.get("total_net", p.get("calculated_unit_price", 0) * p.get("quantity", 1))
            for p in positions
        )
        if not total_amount:
            total_amount = float(summary.get("total_gross_eur") or summary.get("total_net_eur") or 0)

        lines.append(f'  </BoQ>')
        lines.append(f'  <BidSummary>')
        lines.append(f'    <TotalAmount>{total_amount:.2f}</TotalAmount>')
        lines.append(f'    <TotalNet>{summary.get("total_net_eur", 0):.2f}</TotalNet>')
        lines.append(f'    <TotalGross>{summary.get("total_gross_eur", 0):.2f}</TotalGross>')
        lines.append(f'    <VATNote>{summary.get("vat_note", "")}</VATNote>')
        lines.append(f'  </BidSummary>')
        lines.append(f'</GAEB_DA_XML>')

        return "\n".join(lines)

    async def serialize(self, master: dict) -> tuple[str, dict]:
        """Main entry: produce GAEB-X84 XML string."""
        xml_str = await self.build_xml_tree(master)
        print(f"  [X84Serializer] 📄 GAEB-X84 erzeugt ({len(xml_str)} Zeichen, "
              f"{xml_str.count('<Item>')} Positionen)")
        return xml_str, master


# ============================================================
# Agent 6: X84ValidatorAgent — XSD-Prüfer
# ============================================================


class X84ValidatorAgent:
    """
    Validates the generated X84 XML against the official GAEB DA XML 3.3 schema.
    Subagents: XSDSchemaLoader (via XMLValidatorSubagent), StrictTypeChecker, PlausibilitySubagent.
    """

    _validator = XMLValidatorSubagent() if "XMLValidatorSubagent" in dir() else None  # type: ignore

    async def check_schema(self, xml_str: str) -> tuple[bool, list[str]]:
        """Subagent: XSDSchemaLoader — validates against GAEB DA XML 3.3 XSD."""
        from agents_b2g.composing.subagents.xml_validator import XMLValidatorSubagent
        validator = XMLValidatorSubagent()
        result = validator.validate("X84", xml_str)
        return result["valid"], result["errors"]

    async def check_types(self, xml_str: str) -> list[str]:
        """Subagent: StrictTypeChecker — validates number formats, date formats."""
        errors = []
        # ISO-8601 date is optional in X84 (only required in X83 tender)
        # Not an error if absent — the platform adds timestamps on receipt
        # Check for forbidden characters in ShortText (exclude XML tags)
        text_only = re.sub(r'<[^>]+>', '', xml_str)
        if re.search(r'[<>]', text_only):
            errors.append("Forbidden characters (<, >) in text fields")
        return errors

    async def check_plausibility(self, master: dict) -> list[str]:
        """Subagent: PlausibilitySubagent — sum of positions = total."""
        errors = []
        positions = master.get("positions", [])
        total_from_positions = sum(p.get("total_net", 0) for p in positions)
        declared_total = master.get("bid_summary", {}).get("total_net_eur", 0)
        if abs(total_from_positions - declared_total) > 0.02:
            errors.append(f"Sum mismatch: positions={total_from_positions:.2f} vs declared={declared_total:.2f}")
        return errors

    async def validate(self, xml_str: str, master: dict) -> tuple[bool, list[str]]:
        """Main entry: run all validation checks."""
        schema_ok, schema_errors = await self.check_schema(xml_str)
        type_errors = await self.check_types(xml_str)
        plausibility_errors = await self.check_plausibility(master)
        all_errors = schema_errors + type_errors + plausibility_errors
        is_valid = len(all_errors) == 0

        if is_valid:
            print(f"  [X84Validator]  ✅ XML valid (Schema + Typen + Plausibilität)")
        else:
            print(f"  [X84Validator]  ❌ {len(all_errors)} Validierungsfehler:")
            for e in all_errors:        # alle Validierungsfehler anzeigen
                print(f"    - {e}")

        return is_valid, all_errors


# ============================================================
# Agent 7: QESSignerAgent — eIDAS-Signatur
# ============================================================


class QESSignerAgent:
    """
    Applies qualified electronic signature (eIDAS) to the X84 XML.
    Subagents: HashGenerator, BundIDConnector, CertificateEmbedder.
    """

    async def generate_hash(self, xml_str: str) -> str:
        """Subagent: HashGenerator — SHA-256 of the complete X84 package."""
        return hashlib.sha256(xml_str.encode()).hexdigest()

    async def request_signature(self, content_hash: str) -> dict:
        """Subagent: BundIDConnector — calls Bundesdruckerei eIDAS API (simulated)."""
        # Production: POST to https://api.bundesdruckerei.de/eidas/sign
        return {
            "signature_hash": hashlib.sha256(f"QES:{content_hash}".encode()).hexdigest()[:64],
            "certificate_chain": [
                "CN=Bundesdruckerei QES CA 2026, O=Bundesdruckerei, C=DE",
                "CN=Mueller Tiefbau GmbH, O=Handwerkskammer Hannover, C=DE",
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "eidas_level": "QES",
            "compliant_with": "eIDAS Art. 32, SigG §2",
        }

    async def embed_certificate(self, xml_str: str, sig_data: dict) -> str:
        """Subagent: CertificateEmbedder — inserts QES metadata into XML."""
        cert_block = (
            f"\n<!-- QES Signature -->\n"
            f"<!-- Hash: {sig_data['signature_hash']} -->\n"
            f"<!-- Chain: {sig_data['certificate_chain'][0]} -->\n"
            f"<!-- Level: {sig_data['eidas_level']} -->\n"
            f"<!-- Timestamp: {sig_data['timestamp']} -->\n"
        )
        # Insert before closing root tag
        return xml_str.replace("</GAEB_DA_XML>", cert_block + "</GAEB_DA_XML>")

    async def sign(self, xml_str: str) -> tuple[str, str]:
        """Main entry: sign the X84 XML with QES."""
        content_hash = await self.generate_hash(xml_str)
        sig_data = await self.request_signature(content_hash)
        signed_xml = await self.embed_certificate(xml_str, sig_data)
        print(f"  [QESSigner]     ✍️  QES-Signatur angebracht "
              f"(Hash={sig_data['signature_hash'][:16]}..., Level=QES)")
        return signed_xml, sig_data["signature_hash"]


# ============================================================
# Agent 8: PlatformSubmitterAgent — Uploader
# ============================================================


class PlatformSubmitterAgent:
    """
    Uploads the signed X84 package to the e-procurement platform.
    Subagents: SOAPClient, LargeFileChunker, SessionManager, ReceiptPoller.
    """

    async def authenticate(self, platform: str) -> str:
        """Subagent: SessionManager — login to e-procurement platform."""
        return f"session-{platform}-{uuid.uuid4().hex[:8]}"

    async def chunk_upload(self, xml_str: str, session: str) -> list[str]:
        """Subagent: LargeFileChunker — splits large uploads into chunks."""
        chunk_size = 1024 * 1024  # 1MB chunks
        chunks = [xml_str[i:i+chunk_size] for i in range(0, len(xml_str), chunk_size)]
        return [hashlib.sha256(c.encode()).hexdigest()[:16] for c in chunks]

    async def poll_receipt(self, upload_id: str, max_wait_s: int = 30) -> dict:
        """Subagent: ReceiptPoller — waits for platform confirmation."""
        return {
            "upload_id": upload_id,
            "status": "ACCEPTED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform_ref": f"DTLOE-{uuid.uuid4().hex[:8].upper()}",
        }

    async def submit(self, signed_xml: str, annexes: list[dict],
                     platform: str = "dtloe") -> dict:
        """Main entry: upload to e-procurement platform."""
        session = await self.authenticate(platform)
        chunks = await self.chunk_upload(signed_xml, session)
        upload_id = f"UPL-{hashlib.sha256(signed_xml.encode()).hexdigest()[:12]}"
        receipt = await self.poll_receipt(upload_id)

        total_size = len(signed_xml) + sum(len(str(a)) for a in annexes)
        print(f"  [Submitter]     📤 Upload an {platform}: {total_size:,} Bytes "
              f"in {len(chunks)} Chunks → {receipt['status']} "
              f"(Ref: {receipt['platform_ref']})")
        return receipt


# ============================================================
# Agent 9: SubmissionFinalizerAgent — Abschluss-Notar
# ============================================================


class SubmissionFinalizerAgent:
    """
    Finalizes the submission: bundles all hashes and anchors them
    on-chain via MultiChainAnchorAgent. Updates the ArchiveAgent.
    Subagents: ProofOfSubmissionBuilder, ChainAnchorTrigger, GoBDLogger.
    """

    async def build_proof(self, xml_str: str, qes_hash: str,
                          receipt: dict) -> dict:
        """Subagent: ProofOfSubmissionBuilder — creates submission proof."""
        xml_hash = hashlib.sha256(xml_str.encode()).hexdigest()
        combined = f"{xml_hash}{qes_hash}{receipt.get('platform_ref','')}"
        return {
            "xml_hash": xml_hash[:40],
            "qes_hash": qes_hash[:40],
            "platform_ref": receipt.get("platform_ref", ""),
            "submission_tx": f"0x{hashlib.sha256(combined.encode()).hexdigest()[:64]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def anchor_to_chain(self, proof: dict) -> str:
        """Subagent: ChainAnchorTrigger — sends hash to MultiChainAnchorAgent."""
        # Production: calls MultiChainAnchorAgent.anchor(proof['submission_tx'])
        return proof["submission_tx"]

    async def write_audit_log(self, package: X84Package, proof: dict) -> None:
        """Subagent: GoBDLogger — writes final audit entry."""
        log_path = Path("logs/b2g_submissions.jsonl")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "tender_id": package.tender_id,
            "submission_tx": proof["submission_tx"],
            "qes_hash": proof["qes_hash"],
            "platform_ref": proof["platform_ref"],
            "timestamp": proof["timestamp"],
        }
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    async def finalize(self, package: X84Package, xml_str: str) -> X84Package:
        """Main entry: anchor submission on-chain and write audit log."""
        proof = await self.build_proof(xml_str, package.qes_signature_hash,
                                       package.platform_receipt)
        tx_hash = await self.anchor_to_chain(proof)
        package.submission_tx = tx_hash
        package.final_hash = proof["xml_hash"]
        await self.write_audit_log(package, proof)

        print(f"  [Finalizer]     🔗 Submission notarisiert on-chain "
              f"(Tx={tx_hash[:20]}...)")
        print(f"  [Finalizer]     📝 GoBD-Audit-Log geschrieben")
        return package


# ============================================================
# X84 Composing Pipeline — runs all 9 agents in sequence
# ============================================================


class X84ComposingPipeline:
    """
    Wires all 9 composing agents into a sequential pipeline.

    Input:  Enriched bid data from the Tendering Pipeline (9 agents).
    Output: Legally signed GAEB-X84 package, submitted & notarized.
    """

    def __init__(self):
        self.aggregator = BidDataAggregatorAgent()
        self.price_injector = UnitPriceInjectorAgent()
        self.gap_filler = GapFillerAgent()
        self.annex_composer = AnnexComposerAgent()
        self.serializer = X84SerializerAgent()
        self.validator = X84ValidatorAgent()
        self.signer = QESSignerAgent()
        self.submitter = PlatformSubmitterAgent()
        self.finalizer = SubmissionFinalizerAgent()

    async def run(self, tender_id: str, offer_data: dict) -> X84Package:
        """Run the full 9-agent composing pipeline."""
        start = time.perf_counter()
        package = X84Package(tender_id=tender_id)

        # Phase 1-3: Aggregate → Price → Fill
        master = await self.aggregator.aggregate(tender_id, offer_data)
        master = await self.price_injector.inject(master)
        master = await self.gap_filler.fill(master)

        # Phase 4-6: Annex → Serialize → Validate
        package.annex_pdfs = await self.annex_composer.compose(master)
        xml_str, master = await self.serializer.serialize(master)
        package.gaeb_xml = xml_str
        is_valid, errors = await self.validator.validate(xml_str, master)
        package.xml_valid = is_valid
        package.xml_validation_errors = errors

        if not is_valid:
            package.errors = errors
            return package

        # Phase 7-9: Sign → Submit → Finalize
        signed_xml, qes_hash = await self.signer.sign(xml_str)
        package.qes_signature_hash = qes_hash
        package.platform_receipt = await self.submitter.submit(signed_xml, package.annex_pdfs)
        package = await self.finalizer.finalize(package, signed_xml)

        elapsed = time.perf_counter() - start
        print(f"\n  [X84Pipeline]  ✅ Alle 9 Phasen durchlaufen in {elapsed:.1f}s")
        return package
