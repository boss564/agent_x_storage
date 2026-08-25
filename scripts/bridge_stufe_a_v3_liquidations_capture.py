"""Aave v3 / Spark LiquidationCall capture for Stufe A V3.

Captures on pool proxies (not implementations). Pre-Reg §3.0.2.

Usage:
  python3 scripts/bridge_stufe_a_v3_liquidations_capture.py
  python3 scripts/bridge_stufe_a_v3_liquidations_capture.py --smoke
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from eth_hash.auto import keccak

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bridge_stufe_a_config import WINDOW_END_UTC, WINDOW_START_UTC
from bridge_stufe_a_rpc import DEFAULT_RPCS, as_int, block_timestamp, jsonrpc, redact_url, timestamp_to_block
from bridge_stufe_a_v3_chainlink_capture import CHUNK_BLOCKS, MAX_RETRIES, probe_rpc

TOPIC_LIQUIDATION_CALL = "0x" + keccak(
    b"LiquidationCall(address,address,address,uint256,uint256,address,bool)"
).hex()


def parse_liquidation_log(log: dict) -> dict:
    topics = log.get("topics") or []
    if len(topics) < 4:
        raise ValueError(f"LiquidationCall expected 4 topics, got {len(topics)}")
    data = log.get("data", "0x")
    body = data[2:] if str(data).startswith("0x") else data
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


def load_pools(resolved_path: Path) -> list[dict]:
    body = json.loads(resolved_path.read_text(encoding="utf-8"))
    if not body.get("all_resolved") or body.get("capture_release") != "RELEASED":
        raise SystemExit("capture blocked: liquidation resolved file not released")
    return [p for p in body.get("pools", []) if p.get("status") == "RESOLVED"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Stufe A V3 liquidation capture")
    parser.add_argument(
        "--resolved",
        default="bridge_stufe_a_v3_liquidation_resolved.json",
    )
    parser.add_argument(
        "--output",
        default="bridge_stufe_a_v3_liquidations.jsonl",
    )
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    pools = load_pools(Path(args.resolved))
    if not pools:
        raise SystemExit("no resolved pools")

    start_ts = int(WINDOW_START_UTC.timestamp())
    end_ts = int(WINDOW_END_UTC.timestamp())
    seen: set[tuple[str, str, int]] = set()
    ts_cache: dict[int, int] = {}
    rpc_by_chain: dict[str, str] = {}
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_start": WINDOW_START_UTC.isoformat(),
        "window_end": WINDOW_END_UTC.isoformat(),
        "topic0": TOPIC_LIQUIDATION_CALL,
        "chunk_blocks": CHUNK_BLOCKS,
        "smoke": args.smoke,
        "pools": [],
        "n_events_written": 0,
        "n_events_deduped": 0,
    }

    out_path = Path(args.output)
    # Patch get_logs to use liquidation topic by wrapping jsonrpc filter is
    # baked into get_logs_chunked_v3 — it uses TOPIC_ANSWER_UPDATED.
    # Local walker below uses TOPIC_LIQUIDATION_CALL.

    def get_logs(url: str, address: str, from_block: int, to_block: int) -> list[dict]:
        out: list[dict] = []
        n_calls = 0
        width = CHUNK_BLOCKS
        cur = from_block
        while cur <= to_block:
            end = min(cur + width - 1, to_block)
            params = {
                "fromBlock": hex(cur),
                "toBlock": hex(end),
                "address": address,
                "topics": [TOPIC_LIQUIDATION_CALL],
            }
            from bridge_stufe_a_rpc import RangeTooLarge, RpcError

            try:
                logs = jsonrpc(url, "eth_getLogs", [params], retries=MAX_RETRIES)
                if not isinstance(logs, list):
                    raise RpcError(f"eth_getLogs returned {type(logs)}")
                if len(logs) >= 10_000 and end > cur:
                    width = max(1, (end - cur + 1) // 2)
                    continue
                out.extend(logs)
                n_calls += 1
                if n_calls % 20 == 0:
                    print(
                        f"    chunk {n_calls} blocks {cur}-{end} n={len(logs)} total={len(out)}",
                        flush=True,
                    )
                time.sleep(0.12)
                cur = end + 1
                if len(logs) < 20 and width < CHUNK_BLOCKS:
                    width = min(CHUNK_BLOCKS, width * 2)
            except RangeTooLarge as exc:
                if end == cur:
                    raise RpcError(f"eth_getLogs failed at block {cur}: {exc}") from exc
                width = max(1, (end - cur + 1) // 2)
                print(f"    range too large {cur}-{end}; width→{width}", flush=True)
        return out

    with out_path.open("w", encoding="utf-8") as fh:
        for pool in pools:
            chain = pool["chain"]
            addr = pool["pool"]
            if chain not in rpc_by_chain:
                rpc_by_chain[chain] = probe_rpc(chain, DEFAULT_RPCS.get(chain))
                print(f"{chain}: using RPC {redact_url(rpc_by_chain[chain])}", flush=True)
            rpc = rpc_by_chain[chain]
            from_block = timestamp_to_block(rpc, start_ts, ts_cache)
            to_block = timestamp_to_block(rpc, end_ts, ts_cache)
            if args.smoke:
                to_block = min(to_block, from_block + 5_000)
            print(
                f"capture {chain} {pool['protocol']} {addr[:10]}… "
                f"blocks {from_block}-{to_block}",
                flush=True,
            )
            t0 = time.time()
            logs = get_logs(rpc, addr, from_block, to_block)
            n_written = 0
            n_deduped = 0
            ts_min = ts_max = None
            for log in logs:
                tx = str(log.get("transactionHash", "")).lower()
                li = as_int(log.get("logIndex", 0))
                key = (chain, tx, li)
                if key in seen:
                    n_deduped += 1
                    continue
                seen.add(key)
                bn = as_int(log.get("blockNumber"))
                ts = block_timestamp(rpc, bn, ts_cache)
                if ts < start_ts or ts > end_ts:
                    continue
                parsed = parse_liquidation_log(log)
                row = {
                    "chain": chain,
                    "protocol": pool["protocol"],
                    "pool": addr.lower(),
                    "block_number": bn,
                    "tx_hash": tx,
                    "log_index": li,
                    "timestamp": ts,
                    **parsed,
                }
                fh.write(json.dumps(row) + "\n")
                n_written += 1
                ts_min = ts if ts_min is None else min(ts_min, ts)
                ts_max = ts if ts_max is None else max(ts_max, ts)
            status = "ok" if n_written > 0 else "no_events_in_window"
            manifest["pools"].append(
                {
                    "chain": chain,
                    "protocol": pool["protocol"],
                    "pool": addr,
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
                f"  done {chain} {pool['protocol']} written={n_written} "
                f"deduped={n_deduped} status={status}",
                flush=True,
            )

    Path(str(out_path) + ".manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {out_path}")
    print(f"events={manifest['n_events_written']} pools={len(manifest['pools'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
