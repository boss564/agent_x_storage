"""Stufe A event capture: OmniBridge mediator logs + Uniswap Universal Router tx.to.

Respects frozen addresses, window, and topic0 in bridge_stufe_a_config.py.
Uniswap control is tx.to (Etherscan/Arbiscan), not Uniswap V2 Swap topics on the
router — Universal Router does not emit those events.

Usage:
  python3 scripts/bridge_stufe_a_capture.py --stream treat_eth --output bridge_eth.jsonl
  python3 scripts/bridge_stufe_a_capture.py --stream treat_gnosis --output bridge_gnosis.jsonl
  python3 scripts/bridge_stufe_a_capture.py --stream ctrl_eth --output uniswap_eth.jsonl
  python3 scripts/bridge_stufe_a_capture.py --stream ctrl_arbitrum --output uniswap_arb.jsonl
  python3 scripts/bridge_stufe_a_capture.py --all --out-dir .
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Iterable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bridge_stufe_a_config import (
    OMNIBRIDGE_ETH,
    OMNIBRIDGE_GNOSIS,
    STREAM_IDS,
    TOPIC_TOKENS_BRIDGED,
    TOPIC_TOKENS_BRIDGING_INITIATED,
    UNISWAP_UR_ARBITRUM,
    UNISWAP_UR_ETH,
    WINDOW_END_UTC,
    WINDOW_START_UTC,
    assert_frozen_addresses,
)
from bridge_stufe_a_rpc import (
    CHUNK_BLOCKS,
    DEFAULT_RPCS,
    as_int,
    block_timestamp,
    get_logs_chunked,
    latest_block,
    redact_url,
    timestamp_to_block,
)

TOPIC_INIT = TOPIC_TOKENS_BRIDGING_INITIATED.lower()
TOPIC_BRIDGED = TOPIC_TOKENS_BRIDGED.lower()

STREAM_SPEC = {
    "treat_eth": {"chain": "ethereum", "kind": "omnibridge", "address": OMNIBRIDGE_ETH},
    "treat_gnosis": {"chain": "gnosis", "kind": "omnibridge", "address": OMNIBRIDGE_GNOSIS},
    "ctrl_eth": {"chain": "ethereum", "kind": "uniswap", "addresses": UNISWAP_UR_ETH},
    "ctrl_arbitrum": {"chain": "arbitrum", "kind": "uniswap", "addresses": UNISWAP_UR_ARBITRUM},
}

ETHERSCAN_V2 = "https://api.etherscan.io/v2/api"
CHAIN_IDS = {"ethereum": 1, "gnosis": 100, "arbitrum": 42161}


def etherscan_api(params: dict, *, retries: int = 8) -> dict:
    import urllib.parse
    import urllib.request
    from bridge_stufe_a_rpc import USER_AGENT

    qs = urllib.parse.urlencode(params)
    url = f"{ETHERSCAN_V2}?{qs}"
    last_err: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode())
        except Exception as exc:
            last_err = exc
            time.sleep(min(2 ** attempt, 16))
            continue
        time.sleep(0.25)
        if not isinstance(body, dict):
            last_err = RuntimeError(f"non-object explorer body: {body!r}")
            time.sleep(1.5)
            continue
        result = body.get("result")
        message = str(body.get("message", "")).lower()
        if result is None or "rate limit" in message or "max calls" in message:
            last_err = RuntimeError(f"explorer empty/rate-limit: {body.get('message')}")
            if attempt >= 2:
                break
            time.sleep(1.2 * (attempt + 1))
            continue
        return body
    raise RuntimeError(f"Etherscan API failed: {last_err}")


def explorer_api(chain: str, params: dict) -> dict:
    """Prefer Etherscan v2 (incl. chainid 100). Gnosisscan is optional fallback."""
    try:
        return etherscan_api(params)
    except Exception as primary:
        if chain != "gnosis":
            raise
        import urllib.parse
        import urllib.request
        from bridge_stufe_a_rpc import USER_AGENT

        p = {k: v for k, v in params.items() if k != "chainid"}
        qs = urllib.parse.urlencode(p)
        url = f"https://api.gnosisscan.io/api?{qs}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode())
        except Exception as exc:
            raise RuntimeError(f"Gnosisscan fallback failed after v2: {primary}") from exc
        if not isinstance(body, dict) or body.get("result") is None:
            raise RuntimeError(f"Gnosisscan empty after v2: {primary}")
        time.sleep(0.25)
        return body


def etherscan_latest_block(chain: str, api_key: str) -> int:
    body = explorer_api(
        chain,
        {
            "chainid": CHAIN_IDS[chain],
            "module": "proxy",
            "action": "eth_blockNumber",
            "apikey": api_key,
        },
    )
    result = body.get("result")
    if not result:
        raise RuntimeError(f"eth_blockNumber: {body}")
    return as_int(result)


def etherscan_block_by_time(chain: str, timestamp: int, api_key: str, closest: str = "before") -> int:
    body = explorer_api(
        chain,
        {
            "chainid": CHAIN_IDS[chain],
            "module": "block",
            "action": "getblocknobytime",
            "timestamp": int(timestamp),
            "closest": closest,
            "apikey": api_key,
        },
    )
    result = body.get("result")
    if body.get("status") == "0" and not str(result).isdigit():
        raise RuntimeError(f"getblocknobytime: {result}")
    return int(result)


def etherscan_get_logs(
    chain: str,
    address: str,
    topic0: str,
    from_block: int,
    to_block: int,
    api_key: str,
    chunk: int,
) -> list[dict]:
    """Paginated Etherscan v2 getLogs for one topic0."""
    out: list[dict] = []
    cur = from_block
    while cur <= to_block:
        end = min(cur + chunk - 1, to_block)
        body = explorer_api(
            chain,
            {
                "chainid": CHAIN_IDS[chain],
                "module": "logs",
                "action": "getLogs",
                "fromBlock": cur,
                "toBlock": end,
                "address": address,
                "topic0": topic0,
                "apikey": api_key,
            },
        )
        result = body.get("result", [])
        if body.get("status") == "0" and isinstance(result, str):
            msg = result.lower()
            if "no records" in msg or "no logs" in msg:
                cur = end + 1
                continue
            if "window" in msg or "range" in msg or "10000" in msg or "limit" in msg:
                if end == cur:
                    raise RuntimeError(f"Etherscan getLogs: {result}")
                chunk = max(1, chunk // 2)
                continue
            raise RuntimeError(f"Etherscan getLogs: {result}")
        if not isinstance(result, list):
            raise RuntimeError(f"Etherscan getLogs unexpected: {result!r}")
        if len(result) >= 1000 and end > cur:
            chunk = max(1, (end - cur + 1) // 2)
            continue
        out.extend(result)
        if (cur // max(chunk, 1)) % 20 == 0:
            print(f"  getLogs {chain} {address[:10]}… block {cur}-{end} n={len(result)} total={len(out)}", flush=True)
        cur = end + 1
        if len(result) > 400:
            chunk = max(200, chunk // 2)
        elif len(result) < 50:
            chunk = min(chunk * 2, 8_000)
    return out


def capture_omnibridge_etherscan(
    chain: str,
    contract: str,
    from_block: int,
    to_block: int,
    api_key: str,
) -> tuple[list[dict], str]:
    chunk = CHUNK_BLOCKS[chain]
    logs: list[dict] = []
    for topic in (TOPIC_TOKENS_BRIDGING_INITIATED, TOPIC_TOKENS_BRIDGED):
        logs.extend(etherscan_get_logs(chain, contract, topic, from_block, to_block, api_key, chunk))
    events = []
    for log in logs:
        events.append(parse_omnibridge_log(chain, contract, log, as_int(log.get("timeStamp", 0))))
    return dedupe_logs(events), "etherscan_getLogs"


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def topic_addr(topic: str) -> str:
    h = topic.lower().replace("0x", "")
    return "0x" + h[-40:]


def parse_omnibridge_log(chain: str, contract: str, log: dict, block_time: int) -> dict:
    topics = [t.lower() if isinstance(t, str) else t for t in log.get("topics", [])]
    topic0 = topics[0] if topics else ""
    if topic0 == TOPIC_INIT:
        event_type = "TokensBridgingInitiated"
    elif topic0 == TOPIC_BRIDGED:
        event_type = "TokensBridged"
    else:
        event_type = "unknown"
    token = topic_addr(topics[1]) if len(topics) > 1 else None
    counterparty = topic_addr(topics[2]) if len(topics) > 2 else None
    return {
        "chain": chain,
        "address": contract.lower(),
        "txHash": log.get("transactionHash"),
        "logIndex": as_int(log.get("logIndex", 0)),
        "blockNumber": as_int(log.get("blockNumber", 0)),
        "blockTime": block_time,
        "topic0": topic0,
        "event_type": event_type,
        "token": token,
        "counterparty": counterparty,
    }


def dedupe_logs(events: Iterable[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for ev in events:
        key = (ev.get("txHash"), ev.get("logIndex"))
        if key in seen:
            continue
        seen.add(key)
        out.append(ev)
    out.sort(key=lambda e: (e["blockTime"], e["blockNumber"], e["logIndex"]))
    return out


def write_jsonl(path: str, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")


def write_manifest(path: str, manifest: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")


def frozen_manifest_addresses() -> dict:
    return {
        "omnibridge_eth": OMNIBRIDGE_ETH,
        "omnibridge_gnosis": OMNIBRIDGE_GNOSIS,
        "uniswap_ur_eth": list(UNISWAP_UR_ETH),
        "uniswap_ur_arbitrum": list(UNISWAP_UR_ARBITRUM),
        "topic0": [TOPIC_TOKENS_BRIDGING_INITIATED, TOPIC_TOKENS_BRIDGED],
    }


def capture_omnibridge(
    chain: str,
    contract: str,
    rpc_url: str,
    from_block: int,
    to_block: int,
) -> tuple[list[dict], str]:
    logs: list[dict] = []
    for i, topic in enumerate((TOPIC_TOKENS_BRIDGING_INITIATED, TOPIC_TOKENS_BRIDGED), start=1):
        print(f"OmniBridge {chain} topic {i}/2 {topic[:18]}…", flush=True)
        logs.extend(
            get_logs_chunked(
                rpc_url,
                contract,
                [topic],
                from_block,
                to_block,
                CHUNK_BLOCKS[chain],
            )
        )
    cache: dict[int, int] = {}
    events = []
    bns = [as_int(log["blockNumber"]) for log in logs]
    print(f"resolving timestamps for {len(logs)} logs", flush=True)
    ts_by_block: dict[int, int] = {}
    if bns:
        lo, hi = min(bns), max(bns)
        t_lo = block_timestamp(rpc_url, lo, cache)
        t_hi = block_timestamp(rpc_url, hi, cache)
        span = hi - lo
        for bn in set(bns):
            if span == 0:
                ts_by_block[bn] = t_lo
            else:
                ts_by_block[bn] = t_lo + int(round((t_hi - t_lo) * (bn - lo) / span))
        print(
            f"  header clock {lo}@{t_lo} → {hi}@{t_hi} "
            f"({(t_hi - t_lo) / max(span, 1):.3f}s/block)",
            flush=True,
        )
    for log, bn in zip(logs, bns):
        events.append(parse_omnibridge_log(chain, contract, log, ts_by_block[bn]))
    return dedupe_logs(events), "eth_getLogs"


def etherscan_txlist(
    chain: str,
    address: str,
    start_block: int,
    end_block: int,
    api_key: str,
) -> list[dict]:
    out: list[dict] = []
    cursor = start_block
    while cursor <= end_block:
        body = explorer_api(
            chain,
            {
                "chainid": CHAIN_IDS[chain],
                "module": "account",
                "action": "txlist",
                "address": address,
                "startblock": cursor,
                "endblock": end_block,
                "page": 1,
                "offset": 10_000,
                "sort": "asc",
                "apikey": api_key,
            },
        )
        status = str(body.get("status", ""))
        result = body.get("result", [])
        if status == "0" and isinstance(result, str):
            if "no transactions" in result.lower():
                break
            raise RuntimeError(f"Etherscan txlist error: {result}")
        if not isinstance(result, list) or not result:
            break
        out.extend(result)
        last_bn = as_int(result[-1]["blockNumber"])
        print(
            f"  txlist {chain} {address[:10]}… cursor={cursor} n={len(result)} "
            f"total={len(out)} last_block={last_bn}",
            flush=True,
        )
        # Etherscan often caps a page at 1_000 (< offset 10_000). A short page
        # is not end-of-range; advance startblock or we stop after ~1 day.
        nxt = last_bn + 1
        if nxt <= cursor:
            break
        cursor = nxt
        if len(out) > 2_000_000:
            raise RuntimeError("txlist overflow — aborting")
    return out


def capture_uniswap_txlist(
    chain: str,
    addresses: tuple[str, ...],
    from_block: int,
    to_block: int,
    api_key: str,
) -> tuple[list[dict], str]:
    events: list[dict] = []
    seen: set[str] = set()
    for addr in addresses:
        rows = etherscan_txlist(chain, addr, from_block, to_block, api_key)
        for row in rows:
            if str(row.get("isError", "0")) not in ("0", "false", ""):
                continue
            txh = row.get("hash")
            if not txh or txh in seen:
                continue
            to_addr = (row.get("to") or "").lower()
            if to_addr != addr.lower():
                continue
            seen.add(txh)
            events.append(
                {
                    "chain": chain,
                    "address": addr.lower(),
                    "txHash": txh,
                    "logIndex": 0,
                    "blockNumber": as_int(row["blockNumber"]),
                    "blockTime": as_int(row["timeStamp"]),
                    "topic0": None,
                    "event_type": "UniversalRouterTx",
                    "token": None,
                    "counterparty": (row.get("from") or "").lower() or None,
                }
            )
    events.sort(key=lambda e: (e["blockTime"], e["blockNumber"], e["txHash"]))
    return events, "etherscan_txlist"


def capture_uniswap_logs_fallback(
    chain: str,
    addresses: tuple[str, ...],
    rpc_url: str,
    from_block: int,
    to_block: int,
) -> tuple[list[dict], str]:
    """All logs from the frozen UR contracts; one event per txHash (tx.to proxy)."""
    logs = get_logs_chunked(
        rpc_url,
        list(addresses),
        [],
        from_block,
        to_block,
        CHUNK_BLOCKS[chain],
    )
    cache: dict[int, int] = {}
    seen: set[str] = set()
    events: list[dict] = []
    allowed = {a.lower() for a in addresses}
    for log in logs:
        addr = (log.get("address") or "").lower()
        if addr not in allowed:
            continue
        txh = log.get("transactionHash")
        if not txh or txh in seen:
            continue
        seen.add(txh)
        bn = as_int(log["blockNumber"])
        events.append(
            {
                "chain": chain,
                "address": addr,
                "txHash": txh,
                "logIndex": as_int(log.get("logIndex", 0)),
                "blockNumber": bn,
                "blockTime": block_timestamp(rpc_url, bn, cache),
                "topic0": None,
                "event_type": "UniversalRouterTx",
                "token": None,
                "counterparty": None,
            }
        )
    events.sort(key=lambda e: (e["blockTime"], e["blockNumber"], e["txHash"]))
    return events, "eth_getLogs_ur_all"


def resolve_stream(chain: str | None, source: str | None, stream: str | None) -> str:
    if stream:
        if stream not in STREAM_SPEC:
            raise SystemExit(f"unknown stream {stream}; expected {STREAM_IDS}")
        return stream
    if chain == "gnosis":
        return "treat_gnosis"
    if chain == "arbitrum":
        return "ctrl_arbitrum"
    if chain == "ethereum":
        if source == "omnibridge":
            return "treat_eth"
        if source == "uniswap":
            return "ctrl_eth"
        raise SystemExit("--chain ethereum requires --source omnibridge|uniswap (or pass --stream)")
    raise SystemExit("pass --stream or --chain")


def pick_rpc(chain: str, override: str | None) -> list[str]:
    if override:
        return [override]
    if chain == "ethereum":
        from bridge_stufe_a_rpc import ETH_HTTP_FALLBACKS
        seen: list[str] = []
        env = os.environ.get("ETHEREUM_RPC") or os.environ.get("ETH_RPC")
        if env:
            seen.append(env)
        for url in ETH_HTTP_FALLBACKS:
            if url and url not in seen:
                seen.append(url)
        return seen
    if chain == "gnosis":
        from bridge_stufe_a_rpc import GNOSIS_HTTP_FALLBACKS
        seen: list[str] = []
        for url in GNOSIS_HTTP_FALLBACKS:
            if url and url not in seen:
                seen.append(url)
        env = os.environ.get("GNOSIS_RPC")
        if env and env not in seen:
            seen.append(env)
        return seen or [DEFAULT_RPCS["gnosis"]]
    env = os.environ.get(f"{chain.upper()}_RPC")
    return [env or DEFAULT_RPCS[chain]]


def clamp_end_ts() -> int:
    """Etherscan rejects timestamps in the future; window end is 23:59:59 UTC today."""
    return min(int(WINDOW_END_UTC.timestamp()), int(time.time()) - 60)


def capture_via_etherscan(
    spec: dict,
    chain: str,
    smoke: bool,
    api_key: str,
) -> tuple[list[dict], int, int, str, str]:
    if smoke:
        latest = etherscan_latest_block(chain, api_key)
        from_block = max(0, latest - 200)
        to_block = latest
        window_note = "smoke_last_200_blocks"
    else:
        print(f"{chain}: resolving window via Etherscan getblocknobytime", flush=True)
        from_block = etherscan_block_by_time(
            chain, int(WINDOW_START_UTC.timestamp()), api_key, closest="after"
        )
        to_block = etherscan_block_by_time(
            chain, clamp_end_ts(), api_key, closest="before"
        )
        window_note = "frozen_90d"
    print(f"{chain} window blocks {from_block}-{to_block} ({window_note})", flush=True)
    if spec["kind"] == "omnibridge" and chain == "gnosis":
        last_err: Exception | None = None
        events: list[dict] = []
        method = ""
        for rpc_url in pick_rpc("gnosis", None):
            try:
                print(f"gnosis getLogs via {redact_url(rpc_url)}", flush=True)
                events, method = capture_omnibridge(
                    chain, spec["address"], rpc_url, from_block, to_block
                )
                last_err = None
                break
            except Exception as exc:
                last_err = exc
                print(
                    f"gnosis RPC {redact_url(rpc_url)} failed: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
        if last_err is not None:
            raise last_err
        return events, from_block, to_block, method + "+etherscan_blocks", window_note
    if spec["kind"] == "omnibridge":
        events, method = capture_omnibridge_etherscan(
            chain, spec["address"], from_block, to_block, api_key
        )
    else:
        events, method = capture_uniswap_txlist(
            chain, spec["addresses"], from_block, to_block, api_key
        )
    return events, from_block, to_block, method, window_note


def capture_stream(stream: str, output: str, *, smoke: bool, rpc_override: str | None) -> dict:
    spec = STREAM_SPEC[stream]
    chain = spec["chain"]
    events: list[dict] = []
    from_block = to_block = 0
    method = ""
    window_note = "frozen_90d"
    rpc_label = "etherscan_v2"
    api_key = os.environ.get("ETHERSCAN_API_KEY", "")

    used_etherscan = False
    if api_key and not rpc_override:
        try:
            events, from_block, to_block, method, window_note = capture_via_etherscan(
                spec, chain, smoke, api_key
            )
            used_etherscan = True
        except Exception as exc:
            print(f"Etherscan path failed ({exc}); falling back to JSON-RPC", file=sys.stderr)

    if not used_etherscan:
        candidates = pick_rpc(chain, rpc_override)
        last_err: Exception | None = None
        rpc_url = candidates[0]
        for rpc_url in candidates:
            try:
                latest = latest_block(rpc_url)
                ts_cache: dict[int, int] = {}
                if smoke:
                    from_block = max(0, latest - 200)
                    to_block = latest
                    window_note = "smoke_last_200_blocks"
                else:
                    print(
                        f"{chain}: resolving window via JSON-RPC {redact_url(rpc_url)} latest={latest}",
                        flush=True,
                    )
                    from_block = timestamp_to_block(rpc_url, int(WINDOW_START_UTC.timestamp()), ts_cache)
                    to_block = min(
                        latest,
                        timestamp_to_block(rpc_url, int(WINDOW_END_UTC.timestamp()), ts_cache),
                    )
                    window_note = "frozen_90d"

                if spec["kind"] == "omnibridge":
                    events, method = capture_omnibridge(
                        chain, spec["address"], rpc_url, from_block, to_block
                    )
                else:
                    if not api_key:
                        raise RuntimeError("ETHERSCAN_API_KEY unset")
                    try:
                        events, method = capture_uniswap_txlist(
                            chain, spec["addresses"], from_block, to_block, api_key
                        )
                    except Exception as exc:
                        print(
                            f"txlist failed ({exc}); falling back to eth_getLogs on UR addresses",
                            file=sys.stderr,
                        )
                        events, method = capture_uniswap_logs_fallback(
                            chain, spec["addresses"], rpc_url, from_block, to_block
                        )
                last_err = None
                rpc_label = redact_url(rpc_url)
                break
            except Exception as exc:
                last_err = exc
                print(f"RPC {redact_url(rpc_url)} failed: {exc}", file=sys.stderr)
                continue
        if last_err is not None:
            raise last_err

    if not smoke:
        start_ts = int(WINDOW_START_UTC.timestamp())
        end_ts = int(WINDOW_END_UTC.timestamp())
        events = [e for e in events if start_ts <= e["blockTime"] <= end_ts]

    write_jsonl(output, events)
    manifest = {
        "stream": stream,
        "chain": chain,
        "kind": spec["kind"],
        "window_start": WINDOW_START_UTC.isoformat(),
        "window_end": WINDOW_END_UTC.isoformat(),
        "window_mode": window_note,
        "from_block": from_block,
        "to_block": to_block,
        "n_events": len(events),
        "capture_method": method,
        "rpc_url": rpc_label,
        "utc_captured_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "addresses": frozen_manifest_addresses(),
        "output": output,
    }
    assert_frozen_addresses(manifest["addresses"])
    write_manifest(output + ".manifest.json", manifest)
    print(f"{stream}: {len(events)} events via {method} -> {output}")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Stufe A OmniBridge / Uniswap capture")
    parser.add_argument("--stream", choices=list(STREAM_SPEC))
    parser.add_argument("--chain", choices=["ethereum", "gnosis", "arbitrum"])
    parser.add_argument("--source", choices=["omnibridge", "uniswap"])
    parser.add_argument("--output", help="JSONL path (required unless --all)")
    parser.add_argument("--all", action="store_true", help="capture all four streams")
    parser.add_argument("--out-dir", default=".")
    parser.add_argument("--rpc", help="override JSON-RPC URL")
    parser.add_argument("--smoke", action="store_true", help="last 200 blocks only (not confirmatory)")
    args = parser.parse_args()

    default_names = {
        "treat_eth": "bridge_eth.jsonl",
        "treat_gnosis": "bridge_gnosis.jsonl",
        "ctrl_eth": "uniswap_eth.jsonl",
        "ctrl_arbitrum": "uniswap_arb.jsonl",
    }
    if args.all:
        os.makedirs(args.out_dir, exist_ok=True)
        for stream, name in default_names.items():
            capture_stream(stream, os.path.join(args.out_dir, name), smoke=args.smoke, rpc_override=args.rpc)
        return 0
    stream = resolve_stream(args.chain, args.source, args.stream)
    if not args.output:
        raise SystemExit("--output is required unless --all")
    capture_stream(stream, args.output, smoke=args.smoke, rpc_override=args.rpc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
