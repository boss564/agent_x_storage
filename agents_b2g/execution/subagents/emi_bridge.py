"""
EMI Bridge Subagent — Monerium EURe / SEPA-Instant Integration.

Connects public-sector FIAT rails (Kreiskasse SEPA) with on-chain escrow
(EscrowVault.sol) via a licensed E-Money Institute (Monerium).

Flow:
  Behörde → SEPA on Project-IBAN → Monerium detects → Mints EURe into Vault
  BHO green → Burn EURe → SEPA Instant to contractor IBAN

Regulatory: ZAG / KWG compliant — the platform never touches FIAT or EURe.
The EMI (Monerium) handles all regulated activities under its BaFin license.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


class EMIBridgeSubagent:
    """
    Interface to the E-Money Institute (Monerium EURe).

    Converts inbound SEPA deposits into EURe tokens locked in the
    EscrowVault, and executes SEPA-Instant payouts upon BHO approval.
    """

    def __init__(self, emi_provider: str = "Monerium_EURe_EMI"):
        self.emi_provider = emi_provider
        self._mint_log: list[dict] = []
        self._burn_log: list[dict] = []

    # ------------------------------------------------------------------
    # INBOUND: SEPA → Mint EURe → Lock in Vault
    # ------------------------------------------------------------------

    def handle_sepa_inbound(
        self,
        tender_id: str,
        amount_eur: float,
        sepa_reference: str,
        vault_address: str,
    ) -> dict[str, Any]:
        """
        Triggered when the Kreiskasse sends a SEPA transfer to the project IBAN.
        Instructs the EMI to mint EURe tokens into the EscrowVault.
        """
        if tender_id not in sepa_reference and sepa_reference != f"REF-{tender_id}":
            raise ValueError(
                f"SEPA reference '{sepa_reference}' does not match tender {tender_id}"
            )

        mint_result = self._monerium_mint(amount_eur, vault_address)
        self._mint_log.append(mint_result)

        print(f"  [EMI-Bridge]    💶 SEPA-IN: {amount_eur:,.2f} € → "
              f"{mint_result['tx_hash'][:18]}... (Vault: {vault_address[:12]}...)")

        return {
            "status": "EURE_MINTED_TO_VAULT",
            "tender_id": tender_id,
            "amount_eur": amount_eur,
            "mint_tx_hash": mint_result["tx_hash"],
            "vault_address": vault_address,
            "timestamp": mint_result["timestamp"],
        }

    # ------------------------------------------------------------------
    # OUTBOUND: Burn EURe → SEPA Instant
    # ------------------------------------------------------------------

    def process_payout_burn(
        self,
        tender_id: str,
        contractor_iban: str,
        amount_net_eur: float,
        retention_eur: float,
        vault_address: str,
    ) -> dict[str, Any]:
        """
        BHO reconciliation green → burn EURe tokens from the EscrowVault
        and send SEPA-Instant to the contractor's IBAN.
        """
        payable = round(amount_net_eur - retention_eur, 2)

        burn_result = self._monerium_burn_and_sepa(payable, contractor_iban)
        self._burn_log.append(burn_result)

        print(f"  [EMI-Bridge]    💸 SEPA-OUT: {payable:,.2f} € → "
              f"{contractor_iban[:12]}... (Burn: {burn_result['burn_hash'][:18]}...)")

        return {
            "status": "SEPA_INSTANT_DISBURSED",
            "tender_id": tender_id,
            "gross_amount_eur": amount_net_eur,
            "retention_5pct_eur": retention_eur,
            "net_paid_eur": payable,
            "recipient_iban": contractor_iban,
            "sepa_instant_tx_id": burn_result["sepa_tx_id"],
            "burn_tx_hash": burn_result["burn_hash"],
            "timestamp": burn_result["timestamp"],
        }

    # ------------------------------------------------------------------
    # Simulated Monerium API (production: real REST calls)
    # ------------------------------------------------------------------

    def _monerium_mint(self, amount: float, vault_address: str) -> dict:
        ts = datetime.now(timezone.utc).isoformat()
        payload = f"MINT:{amount}:{vault_address}:{ts}"
        return {
            "tx_hash": "0xMINT-" + hashlib.sha256(payload.encode()).hexdigest()[:40],
            "timestamp": ts,
        }

    def _monerium_burn_and_sepa(self, amount: float, iban: str) -> dict:
        ts = datetime.now(timezone.utc).isoformat()
        payload = f"BURN:{amount}:{iban}:{ts}"
        burn_hash = "0xBURN-" + hashlib.sha256(payload.encode()).hexdigest()[:40]
        sepa_id = f"SEPA-INST-{burn_hash[6:14].upper()}"
        return {"burn_hash": burn_hash, "sepa_tx_id": sepa_id, "timestamp": ts}

    @property
    def total_minted(self) -> float:
        return sum(m["amount_eur"] for m in self._mint_log if "amount_eur" in m)

    @property
    def total_burned(self) -> float:
        return sum(b.get("net_paid_eur", 0) for b in self._burn_log)
