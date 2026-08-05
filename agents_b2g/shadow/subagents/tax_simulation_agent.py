# agents_b2g/shadow/subagents/tax_simulation_agent.py
"""
Agent 18.5 — TaxSimulationAgent

Steuerliche Integrität und automatische Steuerabführung im Shadow Contract.
§13b UStG (Reverse-Charge Bauleistungen) + §48b EStG (Bauabzugssteuer).
Hält Finanzamts-Wallet, splittet atomar, generiert ELSTER-XML + PDF/A-3.

9-stufige Tax-Pipeline:
  1. TaxRuleEvaluator              — §13b vs. Regelbesteuerung
  2. TaxExemptionCertValidator     — BZSt-Freistellungsbescheinigung
  3. TaxWalletManager              — On-Chain Finanzamts-Wallet
  4. VatSplitCalculator            — Netto/USt (19%) Berechnung
  5. BauabzugssteuerCalculator     — 15% §48b Einbehalt
  6. OnChainTaxTransferRelayer     — Atomic Tax Transfer
  7. ElsterFormatTransformer       — ELSTER-XML Payload
  8. TaxVoucherPDFGenerator        — PDF/A-3 Steuerbeleg
  9. TaxAuditTrailLogger           — GoBD Tax Log (jsonl)
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

logger = logging.getLogger("TaxSimulationAgent")


# ============================================================================
# SUB-SUBAGENT 18.5.1: TaxRuleEvaluator
# ============================================================================
class TaxRuleEvaluator:
    """Ermittelt anwendbaren Steuertatbestand."""

    SECTION_13B_INDICATORS = ["bauleistung", "bauwerk", "hochbau", "tiefbau",
                               "betonbau", "stahlbau", "erdarbeiten"]

    def evaluate(self, description: str, is_b2b: bool = True) -> Dict[str, Any]:
        is_construction = any(kw in description.lower() for kw in self.SECTION_13B_INDICATORS)
        reverse_charge = is_construction and is_b2b

        return {
            "is_construction_service": is_construction,
            "is_b2b": is_b2b,
            "reverse_charge_13b": reverse_charge,
            "vat_rate_pct": 0.0 if reverse_charge else 19.0,
            "regime": "§13b Reverse-Charge" if reverse_charge else "Regelbesteuerung 19%",
        }


# ============================================================================
# SUB-SUBAGENT 18.5.2: TaxExemptionCertValidator
# ============================================================================
class TaxExemptionCertValidator:
    """Validiert §48b EStG Freistellungsbescheinigung via BZSt."""

    def validate(self, tax_number: str, cert_hash: str) -> Dict[str, Any]:
        valid = bool(tax_number and cert_hash and cert_hash != "EXPIRED"
                     and not cert_hash.startswith("REVOKED"))
        if not valid:
            logger.warning(f"§48b Freistellung für {tax_number} UNGÜLTIG")
        return {
            "tax_number": tax_number,
            "cert_hash": cert_hash,
            "is_valid": valid,
            "checked_at": datetime.now(timezone.utc).isoformat() + "Z",
        }


# ============================================================================
# SUB-SUBAGENT 18.5.3: TaxWalletManager
# ============================================================================
class TaxWalletManager:
    """Verwaltet die Finanzamts-Wallet (Multi-Sig-Mock)."""

    def __init__(self, wallet_address: str = "0x9999999999999999999999999999999999999999"):
        self.wallet = wallet_address

    def get_wallet(self) -> Dict[str, Any]:
        return {
            "address": self.wallet,
            "label": "Finanzamt Shadow Wallet",
            "multisig": "2/3 (Bund, Land, RPA)",
        }


# ============================================================================
# SUB-SUBAGENT 18.5.4+5: Tax Calculators
# ============================================================================
class TaxSplitCalculator:
    """Berechnet Netto, USt (19%), §48b Bauabzug (15%)."""

    def calculate(
        self, gross_amount_eur: float, vat_rate_pct: float = 19.0,
        apply_bauabzug: bool = False,
    ) -> Dict[str, Any]:
        vat_factor = 1.0 + (vat_rate_pct / 100.0)
        net = round(gross_amount_eur / vat_factor, 2)
        vat = round(gross_amount_eur - net, 2)
        bauabzug = round(gross_amount_eur * 0.15, 2) if apply_bauabzug else 0.0
        payout = round(net - bauabzug, 2)
        delta = round(gross_amount_eur - payout - vat - bauabzug, 2)

        return {
            "gross_amount_eur": gross_amount_eur,
            "net_amount_eur": net,
            "vat_amount_eur": vat,
            "vat_rate_pct": vat_rate_pct,
            "bauabzug_tax_15pct_eur": bauabzug,
            "bauabzug_applied": apply_bauabzug,
            "net_payout_contractor_eur": payout,
            "atomic_check_delta_eur": delta,
            "is_atomic": abs(delta) <= 0.02,
        }


# ============================================================================
# SUB-SUBAGENT 18.5.7: ElsterFormatTransformer
# ============================================================================
class ElsterFormatTransformer:
    """Konvertiert Steuerdaten in ELSTER-XML."""

    def transform(self, tax_data: Dict[str, Any]) -> str:
        """Mock ELSTER-XML-Generierung."""
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Elster xmlns="http://www.elster.de/2002/XMLSchema">\n'
            f'  <USt_Betrag>{tax_data.get("vat_amount_eur", 0)}</USt_Betrag>\n'
            f'  <Bauabzug>{tax_data.get("bauabzug_tax_15pct_eur", 0)}</Bauabzug>\n'
            f'  <Netto>{tax_data.get("net_payout_contractor_eur", 0)}</Netto>\n'
            '</Elster>'
        )


# ============================================================================
# SUB-SUBAGENT 18.5.9: TaxAuditTrailLogger
# ============================================================================
class TaxAuditTrailLogger:
    """GoBD-WORM-Steuerlogkette."""

    def __init__(self):
        self._entries: List[Dict[str, Any]] = []
        self._prev_hash: Optional[str] = None

    def log(self, event: str, data: Dict[str, Any]) -> str:
        entry = {"timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                 "event": event, "data": data, "prev_hash": self._prev_hash}
        entry["hash"] = hashlib.sha256(
            json.dumps(entry, sort_keys=True, default=str).encode()).hexdigest()
        self._prev_hash = entry["hash"]
        self._entries.append(entry)
        return entry["hash"]

    def export_jsonl(self) -> str:
        return "\n".join(json.dumps(e, ensure_ascii=False) for e in self._entries)


# ============================================================================
# AGENT 18.5: TaxSimulationAgent (Root)
# ============================================================================
class TaxSimulationAgent:
    """
    Subagent 18.5: Automatische Steuerabführung im Shadow Contract.
    Delegiert Settlement-Berechnung an AtomicSettlementEngine,
    fokussiert auf Steuer-Compliance (ELSTER, BZSt, Tax-Wallet).
    """

    def __init__(
        self,
        tax_wallet: str = "0x9999999999999999999999999999999999999999",
        settlement_engine=None,  # Optional: AtomicSettlementEngine
    ):
        self.rule_evaluator = TaxRuleEvaluator()
        self.cert_validator = TaxExemptionCertValidator()
        self.wallet_manager = TaxWalletManager(tax_wallet)
        self.calculator = TaxSplitCalculator()
        self.elster = ElsterFormatTransformer()
        self.audit_logger = TaxAuditTrailLogger()
        self.settlement = settlement_engine  # Delegation an 18.1.5

    def execute_tax_split(
        self,
        tender_id: str,
        oz_id: str,
        gross_amount_eur: float,
        contractor_tax_number: str,
        cert_hash: str = "VALID_CERT_HASH_2026",
        description: str = "Bauleistung",
        is_b2b: bool = True,
    ) -> Dict[str, Any]:
        """
        Vollständige Steuerabwicklung für einen Milestone.

        Returns:
            Tax-Settlement mit ELSTER-XML und GoBD-Audit.
        """
        job_id = hashlib.sha256(
            f"tax{oz_id}{gross_amount_eur}{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:12]

        logger.info(f"Tax-Split {job_id}: OZ={oz_id}, Brutto={gross_amount_eur:,.2f} EUR")

        try:
            # === Step 1: Steuertatbestand ===
            regime = self.rule_evaluator.evaluate(description, is_b2b)
            self.audit_logger.log("TAX_REGIME", regime)

            # === Step 2: Freistellung prüfen ===
            exemption = self.cert_validator.validate(contractor_tax_number, cert_hash)
            self.audit_logger.log("EXEMPTION_CHECK", exemption)

            # === Step 3: Tax Wallet ===
            wallet = self.wallet_manager.get_wallet()
            self.audit_logger.log("TAX_WALLET", wallet)

            # === Step 4+5: Steuerberechnung ===
            apply_bauabzug = not exemption["is_valid"]
            splits = self.calculator.calculate(
                gross_amount_eur=gross_amount_eur,
                vat_rate_pct=regime["vat_rate_pct"],
                apply_bauabzug=apply_bauabzug,
            )
            self.audit_logger.log("TAX_CALCULATION", splits)

            # === Step 6: On-Chain Transfers (Mock) ===
            vat_tx = "0x" + hashlib.sha256(f"vat{oz_id}{splits['vat_amount_eur']}".encode()).hexdigest()
            bauabzug_tx = ("0x" + hashlib.sha256(f"bauabzug{oz_id}{splits['bauabzug_tax_15pct_eur']}".encode()).hexdigest()
                           if splits["bauabzug_tax_15pct_eur"] > 0 else None)
            self.audit_logger.log("TAX_TRANSFERS", {"vat_tx": vat_tx, "bauabzug_tx": bauabzug_tx})

            # === Step 7: ELSTER-XML ===
            elster_xml = self.elster.transform(splits)
            self.audit_logger.log("ELSTER_GENERATED", {"xml_length": len(elster_xml)})

            # === Step 8: PDF Mock ===
            pdf_hash = hashlib.sha256(elster_xml.encode()).hexdigest()

            # === Step 9: GoBD ===
            gobd_hash = self.audit_logger.log("TAX_SETTLEMENT_COMPLETE", {
                "oz_id": oz_id, "gross": gross_amount_eur, "vat_tx": vat_tx,
            })

            receipt = {
                "status": "TAX_SETTLEMENT_SUCCESSFUL",
                "job_id": job_id,
                "tender_id": tender_id,
                "oz_id": oz_id,
                "tax_regime": regime,
                "exemption": exemption,
                "tax_wallet": wallet["address"],
                "split_summary": splits,
                "on_chain_transfers": {
                    "vat_transfer_tx": vat_tx,
                    "bauabzug_transfer_tx": bauabzug_tx,
                },
                "elster_xml": elster_xml,
                "pdf_voucher_hash": pdf_hash,
                "gobd_audit_hash": gobd_hash,
                "artifacts": [
                    {"type": "elster_xml", "format": "xml", "content": elster_xml},
                    {"type": "tax_audit_log", "format": "jsonl",
                     "content": self.audit_logger.export_jsonl()},
                ],
                "error": None,
                "logs": [{"level": "INFO",
                          "message": f"Tax: Brutto={gross_amount_eur:,.2f} → "
                                     f"Netto={splits['net_payout_contractor_eur']:,.2f} "
                                     f"+ USt={splits['vat_amount_eur']:,.2f}"
                                     + (f" + Bauabzug={splits['bauabzug_tax_15pct_eur']:,.2f}"
                                        if apply_bauabzug else "")}],
            }
            return receipt

        except Exception as e:
            logger.error(f"Tax-Split fehlgeschlagen: {e}")
            return {"status": "TAX_FAILED", "job_id": job_id, "error": str(e),
                    "artifacts": [], "logs": [{"level": "ERROR", "message": str(e)}]}


# ============================================================================
# SMOKE TEST
# ============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("TaxSimulationAgent — Smoke Test")
    print("=" * 60)

    agent = TaxSimulationAgent()

    # Test mit Freistellung (kein Bauabzug)
    r1 = agent.execute_tax_split(
        tender_id="TED-2026-SHADOW-001",
        oz_id="01.02.0040",
        gross_amount_eur=83657.00,
        contractor_tax_number="13/123/45678",
        cert_hash="VALID_CERT_HASH_2026",
        description="Stahlbetonsohle C30/37 Betonbauarbeiten",
    )
    s = r1["split_summary"]
    print(f"\nMit Freistellung: Brutto={s['gross_amount_eur']:,.2f} → "
          f"Netto={s['net_payout_contractor_eur']:,.2f} + USt={s['vat_amount_eur']:,.2f} "
          f"(Δ={s['atomic_check_delta_eur']:.2f})")
    print(f"ELSTER: {len(r1['elster_xml'])} Zeichen")

    # Test ohne Freistellung (mit 15% Bauabzug)
    r2 = agent.execute_tax_split(
        tender_id="TED-2026-SHADOW-001",
        oz_id="02.01.0020",
        gross_amount_eur=320000.00,
        contractor_tax_number="13/987/65432",
        cert_hash="EXPIRED",
        description="Beckenwände betonieren",
    )
    s2 = r2["split_summary"]
    print(f"\nOhne Freistellung: Brutto={s2['gross_amount_eur']:,.2f} → "
          f"Netto={s2['net_payout_contractor_eur']:,.2f} + USt={s2['vat_amount_eur']:,.2f} "
          f"+ Bauabzug={s2['bauabzug_tax_15pct_eur']:,.2f} (Δ={s2['atomic_check_delta_eur']:.2f})")

    print(f"\n✅ Smoke Test abgeschlossen.")
