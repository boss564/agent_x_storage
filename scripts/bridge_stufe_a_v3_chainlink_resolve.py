"""Resolve Chainlink proxy feeds to active aggregator contracts for V3 window.

Requires verification gate with all_verified=true (Schicht A complete).

Schicht B: aggregator() + phaseAggregators(1..latest_phase_id)
Schicht C: latestRoundData() plausibility on each active aggregator

Usage:
  python3 scripts/bridge_stufe_a_v3_chainlink_resolve.py
  python3 scripts/bridge_stufe_a_v3_chainlink_resolve.py --output bridge_stufe_a_v3_chainlink_resolved.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from eth_hash.auto import keccak

from bridge_stufe_a_rpc import (
    DEFAULT_RPCS,
    ETH_HTTP_FALLBACKS,
    GNOSIS_HTTP_FALLBACKS,
    jsonrpc,
    redact_url,
)

SEL_AGGREGATOR = "0x" + keccak(b"aggregator()")[:4].hex()
SEL_LATEST_ROUND = "0x" + keccak(b"latestRoundData()")[:4].hex()
SEL_PHASE_AGGS = "0x" + keccak(b"phaseAggregators(uint16)")[:4].hex()

# Frozen bands — Pre-Reg §3.0 (8 decimals → USD)
PLAUSIBILITY_BANDS_USD: dict[str, tuple[float, float]] = {
    "ETH/USD": (1e2, 1e4),
    "WBTC/USD": (1e3, 1e6),
    "BTC/USD": (1e3, 1e6),
    "USDC/USD": (0.9, 1.1),
    "USDT/USD": (0.9, 1.1),
    "GNO/USD": (1e0, 1e3),
}

ANSWER_DECIMALS = 8
ZERO_ADDR = "0x0000000000000000000000000000000000000000"


def call_hex(rpc_url: str, to: str, data: str) -> str:
    out = jsonrpc(rpc_url, "eth_call", [{"to": to, "data": data}, "latest"])
    if not isinstance(out, str) or not out.startswith("0x"):
        raise RuntimeError(f"bad eth_call result to {to}: {out!r}")
    return out


CHAIN_RPC_FALLBACKS: dict[str, list[str]] = {
    "ethereum": [u for u in [*ETH_HTTP_FALLBACKS, "https://ethereum-rpc.publicnode.com"] if u],
    "gnosis": [u for u in GNOSIS_HTTP_FALLBACKS if u],
}


def rpc_candidates(chain: str, primary: str | None) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for url in [primary, *CHAIN_RPC_FALLBACKS.get(chain, []), DEFAULT_RPCS.get(chain)]:
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def probe_rpc(chain: str, rpc_url: str | None) -> tuple[str, int]:
    """Fail fast if no RPC for chain is reachable."""
    errors: list[str] = []
    for url in rpc_candidates(chain, rpc_url):
        try:
            block_hex = jsonrpc(url, "eth_blockNumber", [])
            block = int(block_hex, 16)
            if block <= 0:
                raise RuntimeError(f"invalid block {block_hex!r}")
            return url, block
        except Exception as exc:
            errors.append(f"{redact_url(url)}: {exc}")
    raise RuntimeError(f"all RPCs failed for {chain}: {' | '.join(errors)}")


def decode_address(word_hex: str) -> str:
    body = word_hex[2:].rjust(64, "0")
    addr = "0x" + body[-40:]
    if int(addr, 16) == 0:
        return ZERO_ADDR
    return addr.lower()


def encode_uint16(v: int) -> str:
    if not (0 <= v <= 65535):
        raise ValueError("phase out of range")
    return hex(v)[2:].rjust(64, "0")


def decode_int256(word_hex: str) -> int:
    val = int(word_hex[2:].rjust(64, "0"), 16)
    if val >= 2**255:
        val -= 2**256
    return val


def latest_phase_id(rpc_url: str, proxy: str) -> int:
    raw = call_hex(rpc_url, proxy, SEL_LATEST_ROUND)
    body = raw[2:]
    if len(body) < 64:
        raise RuntimeError(f"short latestRoundData for proxy {proxy}")
    round_id = int(body[0:64], 16)
    return round_id >> 64


def latest_answer_usd(rpc_url: str, aggregator: str) -> tuple[float, int]:
    raw = call_hex(rpc_url, aggregator, SEL_LATEST_ROUND)
    body = raw[2:]
    if len(body) < 128:
        raise RuntimeError(f"short latestRoundData for aggregator {aggregator}")
    answer = decode_int256("0x" + body[64:128])
    usd = answer / (10**ANSWER_DECIMALS)
    return usd, answer


def plausibility_check(feed_name: str, usd: float) -> tuple[str, str | None]:
    band = PLAUSIBILITY_BANDS_USD.get(feed_name)
    if band is None:
        return "fail", f"no_plausibility_band_for_{feed_name}"
    lo, hi = band
    if lo <= usd <= hi:
        return "pass", None
    return "fail", f"latest_answer_usd={usd:.6g} outside [{lo:g}, {hi:g}]"


def resolve_proxy(rpc_url: str, proxy: str, feed_name: str) -> dict:
    current = decode_address(call_hex(rpc_url, proxy, SEL_AGGREGATOR))
    phase_max = latest_phase_id(rpc_url, proxy)
    phase_map: dict[str, str] = {}
    active: set[str] = set()
    for phase in range(1, phase_max + 1):
        data = SEL_PHASE_AGGS + encode_uint16(phase)
        agg = decode_address(call_hex(rpc_url, proxy, data))
        if agg != ZERO_ADDR:
            phase_map[str(phase)] = agg
            active.add(agg)
    if current != ZERO_ADDR:
        active.add(current)

    aggregator_checks = []
    feed_plausible = True
    for agg in sorted(active):
        is_current = agg == current
        try:
            usd, raw_answer = latest_answer_usd(rpc_url, agg)
        except Exception as exc:
            if is_current:
                feed_plausible = False
                aggregator_checks.append(
                    {
                        "aggregator": agg,
                        "role": "current",
                        "latest_answer_raw": None,
                        "latest_answer_usd": None,
                        "plausibility_check": "fail",
                        "plausibility_reason": f"latestRoundData_reverted: {exc}",
                    }
                )
                continue
            aggregator_checks.append(
                {
                    "aggregator": agg,
                    "role": "historical",
                    "latest_answer_raw": None,
                    "latest_answer_usd": None,
                    "plausibility_check": "skip_historical",
                    "plausibility_reason": "latestRoundData_unavailable_on_historical_aggregator",
                }
            )
            continue

        check, reason = plausibility_check(feed_name, usd)
        if is_current and check != "pass":
            feed_plausible = False
        elif not is_current and check != "pass":
            # Historical aggregator with live but out-of-band data — suspicious, fail feed.
            feed_plausible = False
        aggregator_checks.append(
            {
                "aggregator": agg,
                "role": "current" if is_current else "historical",
                "latest_answer_raw": raw_answer,
                "latest_answer_usd": usd,
                "plausibility_check": check if is_current or check == "pass" else "fail",
                "plausibility_reason": reason,
            }
        )

    status = "RESOLVED" if feed_plausible and active else "V3_UNTESTBAR"
    if not active:
        status = "V3_UNTESTBAR"

    return {
        "proxy": proxy.lower(),
        "current_aggregator": current,
        "latest_phase_id": phase_max,
        "phase_aggregators": phase_map,
        "active_aggregators": sorted(active),
        "aggregator_plausibility": aggregator_checks,
        "plausibility_check": "pass" if feed_plausible and active else "fail",
        "status": status,
    }


def load_verified_feeds(
    candidates_path: Path,
    gate_path: Path,
) -> dict[str, dict]:
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    if not gate.get("all_verified"):
        raise SystemExit(f"resolver blocked: {gate_path} has all_verified != true")
    if gate.get("resolver_release") != "RELEASED":
        raise SystemExit(f"resolver blocked: {gate_path} resolver_release != RELEASED")

    body = json.loads(candidates_path.read_text(encoding="utf-8"))
    verified_keys = {
        (row["chain"], row["feed"])
        for row in gate.get("candidates", [])
        if row.get("status") == "VERIFIED"
    }

    out: dict[str, dict] = {}
    for chain, cfg in body.get("chains", {}).items():
        feeds = []
        for feed in cfg.get("feeds", []):
            key = (chain, feed["name"])
            if key not in verified_keys:
                continue
            proxy = feed.get("proxy_candidate")
            if not proxy:
                raise SystemExit(f"verified feed missing proxy: {chain} {feed['name']}")
            feeds.append({"name": feed["name"], "proxy": proxy})
        if feeds:
            out[chain] = {"feeds": feeds}
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve Chainlink proxy feed aggregators")
    parser.add_argument(
        "--candidates",
        default="config/bridge_stufe_a_v3_chainlink_proxy_candidates.json",
    )
    parser.add_argument(
        "--gate",
        default="bridge_stufe_a_v3_chainlink_verification_gate.json",
    )
    parser.add_argument("--output", default="bridge_stufe_a_v3_chainlink_resolved.json")
    parser.add_argument("--input", default=None, help="Optional manual JSON override")
    args = parser.parse_args()

    if args.input:
        spec = json.loads(Path(args.input).read_text(encoding="utf-8"))
    else:
        spec = load_verified_feeds(Path(args.candidates), Path(args.gate))

    rpc_defaults = {
        "ethereum": DEFAULT_RPCS["ethereum"],
        "gnosis": DEFAULT_RPCS["gnosis"],
    }

    out: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gate": args.gate,
        "chains": {},
    }
    all_resolved = True
    summary_rows = []

    for chain, cfg in spec.items():
        rpc = cfg.get("rpc_url") or rpc_defaults.get(chain)
        if not rpc:
            print(f"ERROR: no RPC URL for chain {chain}", file=sys.stderr)
            return 1
        try:
            rpc, latest_block = probe_rpc(chain, rpc)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

        rows = []
        for feed in cfg.get("feeds", []):
            proxy = feed["proxy"]
            name = feed.get("name", proxy)
            try:
                resolved = resolve_proxy(rpc, proxy, name)
            except Exception as exc:
                print(f"ERROR: resolve failed {chain} {name} {proxy}: {exc}", file=sys.stderr)
                return 1
            resolved["name"] = name
            rows.append(resolved)
            summary_rows.append(resolved)
            if resolved["status"] != "RESOLVED":
                all_resolved = False
            print(
                f"{chain} {name}: phases=1..{resolved['latest_phase_id']} "
                f"aggregators={len(resolved['active_aggregators'])} "
                f"plausibility={resolved['plausibility_check']} "
                f"status={resolved['status']}",
                flush=True,
            )
            for chk in resolved["aggregator_plausibility"]:
                mark = "OK" if chk["plausibility_check"] in ("pass", "skip_historical") else "FAIL"
                usd_s = (
                    f"{chk['latest_answer_usd']:.6g}"
                    if chk["latest_answer_usd"] is not None
                    else "n/a"
                )
                print(
                    f"  [{mark}] {chk['aggregator'][:10]}… "
                    f"role={chk.get('role', '?')} usd={usd_s} "
                    f"{chk.get('plausibility_reason') or ''}",
                    flush=True,
                )

        out["chains"][chain] = {
            "rpc_url": redact_url(rpc),
            "latest_block": latest_block,
            "feeds": rows,
        }

    out["all_resolved"] = all_resolved
    out["capture_release"] = "RELEASED" if all_resolved else "BLOCKED"
    Path(args.output).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {args.output}")
    print(f"all_resolved={all_resolved} capture_release={out['capture_release']}")
    print(f"verified_feeds={len(summary_rows)}")
    return 0 if all_resolved else 2


if __name__ == "__main__":
    raise SystemExit(main())
