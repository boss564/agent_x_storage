"""Dauer-Prozess: PolySentinel-WS + NewsBridge + Telemetrie-Run (C6).

Charter: diagnostic_only=true, live_execution=false, order_send=false.
Startet den read-only Book-Feed und konsumiert News-Items (JSONL/Poll-Ablage).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterator, Optional

from order_execution_engine.fill_simulator import FillSimConfig, StalenessPolicy
from order_execution_engine.hub_wiring import ShadowHub, attach_book_feed
from order_execution_engine.market_data_feed import SnapshotCache
from order_execution_engine.models import RiskConfig
from order_execution_engine.news_bridge import (
    SIGNAL_NAMESPACE,
    BridgePolicy,
    MarketResolver,
    NewsBridge,
    SqliteDedupStore,
)
from order_execution_engine.persistence import SQLiteShadowStorage, TelemetrySink
from order_execution_engine.shadow_execution_engine import ShadowExecutionEngine

_LOG = logging.getLogger(__name__)


def git_commit_short(repo: Path | None = None) -> str:
    """Aktueller HEAD-Kurzhash (+ '-dirty' wenn Working Tree verändert)."""
    cwd = str(repo or Path(__file__).resolve().parents[1])
    try:
        tip = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd, text=True, stderr=subprocess.DEVNULL,
        ).strip()
        dirty = subprocess.call(
            ["git", "diff", "--quiet"],
            cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return f"{tip}-dirty" if dirty != 0 else tip
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def iter_news_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Liest news_agent_multi/v1 Zeilen (skip leer/ungültig)."""
    if not path.exists():
        return
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("item_id"):
                yield obj


def build_runner(
    *,
    data_root: Path,
    user_id: str,
    allowlist: dict[str, dict[str, str]],
    policy_cfg: dict[str, Any],
    start_ws: bool = True,
) -> tuple[ShadowExecutionEngine, NewsBridge, SQLiteShadowStorage, Any]:
    """Verdrahtet Engine + Bridge + Storage + optionalen WS-Feed."""
    store = SQLiteShadowStorage.for_user(data_root, user_id)
    policy = BridgePolicy.from_config(policy_cfg)
    resolver = MarketResolver(allowlist)
    fill_cfg = FillSimConfig(
        max_book_age_ms=int(policy_cfg.get("max_book_age_ms", 2000)),
        staleness_policy=StalenessPolicy.REJECT_STALE,
    )
    engine = ShadowExecutionEngine(
        risk_config=RiskConfig(),
        size_fn=policy.size_fn,
        fill_sim_config=fill_cfg,
    )
    cache = SnapshotCache(max_age_seconds=float(policy_cfg.get("cache_max_age_s", 10)))
    binding = attach_book_feed(engine, cache=cache, start_ws_feed=start_ws)

    config_json = {
        **policy.snapshot(),
        "signal_ref_mode": "fallback_limit",
        "signal_namespace": str(SIGNAL_NAMESPACE),
        "market_allowlist": resolver.entries(),
        "max_book_age_ms": fill_cfg.max_book_age_ms,
        "resting_model": engine.fill_sim.config.resting_model.value,
    }
    run_id = store.open_run(
        git_commit=git_commit_short(),
        config_json=config_json,
    )
    bridge = NewsBridge(
        engine, binding.cache, resolver,
        SqliteDedupStore(store), policy, run_id,
        storage=store,
    )
    return engine, bridge, store, binding


async def run_ws_and_hub(
    binding: Any,
    hub: ShadowHub,
    token_ids: list[str],
    *,
    stop_event: Optional[asyncio.Event] = None,
) -> None:
    """Startet Dauer-WS + Hub-Takt parallel."""
    stop = stop_event or asyncio.Event()
    tasks = [asyncio.create_task(hub.run(interval_seconds=1.0, stop_event=stop))]
    if binding.feed is not None and token_ids:
        tasks.append(asyncio.create_task(binding.feed.run(token_ids)))
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
    finally:
        stop.set()
        for t in tasks:
            t.cancel()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--user-id", default="shadow")
    parser.add_argument(
        "--news-jsonl", type=Path,
        default=Path("data/news_scores.jsonl"),
    )
    parser.add_argument(
        "--allowlist", type=Path,
        help="JSON {ASSET: {token_id, market_id}}",
    )
    parser.add_argument("--once", action="store_true",
                        help="Nur JSONL einmal dispatchen, kein WS-Loop")
    parser.add_argument("--no-ws", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    allowlist: dict[str, dict[str, str]] = {}
    if args.allowlist and args.allowlist.exists():
        allowlist = json.loads(args.allowlist.read_text())

    engine, bridge, store, binding = build_runner(
        data_root=args.data_root,
        user_id=args.user_id,
        allowlist=allowlist,
        policy_cfg={},
        start_ws=not args.no_ws and not args.once,
    )
    sink = TelemetrySink(
        store, engine.telemetry,
        fills_provider=engine.fills_for,
        peak_events_provider=engine.peak_events,
    )

    dispatched = 0
    for item in iter_news_jsonl(args.news_jsonl):
        if bridge.on_news_item(item):
            dispatched += 1
    sink.drain()
    _LOG.info("dispatched=%s discards=%s run_id=%s",
              dispatched, len(bridge.discards), store.active_run_id)

    if args.once or args.no_ws:
        store.close()
        return 0

    token_ids = [e["token_id"] for e in allowlist.values()]
    hub = ShadowHub(engine)
    try:
        asyncio.run(run_ws_and_hub(binding, hub, token_ids))
    except KeyboardInterrupt:
        pass
    finally:
        sink.drain()
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
