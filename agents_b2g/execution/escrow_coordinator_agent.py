"""
EscrowCoordinatorAgent — Manages the escrow lifecycle between
Behörde (SEPA), EMI (Monerium), EscrowVault.sol, and Handwerker.

Triggers on events:
  - b2g.payment.inbound     → SEPA detected → Mint EURe → Lock in Vault
  - b2g.installment.approved → BHO green   → Burn EURe → SEPA to contractor
"""
from __future__ import annotations

from typing import Any

from agents_b2g.execution.subagents.emi_bridge import EMIBridgeSubagent


class EscrowCoordinatorAgent:
    """
    Manages the FIAT ↔ EURe ↔ EscrowVault lifecycle.

    The platform never touches FIAT or EURe — the EMI (Monerium) handles
    all regulated activities under its BaFin license.
    """

    def __init__(self, vault_address: str = "0xEscrowVault-Deployed-Address"):
        self.vault_address = vault_address
        self.emi = EMIBridgeSubagent()
        self._deposits: list[dict] = []
        self._disbursements: list[dict] = []

    # ------------------------------------------------------------------
    # INBOUND: Behörde → SEPA → EURe → Vault
    # ------------------------------------------------------------------

    async def handle_sepa_deposit(self, payload: dict[str, Any]) -> dict:
        """
        Event: b2g.payment.inbound
        The Kreiskasse sent a SEPA transfer. Mint EURe into the Vault.
        """
        result = self.emi.handle_sepa_inbound(
            tender_id=payload["tender_id"],
            amount_eur=payload["amount_eur"],
            sepa_reference=payload.get("sepa_reference", f"REF-{payload['tender_id']}"),
            vault_address=self.vault_address,
        )
        self._deposits.append(result)
        return result

    # ------------------------------------------------------------------
    # OUTBOUND: BHO green → Burn EURe → SEPA Instant
    # ------------------------------------------------------------------

    async def handle_installment_release(self, payload: dict[str, Any]) -> dict:
        """
        Event: b2g.installment.approved
        VOB/B + BHO checks passed. Burn EURe, send SEPA-Instant.
        """
        result = self.emi.process_payout_burn(
            tender_id=payload["tender_id"],
            contractor_iban=payload.get("contractor_iban", "DE89370400440532013000"),
            amount_net_eur=payload["amount_net_eur"],
            retention_eur=payload.get("retention_eur", 0),
            vault_address=self.vault_address,
        )
        self._disbursements.append(result)
        return result

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    def get_vault_balance(self) -> dict:
        """Return current vault state (minted - burned)."""
        return {
            "total_minted_eur": self.emi.total_minted,
            "total_burned_eur": self.emi.total_burned,
            "vault_balance_eur": round(self.emi.total_minted - self.emi.total_burned, 2),
            "deposit_count": len(self._deposits),
            "disbursement_count": len(self._disbursements),
        }

    def get_transaction_log(self) -> list[dict]:
        return [
            {"type": "DEPOSIT", **d} for d in self._deposits
        ] + [
            {"type": "DISBURSEMENT", **d} for d in self._disbursements
        ]
