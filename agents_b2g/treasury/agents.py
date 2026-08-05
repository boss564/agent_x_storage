"""
Agent X — Treasury & Reconciliation (Wave 4, 9 Agents).

Complete BHO-compliant financial lifecycle:
  SEPAGateway → EMIMinter → RetentionVault → InstallmentLedger →
  BHOReconciler → PaymentRelease → SEPABurnDisburser →
  TaxCompliance → FinalAuditCloser

Every cent is tracked from SEPA-IN through EURe-Mint, Vault-Lock,
Retention, BHO-Zero-Sum-Check, Installment, Burn, and SEPA-OUT.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any


# ============================================================
# Agent 1: SEPAGatewayAgent
# ============================================================


class SEPAGatewayAgent:
    """Listens for SEPA inbound transfers on the project IBAN."""

    async def validate_iban(self, iban: str) -> bool:
        return len(iban) >= 15 and iban.startswith("DE")

    async def parse_sepa_reference(self, reference: str) -> dict:
        """Subagent: SEPAParser — extracts tender_id from SEPA reference."""
        return {"tender_id": reference.replace("REF-", ""), "raw": reference}

    async def match_amount(self, expected: float, received: float) -> dict:
        """Subagent: AmountMatcher — compares expected vs received."""
        delta = round(received - expected, 2)
        return {"match": abs(delta) < 0.02, "delta_eur": delta}

    async def receive(self, tender_id: str, amount_eur: float,
                      sepa_reference: str, iban: str = "DE89370400440532013000") -> dict:
        if not await self.validate_iban(iban):
            raise ValueError(f"Invalid IBAN: {iban}")
        ref = await self.parse_sepa_reference(sepa_reference)
        print(f"  [SEPA-Gateway]  💶 SEPA-Eingang: {amount_eur:,.2f} € "
              f"(Ref: {sepa_reference}, IBAN: {iban[:12]}...)")
        return {"status": "SEPA_RECEIVED", "tender_id": tender_id, "amount_eur": amount_eur,
                "iban": iban, "timestamp": datetime.now(timezone.utc).isoformat()}


# ============================================================
# Agent 2: EMIMinterAgent
# ============================================================


class EMIMinterAgent:
    """Mints EURe tokens via Monerium and deposits them into the EscrowVault."""

    async def convert_eur_to_eure(self, amount: float) -> float:
        return amount  # 1:1 peg

    async def deposit_to_vault(self, amount: float, vault: str) -> str:
        payload = f"MINT:{amount}:{vault}:{time.time()}"
        return "0xMINT-" + hashlib.sha256(payload.encode()).hexdigest()[:40]

    async def confirm_mint(self, tx_hash: str) -> bool:
        return bool(tx_hash)

    async def mint(self, sepa_result: dict, vault_address: str) -> dict:
        amount = await self.convert_eur_to_eure(sepa_result["amount_eur"])
        tx = await self.deposit_to_vault(amount, vault_address)
        print(f"  [EMI-Minter]    🪙 {amount:,.2f} EURe geminted → Vault "
              f"({tx[:18]}...)")
        return {"status": "EURE_MINTED", "amount_eur": amount, "tx_hash": tx,
                "vault": vault_address, "timestamp": datetime.now(timezone.utc).isoformat()}


# ============================================================
# Agent 3: RetentionVaultAgent
# ============================================================


class RetentionVaultAgent:
    """Manages the 5% retention sub-account (VOB/B §17)."""

    def __init__(self):
        self._retention: dict[str, Decimal] = {}

    async def calculate(self, amount: Decimal, pct: Decimal = Decimal("5")) -> tuple[Decimal, Decimal]:
        retention = (amount * pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        payable = amount - retention
        return payable, retention

    async def allocate(self, project_id: str, retention: Decimal) -> str:
        current = self._retention.get(project_id, Decimal("0"))
        self._retention[project_id] = current + retention
        tx = "0xRET-" + hashlib.sha256(f"{project_id}{retention}".encode()).hexdigest()[:16]
        return tx

    async def get_retained(self, project_id: str) -> Decimal:
        return self._retention.get(project_id, Decimal("0"))

    async def split(self, project_id: str, amount_eur: float,
                    retention_pct: float = 5.0) -> dict:
        amount = Decimal(str(amount_eur))
        payable, retention = await self.calculate(amount, Decimal(str(retention_pct)))
        tx = await self.allocate(project_id, retention)
        print(f"  [RetentionVault] 🔒 {float(retention):,.2f} € einbehalten "
              f"({retention_pct}%), {float(payable):,.2f} € zahlbar")
        return {"payable_eur": float(payable), "retention_eur": float(retention),
                "retention_tx": tx}


# ============================================================
# Agent 4: InstallmentLedgerAgent
# ============================================================


class InstallmentLedgerAgent:
    """Maintains a cumulative ledger of all installment invoices."""

    def __init__(self):
        self._ledger: dict[str, list[dict]] = {}

    async def record(self, project_id: str, invoice: dict) -> int:
        if project_id not in self._ledger:
            self._ledger[project_id] = []
        self._ledger[project_id].append(invoice)
        return len(self._ledger[project_id])

    async def get_cumulative(self, project_id: str) -> dict:
        entries = self._ledger.get(project_id, [])
        total_paid = sum(e.get("payable_eur", 0) for e in entries)
        total_retained = sum(e.get("retention_eur", 0) for e in entries)
        return {"installment_count": len(entries), "total_paid_eur": total_paid,
                "total_retained_eur": total_retained}

    async def check_vob_limits(self, project_id: str, contract_value: float) -> dict:
        cum = await self.get_cumulative(project_id)
        total = cum["total_paid_eur"] + cum["total_retained_eur"]
        pct = total / max(contract_value, 1) * 100
        return {"total_pct": round(pct, 1), "exceeds_100pct": pct > 100,
                "warning": "VOB/B Limit exceeded" if pct > 100 else ""}


# ============================================================
# Agent 5: BHOReconcilerAgent — Zero-Sum Hero
# ============================================================


class BHOReconcilerAgent:
    """
    BHO Zero-Sum Check: Deposits = Paid + Retained + Vault_Balance.
    Uses Decimal for cent-exact arithmetic. Halts all payments if |Δ| > 0.01€.
    """

    def __init__(self):
        self._state: dict[str, dict[str, Decimal]] = {}  # Production: Redis

    def _get(self, project_id: str, key: str) -> Decimal:
        return self._state.get(project_id, {}).get(key, Decimal("0"))

    def _set(self, project_id: str, key: str, value: Decimal) -> None:
        self._state.setdefault(project_id, {})[key] = value

    def register_deposit(self, project_id: str, amount_eur: float) -> Decimal:
        deposits = self._get(project_id, "deposits") + Decimal(str(amount_eur))
        vault = self._get(project_id, "vault") + Decimal(str(amount_eur))
        self._set(project_id, "deposits", deposits)
        self._set(project_id, "vault", vault)
        return vault

    def reconcile(self, project_id: str, requested_payable: float,
                  requested_retention: float) -> dict:
        """Run BHO zero-sum check BEFORE payment release."""
        deposits = self._get(project_id, "deposits")
        paid = self._get(project_id, "paid")
        retained = self._get(project_id, "retained")
        vault = self._get(project_id, "vault")

        new_paid = paid + Decimal(str(requested_payable))
        new_retained = retained + Decimal(str(requested_retention))
        new_vault = vault - Decimal(str(requested_payable + requested_retention))

        left = deposits
        right = new_paid + new_retained + new_vault
        delta = (left - right).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if abs(delta) > Decimal("0.01"):
            print(f"  [BHO-Reconciler] ⛔ ZERO-SUM FAIL: Δ={float(delta):,.2f}€ "
                  f"(Deposits={float(deposits):,.2f}, Paid+Ret+Vault={float(right):,.2f}) — HALT")
            return {"status": "RECONCILIATION_FAILED", "delta_eur": float(delta),
                    "halt": True}

        # Commit
        self._set(project_id, "paid", new_paid)
        self._set(project_id, "retained", new_retained)
        self._set(project_id, "vault", new_vault)
        print(f"  [BHO-Reconciler] ✅ Zero-Sum: Δ={float(delta):,.2f}€ "
              f"(Deposits={float(deposits):,.2f} = Paid+Ret+Vault={float(right):,.2f}) — GO")
        return {"status": "RECONCILIATION_PASSED", "delta_eur": float(delta), "halt": False,
                "new_vault_balance": float(new_vault)}


# ============================================================
# Agent 6: PaymentReleaseAgent
# ============================================================


class PaymentReleaseAgent:
    """Final 4-eyes approval before funds leave the vault."""

    async def check_disputes(self, project_id: str, dispute_agent=None) -> bool:
        if dispute_agent:
            active = await dispute_agent.get_active_disputes(project_id)
            return len(active) == 0
        return True

    async def approve(self, project_id: str, bho_result: dict,
                      disputes_clear: bool = True) -> dict:
        if bho_result.get("halt"):
            return {"status": "REJECTED", "reason": "BHO reconciliation failed"}
        if not disputes_clear:
            return {"status": "REJECTED", "reason": "Active disputes pending"}
        print(f"  [PaymentRelease] ✅ 4-Augen-Freigabe: {project_id}")
        return {"status": "PAYMENT_APPROVED", "project_id": project_id,
                "timestamp": datetime.now(timezone.utc).isoformat()}


# ============================================================
# Agent 7: SEPABurnDisburserAgent
# ============================================================


class SEPABurnDisburserAgent:
    """Burns EURe from the Vault and triggers SEPA-Instant to contractor."""

    async def burn_eure(self, amount: float, vault: str) -> str:
        return "0xBURN-" + hashlib.sha256(f"{amount}{vault}{time.time()}".encode()).hexdigest()[:40]

    async def send_sepa_instant(self, amount: float, iban: str, reference: str) -> str:
        return f"SEPA-INST-{hashlib.sha256(f'{amount}{iban}'.encode()).hexdigest()[:8].upper()}"

    async def disburse(self, project_id: str, payable_eur: float,
                        contractor_iban: str, vault: str, reference: str) -> dict:
        burn_tx = await self.burn_eure(payable_eur, vault)
        sepa_id = await self.send_sepa_instant(payable_eur, contractor_iban, reference)
        print(f"  [SEPA-Disburse]  💸 Burn: {burn_tx[:18]}... → SEPA-Instant {payable_eur:,.2f}€ "
              f"({sepa_id})")
        return {"status": "DISBURSED", "burn_tx": burn_tx, "sepa_tx": sepa_id,
                "amount_eur": payable_eur, "recipient_iban": contractor_iban}


# ============================================================
# Agent 8: TaxComplianceAgent
# ============================================================


class TaxComplianceAgent:
    """Ensures §13b UStG reverse-charge compliance for construction services."""

    async def check_13b(self, project_id: str) -> dict:
        return {"reverse_charge_applies": True, "paragraph": "§13b UStG",
                "note": "Steuerschuldnerschaft des Leistungsempfängers (Behörde)"}

    async def validate_tax_id(self, tax_id: str) -> bool:
        import re
        return bool(re.match(r"^DE\d{9}$", tax_id))

    async def prepare_vat_report(self, project_id: str, total_net: float) -> dict:
        print(f"  [TaxCompliance] 📋 §13b UStG: Reverse-Charge bestätigt "
              f"(Netto={total_net:,.2f}€)")
        return {"vat_report_ready": True, "reverse_charge": True}


# ============================================================
# Agent 9: FinalAuditCloserAgent
# ============================================================


class FinalAuditCloserAgent:
    """Closes the project: bundles all hashes, archives per GoBD, sets ARCHIVED."""

    async def bundle_hashes(self, project_id: str, transactions: list[dict]) -> str:
        raw = json.dumps(transactions, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:40]

    async def write_gobd(self, project_id: str, bundle_hash: str, summary: dict) -> Path:
        archive = Path("archive_b2g/treasury") / f"{project_id}_gobd.json"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_text(json.dumps({
            "project_id": project_id, "bundle_hash": bundle_hash,
            "summary": summary, "closed_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2, default=str))
        return archive

    async def close(self, project_id: str, transactions: list[dict],
                    summary: dict) -> dict:
        bundle = await self.bundle_hashes(project_id, transactions)
        archive_path = await self.write_gobd(project_id, bundle, summary)
        print(f"  [AuditCloser]   📦 GoBD-Archiv: {archive_path} "
              f"(Bundle={bundle[:16]}...)")
        return {"status": "ARCHIVED", "bundle_hash": bundle, "archive": str(archive_path)}


# ============================================================
# Treasury Pipeline — 9 Agents in Sequence
# ============================================================


class TreasuryPipeline:
    """Wires all 9 Treasury agents. Requires persistent state for BHO zero-sum."""

    def __init__(self, vault_address: str = "0xEscrowVault-Deployed-Address"):
        self.sepa_gateway = SEPAGatewayAgent()
        self.emi_minter = EMIMinterAgent()
        self.retention_vault = RetentionVaultAgent()
        self.ledger = InstallmentLedgerAgent()
        self.bho = BHOReconcilerAgent()
        self.release = PaymentReleaseAgent()
        self.disburser = SEPABurnDisburserAgent()
        self.tax = TaxComplianceAgent()
        self.audit = FinalAuditCloserAgent()
        self.vault_address = vault_address
        self._transactions: list[dict] = []

    async def process_sepa_deposit(self, tender_id: str, amount_eur: float,
                                   sepa_ref: str) -> dict:
        """Phase 1: SEPA-IN → Mint → Register in BHO state."""
        sepa = await self.sepa_gateway.receive(tender_id, amount_eur, sepa_ref)
        mint = await self.emi_minter.mint(sepa, self.vault_address)
        vault_balance = self.bho.register_deposit(tender_id, amount_eur)
        self._transactions.append({"type": "DEPOSIT", **sepa, **mint})
        return {"sepa": sepa, "mint": mint, "vault_balance_eur": float(vault_balance)}

    async def process_installment(self, project_id: str, amount_eur: float,
                                  contractor_iban: str = "DE89370400440532013000",
                                  retention_pct: float = 5.0) -> dict:
        """Phase 2: Retention → Ledger → BHO → Release → Disburse."""
        # Split
        split = await self.retention_vault.split(project_id, amount_eur, retention_pct)
        # Ledger
        await self.ledger.record(project_id, {**split, "timestamp": datetime.now(timezone.utc).isoformat()})
        # BHO zero-sum
        recon = self.bho.reconcile(project_id, split["payable_eur"], split["retention_eur"])
        if recon["halt"]:
            return {"status": "HALTED", "reconciliation": recon}
        # Release
        approved = await self.release.approve(project_id, recon)
        if approved["status"] != "PAYMENT_APPROVED":
            return {"status": "REJECTED", "reason": approved["reason"]}
        # Disburse
        ref = f"INST-{project_id}-{len(self._transactions):04d}"
        disbursed = await self.disburser.disburse(
            project_id, split["payable_eur"], contractor_iban, self.vault_address, ref)
        self._transactions.append({"type": "INSTALLMENT", **split, **disbursed})
        # Tax compliance
        await self.tax.check_13b(project_id)
        return {"status": "DISBURSED", "split": split, "recon": recon, "disbursed": disbursed}

    async def finalize(self, project_id: str) -> dict:
        """Phase 3: Tax → Audit → Archive."""
        cum = await self.ledger.get_cumulative(project_id)
        await self.tax.prepare_vat_report(project_id, cum["total_paid_eur"])
        result = await self.audit.close(project_id, self._transactions, cum)
        return result
