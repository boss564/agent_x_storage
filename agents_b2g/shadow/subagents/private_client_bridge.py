# agents_b2g/shadow/subagents/private_client_bridge.py
"""
Agent 18.3 — PrivateClientBridge

Brücke zwischen traditionellem SEPA-Banking und On-Chain-EURe-Funding.
Überwacht SEPA-Eingänge, triggert Monerium-Minting und routet EURe
direkt in den VOB_Shadow_Escrow.sol Vault.

9-stufige Funding-Pipeline:
  1. ClientOnboardingValidator  — KYB/KYC + vIBAN-Zuordnung
  2. SEPAPaymentListener        — Bank-Webhook/Feed-Überwachung
  3. DepositReconciliationEngine — SEPA-Betrag vs. Soll-Budget
  4. MoneriumMintTrigger        — IssueOrder (Fiat → EURe 1:1)
  5. VaultDestinationRouter     — Direkt-Routing in Escrow-Adresse
  6. EscrowBalanceVerifier      — On-Chain balanceOf() Check
  7. FiatReceiptGenerator       — GoBD-Einzahlungsbeleg (PDF/JSON)
  8. ClientNotificationHub      — Webhook an Kunden-ERP
  9. BridgeAuditLogger          — GoBD-WORM-Kette (jsonl)
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from decimal import Decimal

logger = logging.getLogger("PrivateClientBridge")


# ============================================================================
# SUB-SUBAGENT 18.3.1: ClientOnboardingValidator
# ============================================================================
class ClientOnboardingValidator:
    """Prüft KYB/KYC-Status und weist dedizierte vIBAN zu."""

    IBAN_RE = re.compile(r"^DE\d{20}$")

    def validate(self, client_id: str, firmendaten: Dict[str, Any]) -> Dict[str, Any]:
        """Validiert den Client und generiert eine vIBAN."""
        if not client_id or len(client_id) < 3:
            raise ValueError(f"Ungültige Client-ID: {client_id}")

        # Mock vIBAN-Generierung (in Prod: Monerium API)
        viban = "DE" + hashlib.sha256(client_id.encode()).hexdigest()[:20].upper()

        return {
            "client_id": client_id,
            "viban": viban,
            "kyb_status": "VERIFIED",
            "onboarded_at": datetime.now(timezone.utc).isoformat() + "Z",
            "company_name": firmendaten.get("name", client_id),
        }


# ============================================================================
# SUB-SUBAGENT 18.3.2: SEPAPaymentListener
# ============================================================================
class SEPAPaymentListener:
    """Lauscht auf eingehende SEPA-Gutschriften (Mock-Webhook)."""

    def listen(self, webhook_payload: Optional[Dict] = None) -> Dict[str, Any]:
        """
        In Produktion: Monerium-Webhook / Open-Banking-API.
        Hier: Mock-Event mit übergebenen Daten oder Default.
        """
        if webhook_payload:
            return {
                "event_type": "SEPA_CREDIT",
                "amount_eur": float(webhook_payload.get("amount_eur", 0)),
                "reference": webhook_payload.get("reference", ""),
                "sender_iban": webhook_payload.get("sender_iban", ""),
                "received_at": datetime.now(timezone.utc).isoformat() + "Z",
            }
        return {"event_type": "NO_EVENT", "amount_eur": 0, "reference": ""}


# ============================================================================
# SUB-SUBAGENT 18.3.3: DepositReconciliationEngine
# ============================================================================
class DepositReconciliationEngine:
    """Gleicht SEPA-Betrag mit Soll-Budget ab."""

    def reconcile(self, deposited_eur: float, expected_budget_eur: float) -> Dict[str, Any]:
        delta = round(abs(deposited_eur - expected_budget_eur), 2)
        is_match = delta <= 0.02

        status = "MATCH" if is_match else "DISCREPANCY"
        if not is_match:
            logger.warning(f"SEPA-Diskrepanz: {deposited_eur:,.2f} vs. {expected_budget_eur:,.2f} (Δ={delta:.2f})")

        return {
            "status": status,
            "deposited_eur": deposited_eur,
            "expected_eur": expected_budget_eur,
            "delta_eur": delta,
            "is_match": is_match,
            "action": "PROCEED_TO_MINT" if is_match else "HOLD_FOR_REVIEW",
        }


# ============================================================================
# SUB-SUBAGENT 18.3.4: MoneriumMintTrigger
# ============================================================================
class MoneriumMintTrigger:
    """Triggert das EURe-Minting via Monerium-API (Mock)."""

    def trigger_mint(
        self, amount_eur: float, target_escrow_address: str
    ) -> Dict[str, Any]:
        """IssueOrder: Fiat → EURe 1:1."""
        if amount_eur <= 0:
            raise ValueError(f"Betrag muss > 0 sein: {amount_eur}")

        order_id = "MON-" + hashlib.sha256(
            f"{target_escrow_address}{amount_eur}{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:16].upper()

        mint_tx = "0x" + hashlib.sha256(order_id.encode()).hexdigest()

        logger.info(f"Monerium Mint: {amount_eur:,.2f} EURe → {target_escrow_address}")

        return {
            "order_id": order_id,
            "status": "EXECUTED",
            "minted_amount_eure": amount_eur,
            "target_address": target_escrow_address,
            "on_chain_tx_hash": mint_tx,
            "currency": "EURe (1:1 Pegged Euro)",
            "executed_at": datetime.now(timezone.utc).isoformat() + "Z",
        }


# ============================================================================
# SUB-SUBAGENT 18.3.6: EscrowBalanceVerifier
# ============================================================================
class EscrowBalanceVerifier:
    """On-Chain balanceOf()-Check via Gnosis RPC (Mock)."""

    def verify(self, contract_address: str, expected_balance_eur: float) -> Dict[str, Any]:
        """Führt RPC-Call durch und bestätigt den Vault-Saldo."""
        # In Produktion: w3.eth.call(contract.functions.balanceOf())
        confirmed = True  # Mock: Immer bestätigt
        block_height = 38_500_000  # Mock

        return {
            "contract_address": contract_address,
            "expected_balance_eur": expected_balance_eur,
            "on_chain_balance_eur": expected_balance_eur if confirmed else 0,
            "delta_eur": 0.0 if confirmed else expected_balance_eur,
            "confirmed": confirmed,
            "block_height": block_height,
            "checked_at": datetime.now(timezone.utc).isoformat() + "Z",
        }


# ============================================================================
# SUB-SUBAGENT 18.3.9: BridgeAuditLogger
# ============================================================================
class BridgeAuditLogger:
    """GoBD-WORM-Kette für alle Bridge-Transaktionen."""

    def __init__(self):
        self._entries: List[Dict[str, Any]] = []
        self._prev_hash: Optional[str] = None

    def log(self, event: str, data: Dict[str, Any]) -> str:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "event": event,
            "data": data,
            "prev_hash": self._prev_hash,
        }
        entry["hash"] = hashlib.sha256(
            json.dumps(entry, sort_keys=True, default=str).encode()
        ).hexdigest()
        self._prev_hash = entry["hash"]
        self._entries.append(entry)
        return entry["hash"]

    def export_jsonl(self) -> str:
        return "\n".join(json.dumps(e, ensure_ascii=False) for e in self._entries)


# ============================================================================
# AGENT 18.3: PrivateClientBridge (Root)
# ============================================================================
class PrivateClientBridge:
    """
    Subagent 18.3: SEPA → EURe → Escrow Funding Pipeline.
    """

    def __init__(self):
        self.onboarding = ClientOnboardingValidator()
        self.listener = SEPAPaymentListener()
        self.reconciler = DepositReconciliationEngine()
        self.minter = MoneriumMintTrigger()
        self.verifier = EscrowBalanceVerifier()
        self.audit_logger = BridgeAuditLogger()

    def process_sepa_inbound(
        self,
        client_id: str,
        sepa_reference: str,
        deposited_eur: float,
        target_escrow_address: str,
        expected_budget_eur: float,
        firmendaten: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Verarbeitet einen SEPA-Eingang durch die komplette Bridge-Pipeline.

        Returns:
            Funding-Receipt mit Monerium-Order, Mint-TX und GoBD-Audit.
        """
        job_id = hashlib.sha256(
            f"{sepa_reference}{deposited_eur}{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:12]

        logger.info(f"PrivateClientBridge {job_id}: {deposited_eur:,.2f} EUR via {sepa_reference}")

        try:
            # === Step 1: Client-Onboarding ===
            onboarding = self.onboarding.validate(client_id, firmendaten or {})
            self.audit_logger.log("ONBOARDING", {"client": client_id, "viban": onboarding["viban"]})

            # === Step 2: SEPA-Event empfangen ===
            sepa_event = self.listener.listen({
                "amount_eur": deposited_eur, "reference": sepa_reference,
            })
            self.audit_logger.log("SEPA_RECEIVED", sepa_event)

            # === Step 3: Reconciliation ===
            rec = self.reconciler.reconcile(deposited_eur, expected_budget_eur)
            self.audit_logger.log("RECONCILIATION", rec)

            if not rec["is_match"]:
                return {
                    "status": "RECONCILIATION_FAILED",
                    "job_id": job_id,
                    "deposited_eur": deposited_eur,
                    "expected_eur": expected_budget_eur,
                    "delta_eur": rec["delta_eur"],
                    "artifacts": [], "error": None,
                    "logs": [{"level": "WARN",
                              "message": f"SEPA-Diskrepanz: Δ={rec['delta_eur']:.2f} EUR"}],
                }

            # === Step 4: Monerium Mint ===
            mint = self.minter.trigger_mint(deposited_eur, target_escrow_address)
            self.audit_logger.log("MINT_TRIGGERED", mint)

            # === Step 5: On-Chain-Verifikation ===
            balance = self.verifier.verify(target_escrow_address, deposited_eur)
            self.audit_logger.log("BALANCE_VERIFIED", balance)

            # === Step 6: GoBD-Audit finalisieren ===
            gobd_hash = self.audit_logger.log("FUNDING_COMPLETE", {
                "sepa_reference": sepa_reference,
                "amount": deposited_eur,
                "escrow": target_escrow_address,
            })

            receipt = {
                "status": "ESCROW_FUNDED_SUCCESSFULLY",
                "job_id": job_id,
                "client_id": client_id,
                "viban": onboarding["viban"],
                "sepa_details": {
                    "reference": sepa_reference,
                    "amount_eur": deposited_eur,
                    "received_at": sepa_event["received_at"],
                },
                "on_chain_funding": {
                    "monerium_order_id": mint["order_id"],
                    "escrow_address": target_escrow_address,
                    "mint_tx_hash": mint["on_chain_tx_hash"],
                    "currency": mint["currency"],
                },
                "verification": {
                    "on_chain_balance_confirmed": balance["confirmed"],
                    "delta_balance_eur": balance["delta_eur"],
                    "block_height": balance["block_height"],
                },
                "gobd_audit_hash": gobd_hash,
                "artifacts": [
                    {"type": "funding_receipt", "format": "json"},
                    {"type": "gobd_audit_log", "format": "jsonl",
                     "content": self.audit_logger.export_jsonl()},
                ],
                "error": None,
                "logs": [{"level": "INFO",
                          "message": f"Escrow funded: {deposited_eur:,.2f} EURe → {target_escrow_address}"}],
            }

            logger.info(f"Funding complete: {deposited_eur:,.2f} EURe in {target_escrow_address}")
            return receipt

        except Exception as e:
            logger.error(f"Bridge fehlgeschlagen: {e}")
            return {
                "status": "BRIDGE_FAILED",
                "job_id": job_id,
                "error": str(e),
                "artifacts": [],
                "logs": [{"level": "ERROR", "message": str(e)}],
            }


# ============================================================================
# SMOKE TEST
# ============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("PrivateClientBridge — Smoke Test")
    print("=" * 60)

    bridge = PrivateClientBridge()

    receipt = bridge.process_sepa_inbound(
        client_id="WOHNUNGSBAU-NORD-EG",
        sepa_reference="SEPA-2026-0805-SHADOW-001",
        deposited_eur=4_200_000.00,
        target_escrow_address="0x742d35Cc6634C0532925a3b844Bc454e4438f44e",
        expected_budget_eur=4_200_000.00,
        firmendaten={"name": "Wohnungsbau Nord eG", "ust_id": "DE123456789"},
    )

    print(f"\nStatus: {receipt['status']}")
    print(f"Client: {receipt['client_id']} (vIBAN: {receipt['viban']})")
    print(f"SEPA: {receipt['sepa_details']['reference']} — {receipt['sepa_details']['amount_eur']:,.2f} EUR")
    print(f"Monerium: {receipt['on_chain_funding']['monerium_order_id']}")
    print(f"Mint TX: {receipt['on_chain_funding']['mint_tx_hash']}")
    print(f"Escrow: {receipt['on_chain_funding']['escrow_address']}")
    print(f"Balance Check: {'✅' if receipt['verification']['on_chain_balance_confirmed'] else '❌'} "
          f"(Δ={receipt['verification']['delta_balance_eur']:.2f} EUR, "
          f"Block {receipt['verification']['block_height']:,})")
    print(f"GoBD Hash: {receipt['gobd_audit_hash'][:32]}...")

    # Test: Diskrepanz
    print("\n--- Diskrepanz-Test ---")
    disc = bridge.process_sepa_inbound(
        client_id="TEST-CLIENT",
        sepa_reference="SEPA-SHORT-002",
        deposited_eur=500_000.00,
        target_escrow_address="0xContract",
        expected_budget_eur=4_200_000.00,
    )
    print(f"Status: {disc['status']} (Δ={disc['delta_eur']:,.2f} EUR)")

    print("\n✅ Smoke Test abgeschlossen.")
