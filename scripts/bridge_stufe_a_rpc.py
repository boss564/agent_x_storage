"""HTTP JSON-RPC helpers for Stufe-A capture. No web3 dependency."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any


def _load_dotenv() -> None:
    """Load gitignored .env from repo root without overriding the process env."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, ".env")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


_load_dotenv()

USER_AGENT = "agent-x-bridge-stufe-a/1.0"

ETH_HTTP_FALLBACKS = [
    os.environ.get("ETH_RPC") or os.environ.get("ETHEREUM_RPC") or "https://ethereum-rpc.publicnode.com",
    "https://eth.llamarpc.com",
    "https://rpc.ankr.com/eth",
    "https://eth.drpc.org",
    "https://1rpc.io/eth",
    "https://cloudflare-eth.com",
]

# Public Gnosis first: Alchemy getLogs returns HTTP 400 above ~10 blocks.
GNOSIS_HTTP_FALLBACKS = [
    "https://rpc.gnosischain.com",
    "https://gnosis.drpc.org",
    "https://1rpc.io/gnosis",
    os.environ.get("GNOSIS_RPC") or "",
]

DEFAULT_RPCS = {
    "ethereum": ETH_HTTP_FALLBACKS[0],
    "gnosis": next((u for u in GNOSIS_HTTP_FALLBACKS if u), "https://rpc.gnosischain.com"),
    "arbitrum": os.environ.get("ARBITRUM_RPC", "https://arb1.arbitrum.io/rpc"),
}

CHUNK_BLOCKS = {
    "ethereum": 2_000,
    "gnosis": 5_000,
    "arbitrum": 10_000,
}
MIN_GETLOGS_WIDTH = 32


def as_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 16) if value.startswith("0x") else int(value)
    raise TypeError(f"cannot parse int from {type(value)}")


def redact_url(url: str) -> str:
    if not url:
        return ""
    cut = url.split("?")[0]
    if "://" in cut:
        scheme, rest = cut.split("://", 1)
        host = rest.split("/")[0]
        return f"{scheme}://{host}"
    return cut


def http_json(url: str, payload: dict | None = None, timeout: float = 30.0) -> Any:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
        method="GET" if data is None else "POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def jsonrpc(url: str, method: str, params: list, timeout: float = 45.0, retries: int = 4) -> Any:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            body = http_json(
                url,
                {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                timeout=timeout,
            )
            if isinstance(body, dict) and body.get("error"):
                err = body["error"]
                code = err.get("code") if isinstance(err, dict) else None
                msg = str(err)
                if code in (-32005, -32602, -32000) or "range" in msg.lower() or "too many" in msg.lower():
                    raise RangeTooLarge(msg)
                raise RpcError(msg)
            return body.get("result") if isinstance(body, dict) else body
        except RangeTooLarge:
            raise
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code in (401, 403, 404):
                raise RpcError(f"HTTP {exc.code} from endpoint") from exc
            # Alchemy (Gnosis) returns HTTP 400 for over-wide eth_getLogs; do not retry.
            if exc.code == 400 and method == "eth_getLogs":
                raise RangeTooLarge(f"HTTP 400 {method}") from exc
            time.sleep(min(2 ** attempt, 8))
        except (urllib.error.URLError, TimeoutError, RpcError, OSError) as exc:
            last_err = exc
            time.sleep(min(2 ** attempt, 8))
    raise RpcError(f"{method} failed after {retries} retries: {last_err}")


def jsonrpc_batch(
    url: str,
    calls: list[tuple[str, list]],
    timeout: float = 90.0,
    retries: int = 4,
) -> list[Any]:
    """Execute a JSON-RPC batch. calls = [(method, params), ...]. Returns results in order."""
    if not calls:
        return []
    payload = [
        {"jsonrpc": "2.0", "id": i, "method": method, "params": params}
        for i, (method, params) in enumerate(calls)
    ]
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            body = http_json(url, payload, timeout=timeout)
            if isinstance(body, dict) and body.get("error"):
                # single-call path handled in jsonrpc; batch items below
                pass
            if not isinstance(body, list):
                raise RpcError(f"batch returned {type(body)}")
            by_id: dict[int, Any] = {}
            for item in body:
                if not isinstance(item, dict):
                    continue
                if item.get("error"):
                    err = item["error"]
                    msg = str(err)
                    code = err.get("code") if isinstance(err, dict) else None
                    low = msg.lower()
                    if (
                        code in (-32005, -32602, -32000, -32003)
                        or "range" in low
                        or "too many" in low
                        or "too large" in low
                        or "response size" in low
                    ):
                        raise RangeTooLarge(msg)
                    raise RpcError(msg)
                by_id[int(item["id"])] = item.get("result")
            return [by_id[i] for i in range(len(calls))]
        except RangeTooLarge:
            raise
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code in (401, 403, 404):
                raise RpcError(f"HTTP {exc.code} from endpoint") from exc
            if exc.code == 413:
                raise RangeTooLarge("batch too large") from exc
            time.sleep(min(2 ** attempt, 8))
        except (urllib.error.URLError, TimeoutError, RpcError, OSError) as exc:
            last_err = exc
            # Some providers return size errors as RpcError from earlier parsing
            if "too large" in str(exc).lower():
                raise RangeTooLarge(str(exc)) from exc
            time.sleep(min(2 ** attempt, 8))
    raise RpcError(f"jsonrpc_batch failed after {retries} retries: {last_err}")


