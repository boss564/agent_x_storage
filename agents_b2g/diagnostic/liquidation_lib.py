"""Aave v3 / Spark liquidation helpers for Wave 38 Agent 4.

Topic0 via keccak (same signature as bridge_stufe_a_v3_liquidations_capture.py).
Pool addresses loaded from resolver JSON — never hardcoded.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eth_hash.auto import keccak

from agents_b2g.diagnostic.config import DiagnosticConfig

TOPIC_LIQUIDATION_CALL = (
    "0x"
    + keccak(
        b"LiquidationCall(address,address,address,uint256,uint256,address,bool)"
    ).hex()
)

# View selector for Schicht-B pool verification (resolve-time / fixture)
SEL_GET_RESERVES_LIST = "0x" + keccak(b"getReservesList()")[:4].hex()

DEFAULT_RESOLVED_PATH = (
    DiagnosticConfig.PROJECT_ROOT / "bridge_stufe_a_v3_liquidation_resolved.json"
)

# Coverage gate for liquidations (Bridge coverage_gate: min_day_coverage 0.4)
MIN_COVERAGE_LIQ = 0.40


def word_addr(addr: str) -> str:
    a = addr.lower().removeprefix("0x")
    return "0x" + ("0" * (64 - len(a))) + a


def encode_liquidation_call_log(
    *,
    collateral: str,
    debt: str,
    user: str,
    debt_to_cover: int,
    liq_collateral: int,
    liquidator: str,
    receive_atoken: bool,
) -> tuple[list[str], str]:
    """Build topics + data for fixture LiquidationCall seeding."""
    topics = [
        TOPIC_LIQUIDATION_CALL,
        word_addr(collateral),
        word_addr(debt),
        word_addr(user),
    ]
    data = (
        "0x"
        + format(debt_to_cover, "064x")
        + format(liq_collateral, "064x")
        + word_addr(liquidator)[2:]
        + format(1 if receive_atoken else 0, "064x")
    )
    return topics, data


def parse_liquidation_log(log: dict) -> dict[str, Any]:
    """7-parameter LiquidationCall decode — Topic0 must already match."""
    topics = log.get("topics") or []
    if len(topics) < 4:
        raise ValueError(f"LiquidationCall expected 4 topics, got {len(topics)}")
    data = log.get("data", "0x")
    body = data[2:] if str(data).startswith("0x") else str(data)
    if len(body) < 256:
        raise ValueError(f"LiquidationCall data too short: {data!r}")
    debt_to_cover = str(int(body[0:64], 16))
    liq_coll = str(int(body[64:128], 16))
    liquidator = "0x" + body[128:192][-40:]
    receive = int(body[192:256], 16) != 0
    return {
        "collateral_asset": "0x" + topics[1][-40:],
        "debt_asset": "0x" + topics[2][-40:],
        "user": "0x" + topics[3][-40:],
        "debt_to_cover": debt_to_cover,
        "liquidated_collateral_amount": liq_coll,
        "liquidator": liquidator,
        "receive_atoken": receive,
    }


def load_resolved_pools(path: Path | None = None) -> dict[str, Any]:
    """Load RELEASED liquidation resolver — read-only Bridge artifact as address book."""
    path = path or DEFAULT_RESOLVED_PATH
    body = json.loads(path.read_text(encoding="utf-8"))
    if not body.get("all_resolved") or body.get("capture_release") != "RELEASED":
        raise ValueError(f"liquidation resolved not released: {path}")
    pools = [p for p in body.get("pools", []) if p.get("status") == "RESOLVED"]
    return {
        "path": str(path),
        "all_resolved": True,
        "capture_release": "RELEASED",
        "pools": pools,
        "fixture": False,
    }


def fixture_resolved_pools() -> dict[str, Any]:
    """Offline-Kopie der vier Bridge-resolved Pools.

    §A-NL (Runde 50): das war **kein** Offline-Fixture. `load_resolved_pools()`
    las `bridge_stufe_a_v3_liquidation_resolved.json` aus dem
    Projektwurzel-Verzeichnis — eine Datei, die `.gitignore:81` ausschliesst
    und die nie im Index stand. Im Arbeitsbaum war sie da (aus einem
    früheren Bridge-Lauf), im Klon und im Pre-Commit-Staging-Baum fehlte
    sie. Der Test meldete dort `172/184` statt `281/281`, und der Grund war
    nicht der Test, sondern ein Fixture, das von einem Artefakt abhing.

    Die Adressen sind bei Bridge-Läufen konstant — sie stehen jetzt hier.
    Wer sie gegen den Live-Resolver prüfen will, nimmt
    `load_resolved_pools()`, nicht dieses Fixture.
    """
    return {
        "all_resolved": True,
        "capture_release": "RELEASED",
        "fixture": True,
        "path": "(inline)",
        "pools": [
            {"protocol": "aave_v3", "chain": "ethereum",
             "pool": "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2",
             "n_reserves": 67, "plausibility_check": "pass",
             "status": "RESOLVED"},
            {"protocol": "aave_v3", "chain": "gnosis",
             "pool": "0xb50201558b00496a145fe76f7424749556e326d8",
             "n_reserves": 9, "plausibility_check": "pass",
             "status": "RESOLVED"},
            {"protocol": "spark", "chain": "ethereum",
             "pool": "0xc13e21b648a5ee794902342038ff3adab66be987",
             "n_reserves": 18, "plausibility_check": "pass",
             "status": "RESOLVED"},
            {"protocol": "spark", "chain": "gnosis",
             "pool": "0x2dae5307c5e3fd1cf5a72cb6f698f915860607e0",
             "n_reserves": 9, "plausibility_check": "pass",
             "status": "RESOLVED"},
        ],
    }


def pools_by_protocol(plan: dict[str, Any], protocol: str) -> list[dict[str, Any]]:
    return [
        p
        for p in (plan.get("pools") or [])
        if str(p.get("protocol", "")).lower() == protocol.lower()
    ]


def minute_index(ts: int, window_start_ts: int, n_bins: int) -> int | None:
    idx = (ts - window_start_ts) // 60
    if 0 <= idx < n_bins:
        return idx
    return None


__all__ = [
    "DEFAULT_RESOLVED_PATH",
    "MIN_COVERAGE_LIQ",
    "SEL_GET_RESERVES_LIST",
    "TOPIC_LIQUIDATION_CALL",
    "encode_liquidation_call_log",
    "fixture_resolved_pools",
    "load_resolved_pools",
    "minute_index",
    "parse_liquidation_log",
    "pools_by_protocol",
]
