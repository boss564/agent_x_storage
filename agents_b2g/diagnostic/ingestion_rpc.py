"""RPC transport for Wave 38 DataIngestion — wraps bridge_stufe_a_rpc (code reuse).

Fixture/mock mode for unit tests; live mode probes public RPC fallbacks.
Never writes sealed Bridge reference artifacts.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from bridge_stufe_a_rpc import (  # noqa: E402
    CHUNK_BLOCKS,
    DEFAULT_RPCS,
    ETH_HTTP_FALLBACKS,
    GNOSIS_HTTP_FALLBACKS,
    RangeTooLarge,
    RpcError,
    as_int,
    jsonrpc,
    redact_url,
)


class RpcTransport(Protocol):
    def eth_block_number(self, chain: str) -> int: ...

    def eth_get_block_by_number(self, chain: str, block: int) -> dict[str, Any]: ...

    def eth_get_block_receipts(self, chain: str, block: int) -> list[dict[str, Any]]: ...

    def eth_get_code(self, chain: str, address: str) -> str: ...

    def active_url(self, chain: str) -> str: ...


@dataclass
class FixtureRpcTransport:
    """Deterministic offline RPC for tests — no network."""

    eth_latest: int = 20_000_100
    gnosis_latest: int = 35_000_050
    # Addresses whose eth_getCode returns bytecode (contracts); all others are EOAs.
    contract_code: dict[str, str] = field(default_factory=dict)
    _urls: dict[str, str] = field(
        default_factory=lambda: {
            "ethereum": "fixture://ethereum",
            "gnosis": "fixture://gnosis",
        }
    )

    def eth_block_number(self, chain: str) -> int:
        return self.eth_latest if chain == "ethereum" else self.gnosis_latest

    def eth_get_block_by_number(self, chain: str, block: int) -> dict[str, Any]:
        latest = self.eth_block_number(chain)
        if block < 0 or block > latest:
            raise RpcError(f"block {block} out of range")
        # Synthetic timestamps: ~12s eth, ~5s gnosis
        step = 12 if chain == "ethereum" else 5
        base = 1_700_000_000
        return {
            "number": hex(block),
            "timestamp": hex(base + block * step),
            "hash": f"0x{'ab' if chain == 'ethereum' else 'cd'}{block:060x}"[:66],
            "transactions": [],
        }

    def eth_get_block_receipts(self, chain: str, block: int) -> list[dict[str, Any]]:
        # One synthetic receipt with one log for smoke coverage (+ tx.from for MEV)
        tx = f"0x{'11' if chain == 'ethereum' else '22'}{block:060x}"[:66]
        # Deterministic per-chain from — Agent 3 fixture seed adds cross-chain EOAs
        frm = (
            "0xe100000000000000000000000000000000000001"
            if chain == "ethereum"
            else "0xe100000000000000000000000000000000000002"
        )
        return [
            {
                "transactionHash": tx,
                "blockNumber": hex(block),
                "status": "0x1",
                "from": frm,
                "logs": [
                    {
                        "address": "0x" + ("a" * 40),
                        "topics": ["0x" + ("b" * 64)],
                        "data": "0x",
                        "logIndex": "0x0",
                        "transactionHash": tx,
                        "blockNumber": hex(block),
                    }
                ],
            }
        ]

    def eth_get_code(self, chain: str, address: str) -> str:
        key = (address or "").lower()
        if key in self.contract_code:
            return self.contract_code[key]
        return "0x"

    def active_url(self, chain: str) -> str:
        return self._urls.get(chain, f"fixture://{chain}")


@dataclass
class LiveRpcTransport:
    """Probes fallbacks; uses bridge_stufe_a_rpc.jsonrpc."""

    urls: dict[str, str] = field(default_factory=dict)
    chunk_blocks: dict[str, int] = field(default_factory=lambda: dict(CHUNK_BLOCKS))

    def __post_init__(self) -> None:
        if not self.urls:
            self.urls = {
                "ethereum": DEFAULT_RPCS["ethereum"],
                "gnosis": DEFAULT_RPCS["gnosis"],
            }

    @staticmethod
    def fallbacks(chain: str) -> list[str]:
        if chain == "ethereum":
            return [u for u in ETH_HTTP_FALLBACKS if u]
        if chain == "gnosis":
            return [u for u in GNOSIS_HTTP_FALLBACKS if u]
        primary = os.environ.get(f"{chain.upper()}_RPC")
        return [u for u in [primary, DEFAULT_RPCS.get(chain)] if u]

    def probe(self, chain: str) -> str:
        errors: list[str] = []
        for url in self.fallbacks(chain):
            try:
                block = as_int(jsonrpc(url, "eth_blockNumber", [], retries=2))
                if block <= 0:
                    raise RpcError(f"invalid block {block}")
                self.urls[chain] = url
                return url
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{redact_url(url)}: {exc}")
        raise RpcError(f"all RPCs failed for {chain}: {' | '.join(errors)}")

    def active_url(self, chain: str) -> str:
        if chain not in self.urls:
            return self.probe(chain)
        return self.urls[chain]

    def eth_block_number(self, chain: str) -> int:
        url = self.active_url(chain)
        return as_int(jsonrpc(url, "eth_blockNumber", []))

    def eth_get_block_by_number(self, chain: str, block: int) -> dict[str, Any]:
        url = self.active_url(chain)
        blk = jsonrpc(url, "eth_getBlockByNumber", [hex(block), False])
        if not blk:
            raise RpcError(f"empty block {block} on {chain}")
        return blk

    def eth_get_block_receipts(self, chain: str, block: int) -> list[dict[str, Any]]:
        url = self.active_url(chain)
        try:
            result = jsonrpc(url, "eth_getBlockReceipts", [hex(block)], retries=2)
            if isinstance(result, list):
                return result
        except RpcError:
            pass
        # Fallback: empty list — callers may use eth_getTransactionReceipt later
        return []

    def eth_get_code(self, chain: str, address: str) -> str:
        url = self.active_url(chain)
        code = jsonrpc(url, "eth_getCode", [address, "latest"], retries=2)
        return str(code) if code is not None else "0x"


def default_chunk_width(chain: str) -> int:
    return int(CHUNK_BLOCKS.get(chain, 2_000))


__all__ = [
    "FixtureRpcTransport",
    "LiveRpcTransport",
    "RangeTooLarge",
    "RpcError",
    "RpcTransport",
    "as_int",
    "default_chunk_width",
    "redact_url",
]