class RpcError(RuntimeError):
    pass


class RangeTooLarge(RpcError):
    pass


def latest_block(url: str) -> int:
    return as_int(jsonrpc(url, "eth_blockNumber", []))


def block_timestamp(url: str, block: int, cache: dict[int, int] | None = None) -> int:
    if cache is not None and block in cache:
        return cache[block]
    blk = jsonrpc(url, "eth_getBlockByNumber", [hex(block), False])
    if not blk:
        raise RpcError(f"empty block {block}")
    ts = as_int(blk["timestamp"])
    if cache is not None:
        cache[block] = ts
    return ts


def timestamp_to_block(url: str, timestamp: int, cache: dict[int, int] | None = None) -> int:
    """Smallest block with ts >= timestamp (binary search)."""
    hi = latest_block(url)
    print(
        f"timestamp_to_block {redact_url(url)} ts={timestamp} latest={hi}",
        flush=True,
    )
    lo = 0
    while lo < hi:
        mid = (lo + hi) // 2
        ts = block_timestamp(url, mid, cache)
        if ts < timestamp:
            lo = mid + 1
        else:
            hi = mid
    return lo


def get_logs_chunked(
    url: str,
    address: str | list[str],
    topics: list,
    from_block: int,
    to_block: int,
    chunk: int,
    sleep_s: float = 0.15,
) -> list[dict]:
    """eth_getLogs over [from_block, to_block], splitting on range errors."""
    print(
        f"RPC getLogs {str(address)[:12]}… topics={len(topics)} "
        f"blocks {from_block}-{to_block} chunk={chunk}",
        flush=True,
    )
    out: list[dict] = []
    n_calls = [0]

    def walk(lo: int, hi: int, width: int) -> None:
        if lo > hi:
            return
        cur = lo
        w = max(1, width)
        while cur <= hi:
            end = min(cur + w - 1, hi)
            params = {
                "fromBlock": hex(cur),
                "toBlock": hex(end),
                "address": address if isinstance(address, str) else list(address),
                "topics": topics,
            }
            try:
                logs = jsonrpc(url, "eth_getLogs", [params])
                if not isinstance(logs, list):
                    raise RpcError(f"eth_getLogs returned {type(logs)}")
                if len(logs) >= 10_000 and end > cur:
                    w = max(1, (end - cur + 1) // 2)
                    continue
                out.extend(logs)
                n_calls[0] += 1
                if n_calls[0] % 25 == 0:
                    print(
                        f"  rpc chunk {n_calls[0]} block {cur}-{end} "
                        f"n={len(logs)} total={len(out)} width={w}",
                        flush=True,
                    )
                time.sleep(sleep_s)
                cur = end + 1
                if len(logs) < 20 and w < width:
                    w = min(width, w * 2)
            except (RangeTooLarge, RpcError) as exc:
                too_big = isinstance(exc, RangeTooLarge) or "400" in str(exc)
                if not too_big:
                    raise
                if end == cur:
                    raise
                old = w
                w = max(1, (end - cur + 1) // 2)
                print(
                    f"  range too large {cur}-{end}; width {old}→{w}",
                    flush=True,
                )
                if w < MIN_GETLOGS_WIDTH and width >= MIN_GETLOGS_WIDTH:
                    raise RpcError(
                        f"eth_getLogs range ceiling <{MIN_GETLOGS_WIDTH} blocks "
                        f"at {cur} — endpoint unusable for 90d window"
                    )

    walk(from_block, to_block, max(1, chunk))
    return out


def fee_history(url: str, block_count: int, newest: int) -> dict:
    return jsonrpc(url, "eth_feeHistory", [hex(block_count), hex(newest), []])
