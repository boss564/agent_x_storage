#!/usr/bin/env python3
"""P4 local lab: dual-schema LiquidationEvent seed + hook smoke.

Isolated from host Neo4j Enterprise (:7687) and compose neo4j.
Default Bolt: bolt://127.0.0.1:17687 (throwaway container).

  make raas-p4-lab-up
  python3 scripts/p4_local_neo4j_lab.py
  make raas-p4-lab-down

Does not change the live cluster (ASTROCORE_DATA_SOURCE stays worm).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

DEFAULT_URI = "bolt://127.0.0.1:17687"
BLOCKED_PORTS = {7687}  # host Enterprise / unpublished compose Bolt
LAB_CHERRY = "p4_lab_cherry"
LAB_SEED = "p4_lab_seed"
READER_USER = "astrocore_reader"


def _parse_port(uri: str) -> int:
    parsed = urlparse(uri)
    if parsed.port:
        return int(parsed.port)
    return 7687


def _refuse_default_neo4j(uri: str, allow_default_port: bool) -> None:
    port = _parse_port(uri)
    if port in BLOCKED_PORTS and not allow_default_port:
        raise SystemExit(
            f"REFUSED: {uri} looks like the host/compose Neo4j (port {port}). "
            "Use the throwaway lab on :17687, or pass --allow-default-port."
        )


def _connect(uri: str, user: str, password: str):
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise SystemExit("neo4j driver missing. pip install neo4j") from exc
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    return driver


def _seed_dual_schema(session: Any, n_each: int) -> Dict[str, int]:
    now = time.time()
    session.run("CREATE INDEX liq_ts IF NOT EXISTS FOR (l:LiquidationEvent) ON (l.ts)")
    session.run(
        "CREATE INDEX liq_timestamp IF NOT EXISTS FOR (l:LiquidationEvent) ON (l.timestamp)"
    )
    session.run(
        "MATCH (l:LiquidationEvent) WHERE l.source IN $src DETACH DELETE l",
        src=[LAB_CHERRY, LAB_SEED],
    )

    cherry: List[Dict[str, Any]] = []
    seed: List[Dict[str, Any]] = []
    for i in range(n_each):
        ts = now - (n_each - i) * 30.0
        phase = (ts % 28800.0) / 28800.0
        cherry.append(
            {
                "ts": ts,
                "phase": round(phase, 6),
                "usd": 1000.0 + i,
                "sym": "ETHUSDT",
            }
        )
        seed.append(
            {
                "ts": ts + 1.0,
                "phase": round(((ts + 1.0) % 28800.0) / 28800.0, 6),
                "usd": 2000.0 + i,
                "sym": "BTCUSDT",
            }
        )

    session.run(
        """
        UNWIND $batch AS ev
        CREATE (l:LiquidationEvent {
            ts: ev.ts, phase: ev.phase, usd_value: ev.usd,
            symbol: ev.sym, source: $src, near_cutoff: false
        })
        """,
        batch=cherry,
        src=LAB_CHERRY,
    )
    session.run(
        """
        UNWIND $batch AS ev
        CREATE (l:LiquidationEvent {
            timestamp: ev.ts, funding_phase: ev.phase, amount_usd: ev.usd,
            symbol: ev.sym, is_clustered: false, source: $src
        })
        """,
        batch=seed,
        src=LAB_SEED,
    )
    n = session.run(
        "MATCH (l:LiquidationEvent) WHERE l.source IN $src RETURN count(l) AS n",
        src=[LAB_CHERRY, LAB_SEED],
    ).single()["n"]
    return {"seeded": int(n), "cherry": n_each, "seed": n_each}


def _try_reader_user(session: Any, password: str) -> Dict[str, Any]:
    """Enterprise: ROLE reader. Community 5 typically rejects GRANT ROLE."""
    try:
        session.run(
            "CREATE USER astrocore_reader IF NOT EXISTS "
            "SET PASSWORD $pw CHANGE NOT REQUIRED",
            pw=password,
        )
        session.run("GRANT ROLE reader TO astrocore_reader")
        return {"status": "ok", "user": READER_USER, "role": "reader"}
    except Exception as exc:
        msg = str(exc).split("\n")[0][:240]
        return {
            "status": "unsupported_or_failed",
            "user": READER_USER,
            "error": msg,
            "note": "Community Edition has no ROLE reader; hook still uses READ_ACCESS.",
        }


def _count_binance(session: Any) -> int:
    row = session.run(
        "MATCH (l:LiquidationEvent {source: 'binance_futures'}) RETURN count(l) AS n"
    ).single()
    return int(row["n"] if row else 0)


def _run_binance_listener(uri: str, user: str, password: str, seconds: int) -> Dict[str, Any]:
    """Run CherryStudio LiquidationListener against the lab Bolt URI."""
    os.environ["NEO4J_URI"] = uri
    os.environ["NEO4J_USER"] = user
    os.environ["NEO4J_PASS"] = password

    cherry = _ROOT / "imports" / "cherrystudio" / "choral_text"
    if str(cherry) not in sys.path:
        sys.path.insert(0, str(cherry))

    import asyncio
    import importlib

    import liquidation_listener as ll

    importlib.reload(ll)

    try:
        import websockets
    except ImportError as exc:
        raise SystemExit("websockets missing. pip install websockets") from exc

    listener = ll.LiquidationListener()
    raw_messages = 0
    skipped_no_order = 0
    sample_box: List[str] = []

    async def _listen_box() -> None:
        nonlocal raw_messages, skipped_no_order
        deadline = time.time() + seconds
        async with websockets.connect(ll.BINANCE_FORCE_ORDER_WS) as ws:
            while time.time() < deadline:
                remaining = deadline - time.time()
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=max(0.2, remaining))
                except asyncio.TimeoutError:
                    break
                raw_messages += 1
                try:
                    payload = json.loads(message)
                except json.JSONDecodeError:
                    continue
                items = payload if isinstance(payload, list) else [payload]
                if raw_messages == 1 and items and isinstance(items[0], dict):
                    sample_box.extend(list(items[0].keys()))
                for item in items:
                    if not isinstance(item, dict) or "o" not in item:
                        skipped_no_order += 1
                        continue
                    await listener._process(json.dumps(item))

    try:
        asyncio.run(_listen_box())
    except Exception as exc:
        listener.close()
        return {
            "status": "FAIL",
            "error": str(exc).split("\n")[0][:240],
            "raw_messages": raw_messages,
        }

    status = listener.status()
    listener.close()
    return {
        "status": "ok",
        "seconds": seconds,
        "ws": ll.BINANCE_FORCE_ORDER_WS,
        "raw_messages": raw_messages,
        "skipped_no_order": skipped_no_order,
        "first_message_keys": sample_box[:12],
        "events_processed": status["events_processed"],
        "total_in_neo4j": status["total_in_neo4j"],
        "rate_per_minute": status["rate_per_minute"],
        "top_symbols": status["top_symbols"][:8],
    }


def _run_hook(uri: str, user: str, password: str, dedicated: bool) -> Dict[str, Any]:
    os.environ["NEO4J_URI_READ"] = uri
    os.environ["NEO4J_URI"] = uri
    if dedicated:
        os.environ["NEO4J_USER_READ"] = user
        os.environ["NEO4J_PASS_READ"] = password
    else:
        os.environ.pop("NEO4J_USER_READ", None)
        os.environ.pop("NEO4J_PASS_READ", None)
        os.environ["NEO4J_USER"] = user
        os.environ["NEO4J_PASS"] = password
        os.environ["NEO4J_PASSWORD"] = password

    from agents_b2g.astrocore_hook import AstrocoreHookClient

    client = AstrocoreHookClient(
        data_source="neo4j",
        neo4j_uri=uri,
        neo4j_user=user,
        neo4j_password=password,
        lookback_days=7,
        strict=False,
    )
    env = client.analyze_liquidations()
    return {
        "data_provenance": env.get("data_provenance"),
        "verdict": env.get("verdict"),
        "events_read": env.get("stats", {}).get("events_read"),
        "warnings": env.get("warnings") or [],
        "dedicated_reader_env": dedicated,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="P4 local Neo4j lab (dual-schema + hook)")
    parser.add_argument("--uri", default=os.getenv("NEO4J_URI_READ", DEFAULT_URI))
    parser.add_argument("--user", default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument(
        "--password",
        default=os.getenv("P4_NEO4J_PASS") or os.getenv("NEO4J_PASS", "p4lab-local-only"),
    )
    parser.add_argument("--n", type=int, default=80, help="events per schema")
    parser.add_argument(
        "--allow-default-port",
        action="store_true",
        help="Allow Bolt :7687 (host Enterprise / compose). Off by default.",
    )
    parser.add_argument("--keep-nodes", action="store_true")
    parser.add_argument(
        "--listener-seconds",
        type=int,
        default=0,
        help="If >0, listen to Binance !forceOrder@arr into lab Neo4j (no seed).",
    )
    args = parser.parse_args()

    _refuse_default_neo4j(args.uri, args.allow_default_port)

    if args.listener_seconds > 0:
        return _main_listener(args)

    try:
        driver = _connect(args.uri, args.user, args.password)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "reason": "connect_failed",
                    "uri": args.uri,
                    "error": str(exc).split("\n")[0][:240],
                    "hint": "make raas-p4-lab-up",
                },
                indent=2,
            )
        )
        return 1

    reader_info: Dict[str, Any]
    seed_info: Dict[str, int]
    try:
        with driver.session() as session:
            seed_info = _seed_dual_schema(session, args.n)
            reader_info = _try_reader_user(session, args.password)
    except Exception as exc:
        driver.close()
        print(json.dumps({"status": "FAIL", "reason": "seed_failed", "error": str(exc)[:240]}, indent=2))
        return 1

    hook_user, hook_pass, dedicated = args.user, args.password, False
    if reader_info.get("status") == "ok":
        hook_user, dedicated = READER_USER, True

    try:
        hook = _run_hook(args.uri, hook_user, hook_pass, dedicated)
    except Exception as exc:
        driver.close()
        print(json.dumps({"status": "FAIL", "reason": "hook_failed", "error": str(exc)[:240]}, indent=2))
        return 1

    if not args.keep_nodes:
        with driver.session() as session:
            session.run(
                "MATCH (l:LiquidationEvent) WHERE l.source IN $src DETACH DELETE l",
                src=[LAB_CHERRY, LAB_SEED],
            )
    driver.close()

    ok = hook.get("data_provenance") == "neo4j" and int(hook.get("events_read") or 0) >= args.n
    summary = {
        "status": "PASS" if ok else "FAIL",
        "uri": args.uri,
        "seed": seed_info,
        "reader_user": reader_info,
        "hook": hook,
        "cluster_untouched": True,
        "note": "Live ASTROCORE_DATA_SOURCE remains worm. Lab only.",
    }
    print(json.dumps(summary, indent=2))
    return 0 if ok else 1


def _main_listener(args: argparse.Namespace) -> int:
    try:
        driver = _connect(args.uri, args.user, args.password)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "reason": "connect_failed",
                    "uri": args.uri,
                    "error": str(exc).split("\n")[0][:240],
                },
                indent=2,
            )
        )
        return 1

    with driver.session() as session:
        before = _count_binance(session)
    driver.close()

    listen = _run_binance_listener(args.uri, args.user, args.password, args.listener_seconds)
    if listen.get("status") != "ok":
        print(json.dumps({"status": "FAIL", "listener": listen}, indent=2))
        return 1

    try:
        hook = _run_hook(args.uri, args.user, args.password, dedicated=False)
    except Exception as exc:
        print(
            json.dumps(
                {"status": "FAIL", "reason": "hook_failed", "error": str(exc)[:240]},
                indent=2,
            )
        )
        return 1

    n_binance = int(listen.get("events_processed") or 0)
    quiet = n_binance == 0
    hook_ok = hook.get("data_provenance") == "neo4j" and int(hook.get("events_read") or 0) > 0
    status = "QUIET" if quiet else ("PASS" if hook_ok else "FAIL")
    summary = {
        "status": status,
        "uri": args.uri,
        "binance_before": before,
        "listener": listen,
        "hook": hook,
        "cluster_untouched": True,
        "note": (
            "No force-order in window — market quiet, retry with more seconds."
            if quiet
            else "Live Binance force-orders written to lab Neo4j (Cherry schema)."
        ),
    }
    print(json.dumps(summary, indent=2))
    if quiet:
        return 0
    return 0 if hook_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
