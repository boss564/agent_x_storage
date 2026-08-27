"""Untrusted shell — synthetic strategy proposals (no LLM required).

Phase-1 pilot: shell invents parameters; core alone verifies.
"""
from __future__ import annotations

import hashlib
from typing import Literal

from prototypes.raas_hybrid_shell.schemas import LLMStrategyProposal

Kind = Literal["mild", "aggressive"]


def propose(kind: Kind = "mild") -> LLMStrategyProposal:
    """Deterministic synthetic proposals — recognizably non-measured."""
    if kind == "aggressive":
        body = {
            "label": "SYNTHETIC_AGGRESSIVE",
            "rebalance_interval_h": 0.01,
            "max_slippage_pct": 99.99,
            "latency_budget_ms": 1.0,
            "profile_hint": "aggressive",
        }
    else:
        body = {
            "label": "SYNTHETIC_MILD",
            "rebalance_interval_h": 4.0,
            "max_slippage_pct": 0.5,
            "latency_budget_ms": 500.0,
            "profile_hint": "default",
        }
    dig = hashlib.sha256(
        f"{kind}|{body['max_slippage_pct']}|{body['profile_hint']}".encode()
    ).hexdigest()[:16]
    return LLMStrategyProposal(proposal_id=f"shell-{dig}", **body)
