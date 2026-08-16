"""Aktion vocabulary + the 9 Wirtschaftsagenten competence profiles (Baustein 2).

Gewaltenteilung: Klasse A (Kapital) darf nicht pruefen, Klasse B (Ausfuehrung)
darf keine Risikoentscheidungen treffen, Klasse C (Governance) darf nicht
selbst ausfuehren. Defizite werden an die zustaendige Klasse delegiert.
"""
from typing import Optional

from agents_b2g.wirtschaft.base import KompetenzKlasse, KompetenzProfil


class Aktion:
    """Canonical capability identifiers."""
    # Klasse A — Kapital & Liquiditaet
    POOL_READ = "pool.read"
    POOL_WRITE = "pool.write"
    TOKEN_TRANSFER = "token.transfer"
    TREASURY_ACCESS = "treasury.access"
    STAKING_REWARDS = "staking.rewards.claim"
    STAKING_DEPOSIT = "staking.deposit"
    STAKING_WITHDRAW = "staking.withdraw"
    VALIDATOR_INFLUENCE = "validator.influence"
    # Klasse B — Ausfuehrung & Abwicklung
    TOKEN_MINT = "token.mint"
    LEDGER_ANCHOR = "ledger.anchor"
    LEDGER_FINALIZE = "ledger.finalize"
    FEE_COLLECT = "fee.collect"
    # Klasse C — Governance & Risiko
    TOKEN_BURN = "token.burn"
    Z3_SOLVE = "z3.solve"
    TX_APPROVE = "tx.approve"
    TX_BLOCK = "tx.block"
    AGENT_DRAIN = "agent.drain"
    # Cross-class / delegated
    COMPLIANCE_CHECK = "compliance.check"
    RISK_ASSESS = "risk.assess"
    SETTLEMENT_COMMIT = "settlement.commit"
    CONTRACT_DEPLOY = "contract.deploy"
    TX_EXECUTE = "tx.execute"


A = KompetenzKlasse.KAPITAL
B = KompetenzKlasse.AUSFUEHRUNG
C = KompetenzKlasse.GOVERNANCE


def _profil(klasse, rechte, defizite=None, genehmigungspflichtig=None,
            routing=None, default_pfad=None):
    return KompetenzProfil(
        klasse=klasse,
        exklusive_rechte=list(rechte),
        defizite=list(defizite or []),
        freigabe_pfad=default_pfad,
        genehmigungspflichtig=list(genehmigungspflichtig or []),
        defizit_routing=dict(routing or {}),
    )


WIRTSCHAFT_PROFILE = {
    # --- Klasse A: Kapital & Liquiditaet ---
    "liquidity": _profil(
        A,
        rechte=[Aktion.POOL_READ, Aktion.POOL_WRITE, Aktion.TOKEN_TRANSFER],
        defizite=[Aktion.COMPLIANCE_CHECK, Aktion.RISK_ASSESS],
        genehmigungspflichtig=[Aktion.TOKEN_TRANSFER],
        routing={Aktion.COMPLIANCE_CHECK: C, Aktion.RISK_ASSESS: C,
                 Aktion.TOKEN_TRANSFER: C},
        default_pfad=C,
    ),
    "treasury": _profil(
        A,
        rechte=[Aktion.TREASURY_ACCESS, Aktion.STAKING_REWARDS],
        defizite=[Aktion.LEDGER_ANCHOR, Aktion.SETTLEMENT_COMMIT],
        routing={Aktion.LEDGER_ANCHOR: B, Aktion.SETTLEMENT_COMMIT: B},
        default_pfad=B,
    ),
    "staking": _profil(
        A,
        rechte=[Aktion.STAKING_DEPOSIT, Aktion.STAKING_WITHDRAW,
                Aktion.VALIDATOR_INFLUENCE],
        defizite=[Aktion.RISK_ASSESS],
        genehmigungspflichtig=[Aktion.STAKING_WITHDRAW],
        routing={Aktion.RISK_ASSESS: C, Aktion.STAKING_WITHDRAW: C},
        default_pfad=C,
    ),
    # --- Klasse B: Ausfuehrung & Abwicklung ---
    "minter": _profil(
        B,
        rechte=[Aktion.TOKEN_MINT, Aktion.LEDGER_ANCHOR],
        genehmigungspflichtig=[Aktion.TOKEN_MINT],
        routing={Aktion.TOKEN_MINT: C},
        default_pfad=C,
    ),
    "settlement": _profil(
        B,
        rechte=[Aktion.LEDGER_FINALIZE, Aktion.TX_EXECUTE],
        genehmigungspflichtig=[Aktion.LEDGER_FINALIZE],
        routing={Aktion.LEDGER_FINALIZE: C},
        default_pfad=C,
    ),
    "paymaster": _profil(
        B,
        rechte=[Aktion.FEE_COLLECT],
        defizite=[Aktion.CONTRACT_DEPLOY],
        genehmigungspflichtig=[Aktion.FEE_COLLECT],
        routing={Aktion.CONTRACT_DEPLOY: B, Aktion.FEE_COLLECT: A},
        default_pfad=A,
    ),
    # --- Klasse C: Governance & Risiko ---
    "burn": _profil(
        C,
        rechte=[Aktion.TOKEN_BURN],
        genehmigungspflichtig=[Aktion.TOKEN_BURN],
        routing={Aktion.TOKEN_BURN: A},
        default_pfad=A,
    ),
    "retention": _profil(
        C,
        rechte=[Aktion.Z3_SOLVE, Aktion.TX_APPROVE, Aktion.TX_BLOCK,
                Aktion.COMPLIANCE_CHECK],
        defizite=[Aktion.TX_EXECUTE],
        routing={Aktion.TX_EXECUTE: B},
        default_pfad=B,
    ),
    "risk_auditor": _profil(
        C,
        rechte=[Aktion.AGENT_DRAIN, Aktion.RISK_ASSESS],
        default_pfad=None,
    ),
}


def profil_fuer(agent_name: str) -> Optional[KompetenzProfil]:
    """Return a fresh KompetenzProfil for one of the 9 agents (or None).

    Returns a copy so agents never share mutable profile state."""
    template = WIRTSCHAFT_PROFILE.get(agent_name)
    if template is None:
        return None
    return KompetenzProfil(
        klasse=template.klasse,
        exklusive_rechte=list(template.exklusive_rechte),
        defizite=list(template.defizite),
        freigabe_pfad=template.freigabe_pfad,
        genehmigungspflichtig=list(template.genehmigungspflichtig),
        defizit_routing=dict(template.defizit_routing),
    )
