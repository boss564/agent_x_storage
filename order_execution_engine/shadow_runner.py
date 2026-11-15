"""Dauer-Prozess: PolySentinel-WS + NewsBridge + Telemetrie-Run (C6/Ops).

Charter: diagnostic_only=true, live_execution=false, order_send=false.
Startet den read-only Book-Feed und tailt News-Items (JSONL, Stunden-Batches).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import threading
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterator, Optional

from order_execution_engine.allowlist_freeze import FreezeError, load_allowlist_file
from order_execution_engine.fill_simulator import (
    FillSimConfig,
    RestingModel,
    StalenessPolicy,
)
from order_execution_engine.event_log import (
    TAP_ANCHOR_UPDATE,
    JsonlEventLog,
    emit_tick_samples,
    install_cache_tap,
    resolve_event_log_path,
)
from order_execution_engine.hub_wiring import ShadowHub, attach_book_feed
from order_execution_engine.market_data_feed import PolymarketWsFeed, SnapshotCache
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

# Messperiode v1: stündlicher News-Agent → ~65 min Fenster.
DEFAULT_MAX_NEWS_AGE_S = 3900.0
DEFAULT_TAIL_INTERVAL_S = 5.0
# GP-S2-1: tick_sample at decision takt (~60 s); independent of book_update.
DEFAULT_TICK_SAMPLE_S = 60.0


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


def load_policy_cfg(path: Optional[Path]) -> dict[str, Any]:
    """Lädt run_policy.json; Defaults für die Messperiode."""
    cfg: dict[str, Any] = {
        "theta": "0.1",
        "max_book_age_ms": 2000,
        "max_news_age_s": DEFAULT_MAX_NEWS_AGE_S,
        "staleness_policy": StalenessPolicy.REJECT_STALE.value,
        "resting_model": RestingModel.RE_CROSS.value,
        "signal_ref_mode": "fallback_limit",
        "size_by_impact": {
            "LOW": "25",
            "MEDIUM": "50",
            "MID": "50",
            "HIGH": "100",
        },
        "default_size": "25",
        "cache_max_age_s": 10,
    }
    if path is not None and path.exists():
        loaded = json.loads(path.read_text())
        if not isinstance(loaded, dict):
            raise ValueError(f"policy JSON must be object: {path}")
        cfg.update(loaded)
    # Messperiode: fehlendes max_news_age_s → 3900 (nicht Bridge-Default 300).
    if "max_news_age_s" not in cfg:
        cfg["max_news_age_s"] = DEFAULT_MAX_NEWS_AGE_S
    return cfg


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


class JsonlTail:
    """Byte-Offset-Tail für Stunden-Batches (Dedup bleibt in SQLite)."""

    def __init__(self, path: Path, offset_path: Path) -> None:
        self.path = path
        self.offset_path = offset_path
        self._offset = self._read_offset()

    def _read_offset(self) -> int:
        if not self.offset_path.exists():
            return 0
        try:
            return max(0, int(self.offset_path.read_text().strip() or "0"))
        except ValueError:
            return 0

    def _write_offset(self) -> None:
        self.offset_path.parent.mkdir(parents=True, exist_ok=True)
        self.offset_path.write_text(str(self._offset))

    def seek_end(self) -> None:
        """Messperiode: Altbestand überspringen (kein Aug-Dump → news_too_old)."""
        if self.path.exists():
            self._offset = self.path.stat().st_size
        else:
            self._offset = 0
        self._write_offset()

    def poll(self) -> list[dict[str, Any]]:
        """Liest neue vollständige Zeilen ab Offset; aktualisiert Offset."""
        if not self.path.exists():
            return []
        size = self.path.stat().st_size
        if self._offset > size:
            # Truncate/rotate → von vorn
            self._offset = 0
        items: list[dict[str, Any]] = []
        with self.path.open("rb") as fh:
            fh.seek(self._offset)
            while True:
                line_b = fh.readline()
                if not line_b:
                    break
                if not line_b.endswith(b"\n"):
                    # unvollständige Zeile — Offset nicht vorrücken
                    break
                self._offset = fh.tell()
                line = line_b.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and obj.get("item_id"):
                    items.append(obj)
        self._write_offset()
        return items


def build_runner(
    *,
    data_root: Path,
    user_id: str,
    allowlist: dict[str, dict[str, str]],
    policy_cfg: dict[str, Any],
    start_ws: bool = True,
    config_allowlist: Optional[dict[str, Any]] = None,
    git_commit: Optional[str] = None,
    lease_token: Optional[str] = None,
) -> tuple[ShadowExecutionEngine, NewsBridge, SQLiteShadowStorage, Any, dict[str, Any]]:
    """Verdrahtet Engine + Bridge + Storage + optionalen WS-Feed.

    Returns:
        engine, bridge, store, binding, config_json (eingefroren im Run).
    """
    if not allowlist:
        raise ValueError("allowlist empty — refuse WS start (would yield 100% no_book)")

    store = SQLiteShadowStorage.for_user(data_root, user_id)
    policy = BridgePolicy.from_config(policy_cfg)
    resolver = MarketResolver(allowlist)

    staleness_raw = str(
        policy_cfg.get("staleness_policy", StalenessPolicy.REJECT_STALE.value)
    ).lower()
    try:
        staleness = StalenessPolicy(staleness_raw)
    except ValueError:
        staleness = StalenessPolicy.REJECT_STALE

    resting_raw = str(
        policy_cfg.get("resting_model", RestingModel.RE_CROSS.value)
    ).lower()
    try:
        resting = RestingModel(resting_raw)
    except ValueError:
        resting = RestingModel.RE_CROSS

    fill_cfg = FillSimConfig(
        max_book_age_ms=int(policy_cfg.get("max_book_age_ms", 2000)),
        staleness_policy=staleness,
        resting_model=resting,
    )
    engine = ShadowExecutionEngine(
        risk_config=RiskConfig(),
        size_fn=policy.size_fn,
        fill_sim_config=fill_cfg,
    )
    cache = SnapshotCache(max_age_seconds=float(policy_cfg.get("cache_max_age_s", 10)))
    # GP-S2-1 / GP-S2-7: tap SnapshotCache.update → JSONL (never shadow.db).
    elog_path = resolve_event_log_path()
    if elog_path is not None:
        event_log = JsonlEventLog(elog_path, producer="runner")
        install_cache_tap(cache, event_log)
        setattr(cache, "_event_log", event_log)
        # N-6 Start-Log: resolved absolute path (never cwd-relative).
        _LOG.info(
            "event_log enabled absolute_path=%s tap=%s",
            elog_path,
            TAP_ANCHOR_UPDATE,
        )
    else:
        setattr(cache, "_event_log", None)
    binding = attach_book_feed(engine, cache=cache, start_ws_feed=start_ws)

    commit = git_commit if git_commit is not None else git_commit_short()
    market_allowlist = config_allowlist if config_allowlist is not None else resolver.entries()
    token_ids = [e["token_id"] for e in allowlist.values()]
    config_json: dict[str, Any] = {
        **policy.snapshot(),
        "signal_ref_mode": str(policy_cfg.get("signal_ref_mode", "fallback_limit")),
        "signal_namespace": str(SIGNAL_NAMESPACE),
        "market_allowlist": market_allowlist,
        "max_book_age_ms": fill_cfg.max_book_age_ms,
        "max_news_age_s": policy.max_news_age_s,
        "staleness_policy": fill_cfg.staleness_policy.value,
        "resting_model": fill_cfg.resting_model.value,
        "git_commit": commit,
        "ws_token_ids": token_ids,
        "diagnostic_only": True,
        "live_execution": False,
        "order_send": False,
    }
    run_id = store.open_run(
        git_commit=commit,
        config_json=config_json,
        lease_token=lease_token,
    )
    bridge = NewsBridge(
        engine, binding.cache, resolver,
        SqliteDedupStore(store), policy, run_id,
        storage=store,
    )
    return engine, bridge, store, binding, config_json


def assert_ws_covers_allowlist(token_ids: list[str], allowlist: dict[str, dict[str, str]]) -> None:
    """WS-Subscription ⊇ Allowlist (exakte Mengen-Gleichheit)."""
    expected = {e["token_id"] for e in allowlist.values()}
    got = set(token_ids)
    if got != expected:
        raise ValueError(
            f"WS token_ids != allowlist: missing={expected - got} extra={got - expected}"
        )
    payload = PolymarketWsFeed.subscription_payload(token_ids)
    if set(payload["assets_ids"]) != expected:
        raise ValueError("subscription_payload assets_ids mismatch")


async def run_ws_hub_and_tail(
    binding: Any,
    hub: ShadowHub,
    token_ids: list[str],
    *,
    bridge: NewsBridge,
    sink: TelemetrySink,
    tail: JsonlTail,
    tail_interval_s: float = DEFAULT_TAIL_INTERVAL_S,
    tick_sample_s: float = DEFAULT_TICK_SAMPLE_S,
    stop_event: Optional[asyncio.Event] = None,
    ws_reconnect_s: float = 5.0,
) -> None:
    """Dauer-WS + Hub-Takt + JSONL-Tail parallel (WS reconnect, kein Exit bei Drop)."""
    stop = stop_event or asyncio.Event()

    async def _tail_loop() -> None:
        while not stop.is_set():
            batch = await asyncio.to_thread(tail.poll)
            if batch:
                n = 0
                for item in batch:
                    if bridge.on_news_item(item):
                        n += 1
                await asyncio.to_thread(sink.drain)
                _LOG.info(
                    "tail_batch size=%s dispatched=%s discards_total=%s",
                    len(batch), n, len(bridge.discards),
                )
            try:
                await asyncio.wait_for(stop.wait(), timeout=tail_interval_s)
            except asyncio.TimeoutError:
                continue

    async def _tick_sample_loop() -> None:
        # A-A6: tick_sample fires even when venue is deaf (no book_update).
        elog = getattr(binding.cache, "_event_log", None)
        if elog is None or not token_ids:
            await stop.wait()
            return
        max_age = float(getattr(binding.cache, "_max_age", 10.0))
        while not stop.is_set():
            n = emit_tick_samples(
                binding.cache, elog, token_ids, max_age_s=max_age,
            )
            _LOG.debug("tick_sample tokens=%s", n)
            try:
                await asyncio.wait_for(stop.wait(), timeout=tick_sample_s)
            except asyncio.TimeoutError:
                continue

    async def _ws_loop() -> None:
        if binding.feed is None or not token_ids:
            await stop.wait()
            return
        while not stop.is_set():
            try:
                _LOG.info("ws_connect tokens=%s", len(token_ids))
                await binding.feed.run(token_ids)
                _LOG.warning("ws_stream_ended — reconnect in %ss", ws_reconnect_s)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — KeepAlive must not die on WS blips
                _LOG.warning("ws_error %s — reconnect in %ss", exc, ws_reconnect_s)
            try:
                await asyncio.wait_for(stop.wait(), timeout=ws_reconnect_s)
            except asyncio.TimeoutError:
                continue

    tasks = [
        asyncio.create_task(hub.run(interval_seconds=1.0, stop_event=stop)),
        asyncio.create_task(_tail_loop()),
        asyncio.create_task(_tick_sample_loop()),
        asyncio.create_task(_ws_loop()),
    ]
    try:
        # Stay alive until external stop / cancel (not FIRST_EXCEPTION).
        await stop.wait()
    finally:
        stop.set()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

async def run_ws_and_hub(
    binding: Any,
    hub: ShadowHub,
    token_ids: list[str],
    *,
    stop_event: Optional[asyncio.Event] = None,
) -> None:
    """Startet Dauer-WS + Hub-Takt parallel (ohne Tail; Tests/Compat)."""
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


# Gate #6 exit codes (lock vs control-plane).
EXIT_RUN_LOCK = 75
EXIT_CONTROL_PLANE = 76
EXIT_STOPPED_BEFORE_CLAIM = 77  # SIGTERM before claim; token unused


def default_run_lock_path() -> Path:
    """ops/RUN.lock next to this package — Abort sets LOCKED=1 before kill."""
    return Path(__file__).resolve().parent / "ops" / "RUN.lock"


def package_retired_marker_path(lock_path: Optional[Path] = None) -> Path:
    """D3 post-retire marker beside package RUN.lock (written by authorized retire)."""
    base = (lock_path or default_run_lock_path()).resolve().parent
    return base / "RUN.RETIRED"


def parse_run_lock(lock_path: Path) -> dict[str, Any]:
    """Parse RUN.lock → ``locked`` + optional ``forbid_run_id_gt``."""
    out: dict[str, Any] = {"locked": False, "forbid_run_id_gt": None, "path": str(lock_path)}
    if not lock_path.is_file():
        return out
    try:
        text = lock_path.read_text(encoding="utf-8")
    except OSError:
        out["locked"] = True  # fail-closed: unreadable lock blocks start
        return out
    for line in text.splitlines():
        raw = line.strip()
        if raw == "LOCKED=1" or raw.startswith("LOCKED=1"):
            out["locked"] = True
        if raw.startswith("forbid_run_id_gt="):
            try:
                out["forbid_run_id_gt"] = int(raw.split("=", 1)[1].strip())
            except ValueError:
                out["locked"] = True  # malformed forbid → refuse
    return out


def run_lock_blocks(lock_path: Path) -> bool:
    """True if RUN.lock exists and declares LOCKED=1 (runtime gate)."""
    return bool(parse_run_lock(lock_path)["locked"])


def evaluate_start_lock(
    lock_path: Path, *, run_lock_override: bool
) -> tuple[bool, str]:
    """D3 phase-aware lock gate.

    Returns ``(refuse, reason)``. Package path: absent without ``RUN.RETIRED``
    is fail-closed (pre-retire freeze). Scratch override: absent = proceed.
    """
    pkg = default_run_lock_path().resolve()
    path = lock_path.resolve()
    info = parse_run_lock(lock_path)
    if path == pkg and not run_lock_override:
        if not lock_path.is_file():
            marker = package_retired_marker_path(lock_path)
            if not marker.is_file():
                return (
                    True,
                    "package RUN.lock absent without RUN.RETIRED — refuse (D3 pre-retire fail-closed)",
                )
            return False, "post-retire marker present — proceed to lease"
        if info["locked"]:
            forbid = info.get("forbid_run_id_gt")
            extra = f" forbid_run_id_gt={forbid}" if forbid is not None else ""
            return True, f"RUN.lock active — refuse start path={lock_path}{extra}"
        return False, "package lock unlocked"
    # Scratch / explicit --run-lock: absent or LOCKED=0 → proceed; LOCKED=1 → refuse
    if info["locked"]:
        forbid = info.get("forbid_run_id_gt")
        extra = f" forbid_run_id_gt={forbid}" if forbid is not None else ""
        return True, f"RUN.lock active — refuse start path={lock_path}{extra}"
    return False, "scratch lock allows start"


def _peek_argv_path(argv_list: list[str], flag: str) -> Optional[Path]:
    """Space form ``--flag PATH`` and equals form ``--flag=PATH``."""
    eq = flag + "="
    for i, tok in enumerate(argv_list):
        if tok == flag:
            if i + 1 >= len(argv_list):
                return None
            return Path(argv_list[i + 1])
        if tok.startswith(eq):
            return Path(tok[len(eq) :])
    return None


def _is_live_data_root(path: Path) -> bool:
    from order_execution_engine.control_plane_lease import is_live_agentx_path

    return is_live_agentx_path(path)


def _consume_lease_token_file(path: Path) -> str:
    """Read token file; caller deletes after successful claim (M1)."""
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        raise ValueError(f"empty lease token file: {path}")
    return raw


def main(argv: Optional[list[str]] = None) -> int:
    # FIRST instruction on the start path: refuse if RUN.lock is set.
    # No logging, no SQLite, no WS, no Falkor — stderr only, then exit 75.
    # A4: --run-lock is never the default; package ops/RUN.lock unless explicit.
    # D3: package absent without RUN.RETIRED → refuse (freeze fail-closed).
    # M2: --run-lock override refused when --data-root is LIVE.
    # D6b: Exit 76 = control-plane refusal — callers must NOT retry as transient.
    argv_list = list(sys.argv[1:] if argv is None else argv)
    lock_path = default_run_lock_path()
    run_lock_override = False
    peeked = _peek_argv_path(argv_list, "--run-lock")
    if peeked is not None:
        lock_path = peeked
        run_lock_override = True
    data_root_peek = _peek_argv_path(argv_list, "--data-root") or Path(
        "data/shadow_live"
    )
    if run_lock_override and _is_live_data_root(data_root_peek):
        sys.stderr.write(
            "refuse --run-lock override on LIVE data-root (M2)\n"
        )
        return EXIT_RUN_LOCK
    refuse, reason = evaluate_start_lock(
        lock_path, run_lock_override=run_lock_override
    )
    if refuse:
        sys.stderr.write(reason + "\n")
        return EXIT_RUN_LOCK

    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument(
        "--data-root", type=Path,
        default=Path("data/shadow_live"),
    )
    parser.add_argument("--user-id", default="shadow")
    parser.add_argument(
        "--news-jsonl", type=Path,
        default=Path("data/news_scores.jsonl"),
    )
    parser.add_argument(
        "--allowlist", type=Path,
        help="allowlist.freeze.json oder flache {ASSET: {token_id, market_id}}",
    )
    parser.add_argument(
        "--policy-json", type=Path,
        help="run_policy.json (θ, sizes, max_news_age_s, …)",
    )
    parser.add_argument("--once", action="store_true",
                        help="Nur JSONL einmal dispatchen, kein WS-Loop")
    parser.add_argument("--no-ws", action="store_true")
    parser.add_argument(
        "--tail-from-end", action="store_true", default=True,
        help="Offset auf EOF setzen (Default: an, Altbestand überspringen)",
    )
    parser.add_argument(
        "--no-tail-from-end", action="store_true",
        help="Von Offset 0 / gespeichertem Offset lesen",
    )
    parser.add_argument("--tail-interval-s", type=float, default=DEFAULT_TAIL_INTERVAL_S)
    parser.add_argument(
        "--run-lock", type=Path, default=None,
        help="Path to RUN.lock (default: order_execution_engine/ops/RUN.lock)",
    )
    parser.add_argument(
        "--lease-token-file",
        type=Path,
        default=None,
        help="M1: path from gatectl issue-token (O_EXCL 0600); deleted after claim",
    )
    parser.add_argument(
        "--lease-token",
        default=None,
        help="Scratch/unit-test only; prefer --lease-token-file (not for LIVE)",
    )
    args = parser.parse_args(argv)

    # M2: re-check after parse (covers --data-root= and abbreviations if any).
    if args.run_lock is not None and _is_live_data_root(args.data_root):
        sys.stderr.write(
            "refuse --run-lock override on LIVE data-root (M2 post-parse)\n"
        )
        return EXIT_RUN_LOCK

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not args.allowlist or not args.allowlist.exists():
        _LOG.error("allowlist required and must exist (freeze JSON)")
        return 2

    try:
        allowlist, config_allowlist = load_allowlist_file(args.allowlist)
    except (FreezeError, json.JSONDecodeError, OSError) as exc:
        _LOG.error("allowlist load failed: %s", exc)
        return 2

    if not allowlist:
        _LOG.error("allowlist empty — abort")
        return 2

    # M1: no env token; LIVE refuses raw --lease-token (ps-visible).
    token_file_path: Optional[Path] = args.lease_token_file
    lease_tok: Optional[str] = None
    if token_file_path is not None:
        try:
            lease_tok = _consume_lease_token_file(token_file_path)
        except (OSError, ValueError) as exc:
            _LOG.error("lease token file refused: %s", exc)
            return EXIT_CONTROL_PLANE
    elif args.lease_token:
        if _is_live_data_root(args.data_root):
            _LOG.error("refuse --lease-token on LIVE data-root (M1 use --lease-token-file)")
            return EXIT_CONTROL_PLANE
        lease_tok = args.lease_token
    elif os.environ.get("SHADOW_LEASE_TOKEN"):
        _LOG.error("refuse SHADOW_LEASE_TOKEN env (M1 — use --lease-token-file)")
        return EXIT_CONTROL_PLANE

    policy_cfg = load_policy_cfg(args.policy_json)
    token_ids = [e["token_id"] for e in allowlist.values()]
    try:
        assert_ws_covers_allowlist(token_ids, allowlist)
    except ValueError as exc:
        _LOG.error("%s", exc)
        return 2

    from order_execution_engine.control_plane_lease import (
        ControlPlaneError,
        LeaseError,
        ensure_control_plane_ready,
    )

    store: Optional[SQLiteShadowStorage] = None
    run_status = "COMMITTED"
    # M3: STOPPED = ordered SIGTERM; ABORTED = interrupt/exception/abort-run only.
    shutdown = threading.Event()
    stop_flag = {"stop": None}  # asyncio.Event after loop start

    def _early_sigterm(_signum: int, _frame: Any) -> None:
        _LOG.info("SIGTERM early (pre-loop) — will STOPPED")
        shutdown.set()
        ev = stop_flag.get("stop")
        if ev is not None:
            try:
                loop = asyncio.get_event_loop()
                loop.call_soon_threadsafe(ev.set)
            except Exception:  # noqa: BLE001
                pass

    try:
        signal.signal(signal.SIGTERM, _early_sigterm)
    except (ValueError, OSError) as exc:
        _LOG.warning("early SIGTERM handler not installed: %s", exc)

    if shutdown.is_set():
        # Restpunkt: do not claim — leave lease token unused (no run_id burn).
        _LOG.info("SIGTERM before claim — exit without claim (token unused)")
        return EXIT_STOPPED_BEFORE_CLAIM

    try:
        # Gate #6: enforce v12 + Soll-manifest + forbid_run_id_gt, then claim.
        store = SQLiteShadowStorage.for_user(args.data_root, args.user_id)
        try:
            ready = ensure_control_plane_ready(store._conn)  # noqa: SLF001
        except ControlPlaneError as exc:
            _LOG.error("control-plane preflight: %s", exc)
            store.close()
            return EXIT_CONTROL_PLANE
        _ = ready
        store.close()
        store = None

        if shutdown.is_set():
            _LOG.info("SIGTERM before claim — exit without claim (token unused)")
            return EXIT_STOPPED_BEFORE_CLAIM

        try:
            engine, bridge, store, binding, config_json = build_runner(
                data_root=args.data_root,
                user_id=args.user_id,
                allowlist=allowlist,
                policy_cfg=policy_cfg,
                start_ws=not args.no_ws and not args.once,
                config_allowlist=config_allowlist,
                lease_token=lease_tok,
            )
            if token_file_path is not None and token_file_path.is_file():
                try:
                    token_file_path.unlink()
                except OSError as exc:
                    _LOG.warning("token file unlink after claim: %s", exc)
        except LeaseError as exc:
            _LOG.error("lease claim refused (D1/D6b no-retry): %s", exc)
            return EXIT_CONTROL_PLANE
        except (sqlite3.Error, OSError) as exc:
            _LOG.error("lease claim path failed closed: %s", exc)
            return EXIT_CONTROL_PLANE
        except ValueError as exc:
            _LOG.error("%s", exc)
            return 2
    except ControlPlaneError as exc:
        _LOG.error("control-plane refused (D6b no-retry): %s", exc)
        if store is not None:
            try:
                store.close()
            except Exception:  # noqa: BLE001
                pass
        return EXIT_CONTROL_PLANE
    except LeaseError as exc:
        _LOG.error("lease refused (D6b no-retry): %s", exc)
        if store is not None:
            try:
                store.close()
            except Exception:  # noqa: BLE001
                pass
        return EXIT_CONTROL_PLANE
    except Exception:
        if store is not None:
            try:
                store.close()
            except Exception:  # noqa: BLE001
                pass
        raise

    if shutdown.is_set():
        run_status = "STOPPED"
        _LOG.info("SIGTERM after claim before loop — STOPPED (run_id consumed)")
        try:
            if store is not None and store.active_run_id is not None:
                store.close_run(run_status)
        except Exception as exc:  # noqa: BLE001
            _LOG.error("close_run failed: %s", exc)
        try:
            if store is not None:
                store.close()
        except Exception:  # noqa: BLE001
            pass
        return 0

    from order_execution_engine.epoch_hydrate import try_hydrate_engine_portfolio

    _epoch_on = os.environ.get("EPOCH_HYDRATE", "").strip() in ("1", "true", "yes")
    _epoch_marker = os.environ.get("EPOCH_MARKER_ROWID", "").strip()
    _marker_i = int(_epoch_marker) if _epoch_marker.isdigit() else None
    if try_hydrate_engine_portfolio(
        engine, store, epoch_marker_rowid=_marker_i, enabled=_epoch_on,
    ):
        _LOG.info(
            "epoch_hydrate enabled marker_rowid=%s (read-only)",
            _marker_i,
        )

    _LOG.info(
        "run_id=%s git_commit=%s max_news_age_s=%s ws_tokens=%s",
        store.active_run_id,
        config_json.get("git_commit"),
        config_json.get("max_news_age_s"),
        len(token_ids),
    )

    sink = TelemetrySink(
        store, engine.telemetry,
        fills_provider=engine.fills_for,
        peak_events_provider=engine.peak_events,
    )

    user_dir = args.data_root / args.user_id / "shadow"
    offset_path = user_dir / "news_tail.offset"
    tail = JsonlTail(args.news_jsonl, offset_path)

    try:
        if args.once:
            dispatched = 0
            for item in iter_news_jsonl(args.news_jsonl):
                if bridge.on_news_item(item):
                    dispatched += 1
            sink.drain()
            _LOG.info(
                "once dispatched=%s discards=%s run_id=%s",
                dispatched, len(bridge.discards), store.active_run_id,
            )
            return 0

        if (
            not args.no_tail_from_end
            and args.tail_from_end
            and not offset_path.exists()
        ):
            tail.seek_end()
            _LOG.info("tail_from_end offset=%s path=%s", tail._offset, args.news_jsonl)
        else:
            _LOG.info("tail_resume offset=%s path=%s", tail._offset, args.news_jsonl)

        if args.no_ws:
            return 0

        hub = ShadowHub(engine)

        async def _run_until_stop() -> None:
            stop_event = asyncio.Event()
            stop_flag["stop"] = stop_event
            loop = asyncio.get_running_loop()

            def _on_sigterm() -> None:
                _LOG.info("SIGTERM — ordered stop (M3 → STOPPED)")
                shutdown.set()
                stop_event.set()

            try:
                loop.add_signal_handler(signal.SIGTERM, _on_sigterm)
            except (NotImplementedError, RuntimeError) as exc:
                # Windows / non-main thread: fall back to signal.signal
                _LOG.warning("add_signal_handler unavailable: %s", exc)

                def _sync_sigterm(_s: int, _f: Any) -> None:
                    _LOG.info("SIGTERM — ordered stop (M3 → STOPPED)")
                    shutdown.set()
                    loop.call_soon_threadsafe(stop_event.set)

                signal.signal(signal.SIGTERM, _sync_sigterm)
            await run_ws_hub_and_tail(
                binding,
                hub,
                token_ids,
                bridge=bridge,
                sink=sink,
                tail=tail,
                tail_interval_s=args.tail_interval_s,
                stop_event=stop_event,
            )

        try:
            asyncio.run(_run_until_stop())
        except KeyboardInterrupt:
            run_status = "ABORTED"
        if shutdown.is_set():
            run_status = "STOPPED"
        return 0
    except Exception:
        run_status = "ABORTED"
        raise
    finally:
        try:
            sink.drain()
        except Exception:  # noqa: BLE001
            pass
        try:
            if store.active_run_id is not None:
                store.close_run(run_status)
        except Exception as exc:  # noqa: BLE001
            _LOG.error("close_run failed: %s", exc)
        try:
            store.close()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main())
