"""Intent-relayer + Stablecoin mint/burn helpers for Wave 38 Agent 5.

Corrected Bridge V3 signatures (keccak Topic0):
  CoW Trade: 7-param (not 8)
  PSM BuyGem/SellGem: 3-param (not 4)
  Across: FilledRelay + FilledV3Relay (migration-safe)
  CCTP V1 + V2 (V2 MintAndWithdraw includes feeCollected)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eth_hash.auto import keccak

from agents_b2g.diagnostic.config import DiagnosticConfig

# --- Topics (single source of truth, same as Bridge V3 capture scripts) -------

TOPIC_BY_EVENT: dict[str, str] = {
    "across_filled_relay": "0x"
    + keccak(
        b"FilledRelay(bytes32,bytes32,uint256,uint256,uint256,uint256,uint256,"
        b"uint32,uint32,bytes32,bytes32,bytes32,bytes32,bytes32,"
        b"(bytes32,bytes32,uint256,uint8))"
    ).hex(),
    "across_filled_v3_relay": "0x"
    + keccak(
        b"FilledV3Relay(address,address,uint256,uint256,uint256,uint256,uint32,"
        b"uint32,uint32,address,address,address,address,bytes,"
        b"(address,bytes,uint256,uint8))"
    ).hex(),
    "cow_trade": "0x"
    + keccak(b"Trade(address,address,address,uint256,uint256,uint256,bytes)").hex(),
    "psm_buy_gem": "0x" + keccak(b"BuyGem(address,uint256,uint256)").hex(),
    "psm_sell_gem": "0x" + keccak(b"SellGem(address,uint256,uint256)").hex(),
    "cctp_v1_deposit_for_burn": "0x"
    + keccak(
        b"DepositForBurn(uint64,address,uint256,address,bytes32,uint32,bytes32,bytes32)"
    ).hex(),
    "cctp_v1_mint_and_withdraw": "0x"
    + keccak(b"MintAndWithdraw(address,uint256,address)").hex(),
    "cctp_v2_deposit_for_burn": "0x"
    + keccak(
        b"DepositForBurn(address,uint256,address,bytes32,uint32,bytes32,bytes32,"
        b"uint256,uint32,bytes)"
    ).hex(),
    "cctp_v2_mint_and_withdraw": "0x"
    + keccak(b"MintAndWithdraw(address,uint256,address,uint256)").hex(),
}

EVENT_NAME: dict[str, str] = {
    "across_filled_relay": "FilledRelay",
    "across_filled_v3_relay": "FilledV3Relay",
    "cow_trade": "Trade",
    "psm_buy_gem": "BuyGem",
    "psm_sell_gem": "SellGem",
    "cctp_v1_deposit_for_burn": "DepositForBurn",
    "cctp_v1_mint_and_withdraw": "MintAndWithdraw",
    "cctp_v2_deposit_for_burn": "DepositForBurn",
    "cctp_v2_mint_and_withdraw": "MintAndWithdraw",
}

DEFAULT_INTENT_RESOLVED = (
    DiagnosticConfig.PROJECT_ROOT / "bridge_stufe_a_v3_intent_relayer_resolved.json"
)
DEFAULT_STABLE_RESOLVED = (
    DiagnosticConfig.PROJECT_ROOT
    / "bridge_stufe_a_v3_stablecoin_mint_burn_resolved.json"
)

# Bridge coverage_gate: intent 0.6, stablecoin 0.6
MIN_COVERAGE_INTENT_STABLE = 0.60

# Wrong signatures (must NOT match) — regression guards
WRONG_COW_TRADE_8 = (
    "0x"
    + keccak(
        b"Trade(address,address,address,uint256,uint256,uint256,uint256,bytes)"
    ).hex()
)
WRONG_PSM_BUY_4 = (
    "0x" + keccak(b"BuyGem(address,address,uint256,uint256)").hex()
)


def topic_for(event_key: str) -> str:
    return TOPIC_BY_EVENT[event_key]


def event_key_for_topic(topic: str) -> str | None:
    t = topic.lower()
    for key, val in TOPIC_BY_EVENT.items():
        if val.lower() == t:
            return key
    return None


def _load_resolved(path: Path) -> dict[str, Any]:
    body = json.loads(path.read_text(encoding="utf-8"))
    if not body.get("all_resolved") or body.get("capture_release") != "RELEASED":
        raise ValueError(f"resolved not released: {path}")
    contracts = [c for c in body.get("contracts", []) if c.get("status") == "RESOLVED"]
    return {
        "path": str(path),
        "all_resolved": True,
        "capture_release": "RELEASED",
        "contracts": contracts,
        "fixture": False,
    }


def load_intent_resolved(path: Path | None = None) -> dict[str, Any]:
    return _load_resolved(path or DEFAULT_INTENT_RESOLVED)


def load_stable_resolved(path: Path | None = None) -> dict[str, Any]:
    return _load_resolved(path or DEFAULT_STABLE_RESOLVED)


# §A-NL (Runde 50): Die vier Adressen sind bei Bridge-Läufen konstant
# (RESOLVED, plausibility pass). Sie standen nur in einer
# `.gitignore`-Datei, nie im Index — der Staging-Baum des Pre-Commit-Hooks
# hatte sie nicht, und `test_wave38_diagnostic` fiel dort auf 172/184.
# Ein Fixture liest keine Laufzeit-Artefakte.
_FIXTURE_INTENT_CONTRACTS: list[dict[str, Any]] = [
    {
        "protocol": "across", "chain": "ethereum", "role": "spoke_pool",
        "address": "0x5c7bcd6e7de5423a257d81b442095a1a6ced35c5",
        "events": ["across_filled_relay", "across_filled_v3_relay"],
        "status": "RESOLVED", "plausibility_check": "pass",
    },
    {
        "protocol": "cow", "chain": "ethereum", "role": "gpv2_settlement",
        "address": "0x9008d19f58aabd9ed0d60971565aa8510560ab41",
        "events": ["cow_trade"],
        "status": "RESOLVED", "plausibility_check": "pass",
    },
    {
        "protocol": "cow", "chain": "gnosis", "role": "gpv2_settlement",
        "address": "0x9008d19f58aabd9ed0d60971565aa8510560ab41",
        "events": ["cow_trade"],
        "status": "RESOLVED", "plausibility_check": "pass",
    },
]

_FIXTURE_STABLE_CONTRACTS: list[dict[str, Any]] = [
    {
        "protocol": "lite_psm", "chain": "ethereum", "role": "psm",
        "address": "0xf6e72db5454dd049d0788e411b06cfaf16853042",
        "events": ["psm_buy_gem", "psm_sell_gem"],
        "status": "RESOLVED", "plausibility_check": "pass",
    },
    {
        "protocol": "classic_psm", "chain": "ethereum", "role": "psm",
        "address": "0x89b78cfa322f6c5de0abceecab66aee45393cc5a",
        "events": ["psm_buy_gem", "psm_sell_gem"],
        "status": "RESOLVED", "plausibility_check": "pass",
    },
    {
        "protocol": "cctp_v1", "chain": "ethereum", "role": "token_messenger",
        "address": "0xbd3fa81b58ba92a82136038b25adec7066af3155",
        "events": ["cctp_v1_deposit_for_burn", "cctp_v1_mint_and_withdraw"],
        "status": "RESOLVED", "plausibility_check": "pass",
    },
    {
        "protocol": "cctp_v2", "chain": "ethereum", "role": "token_messenger",
        "address": "0x28b5a0e9c621a5badaa536219b3a228c8168cf5d",
        "events": ["cctp_v2_deposit_for_burn", "cctp_v2_mint_and_withdraw"],
        "status": "RESOLVED", "plausibility_check": "pass",
    },
]


def fixture_intent_resolved() -> dict[str, Any]:
    """Offline-Fixture — keine Laufzeit-Datei (Runde 50, §A-NL)."""
    return {
        "all_resolved": True,
        "capture_release": "RELEASED",
        "fixture": True,
        "path": "(inline)",
        "contracts": [dict(c) for c in _FIXTURE_INTENT_CONTRACTS],
    }


def fixture_stable_resolved() -> dict[str, Any]:
    """Offline-Fixture — keine Laufzeit-Datei (Runde 50, §A-NL)."""
    return {
        "all_resolved": True,
        "capture_release": "RELEASED",
        "fixture": True,
        "path": "(inline)",
        "contracts": [dict(c) for c in _FIXTURE_STABLE_CONTRACTS],
    }


def contracts_by_protocol(plan: dict[str, Any], protocol: str) -> list[dict[str, Any]]:
    return [
        c
        for c in (plan.get("contracts") or [])
        if str(c.get("protocol", "")).lower() == protocol.lower()
    ]


def minute_index(ts: int, window_start_ts: int, n_bins: int) -> int | None:
    idx = (ts - window_start_ts) // 60
    if 0 <= idx < n_bins:
        return idx
    return None


def family_for_protocol(protocol: str) -> str:
    p = protocol.lower()
    if p in ("across", "cow"):
        return "intent_relayers"
    return "stablecoin_mint_burn"


__all__ = [
    "DEFAULT_INTENT_RESOLVED",
    "DEFAULT_STABLE_RESOLVED",
    "EVENT_NAME",
    "MIN_COVERAGE_INTENT_STABLE",
    "TOPIC_BY_EVENT",
    "WRONG_COW_TRADE_8",
    "WRONG_PSM_BUY_4",
    "contracts_by_protocol",
    "event_key_for_topic",
    "family_for_protocol",
    "fixture_intent_resolved",
    "fixture_stable_resolved",
    "load_intent_resolved",
    "load_stable_resolved",
    "minute_index",
    "topic_for",
]
