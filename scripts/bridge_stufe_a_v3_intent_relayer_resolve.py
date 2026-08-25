"""Schicht B: Across numberOfDeposits() / CoW vaultRelayer()."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from eth_hash.auto import keccak

from bridge_stufe_a_rpc import DEFAULT_RPCS, jsonrpc, redact_url
from bridge_stufe_a_v3_chainlink_resolve import probe_rpc

SEL_NUMBER_OF_DEPOSITS = "0x" + keccak(b"numberOfDeposits()")[:4].hex()
SEL_VAULT_RELAYER = "0x" + keccak(b"vaultRelayer()")[:4].hex()


def decode_uint(raw: str) -> int:
    body = raw[2:] if raw.startswith("0x") else raw
    if len(body) < 64:
        raise RuntimeError(f"short uint return: {raw[:66]}")
    return int(body[:64], 16)


def decode_address(raw: str) -> str:
    body = raw[2:] if raw.startswith("0x") else raw
    if len(body) < 64:
        raise RuntimeError(f"short address return: {raw[:66]}")
    return "0x" + body[-40:]


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve Intent-Relayer contracts")
    parser.add_argument(
        "--candidates",
        default="config/bridge_stufe_a_v3_intent_relayer_candidates.json",
    )
    parser.add_argument(
        "--gate",
        default="bridge_stufe_a_v3_intent_relayer_verification_gate.json",
    )
    parser.add_argument(
        "--output",
        default="bridge_stufe_a_v3_intent_relayer_resolved.json",
    )
    args = parser.parse_args()

    gate = json.loads(Path(args.gate).read_text(encoding="utf-8"))
    if not gate.get("all_verified") or gate.get("resolver_release") != "RELEASED":
        raise SystemExit(f"resolver blocked: {args.gate}")

    body = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    verified = {
        (r["chain"], r["protocol"], r.get("role"))
        for r in gate.get("candidates", [])
        if r.get("status") == "VERIFIED"
    }

    rows = []
    all_ok = True
    for item in body.get("contracts", []):
        key = (item["chain"], item["protocol"], item.get("role"))
        if key not in verified:
            continue
        chain = item["chain"]
        addr = item["address"]
        protocol = item["protocol"]
        try:
            rpc, latest = probe_rpc(chain, DEFAULT_RPCS.get(chain))
            if protocol == "across":
                raw = jsonrpc(
                    rpc, "eth_call", [{"to": addr, "data": SEL_NUMBER_OF_DEPOSITS}, "latest"]
                )
                n_dep = decode_uint(raw)
                extra = {"number_of_deposits": n_dep}
                ok = n_dep >= 0
            elif protocol == "cow":
                raw = jsonrpc(
                    rpc, "eth_call", [{"to": addr, "data": SEL_VAULT_RELAYER}, "latest"]
                )
                vault = decode_address(raw)
                extra = {"vault_relayer": vault}
                ok = int(vault, 16) != 0
            else:
                raise RuntimeError(f"unexpected protocol {protocol}")
        except Exception as exc:
            print(f"ERROR {chain} {protocol} {addr}: {exc}", file=sys.stderr)
            return 1
        if not ok:
            all_ok = False
        status = "RESOLVED" if ok else "V3_UNTESTBAR"
        print(
            f"{chain} {protocol}: {extra} rpc={redact_url(rpc)} status={status}",
            flush=True,
        )
        rows.append(
            {
                "protocol": protocol,
                "chain": chain,
                "role": item.get("role"),
                "address": addr.lower(),
                "events": item.get("events") or [],
                "rpc_url": redact_url(rpc),
                "latest_block": latest,
                "plausibility_check": "pass" if ok else "fail",
                "status": status,
                **extra,
            }
        )

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gate": args.gate,
        "contracts": rows,
        "all_resolved": all_ok and bool(rows),
        "capture_release": "RELEASED" if all_ok and rows else "BLOCKED",
    }
    Path(args.output).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    print(f"all_resolved={out['all_resolved']} capture_release={out['capture_release']}")
    return 0 if out["all_resolved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
