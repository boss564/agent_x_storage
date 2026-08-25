"""MEV-cluster helpers for Wave 38 Agent 3 — address normalize, exclusion, EOA."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents_b2g.diagnostic.config import DiagnosticConfig

# Bridge method-reference list (read-only); Wave 38 binds via wave38_mev_exclusion_list.json
DEFAULT_EXCLUSION_PATH = (
    DiagnosticConfig.PROJECT_ROOT / "config" / "wave38_mev_exclusion_list.json"
)

# Fixture addresses for cross-chain EOA occupancy tests
FIXTURE_EOA_A = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
FIXTURE_EOA_B = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
FIXTURE_CONTRACT = "0xcccccccccccccccccccccccccccccccccccccccc"
# OmniBridge mediator ETH — must appear in binding exclusion list
FIXTURE_EXCLUDED = "0x88ad09518695c6c3712ac10a214be5109a655671"


def normalize_address(addr: str | None) -> str:
    """Lowercase hex address; strip EIP-55 casing. Empty if invalid."""
    if not addr:
        return ""
    a = str(addr).strip().lower()
    if not a.startswith("0x") or len(a) != 42:
        return ""
    try:
        int(a[2:], 16)
    except ValueError:
        return ""
    return a


def minute_bucket(ts: int) -> int:
    """Same UTC minute join key: t // 60 (not |Δt| ≤ 60 s)."""
    return int(ts) // 60


def is_eoa_code(code: Any) -> bool:
    return code in ("0x", "0x0", "", None)


def load_exclusion_list(path: Path | None = None) -> set[str]:
    """Load Wave 38 exclusion set; resolve `inherits` to Bridge V3 list."""
    path = path or DEFAULT_EXCLUSION_PATH
    body = json.loads(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    inherits = body.get("inherits")
    if inherits:
        inh = Path(inherits)
        if not inh.is_absolute():
            inh = DiagnosticConfig.PROJECT_ROOT / inh
        parent = json.loads(inh.read_text(encoding="utf-8"))
        for e in parent.get("entries") or []:
            a = normalize_address(e.get("address"))
            if a:
                out.add(a)
    for e in body.get("entries") or []:
        a = normalize_address(e.get("address"))
        if a:
            out.add(a)
    return out


def fixture_seed_transactions(
    *,
    window_start_ts: int = 1_700_000_000,
    n_occupied_minutes: int = 5,
) -> list[dict[str, Any]]:
    """Synthetic success txs for cross-chain EOA matching + exclusion/contract negatives."""
    rows: list[dict[str, Any]] = []
    base_min = minute_bucket(window_start_ts) + 10
    # Shared EOAs on both chains, same minute → occupancy
    for i in range(n_occupied_minutes):
        minute = base_min + i
        ts = minute * 60
        for chain, eoa, salt in (
            ("ethereum", FIXTURE_EOA_A, "aa"),
            ("gnosis", FIXTURE_EOA_A, "ab"),
            ("ethereum", FIXTURE_EOA_B, "ba"),
            ("gnosis", FIXTURE_EOA_B, "bb"),
        ):
            rows.append(
                {
                    "chain": chain,
                    "tx_hash": f"0x{salt}{i:02x}{'00' * 28}"[:66],
                    "block_number": 1000 + i,
                    "timestamp": ts,
                    "tx_from": eoa,
                    "status": 1,
                }
            )
    # Excluded bridge address on both chains same minute — must not occupy
    excl_min = base_min + n_occupied_minutes
    excl_ts = excl_min * 60
    for chain, salt in (("ethereum", "ee"), ("gnosis", "ef")):
        rows.append(
            {
                "chain": chain,
                "tx_hash": f"0x{salt}{'11' * 30}"[:66],
                "block_number": 2000,
                "timestamp": excl_ts,
                "tx_from": FIXTURE_EXCLUDED,
                "status": 1,
            }
        )
    # Contract on both chains same minute — EOA filter drops it
    c_min = excl_min + 1
    c_ts = c_min * 60
    for chain, salt in (("ethereum", "cc"), ("gnosis", "cd")):
        rows.append(
            {
                "chain": chain,
                "tx_hash": f"0x{salt}{'22' * 30}"[:66],
                "block_number": 3000,
                "timestamp": c_ts,
                "tx_from": FIXTURE_CONTRACT,
                "status": 1,
            }
        )
    # Failed TX — must be ignored by extractor
    rows.append(
        {
            "chain": "ethereum",
            "tx_hash": f"0x{'ff' * 32}",
            "block_number": 4000,
            "timestamp": (base_min + 50) * 60,
            "tx_from": FIXTURE_EOA_A,
            "status": 0,
        }
    )
    return rows


__all__ = [
    "DEFAULT_EXCLUSION_PATH",
    "FIXTURE_CONTRACT",
    "FIXTURE_EOA_A",
    "FIXTURE_EOA_B",
    "FIXTURE_EXCLUDED",
    "fixture_seed_transactions",
    "is_eoa_code",
    "load_exclusion_list",
    "minute_bucket",
    "normalize_address",
]
