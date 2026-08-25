"""Schicht B: confirm each liquidation pool via getReservesList()."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from eth_hash.auto import keccak

from bridge_stufe_a_rpc import DEFAULT_RPCS, jsonrpc, redact_url
from bridge_stufe_a_v3_chainlink_resolve import probe_rpc

SEL_GET_RESERVES = "0x" + keccak(b"getReservesList()")[:4].hex()


def decode_address_array(raw: str) -> list[str]:
    body = raw[2:]
    if len(body) < 128:
        raise RuntimeError(f"short getReservesList: {raw[:66]}")
    offset = int(body[0:64], 16)
    # offset is in bytes from start of return data
    start = offset * 2
    n = int(body[start : start + 64], 16)
    addrs = []
    cursor = start + 64
    for _ in range(n):
        word = body[cursor : cursor + 64]
        addrs.append("0x" + word[-40:])
        cursor += 64
    return addrs


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve/verify Aave/Spark pools")
    parser.add_argument(
        "--candidates",
        default="config/bridge_stufe_a_v3_liquidation_pool_candidates.json",
    )
    parser.add_argument(
        "--gate",
        default="bridge_stufe_a_v3_liquidation_verification_gate.json",
    )
    parser.add_argument(
        "--output",
        default="bridge_stufe_a_v3_liquidation_resolved.json",
    )
    args = parser.parse_args()

    gate = json.loads(Path(args.gate).read_text(encoding="utf-8"))
    if not gate.get("all_verified") or gate.get("resolver_release") != "RELEASED":
        raise SystemExit(f"resolver blocked: {args.gate}")

    body = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    verified = {
        (r["chain"], r["protocol"])
        for r in gate.get("candidates", [])
        if r.get("status") == "VERIFIED"
    }

    rows = []
    all_ok = True
    for pool in body.get("pools", []):
        key = (pool["chain"], pool["protocol"])
        if key not in verified:
            continue
        chain = pool["chain"]
        addr = pool["pool"]
        try:
            rpc, latest = probe_rpc(chain, DEFAULT_RPCS.get(chain))
            raw = jsonrpc(rpc, "eth_call", [{"to": addr, "data": SEL_GET_RESERVES}, "latest"])
            reserves = decode_address_array(raw)
        except Exception as exc:
            print(f"ERROR {chain} {pool['protocol']} {addr}: {exc}", file=sys.stderr)
            return 1
        ok = len(reserves) > 0
        if not ok:
            all_ok = False
        status = "RESOLVED" if ok else "V3_UNTESTBAR"
        print(
            f"{chain} {pool['protocol']}: reserves={len(reserves)} "
            f"rpc={redact_url(rpc)} status={status}",
            flush=True,
        )
        rows.append(
            {
                "protocol": pool["protocol"],
                "chain": chain,
                "pool": addr.lower(),
                "n_reserves": len(reserves),
                "rpc_url": redact_url(rpc),
                "latest_block": latest,
                "plausibility_check": "pass" if ok else "fail",
                "status": status,
            }
        )

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gate": args.gate,
        "pools": rows,
        "all_resolved": all_ok and bool(rows),
        "capture_release": "RELEASED" if all_ok and rows else "BLOCKED",
    }
    Path(args.output).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    print(f"all_resolved={out['all_resolved']} capture_release={out['capture_release']}")
    return 0 if out["all_resolved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
