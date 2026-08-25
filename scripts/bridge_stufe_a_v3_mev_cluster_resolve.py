"""Schicht B: RPC smoke for MEV-cluster (batch size + receipt method)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from bridge_stufe_a_rpc import DEFAULT_RPCS, RpcError, as_int, jsonrpc, jsonrpc_batch, redact_url


def try_block_receipts(rpc: str, block: int) -> tuple[bool, str]:
    try:
        raw = jsonrpc(rpc, "eth_getBlockReceipts", [hex(block)], retries=2)
        if not isinstance(raw, list) or not raw:
            return False, "empty_or_non_list"
        sample = raw[0]
        if "status" not in sample or "from" not in sample:
            return False, "missing_status_or_from"
        return True, f"n_receipts={len(raw)}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:160]


def try_full_block(rpc: str, block: int) -> tuple[bool, str, int]:
    try:
        blk = jsonrpc(rpc, "eth_getBlockByNumber", [hex(block), True], retries=2)
        if not isinstance(blk, dict):
            return False, "non_dict", 0
        txs = blk.get("transactions") or []
        if not txs:
            return False, "no_txs", 0
        tx0 = txs[0]
        if not isinstance(tx0, dict) or "from" not in tx0:
            return False, "tx_missing_from", 0
        ts = as_int(blk["timestamp"])
        return True, f"n_txs={len(txs)} ts={ts}", len(txs)
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:160], 0


def probe_batch_size(
    rpc: str,
    start_block: int,
    sizes: list[int],
    *,
    full_txs: bool = False,
) -> int:
    best = 1
    for size in sizes:
        calls = [
            ("eth_getBlockByNumber", [hex(start_block + i), full_txs])
            for i in range(size)
        ]
        t0 = time.time()
        try:
            results = jsonrpc_batch(rpc, calls, retries=2)
            if len(results) != size or any(r is None for r in results):
                print(f"  batch full={full_txs} {size}: incomplete", flush=True)
                break
            elapsed = time.time() - t0
            print(f"  batch full={full_txs} {size}: ok in {elapsed:.2f}s", flush=True)
            best = size
        except Exception as exc:  # noqa: BLE001
            print(f"  batch full={full_txs} {size}: fail {exc}", flush=True)
            break
    return best


def pick_rpc_with_batch(chain: str, primary: str | None) -> dict:
    """Pick an RPC that supports full blocks + receipts; prefer batch≥10."""
    from bridge_stufe_a_v3_chainlink_capture import rpc_candidates

    last_err: Exception | None = None
    fallback: dict | None = None
    for url in rpc_candidates(chain, primary):
        try:
            latest = as_int(jsonrpc(url, "eth_blockNumber", [], retries=2))
            sample = max(0, latest - 64)
            ok_full, msg_full, n_txs = try_full_block(url, sample)
            ok_rcpt, msg_rcpt = try_block_receipts(url, sample)
            print(
                f"{chain}: try {redact_url(url)} full={ok_full} receipts={ok_rcpt}",
                flush=True,
            )
            if not ok_full or not ok_rcpt:
                continue
            print(f"{chain}: probing batch on {redact_url(url)}…", flush=True)
            batch_hdr = probe_batch_size(url, sample - 200, [10, 25, 50, 75, 100], full_txs=False)
            batch_full = probe_batch_size(
                url, sample - 50, [1, 2, 5, 10, 15, 20], full_txs=True
            )
            batch_rcpt = probe_batch_size(url, sample - 50, [10, 25, 50, 75, 100], full_txs=False)
            # Receipt batch probe uses getBlockByNumber headers only as size proxy;
            # dedicated receipt probe below.
            rcpt_best = 1
            for size in [10, 25, 50, 75, 100]:
                try:
                    calls = [("eth_getBlockReceipts", [hex(sample - i)]) for i in range(size)]
                    jsonrpc_batch(url, calls, retries=1)
                    rcpt_best = size
                    print(f"  batch receipts {size}: ok", flush=True)
                except Exception as exc:  # noqa: BLE001
                    print(f"  batch receipts {size}: fail {exc}", flush=True)
                    break
            row = {
                "chain": chain,
                "rpc_url": redact_url(url),
                "rpc_url_raw": url,
                "latest_block": latest,
                "sample_block": sample,
                "full_block_ok": True,
                "full_block_detail": msg_full,
                "receipt_method": "eth_getBlockReceipts",
                "receipt_detail": msg_rcpt,
                "recommended_batch_size": max(batch_full, 1),
                "recommended_header_batch_size": max(batch_hdr, 1),
                "recommended_receipt_batch_size": max(rcpt_best, 1),
                "sample_n_txs": n_txs,
                "status": "RESOLVED",
            }
            # Prefer endpoints that can batch headers+receipts (≥10); keep weak
            # endpoints only as last-resort fallback for full-window capture.
            if batch_hdr >= 10 and rcpt_best >= 10:
                return row
            if fallback is None or (
                rcpt_best * batch_hdr
                > int(fallback.get("recommended_receipt_batch_size") or 1)
                * int(fallback.get("recommended_header_batch_size") or 1)
            ):
                fallback = row
                print(
                    f"{chain}: weak batch hdr={batch_hdr} rcpt={rcpt_best} "
                    f"— keep as fallback, continue",
                    flush=True,
                )
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            print(f"{chain}: skip {redact_url(url or '')}: {exc}", flush=True)
            continue
    if fallback is not None:
        print(
            f"{chain}: using fallback {fallback.get('rpc_url')} "
            f"hdr={fallback.get('recommended_header_batch_size')} "
            f"rcpt={fallback.get('recommended_receipt_batch_size')}",
            flush=True,
        )
        return fallback
    raise RpcError(f"no usable RPC for {chain}: {last_err}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve/smoke MEV-cluster RPC strategy")
    parser.add_argument(
        "--candidates",
        default="config/bridge_stufe_a_v3_mev_cluster_candidates.json",
    )
    parser.add_argument(
        "--gate",
        default="bridge_stufe_a_v3_mev_cluster_verification_gate.json",
    )
    parser.add_argument(
        "--output",
        default="bridge_stufe_a_v3_mev_cluster_resolved.json",
    )
    args = parser.parse_args()

    gate = json.loads(Path(args.gate).read_text(encoding="utf-8"))
    if not gate.get("all_verified") or gate.get("resolver_release") != "RELEASED":
        raise SystemExit(f"resolver blocked: {args.gate}")

    body = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    verified_chains = [
        r["chain"]
        for r in gate.get("candidates", [])
        if r.get("status") == "VERIFIED"
    ]
    if set(verified_chains) != {"ethereum", "gnosis"}:
        raise SystemExit(f"expected ethereum+gnosis verified, got {verified_chains}")

    chain_rows = []
    all_ok = True
    for chain in ("ethereum", "gnosis"):
        try:
            row = pick_rpc_with_batch(chain, DEFAULT_RPCS.get(chain))
        except Exception as exc:
            print(f"ERROR probe {chain}: {exc}", file=sys.stderr)
            return 1
        print(
            f"{chain}: selected {row['rpc_url']} batch={row['recommended_batch_size']}",
            flush=True,
        )
        # Do not persist raw URL secrets beyond host redaction in public fields;
        # capture re-probes via DEFAULT_RPCS + same fallbacks.
        row.pop("rpc_url_raw", None)
        chain_rows.append(row)
        if row["status"] != "RESOLVED":
            all_ok = False

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gate": args.gate,
        "candidates_file": args.candidates,
        "exclusion_list": body.get("exclusion_list"),
        "operationalization": body.get("operationalization"),
        "chains": chain_rows,
        "all_resolved": all_ok and len(chain_rows) == 2,
        "capture_release": "RELEASED" if all_ok and len(chain_rows) == 2 else "BLOCKED",
        "recommended_chunk_blocks": 1000,
    }
    Path(args.output).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    print(f"all_resolved={out['all_resolved']} capture_release={out['capture_release']}")
    return 0 if out["all_resolved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
