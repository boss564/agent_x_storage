"""Chainlink AnswerUpdated capture for Stufe A V3.

Reads resolved aggregator addresses from bridge_stufe_a_v3_chainlink_resolved.json.
Captures on aggregators (not proxies) over the frozen Stufe-A 90-day window.

Usage:
  python3 scripts/bridge_stufe_a_v3_chainlink_capture.py
  python3 scripts/bridge_stufe_a_v3_chainlink_capture.py \\
    --resolved bridge_stufe_a_v3_chainlink_resolved.json \\
    --output bridge_stufe_a_v3_chainlink.jsonl
  python3 scripts/bridge_stufe_a_v3_chainlink_capture.py --smoke
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from eth_hash.auto import keccak

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bridge_stufe_a_config import WINDOW_END_UTC, WINDOW_START_UTC
from bridge_stufe_a_rpc import (
    DEFAULT_RPCS,
    ETH_HTTP_FALLBACKS,
    GNOSIS_HTTP_FALLBACKS,
    RangeTooLarge,
    RpcError,
    as_int,
    block_timestamp,
    jsonrpc,
    redact_url,
    timestamp_to_block,
)

TOPIC_ANSWER_UPDATED = "0x" + keccak(b"AnswerUpdated(int256,uint256,uint256)").hex()
CHUNK_BLOCKS = 10_000
MAX_RETRIES = 5

CHAIN_RPC_FALLBACKS: dict[str, list[str]] = {
    "ethereum": [u for u in [*ETH_HTTP_FALLBACKS, "https://ethereum-rpc.publicnode.com"] if u],
    "gnosis": [u for u in GNOSIS_HTTP_FALLBACKS if u],
}


def rpc_candidates(chain: str, primary: str | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for url in [primary, *CHAIN_RPC_FALLBACKS.get(chain, []), DEFAULT_RPCS.get(chain)]:
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def probe_rpc(chain: str, primary: str | None) -> str:
    errors: list[str] = []
    for url in rpc_candidates(chain, primary):
        try:
            block = as_int(jsonrpc(url, "eth_blockNumber", [], retries=MAX_RETRIES))
            if block <= 0:
                raise RpcError(f"invalid block {block}")
            # Sanity eth_call path via getLogs on tiny range at latest block.
            jsonrpc(
                url,
                "eth_getLogs",
                [
                    {
                        "fromBlock": hex(max(0, block - 2)),
                        "toBlock": hex(block),
                        "topics": [TOPIC_ANSWER_UPDATED],
                    }
                ],
                retries=MAX_RETRIES,
            )
            return url
        except Exception as exc:
            errors.append(f"{redact_url(url)}: {exc}")
    raise RuntimeError(f"all RPCs failed for {chain}: {' | '.join(errors)}")


def get_logs_chunked_v3(
    url: str,
    address: str,
    from_block: int,
    to_block: int,
    *,
    chunk: int = CHUNK_BLOCKS,
) -> list[dict]:
    """eth_getLogs with conservative chunking and binary split on range errors."""
    out: list[dict] = []
    n_calls = 0

    def walk(lo: int, hi: int, width: int) -> None:
        nonlocal n_calls
        if lo > hi:
            return
        cur = lo
        w = max(1, width)
        while cur <= hi:
            end = min(cur + w - 1, hi)
            params = {
                "fromBlock": hex(cur),
                "toBlock": hex(end),
                "address": address,
                "topics": [TOPIC_ANSWER_UPDATED],
            }
            try:
                logs = jsonrpc(url, "eth_getLogs", [params], retries=MAX_RETRIES)
                if not isinstance(logs, list):
                    raise RpcError(f"eth_getLogs returned {type(logs)}")
                if len(logs) >= 10_000 and end > cur:
                    w = max(1, (end - cur + 1) // 2)
                    continue
                out.extend(logs)
                n_calls += 1
                if n_calls % 20 == 0:
                    print(
                        f"    chunk {n_calls} blocks {cur}-{end} "
                        f"n={len(logs)} total={len(out)} width={w}",
                        flush=True,
                    )
                time.sleep(0.12)
                cur = end + 1
                if len(logs) < 20 and w < chunk:
                    w = min(chunk, w * 2)
            except RangeTooLarge as exc:
                if end == cur:
                    raise RpcError(f"eth_getLogs failed at single block {cur}: {exc}") from exc
                old = w
                w = max(1, (end - cur + 1) // 2)
                print(f"    range too large {cur}-{end}; width {old}→{w}", flush=True)

    walk(from_block, to_block, chunk)
    return out


def decode_topic_uint256(topic: str) -> int:
    return int(topic, 16)


def decode_topic_int256(topic: str) -> int:
    val = int(topic, 16)
    if val >= 2**255:
        val -= 2**256
    return val


def parse_answer_updated_log(log: dict) -> dict:
    topics = log.get("topics") or []
    if len(topics) < 3:
        raise ValueError(f"AnswerUpdated expected >=3 topics, got {len(topics)}")
    data = log.get("data", "0x")
    body = data[2:] if data.startswith("0x") else data
    if len(body) < 64:
        raise ValueError(f"AnswerUpdated data too short: {data!r}")
    updated_at = int(body[0:64], 16)
    return {
        "current": str(decode_topic_int256(topics[1])),
        "round_id": str(decode_topic_uint256(topics[2])),
        "updated_at": updated_at,
    }


def load_capture_plan(resolved_path: Path) -> tuple[dict, dict[str, list[str]]]:
    body = json.loads(resolved_path.read_text(encoding="utf-8"))
    if not body.get("all_resolved") or body.get("capture_release") != "RELEASED":
        raise SystemExit("capture blocked: resolved file not released for capture")

    agg_feeds: dict[tuple[str, str], list[str]] = defaultdict(list)
    chains: dict[str, dict] = {}

    for chain, cfg in body.get("chains", {}).items():
        feeds_cfg = []
        for feed in cfg.get("feeds", []):
            if feed.get("status") != "RESOLVED":
                continue
            name = feed["name"]
            for agg in feed.get("active_aggregators", []):
                key = (chain, agg.lower())
                if name not in agg_feeds[key]:
                    agg_feeds[key].append(name)
            feeds_cfg.append(feed)
        chains[chain] = {"feeds": feeds_cfg}

    return body, dict(agg_feeds)


def event_record(
    *,
    chain: str,
    aggregator: str,
    feeds: list[str],
    block_number: int,
    tx_hash: str,
    log_index: int,
    timestamp: int,
    parsed: dict,
) -> dict:
    primary = sorted(feeds)[0]
    row = {
        "chain": chain,
        "aggregator": aggregator.lower(),
        "feed": primary,
        "block_number": block_number,
        "tx_hash": tx_hash.lower(),
        "log_index": log_index,
        "timestamp": timestamp,
        "current": parsed["current"],
        "round_id": parsed["round_id"],
        "updated_at": parsed["updated_at"],
    }
    if len(feeds) > 1:
        row["feeds"] = sorted(feeds)
    return row


def run_capture(
    *,
    resolved_path: Path,
    output_path: Path,
    smoke: bool,
) -> dict:
    _, agg_feeds = load_capture_plan(resolved_path)
    if not agg_feeds:
        raise SystemExit("no aggregators in resolved plan")

    start_ts = int(WINDOW_START_UTC.timestamp())
    end_ts = int(WINDOW_END_UTC.timestamp())

    seen_global: set[tuple[str, str, int]] = set()
    manifest: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_start": WINDOW_START_UTC.isoformat(),
        "window_end": WINDOW_END_UTC.isoformat(),
        "topic0": TOPIC_ANSWER_UPDATED,
        "chunk_blocks": CHUNK_BLOCKS,
        "smoke": smoke,
        "aggregators": [],
        "n_events_written": 0,
        "n_events_deduped": 0,
    }

    chains_seen: dict[str, str] = {}
    ts_cache: dict[int, int] = {}

    with output_path.open("w", encoding="utf-8") as out_fh:
        by_chain: dict[str, list[tuple[str, list[str]]]] = defaultdict(list)
        for (chain, agg), feeds in sorted(agg_feeds.items()):
            by_chain[chain].append((agg, sorted(feeds)))

        for chain, jobs in sorted(by_chain.items()):
            if chain not in chains_seen:
                rpc = probe_rpc(chain, DEFAULT_RPCS.get(chain))
                chains_seen[chain] = rpc
                print(f"{chain}: using RPC {redact_url(rpc)}", flush=True)
            rpc = chains_seen[chain]

            from_block = timestamp_to_block(rpc, start_ts, ts_cache)
            to_block = timestamp_to_block(rpc, end_ts, ts_cache)
            if smoke:
                to_block = min(to_block, from_block + 5_000)
                print(f"{chain}: SMOKE blocks {from_block}-{to_block}", flush=True)
            else:
                print(f"{chain}: window blocks {from_block}-{to_block}", flush=True)

            for agg, feeds in jobs:
                label = f"{chain} {agg[:10]}… feeds={','.join(feeds)}"
                print(f"capture {label} blocks {from_block}-{to_block}", flush=True)
                t0 = time.time()
                try:
                    logs = get_logs_chunked_v3(rpc, agg, from_block, to_block)
                except Exception as exc:
                    raise RuntimeError(f"capture failed {chain} {agg}: {exc}") from exc

                n_written = 0
                n_deduped = 0
                ts_min: int | None = None
                ts_max: int | None = None

                for log in logs:
                    tx = str(log.get("transactionHash", "")).lower()
                    li = as_int(log.get("logIndex", 0))
                    dedup_key = (chain, tx, li)
                    if dedup_key in seen_global:
                        n_deduped += 1
                        continue
                    seen_global.add(dedup_key)

                    bn = as_int(log.get("blockNumber"))
                    ts = block_timestamp(rpc, bn, ts_cache)
                    if ts < start_ts or ts > end_ts:
                        continue

                    parsed = parse_answer_updated_log(log)
                    row = event_record(
                        chain=chain,
                        aggregator=agg,
                        feeds=feeds,
                        block_number=bn,
                        tx_hash=tx,
                        log_index=li,
                        timestamp=ts,
                        parsed=parsed,
                    )
                    out_fh.write(json.dumps(row) + "\n")
                    n_written += 1
                    ts_min = ts if ts_min is None else min(ts_min, ts)
                    ts_max = ts if ts_max is None else max(ts_max, ts)

                status = "ok" if n_written > 0 else "no_events_in_window"
                manifest["aggregators"].append(
                    {
                        "chain": chain,
                        "aggregator": agg,
                        "feeds": feeds,
                        "n_logs_raw": len(logs),
                        "n_events_written": n_written,
                        "n_events_deduped": n_deduped,
                        "status": status,
                        "timestamp_min": ts_min,
                        "timestamp_max": ts_max,
                        "elapsed_s": round(time.time() - t0, 2),
                    }
                )
                manifest["n_events_written"] += n_written
                manifest["n_events_deduped"] += n_deduped
                print(
                    f"  done {label} raw={len(logs)} written={n_written} "
                    f"deduped={n_deduped} status={status} "
                    f"elapsed={manifest['aggregators'][-1]['elapsed_s']}s",
                    flush=True,
                )

    manifest_path = Path(str(output_path) + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Stufe A V3 Chainlink AnswerUpdated capture")
    parser.add_argument(
        "--resolved",
        default="bridge_stufe_a_v3_chainlink_resolved.json",
    )
    parser.add_argument(
        "--output",
        default="bridge_stufe_a_v3_chainlink.jsonl",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="First ~5000 blocks per chain only (connectivity test)",
    )
    args = parser.parse_args()

    resolved_path = Path(args.resolved)
    output_path = Path(args.output)
    if not resolved_path.exists():
        raise SystemExit(f"missing resolved file: {resolved_path}")

    manifest = run_capture(
        resolved_path=resolved_path,
        output_path=output_path,
        smoke=args.smoke,
    )
    print(f"Wrote {output_path}")
    print(f"Wrote {output_path}.manifest.json")
    print(
        f"events={manifest['n_events_written']} deduped={manifest['n_events_deduped']} "
        f"aggregators={len(manifest['aggregators'])}"
    )
    no_event = sum(1 for a in manifest["aggregators"] if a["status"] == "no_events_in_window")
    if no_event:
        print(f"no_events_in_window: {no_event} aggregators (see manifest)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
