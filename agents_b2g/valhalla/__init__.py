"""Valhalla — ZK Honor Protocol. Anonymous authorship, public quality scores.

  H_stamp = α·Z3_SAT + β·TPS − γ·UNSAT + δ·Perfection_Bonus

ZK-Proofs + Nullifier = anonymity. Honor score + Valhalla Ledger = reputation.
Top stamps earn system privileges without ever revealing identity.
"""

from .valhalla import (
    ValhallaOrchestrator, HonorCalculator, ValhallaLedger,
    NullifierManager, ZKProofEngine, PrivilegeManager,
    demo_valhalla,
)

__all__ = [
    "ValhallaOrchestrator", "HonorCalculator", "ValhallaLedger",
    "NullifierManager", "ZKProofEngine", "PrivilegeManager",
    "demo_valhalla",
]
