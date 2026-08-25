"""PSM BuyGem/SellGem + CCTP DepositForBurn/MintAndWithdraw capture (Stufe A V3).

Pre-Reg §3.0.4. ETH-only. Occupancy join is OR in the minute (downstream).

Usage:
  python3 scripts/bridge_stufe_a_v3_stablecoin_mint_burn_capture.py
  python3 scripts/bridge_stufe_a_v3_stablecoin_mint_burn_capture.py --smoke
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
from bridge_stufe_a_rpc import (
    DEFAULT_RPCS,
    RpcError,
    as_int,
    block_timestamp,
    jsonrpc,
    redact_url,
    timestamp_to_block,
)
from bridge_stufe_a_v3_chainlink_capture import CHUNK_BLOCKS, MAX_RETRIES, probe_rpc

TOPIC_BY_EVENT = {
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
        b"DepositForBurn(address,uint256,address,bytes32,uint32,bytes32,bytes32,uint256,uint32,bytes)"
    ).hex(),
    "cctp_v2_mint_and_withdraw": "0x"
    + keccak(b"MintAndWithdraw(address,uint256,address,uint256)").hex(),
}

EVENT_NAME = {
    "psm_buy_gem": "BuyGem",
    "psm_sell_gem": "SellGem",
    "cctp_v1_deposit_for_burn": "DepositForBurn",
    "cctp_v1_mint_and_withdraw": "MintAndWithdraw",
    "cctp_v2_deposit_for_burn": "DepositForBurn",
    "cctp_v2_mint_and_withdraw": "MintAndWithdraw",
}


def topic0_of(log: dict) -> str:
    topics = log.get("topics") or []
    if not topics:
        return ""
    return str(topics[0]).lower()


def event_key_for_topic(topic: str) -> str | None:
    t = topic.lower()
    for key, val in TOPIC_BY_EVENT.items():
        if val.lower() == t:
            return key
    return None


def load_contracts(resolved_path: Path) -> list[dict]:
    body = json.loads(resolved_path.read_text(encoding="utf-8"))
    if not body.get("all_resolved") or body.get("capture_release") != "RELEASED":
        raise SystemExit("capture blocked: stablecoin mint/burn resolved file not released")
    return [p for p in body.get("contracts", []) if p.get("status") == "RESOLVED"]


def block_timestamp_resilient(
    chain: str,
    rpc_by_chain: dict[str, str],
    block: int,
    ts_cache: dict[tuple[str, int], int],
) -> int:
    key = (chain, block)
    if key in ts_cache:
        return ts_cache[key]
    last_err: Exception | None = None
    for attempt in range(4):
        rpc = rpc_by_chain[chain]
        try:
            ts = block_timestamp(rpc, block, None)
            ts_cache[key] = ts
            return ts
        except RpcError as exc:
            last_err = exc
            print(
                f"    ts RPC fail {redact_url(rpc)} block={block}: {exc}; reprobe…",
                flush=True,
            )
            time.sleep(min(2**attempt, 8))
            rpc_by_chain[chain] = probe_rpc(chain, DEFAULT_RPCS.get(chain))
            print(f"    {chain}: switched RPC → {redact_url(rpc_by_chain[chain])}", flush=True)
    raise RpcError(f"block_timestamp failed for {chain} block {block}: {last_err}")


def get_logs(url: str, address: str, from_block: int, to_block: int, topic0: str) -> list[dict]:
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
            "topics": [topic0],
        }
        from bridge_stufe_a_rpc import RangeTooLarge

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


def main() -> int:
    parser = argparse.ArgumentParser(description="Stufe A V3 stablecoin mint/burn capture")
    parser.add_argument(
        "--resolved",
        default="bridge_stufe_a_v3_stablecoin_mint_burn_resolved.json",
    )
    parser.add_argument(
        "--output",
        default="bridge_stufe_a_v3_stablecoin_mint_burn.jsonl",
    )
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--append", action="store_true")
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Restrict to chain:protocol (repeatable)",
    )
    args = parser.parse_args()

    contracts = load_contracts(Path(args.resolved))
    if args.only:
        wanted = {tuple(x.split(":", 1)) for x in args.only}
        contracts = [c for c in contracts if (c["chain"], c["protocol"]) in wanted]
    if not contracts:
        raise SystemExit("no resolved stablecoin mint/burn contracts")

    start_ts = int(WINDOW_START_UTC.timestamp())
    end_ts = int(WINDOW_END_UTC.timestamp())
    seen: set[tuple[str, str, int]] = set()
    occupied_minutes: set[int] = set()
    events_by_name: dict[str, int] = {}
    ts_cache: dict[tuple[str, int], int] = {}
    block_cache: dict[int, int] = {}
    rpc_by_chain: dict[str, str] = {}
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_start": WINDOW_START_UTC.isoformat(),
        "window_end": WINDOW_END_UTC.isoformat(),
        "topics": TOPIC_BY_EVENT,
        "chunk_blocks": CHUNK_BLOCKS,
        "smoke": args.smoke,
        "append": args.append,
        "only": args.only,
        "contracts": [],
        "n_events_written": 0,
        "n_events_deduped": 0,
        "n_occupied_minutes": 0,
        "events_by_name": {},
    }

    out_path = Path(args.output)
    if args.append and out_path.exists():
        with out_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                seen.add((obj["chain"], obj["tx_hash"], int(obj["log_index"])))
                occupied_minutes.add(int(obj["timestamp"]) // 60)
                events_by_name[obj["event"]] = events_by_name.get(obj["event"], 0) + 1
        print(f"append: seeded {len(seen)} prior keys from {out_path}", flush=True)

    mode = "a" if args.append else "w"
    with out_path.open(mode, encoding="utf-8") as fh:
        for item in contracts:
            chain = item["chain"]
            addr = item["address"]
            if chain not in rpc_by_chain:
                rpc_by_chain[chain] = probe_rpc(chain, DEFAULT_RPCS.get(chain))
                print(f"{chain}: using RPC {redact_url(rpc_by_chain[chain])}", flush=True)
            rpc = rpc_by_chain[chain]
            from_block = timestamp_to_block(rpc, start_ts, block_cache)
            to_block = timestamp_to_block(rpc, end_ts, block_cache)
            if args.smoke:
                to_block = min(to_block, from_block + 5_000)
            event_keys = item.get("events") or []
            print(
                f"capture {chain} {item['protocol']} {addr[:10]}… "
                f"blocks {from_block}-{to_block} events={event_keys}",
                flush=True,
            )
            t0 = time.time()
            n_written = 0
            n_deduped = 0
            n_raw = 0
            ts_min = ts_max = None
            for ev_key in event_keys:
                topic = TOPIC_BY_EVENT[ev_key]
                logs = get_logs(rpc_by_chain[chain], addr, from_block, to_block, topic)
                n_raw += len(logs)
                for log in logs:
                    tx = str(log.get("transactionHash", "")).lower()
                    li = as_int(log.get("logIndex", 0))
                    key = (chain, tx, li)
                    if key in seen:
                        n_deduped += 1
                        continue
                    seen.add(key)
                    bn = as_int(log.get("blockNumber"))
                    ts = block_timestamp_resilient(chain, rpc_by_chain, bn, ts_cache)
                    if ts < start_ts or ts > end_ts:
                        continue
                    t0h = topic0_of(log)
                    matched = event_key_for_topic(t0h) or ev_key
                    topics = log.get("topics") or []
                    row = {
                        "chain": chain,
                        "protocol": item["protocol"],
                        "contract": addr.lower(),
                        "event": EVENT_NAME.get(matched, matched),
                        "event_key": matched,
                        "block_number": bn,
                        "tx_hash": tx,
                        "log_index": li,
                        "timestamp": ts,
                    }
                    if matched.startswith("psm_") and len(topics) >= 2:
                        row["owner"] = "0x" + str(topics[1])[-40:]
                    fh.write(json.dumps(row) + "\n")
                    n_written += 1
                    occupied_minutes.add(ts // 60)
                    events_by_name[row["event"]] = events_by_name.get(row["event"], 0) + 1
                    ts_min = ts if ts_min is None else min(ts_min, ts)
                    ts_max = ts if ts_max is None else max(ts_max, ts)
            status = "ok" if n_written > 0 else "no_events_in_window"
            manifest["contracts"].append(
                {
                    "chain": chain,
                    "protocol": item["protocol"],
                    "address": addr,
                    "n_logs_raw": n_raw,
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
                f"  done {chain} {item['protocol']} written={n_written} "
                f"deduped={n_deduped} status={status}",
                flush=True,
            )

    manifest["n_occupied_minutes"] = len(occupied_minutes)
    manifest["events_by_name"] = events_by_name
    Path(str(out_path) + ".manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {out_path}")
    print(f"events={manifest['n_events_written']} contracts={len(manifest['contracts'])}")
    print(f"occupied_minutes={len(occupied_minutes)} events_by_name={events_by_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
