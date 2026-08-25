#!/usr/bin/env python3
"""RPC connectivity and block-time probe.

Determines whether the configured chain RPCs are reachable and can serve
block-timestamp series. The result decides Stufe A feasibility. No thresholds,
no pre-registration — this is a data-availability probe only.

Defaults: CLAUDE.md env (GNOSIS_RPC, PEAQ_RPC) plus ETH HTTP from
seed_gas_prices.py (ETH_RPC / public fallbacks). peaq WebSocket is skipped
by the HTTP probe.

Usage:
    python3 scripts/probe_chain_rpcs.py
    python3 scripts/probe_chain_rpcs.py --blocks 500 --out blocktimes_probe.json
    python3 scripts/probe_chain_rpcs.py --rpc ethereum=https://eth.llamarpc.com --rpc arbitrum=https://arb1.arbitrum.io/rpc
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

# ETH HTTP fallbacks — same list as cherrystudio astrocore/seed_gas_prices.py
ETH_HTTP_FALLBACKS = [
    os.environ.get("ETH_RPC", "https://ethereum-rpc.publicnode.com"),
    "https://eth.llamarpc.com",
    "https://rpc.ankr.com/eth",
    "https://eth.drpc.org",
    "https://1rpc.io/eth",
    "https://cloudflare-eth.com",
]

DEFAULT_RPCS = {
    "ethereum": ETH_HTTP_FALLBACKS[0],
    "gnosis": os.environ.get("GNOSIS_RPC", "https://rpc.gnosischain.com"),
    "peaq": os.environ.get("PEAQ_RPC", "wss://wsspc.peaq.network"),
}


def http_jsonrpc(url: str, method: str, params: list, timeout: float = 15.0):
    """Minimal JSON-RPC over HTTP using urllib (no external deps)."""
    import urllib.request
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
    }).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "agent-x-rpc-probe/1.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def probe_chain(name: str, url: str, n_blocks: int) -> dict:
    """Probe one chain: reachability + recent block-time series."""
    result = {"chain": name, "url": url, "reachable": False}
    if url.startswith("ws"):
        result["error"] = "WebSocket endpoint — skipped in minimal HTTP probe"
        return result
    t0 = time.time()
    try:
        bn = http_jsonrpc(url, "eth_blockNumber", [])
        if "error" in bn:
            result["error"] = str(bn["error"])
            return result
        latest = int(bn["result"], 16)
        result["reachable"] = True
        result["latest_block"] = latest
        result["latency_ms"] = round((time.time() - t0) * 1000, 1)
        timestamps = []
        start = latest - n_blocks + 1
        if start < 0:
            start = 0
        for h in range(start, latest + 1):
            blk = http_jsonrpc(url, "eth_getBlockByNumber", [hex(h), False])
            timestamps.append(int(blk["result"]["timestamp"], 16))
        gaps = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]
        result["n_blocks"] = len(timestamps)
        result["block_time_mean_s"] = round(sum(gaps) / len(gaps), 3) if gaps else None
        result["block_time_min_s"] = min(gaps) if gaps else None
        result["block_time_max_s"] = max(gaps) if gaps else None
        result["timestamps"] = timestamps
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        result["reachable"] = False
    return result


def probe_ethereum_with_fallbacks(n_blocks: int) -> dict:
    """Try ETH HTTP endpoints until one serves blockNumber + timestamps."""
    last = None
    for url in ETH_HTTP_FALLBACKS:
        r = probe_chain("ethereum", url, n_blocks)
        last = r
        if r.get("reachable") and r.get("timestamps"):
            return r
    return last or {"chain": "ethereum", "reachable": False, "error": "no fallbacks"}


def main() -> None:
    ap = argparse.ArgumentParser(description="Chain RPC + block-time probe")
    ap.add_argument("--blocks", type=int, default=200,
                    help="recent blocks to cover per chain (may subsample)")
    ap.add_argument("--out", default="blocktimes_probe.json",
                    help="output JSON path")
    ap.add_argument("--rpc", action="append",
                    help="extra endpoint as name=url (repeatable)")
    args = ap.parse_args()

    rpcs = dict(DEFAULT_RPCS)
    for item in (args.rpc or []):
        name, _, url = item.partition("=")
        if url:
            rpcs[name] = url

    print(f"Probing {len(rpcs)} chain RPC(s), {args.blocks} blocks each ...\n")
    results = {}
    for name, url in rpcs.items():
        if name == "ethereum" and not any(
            (item or "").startswith("ethereum=") for item in (args.rpc or [])
        ):
            r = probe_ethereum_with_fallbacks(args.blocks)
        else:
            r = probe_chain(name, url, args.blocks)
        shown = (r.get("url") or url)[:52]
        print(f"  {name:12s} {shown:52s} ", end="", flush=True)
        if r.get("reachable"):
            print(f"OK  latest={r['latest_block']}  "
                  f"mean_block={r['block_time_mean_s']}s  lat={r['latency_ms']}ms")
        else:
            print(f"FAIL  {r.get('error', 'unknown')[:70]}")
        results[name] = r

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)

    reachable = [n for n, r in results.items() if r.get("reachable")]
    print(f"\nReachable: {len(reachable)}/{len(results)}"
          f" -> {', '.join(reachable) or 'none'}")
    print(f"Probe written to: {args.out}")
    if len(reachable) >= 2:
        print("\n>=2 chains reachable -> pick a bridged pair, proceed to Stufe A pre-reg.")
    elif len(reachable) == 1:
        print("\nOnly 1 chain reachable -> need a second chain for a bridge pair.")
    else:
        print("\nNo chain reachable -> Stufe A blocked; check network/RPC config.")


if __name__ == "__main__":
    main()
