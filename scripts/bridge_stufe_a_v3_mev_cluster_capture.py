"""MEV-cluster capture: cross-chain EOA same-UTC-minute occupancy (Stufe A V3).

Pre-Reg §3.0.5. Not eth_getLogs — full block scan + receipts + join.

Usage:
  python3 scripts/bridge_stufe_a_v3_mev_cluster_capture.py --smoke
  python3 scripts/bridge_stufe_a_v3_mev_cluster_capture.py
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bridge_stufe_a_config import WINDOW_END_UTC, WINDOW_START_UTC
from bridge_stufe_a_rpc import (
    DEFAULT_RPCS,
    RangeTooLarge,
    RpcError,
    as_int,
    jsonrpc,
    jsonrpc_batch,
    redact_url,
    timestamp_to_block,
)
from bridge_stufe_a_v3_chainlink_capture import MAX_RETRIES


def load_resolved(path: Path) -> dict:
    body = json.loads(path.read_text(encoding="utf-8"))
    if not body.get("all_resolved") or body.get("capture_release") != "RELEASED":
        raise SystemExit("capture blocked: mev-cluster resolved file not released")
    return body


def load_exclusion(path: Path) -> set[str]:
    body = json.loads(path.read_text(encoding="utf-8"))
    out = set()
    for e in body.get("entries") or []:
        a = (e.get("address") or "").lower()
        if a.startswith("0x") and len(a) == 42:
            out.add(a)
    return out


def open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activity (
            chain TEXT NOT NULL,
            address TEXT NOT NULL,
            minute INTEGER NOT NULL,
            PRIMARY KEY (chain, address, minute)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS checkpoint (
            chain TEXT PRIMARY KEY,
            next_block INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def get_checkpoint(conn: sqlite3.Connection, chain: str, default: int) -> int:
    row = conn.execute(
        "SELECT next_block FROM checkpoint WHERE chain=?", (chain,)
    ).fetchone()
    return int(row[0]) if row else default


def set_checkpoint(conn: sqlite3.Connection, chain: str, next_block: int) -> None:
    conn.execute(
        "INSERT INTO checkpoint(chain, next_block) VALUES(?, ?) "
        "ON CONFLICT(chain) DO UPDATE SET next_block=excluded.next_block",
        (chain, next_block),
    )


def insert_activity(
    conn: sqlite3.Connection, chain: str, rows: list[tuple[str, int]]
) -> int:
    if not rows:
        return 0
    before = conn.total_changes
    conn.executemany(
        "INSERT OR IGNORE INTO activity(chain, address, minute) VALUES(?,?,?)",
        [(chain, a, m) for a, m in rows],
    )
    return conn.total_changes - before


def fetch_block_headers(rpc: str, blocks: list[int], batch_size: int) -> tuple[list[dict | None], int]:
    """Return (headers, adapted_batch_size). Shrinks only on RangeTooLarge."""
    out: list[dict | None] = []
    adapted = max(1, batch_size)
    i = 0
    while i < len(blocks):
        size = min(adapted, len(blocks) - i)
        while True:
            try:
                chunk = blocks[i : i + size]
                calls = [("eth_getBlockByNumber", [hex(b), False]) for b in chunk]
                results = jsonrpc_batch(rpc, calls, retries=MAX_RETRIES)
                out.extend(results)
                i += size
                break
            except RangeTooLarge:
                if size == 1:
                    raise
                size = max(1, size // 2)
                adapted = size
                print(f"    header batch too large → size {size}", flush=True)
    return out, adapted


def fetch_receipts(rpc: str, blocks: list[int], batch_size: int) -> tuple[list[list[dict] | None], int]:
    out: list[list[dict] | None] = []
    adapted = max(1, batch_size)
    i = 0
    while i < len(blocks):
        size = min(adapted, len(blocks) - i)
        while True:
            try:
                chunk = blocks[i : i + size]
                calls = [("eth_getBlockReceipts", [hex(b)]) for b in chunk]
                results = jsonrpc_batch(rpc, calls, retries=MAX_RETRIES)
                out.extend(results)
                i += size
                break
            except RangeTooLarge:
                if size == 1:
                    raise
                size = max(1, size // 2)
                adapted = size
                print(f"    receipt batch too large → size {size}", flush=True)
    return out, adapted


def scan_chain(
    conn: sqlite3.Connection,
    chain: str,
    rpc: str,
    from_block: int,
    to_block: int,
    header_batch: int,
    receipt_batch: int,
    chunk_blocks: int,
    exclusion: set[str],
    address_allowlist: set[str] | None = None,
) -> dict:
    cur = get_checkpoint(conn, chain, from_block)
    if cur < from_block:
        cur = from_block
    n_blocks = 0
    n_success_tx = 0
    n_rows = 0
    n_skipped_allowlist = 0
    hdr_bs = header_batch
    rcpt_bs = receipt_batch
    t0 = time.time()
    allow_n = len(address_allowlist) if address_allowlist is not None else None
    print(
        f"scan {chain} blocks {cur}-{to_block} "
        f"hdr_batch={hdr_bs} rcpt_batch={rcpt_bs} chunk={chunk_blocks} "
        f"allowlist={allow_n} rpc={redact_url(rpc)}",
        flush=True,
    )
    while cur <= to_block:
        end = min(cur + chunk_blocks - 1, to_block)
        blocks = list(range(cur, end + 1))
        # Overlap header + receipt RPC latency.
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_h = pool.submit(fetch_block_headers, rpc, blocks, hdr_bs)
            fut_r = pool.submit(fetch_receipts, rpc, blocks, rcpt_bs)
            headers, hdr_bs = fut_h.result()
            rcpts, rcpt_bs = fut_r.result()
        rows: list[tuple[str, int]] = []
        for blk, receipts in zip(headers, rcpts):
            if not isinstance(blk, dict):
                continue
            n_blocks += 1
            ts = as_int(blk["timestamp"])
            minute = ts // 60
            if not isinstance(receipts, list):
                raise RpcError(f"{chain} missing receipts at block {blk.get('number')}")
            for rcpt in receipts:
                if not isinstance(rcpt, dict):
                    continue
                status = rcpt.get("status")
                if status not in ("0x1", 1, "1"):
                    continue
                frm = str(rcpt.get("from") or "").lower()
                if len(frm) != 42 or not frm.startswith("0x"):
                    continue
                if frm in exclusion:
                    continue
                n_success_tx += 1
                if address_allowlist is not None and frm not in address_allowlist:
                    n_skipped_allowlist += 1
                    continue
                rows.append((frm, minute))
        n_rows += insert_activity(conn, chain, rows)
        set_checkpoint(conn, chain, end + 1)
        conn.commit()
        # Progress every ~5k blocks (or every chunk if small).
        if chunk_blocks <= 200 or (end - from_block) // chunk_blocks % 5 == 0:
            rate = n_blocks / max(time.time() - t0, 1e-6)
            eta_h = (to_block - end) / max(rate, 1e-6) / 3600
            print(
                f"  {chain} … block {end}/{to_block} success_tx={n_success_tx} "
                f"rows+={n_rows} skip_allow={n_skipped_allowlist} "
                f"rcpt_bs={rcpt_bs} {rate:.1f} blk/s eta≈{eta_h:.1f}h",
                flush=True,
            )
        cur = end + 1
    return {
        "chain": chain,
        "from_block": from_block,
        "to_block": to_block,
        "n_blocks_scanned": n_blocks,
        "n_success_tx": n_success_tx,
        "n_activity_inserts": n_rows,
        "n_skipped_allowlist": n_skipped_allowlist,
        "final_header_batch": hdr_bs,
        "final_receipt_batch": rcpt_bs,
        "elapsed_s": round(time.time() - t0, 2),
    }


def is_eoa(rpc: str, address: str) -> bool:
    code = jsonrpc(rpc, "eth_getCode", [address, "latest"], retries=MAX_RETRIES)
    return code in ("0x", "0x0", "", None)


def build_occupancy(
    conn: sqlite3.Connection,
    rpc_eth: str,
    rpc_gno: str,
    exclusion: set[str],
    out_path: Path,
) -> dict:
    # Distinct addresses appearing in the same minute on both chains.
    candidates = conn.execute(
        """
        SELECT e.address, e.minute
        FROM activity e
        JOIN activity g
          ON e.address = g.address AND e.minute = g.minute
        WHERE e.chain = 'ethereum' AND g.chain = 'gnosis'
        """
    ).fetchall()
    addrs = sorted({a for a, _ in candidates if a not in exclusion})
    print(f"cross-chain (address,minute) pairs={len(candidates)} unique_addrs={len(addrs)}", flush=True)

    eoa_ok: dict[str, bool] = {}
    for i, addr in enumerate(addrs):
        # Prefer ethereum code; contracts are contracts on both.
        try:
            eoa_ok[addr] = is_eoa(rpc_eth, addr)
        except RpcError:
            eoa_ok[addr] = is_eoa(rpc_gno, addr)
        if (i + 1) % 200 == 0:
            print(f"  eth_getCode {i+1}/{len(addrs)}", flush=True)
        time.sleep(0.02)

    occupied: dict[int, list[str]] = {}
    for addr, minute in candidates:
        if addr in exclusion:
            continue
        if not eoa_ok.get(addr):
            continue
        occupied.setdefault(int(minute), []).append(addr)

    with out_path.open("w", encoding="utf-8") as fh:
        for minute in sorted(occupied):
            eoas = sorted(set(occupied[minute]))
            row = {
                "chain": "cross",
                "minute": minute,
                "timestamp": minute * 60,
                "n_eoas": len(eoas),
                "eoas": eoas[:20],  # cap payload; full count in n_eoas
                "event": "CrossChainEoaMinute",
            }
            fh.write(json.dumps(row) + "\n")

    return {
        "n_candidate_pairs": len(candidates),
        "n_unique_addrs": len(addrs),
        "n_eoa": sum(1 for v in eoa_ok.values() if v),
        "n_contract": sum(1 for v in eoa_ok.values() if not v),
        "n_occupied_minutes": len(occupied),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stufe A V3 MEV-cluster capture")
    parser.add_argument("--resolved", default="bridge_stufe_a_v3_mev_cluster_resolved.json")
    parser.add_argument("--output", default="bridge_stufe_a_v3_mev_cluster.jsonl")
    parser.add_argument("--db", default="bridge_stufe_a_v3_mev_cluster_activity.sqlite")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--join-only", action="store_true", help="Skip scan; join from DB")
    args = parser.parse_args()

    resolved = load_resolved(Path(args.resolved))
    excl_path = Path(
        resolved.get("exclusion_list")
        or "config/bridge_stufe_a_v3_mev_cluster_exclusion_list.json"
    )
    exclusion = load_exclusion(excl_path)
    chunk_blocks = int(resolved.get("recommended_chunk_blocks") or 1000)
    header_by_chain = {
        c["chain"]: int(
            c.get("recommended_header_batch_size")
            or c.get("recommended_batch_size")
            or 50
        )
        for c in resolved.get("chains", [])
    }
    receipt_by_chain = {
        c["chain"]: int(
            c.get("recommended_receipt_batch_size")
            or c.get("recommended_batch_size")
            or 25
        )
        for c in resolved.get("chains", [])
    }
    preferred_host = {
        c["chain"]: (c.get("rpc_url") or "").split("://")[-1]
        for c in resolved.get("chains", [])
    }

    start_ts = int(WINDOW_START_UTC.timestamp())
    end_ts = int(WINDOW_END_UTC.timestamp())
    conn = open_db(Path(args.db))
    rpc_by_chain: dict[str, str] = {}
    scan_stats = []

    def pick_rpc(chain: str) -> str:
        from bridge_stufe_a_v3_chainlink_capture import rpc_candidates

        host = preferred_host.get(chain) or ""
        ordered = rpc_candidates(chain, DEFAULT_RPCS.get(chain))
        if host:
            ordered = sorted(ordered, key=lambda u: 0 if host in u else 1)
        # Reuse probe order but prefer resolved host.
        errors: list[str] = []
        for url in ordered:
            try:
                as_int(jsonrpc(url, "eth_blockNumber", [], retries=2))
                return url
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{redact_url(url)}: {exc}")
        raise RpcError(f"no RPC for {chain}: {errors[:3]}")

    if not args.join_only:
        # Gnosis first (lighter), then Ethereum filtered to gnosis address universe.
        # Same-minute join only needs ETH rows for addresses that appear on Gnosis.
        for chain in ("gnosis", "ethereum"):
            rpc_by_chain[chain] = pick_rpc(chain)
            print(f"{chain}: using RPC {redact_url(rpc_by_chain[chain])}", flush=True)
            from_block = timestamp_to_block(rpc_by_chain[chain], start_ts)
            to_block = timestamp_to_block(rpc_by_chain[chain], end_ts)
            if args.smoke:
                to_block = min(to_block, from_block + 200)
            allowlist: set[str] | None = None
            if chain == "ethereum":
                allowlist = {
                    r[0]
                    for r in conn.execute(
                        "SELECT DISTINCT address FROM activity WHERE chain='gnosis'"
                    )
                }
                print(f"ethereum allowlist from gnosis: {len(allowlist)} addresses", flush=True)
            # Dense ETH receipts often exceed provider payload at batch=25.
            rcpt = receipt_by_chain.get(chain, 25)
            if chain == "ethereum":
                rcpt = min(rcpt, 12)
            stats = scan_chain(
                conn,
                chain,
                rpc_by_chain[chain],
                from_block,
                to_block,
                header_by_chain.get(chain, 50),
                rcpt,
                chunk_blocks if not args.smoke else min(chunk_blocks, 50),
                exclusion,
                address_allowlist=allowlist,
            )
            scan_stats.append(stats)
            print(f"  done {chain}: {stats}", flush=True)
    else:
        for chain in ("ethereum", "gnosis"):
            rpc_by_chain[chain] = pick_rpc(chain)

    join_stats = build_occupancy(
        conn,
        rpc_by_chain["ethereum"],
        rpc_by_chain["gnosis"],
        exclusion,
        Path(args.output),
    )
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_start": WINDOW_START_UTC.isoformat(),
        "window_end": WINDOW_END_UTC.isoformat(),
        "smoke": args.smoke,
        "exclusion_n": len(exclusion),
        "scan": scan_stats,
        "join": join_stats,
        "n_events_written": join_stats["n_occupied_minutes"],
    }
    Path(str(args.output) + ".manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {args.output}")
    print(f"occupied_minutes={join_stats['n_occupied_minutes']}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
