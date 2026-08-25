"""Live RPC ingestion for Wave 38 — getLogs + optional MEV block subsample.

Fills Agent-1 SQLite under ``wave38/live/`` for a frozen window.
Never writes sealed Bridge reference artifacts.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from agents_b2g.diagnostic.config import DiagnosticConfig
from agents_b2g.diagnostic.ingestion_rpc import LiveRpcTransport, as_int, redact_url
from agents_b2g.diagnostic.intent_stable_lib import TOPIC_BY_EVENT
from agents_b2g.diagnostic.liquidation_lib import TOPIC_LIQUIDATION_CALL
from agents_b2g.diagnostic.live_window import FrozenLiveWindow
from agents_b2g.diagnostic.oracle_lib import TOPIC_ANSWER_UPDATED
from agents_b2g.diagnostic.reference_guard import (
    ReferenceArtifactGuard,
    ensure_live_directory,
)

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from bridge_stufe_a_config import (  # noqa: E402
    OMNIBRIDGE_ETH,
    OMNIBRIDGE_GNOSIS,
    TOPIC_TOKENS_BRIDGED,
    TOPIC_TOKENS_BRIDGING_INITIATED,
)
from bridge_stufe_a_rpc import (  # noqa: E402
    ETH_HTTP_FALLBACKS,
    GNOSIS_HTTP_FALLBACKS,
    RpcError,
    get_logs_chunked,
    timestamp_to_block,
)
import os


# Prefer public getLogs-capable endpoints; paid/alchemy keys often 403 or tiny ranges.
_ETH_GETLOGS_URLS: tuple[str, ...] = (
    "https://ethereum-rpc.publicnode.com",
    "https://eth.llamarpc.com",
    "https://rpc.ankr.com/eth",
    "https://eth.drpc.org",
    "https://1rpc.io/eth",
    "https://cloudflare-eth.com",
)


ProgressCb = Callable[[str], None]


def _checkpoint_path(live: Path, job_id: str) -> Path:
    return live / f"checkpoint_{job_id}.json"


def _target_fingerprint(tgt: dict[str, Any]) -> str:
    topics = tgt.get("topics")
    if isinstance(topics, list) and topics:
        if isinstance(topics[0], list):
            topic_key = "|".join(str(t) for t in topics[0])
        else:
            topic_key = "|".join(str(t) for t in topics)
    else:
        topic_key = ""
    return f"{tgt.get('family')}:{tgt['chain']}:{tgt['address']}:{topic_key}"


def _load_capture_checkpoint(live: Path, job_id: str) -> dict[str, Any] | None:
    path = _checkpoint_path(live, job_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _write_capture_checkpoint(
    path: Path,
    *,
    guard: ReferenceArtifactGuard,
    payload: dict[str, Any],
) -> None:
    guard.assert_write_allowed(path)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _count_sqlite_rows(conn: sqlite3.Connection) -> tuple[int, int]:
    n_events = int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
    n_tx = int(conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])
    return n_events, n_tx


def _rebuild_occ_from_sqlite(
    conn: sqlite3.Connection,
    *,
    capture_start_ts: int,
    n_bins: int,
    bridge_eth: list[int],
    bridge_gno: list[int],
    gas_eth: list[int],
    gas_gno: list[int],
) -> None:
    """Rebuild in-memory occupancy vectors from persisted Agent-1 SQLite."""
    eth_bridge = OMNIBRIDGE_ETH.lower()
    gno_bridge = OMNIBRIDGE_GNOSIS.lower()
    rows = conn.execute("SELECT chain, address, payload FROM events").fetchall()
    for chain, address, payload in rows:
        try:
            body = json.loads(payload)
        except json.JSONDecodeError:
            continue
        ts = int(body.get("blockTime") or 0)
        idx = _minute_index(ts, capture_start_ts, n_bins)
        if idx is None:
            continue
        addr = str(address or "").lower()
        if chain == "ethereum" and addr == eth_bridge:
            bridge_eth[idx] = 1
        elif chain == "gnosis" and addr == gno_bridge:
            bridge_gno[idx] = 1
        if chain == "ethereum":
            gas_eth[idx] = 1
        else:
            gas_gno[idx] = 1


def _etherscan_strategy_status() -> dict[str, Any]:
    key = os.environ.get("ETHERSCAN_API_KEY", "").strip()
    return {
        "etherscan_api_key_set": bool(key),
        "ethereum_strategy": "etherscan_first" if key else "rpc_fallback",
    }


def _rpc_fallbacks(chain: str, primary: str) -> list[str]:
    """Ordered RPC URLs for getLogs — public getLogs pool first, then primary."""
    if chain == "ethereum":
        pool = list(_ETH_GETLOGS_URLS)
        env_rpc = os.environ.get("ETH_RPC") or os.environ.get("ETHEREUM_RPC")
        if env_rpc:
            pool.append(env_rpc)
        pool.extend(ETH_HTTP_FALLBACKS)
    else:
        pool = list(GNOSIS_HTTP_FALLBACKS)
        pool.append(primary)
    ordered: list[str] = []
    for u in [primary, *pool]:
        if u and u not in ordered:
            ordered.append(u)
    return ordered


def _etherscan_logs_if_available(
    chain: str,
    address: str,
    topic0: str,
    from_block: int,
    to_block: int,
    *,
    log: ProgressCb,
) -> list[dict[str, Any]] | None:
    """Optional Etherscan v2 path when ETHERSCAN_API_KEY is set (Bridge capture reuse)."""
    api_key = os.environ.get("ETHERSCAN_API_KEY", "").strip()
    if not api_key or chain != "ethereum":
        return None
    try:
        from bridge_stufe_a_capture import etherscan_get_logs  # noqa: WPS433
    except Exception:  # noqa: BLE001
        return None
    log("  getLogs via Etherscan v2 (ETHERSCAN_API_KEY)")
    return etherscan_get_logs(
        chain, address, topic0, from_block, to_block, api_key, chunk=5_000
    )


def get_logs_resilient(
    chain: str,
    primary_url: str,
    address: str,
    topics: list[Any],
    from_block: int,
    to_block: int,
    chunk: int,
    *,
    log: ProgressCb,
) -> list[dict[str, Any]]:
    """Try publicnode/fallbacks; optional Etherscan; OR-topic0 → single-topic calls."""
    last_exc: Exception | None = None
    if topics and isinstance(topics[0], list) and len(topics[0]) > 1:
        topic_variants: list[list[Any]] = [[t] for t in topics[0]]
    elif topics and isinstance(topics[0], list) and len(topics[0]) == 1:
        topic_variants = [[topics[0][0]]]
    else:
        topic_variants = [topics]

    aggregated: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for topic_arg in topic_variants:
        topic0 = ""
        if topic_arg and isinstance(topic_arg[0], str):
            topic0 = topic_arg[0]
        elif topic_arg and isinstance(topic_arg[0], list) and topic_arg[0]:
            topic0 = str(topic_arg[0][0])

        got: list[dict[str, Any]] | None = None
        # Ethereum: Etherscan first when key present (public RPCs often unusable for 90d)
        if topic0 and chain == "ethereum":
            try:
                got = _etherscan_logs_if_available(
                    chain, address, topic0, from_block, to_block, log=log
                )
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                log(f"  Etherscan getLogs fail: {exc}")
        if got is None:
            for url in _rpc_fallbacks(chain, primary_url):
                try:
                    start_chunk = min(chunk, 500) if chain == "ethereum" else chunk
                    got = get_logs_chunked(
                        url,
                        address,
                        topic_arg,
                        from_block,
                        to_block,
                        start_chunk,
                        sleep_s=0.08,
                    )
                    if url != primary_url:
                        log(f"  getLogs OK via fallback {redact_url(url)}")
                    break
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    log(f"  getLogs fail {redact_url(url)}: {exc}")
                    continue
        if got is None:
            raise last_exc or RpcError(f"getLogs exhausted for {chain} {address[:12]}")
        for lg in got:
            key = (str(lg.get("transactionHash") or ""), as_int(lg.get("logIndex", 0)))
            if key in seen:
                continue
            seen.add(key)
            aggregated.append(lg)
    return aggregated


@dataclass
class LiveIngestResult:
    raw_db_path: str
    bridge_eth_occ: list[int]
    bridge_gnosis_occ: list[int]
    z_alt: list[list[int]]
    block_ranges: dict[str, dict[str, int]]
    rpc_urls: dict[str, str]
    n_events: int
    n_transactions: int
    mev_blocks_scanned: int
    capture_start_ts: int = 0
    capture_end_ts: int = 0
    n_bins: int = 0
    capture_tail_days: int | None = None
    log_targets: list[dict[str, Any]] = field(default_factory=list)


def prepare_live_address_books(*, user_id: str) -> dict[str, Path]:
    """Copy Bridge resolver JSONs into live/ as address books (not occupancy)."""
    live = ensure_live_directory(DiagnosticConfig.DATA_ROOT, user_id)
    guard = ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT)
    root = DiagnosticConfig.PROJECT_ROOT
    mapping = {
        live / "oracle" / "chainlink_resolved.json": root
        / "bridge_stufe_a_v3_chainlink_resolved.json",
        live / "liquidations" / "liquidation_resolved.json": root
        / "bridge_stufe_a_v3_liquidation_resolved.json",
        live / "intent_stablecoin" / "intent_relayer_resolved.json": root
        / "bridge_stufe_a_v3_intent_relayer_resolved.json",
        live / "intent_stablecoin" / "stablecoin_mint_burn_resolved.json": root
        / "bridge_stufe_a_v3_stablecoin_mint_burn_resolved.json",
    }
    out: dict[str, Path] = {}
    for dest, src in mapping.items():
        dest.parent.mkdir(parents=True, exist_ok=True)
        guard.assert_write_allowed(dest)
        if not dest.is_file():
            dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        out[str(dest.relative_to(live))] = dest
    return out


def _open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            chain TEXT NOT NULL,
            tx TEXT NOT NULL,
            log_index INTEGER NOT NULL,
            block_number INTEGER,
            address TEXT,
            topic0 TEXT,
            payload TEXT,
            PRIMARY KEY (chain, tx, log_index)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            chain TEXT NOT NULL,
            tx_hash TEXT NOT NULL,
            block_number INTEGER,
            timestamp INTEGER,
            tx_from TEXT,
            status INTEGER,
            PRIMARY KEY (chain, tx_hash)
        )
        """
    )
    conn.commit()
    return conn


def _minute_index(ts: int, window_start_ts: int, n_bins: int) -> int | None:
    if ts < window_start_ts:
        return None
    idx = (ts - window_start_ts) // 60
    if 0 <= idx < n_bins:
        return idx
    return None


def _collect_log_targets(user_id: str) -> list[dict[str, Any]]:
    live = ensure_live_directory(DiagnosticConfig.DATA_ROOT, user_id)
    targets: list[dict[str, Any]] = []

    # OmniBridge (treatment X/Y)
    targets.append(
        {
            "family": "bridge",
            "chain": "ethereum",
            "address": OMNIBRIDGE_ETH.lower(),
            "topics": [[TOPIC_TOKENS_BRIDGING_INITIATED, TOPIC_TOKENS_BRIDGED]],
        }
    )
    targets.append(
        {
            "family": "bridge",
            "chain": "gnosis",
            "address": OMNIBRIDGE_GNOSIS.lower(),
            "topics": [[TOPIC_TOKENS_BRIDGED, TOPIC_TOKENS_BRIDGING_INITIATED]],
        }
    )

    # Chainlink aggregators — current aggregator only (historical phases = noise for live)
    cl = json.loads((live / "oracle" / "chainlink_resolved.json").read_text())
    for chain, cfg in (cl.get("chains") or {}).items():
        for feed in cfg.get("feeds") or []:
            if feed.get("status") != "RESOLVED":
                continue
            current = str(feed.get("current_aggregator") or "").lower()
            if current.startswith("0x") and len(current) == 42:
                targets.append(
                    {
                        "family": "oracle",
                        "chain": chain,
                        "address": current,
                        "topics": [TOPIC_ANSWER_UPDATED],
                        "feed": feed.get("name"),
                    }
                )

    # Liquidations
    liq = json.loads(
        (live / "liquidations" / "liquidation_resolved.json").read_text()
    )
    for pool in liq.get("pools") or []:
        if pool.get("status") != "RESOLVED":
            continue
        targets.append(
            {
                "family": "liquidations",
                "chain": pool["chain"],
                "address": str(pool["pool"]).lower(),
                "topics": [TOPIC_LIQUIDATION_CALL],
            }
        )

    # Intent + stablecoin
    for name in (
        "intent_relayer_resolved.json",
        "stablecoin_mint_burn_resolved.json",
    ):
        body = json.loads((live / "intent_stablecoin" / name).read_text())
        for c in body.get("contracts") or []:
            if c.get("status") != "RESOLVED":
                continue
            topics = [TOPIC_BY_EVENT[e] for e in c.get("events") or [] if e in TOPIC_BY_EVENT]
            if not topics:
                continue
            targets.append(
                {
                    "family": "intent_stable",
                    "chain": c["chain"],
                    "address": str(c["address"]).lower(),
                    "topics": topics if len(topics) == 1 else [topics],
                }
            )

    # Z_alt drivers: gas occupancy from block headers during log ingest.
    # Do NOT eth_getLogs Uniswap with empty topic filter (unbounded volume).
    # Optional: one Uniswap Universal Router address with a Swap topic0 if present
    # in TOPIC_BY_EVENT — skipped; gas series fill z_alt slots.
    return targets


def run_live_ingestion(
    window: FrozenLiveWindow,
    *,
    user_id: str = "wave38",
    job_id: str = "live-first",
    mev_stride: int = 120,
    mev_max_blocks: int | None = 8_000,
    getlogs_chunk: int = 2_000,
    capture_tail_days: int | None = None,
    capture_resume: bool = False,
    capture_resume_from_target: int | None = None,
    require_etherscan: bool = False,
    progress: ProgressCb | None = None,
) -> LiveIngestResult:
    """Capture frozen window into SQLite + bridge/Z_alt occupancy vectors.

    If ``capture_tail_days`` is set, only the last N days of the frozen window
    are fetched (first-cycle / progressive fill). Occupancy vectors then use
    N×1440 bins with window_start = frozen_end − N days. The frozen 90d
    metadata remains authoritative in live_window.json.
    """

    def log(msg: str) -> None:
        if progress:
            progress(msg)
        else:
            print(msg, flush=True)

    eth_strategy = _etherscan_strategy_status()
    if require_etherscan and not eth_strategy["etherscan_api_key_set"]:
        raise RuntimeError(
            "ETHERSCAN_API_KEY required for Ethereum getLogs (Etherscan-first strategy)"
        )
    if eth_strategy["etherscan_api_key_set"]:
        log("Etherscan-first: ETHERSCAN_API_KEY set for Ethereum getLogs")
    else:
        log(
            "WARN: ETHERSCAN_API_KEY unset — Ethereum getLogs use RPC fallback "
            "(slow/unreliable for 90d; set key for Etherscan-first)"
        )

    prepare_live_address_books(user_id=user_id)
    live = ensure_live_directory(DiagnosticConfig.DATA_ROOT, user_id)
    guard = ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT)
    guard.verify_unchanged()
    db_path = live / f"raw_events_{job_id}.sqlite"
    guard.assert_write_allowed(db_path)

    transport = LiveRpcTransport()
    rpc_urls: dict[str, str] = {}
    for chain in ("ethereum", "gnosis"):
        rpc_urls[chain] = transport.probe(chain)
        log(f"RPC {chain}: {redact_url(rpc_urls[chain])}")

    capture_start_ts = window.window_start_ts
    capture_end_ts = window.window_end_ts
    n_bins = window.n_bins
    if capture_tail_days is not None and capture_tail_days > 0:
        n_bins = capture_tail_days * 24 * 60
        capture_start_ts = capture_end_ts - capture_tail_days * 86_400
        log(
            f"First-cycle capture tail: {capture_tail_days}d "
            f"(bins={n_bins}); frozen 90d window unchanged in live_window.json"
        )

    block_ranges: dict[str, dict[str, int]] = {}
    ts_cache: dict[str, dict[int, int]] = {"ethereum": {}, "gnosis": {}}
    for chain in ("ethereum", "gnosis"):
        url = rpc_urls[chain]
        log(f"Resolving blocks for {chain} capture span…")
        lo = timestamp_to_block(url, capture_start_ts, ts_cache[chain])
        hi = timestamp_to_block(url, capture_end_ts, ts_cache[chain])
        if hi < lo:
            lo, hi = hi, lo
        block_ranges[chain] = {"from": lo, "to": hi}
        log(f"{chain} blocks {lo}-{hi}")

    bridge_eth = [0] * n_bins
    bridge_gno = [0] * n_bins
    uni_occ = [0] * n_bins
    gas_eth = [0] * n_bins
    gas_gno = [0] * n_bins

    targets = _collect_log_targets(user_id)

    ck_path = _checkpoint_path(live, job_id)
    prior_ck = _load_capture_checkpoint(live, job_id) if capture_resume else None
    if prior_ck and prior_ck.get("status") == "completed":
        log(f"Checkpoint {job_id} already completed — rebuilding from SQLite")
        return rebuild_ingest_from_sqlite(window, user_id=user_id, job_id=job_id)

    start_target = 0
    mev_phase = "pending"
    mev_chain_progress: dict[str, int] = {}
    if capture_resume and prior_ck and prior_ck.get("status") == "in_progress":
        start_target = int(prior_ck.get("next_target_index") or 0)
        mev_phase = str(prior_ck.get("mev_phase") or "pending")
        mev_chain_progress = dict(prior_ck.get("mev_chain_progress") or {})
        log(
            f"Capture resume: target {start_target + 1}/{len(targets)}, "
            f"mev_phase={mev_phase}, prior_events={prior_ck.get('n_events', 0)}"
        )
    elif capture_resume and capture_resume_from_target is not None:
        start_target = max(0, capture_resume_from_target - 1)
        log(
            f"Capture bootstrap resume from target {capture_resume_from_target}/{len(targets)} "
            "(no checkpoint — SQLite dedup active)"
        )

    conn = _open_db(db_path)
    n_events = 0
    n_tx = 0

    try:
        n_events, n_tx = _count_sqlite_rows(conn)
        bridge_eth = [0] * n_bins
        bridge_gno = [0] * n_bins
        uni_occ = [0] * n_bins
        gas_eth = [0] * n_bins
        gas_gno = [0] * n_bins
        if capture_resume and (start_target > 0 or mev_phase != "pending"):
            _rebuild_occ_from_sqlite(
                conn,
                capture_start_ts=capture_start_ts,
                n_bins=n_bins,
                bridge_eth=bridge_eth,
                bridge_gno=bridge_gno,
                gas_eth=gas_eth,
                gas_gno=gas_gno,
            )
            log(f"Rebuilt occupancy from SQLite ({n_events} events, {n_tx} tx)")

        def flush_checkpoint(
            *,
            status: str,
            next_target_index: int,
            mev_phase_value: str,
            mev_scanned: int = 0,
        ) -> None:
            _write_capture_checkpoint(
                ck_path,
                guard=guard,
                payload={
                    "job_id": job_id,
                    "status": status,
                    "next_target_index": next_target_index,
                    "completed_targets": [
                        _target_fingerprint(targets[i])
                        for i in range(min(next_target_index, len(targets)))
                    ],
                    "mev_phase": mev_phase_value,
                    "mev_chain_progress": mev_chain_progress,
                    "etherscan_strategy": eth_strategy,
                    "block_ranges": block_ranges,
                    "rpc_urls": {k: redact_url(v) for k, v in rpc_urls.items()},
                    "n_events": n_events,
                    "n_transactions": n_tx,
                    "mev_blocks_scanned": mev_scanned,
                    "mev_stride": mev_stride,
                    "mev_max_blocks": mev_max_blocks,
                    "capture_start_ts": capture_start_ts,
                    "capture_end_ts": capture_end_ts,
                    "n_bins": n_bins,
                    "capture_tail_days": capture_tail_days,
                    "window": window.to_dict(),
                    "log_targets": [
                        {
                            "family": t.get("family"),
                            "chain": t["chain"],
                            "address": t["address"],
                        }
                        for t in targets
                    ],
                },
            )

        for i, tgt in enumerate(targets):
            if i < start_target:
                continue
            chain = tgt["chain"]
            url = rpc_urls[chain]
            lo = block_ranges[chain]["from"]
            hi = block_ranges[chain]["to"]
            addr = tgt["address"]
            topics = tgt["topics"]
            # Normalize topics for eth_getLogs: list with topic0 filter
            if topics == [None]:
                topic_arg: list[Any] = []
            elif isinstance(topics[0], list):
                topic_arg = [topics[0]]
            else:
                topic_arg = [topics[0]] if len(topics) == 1 else [topics]
            log(
                f"[{i+1}/{len(targets)}] getLogs {chain} {addr[:10]}… "
                f"family={tgt.get('family')}"
            )
            try:
                logs = get_logs_resilient(
                    chain,
                    url,
                    addr,
                    topic_arg,
                    lo,
                    hi,
                    getlogs_chunk,
                    log=log,
                )
            except Exception as exc:  # noqa: BLE001
                log(f"  WARN getLogs failed: {exc}")
                continue
            for lg in logs:
                bn = as_int(lg.get("blockNumber", 0))
                if bn not in ts_cache[chain]:
                    try:
                        blk = transport.eth_get_block_by_number(chain, bn)
                        ts_cache[chain][bn] = as_int(blk["timestamp"])
                        # gas for Z_alt
                        gp = blk.get("baseFeePerGas") or blk.get("gasPrice") or "0x0"
                        gwei = as_int(gp) / 1e9
                        idx_g = _minute_index(
                            ts_cache[chain][bn], capture_start_ts, n_bins
                        )
                        if idx_g is not None:
                            series = gas_eth if chain == "ethereum" else gas_gno
                            series[idx_g] = max(series[idx_g], 1 if gwei > 0 else 0)
                    except Exception:  # noqa: BLE001
                        ts_cache[chain][bn] = capture_start_ts
                ts = ts_cache[chain][bn]
                tx = str(lg.get("transactionHash") or "")
                log_index = as_int(lg.get("logIndex", 0))
                topics_l = lg.get("topics") or []
                topic0 = topics_l[0] if topics_l else ""
                payload = dict(lg)
                payload["blockTime"] = ts
                try:
                    conn.execute(
                        """
                        INSERT INTO events
                        (chain, tx, log_index, block_number, address, topic0, payload)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            chain,
                            tx,
                            log_index,
                            bn,
                            str(lg.get("address") or addr).lower(),
                            str(topic0),
                            json.dumps(payload, default=str),
                        ),
                    )
                    n_events += 1
                except sqlite3.IntegrityError:
                    pass

                idx = _minute_index(ts, capture_start_ts, n_bins)
                if idx is None:
                    continue
                fam = tgt.get("family")
                if fam == "bridge":
                    if chain == "ethereum":
                        bridge_eth[idx] = 1
                    else:
                        bridge_gno[idx] = 1
                elif fam == "z_alt_uniswap":
                    uni_occ[idx] = 1

            conn.commit()
            time.sleep(0.05)
            flush_checkpoint(
                status="in_progress",
                next_target_index=i + 1,
                mev_phase_value="pending",
            )

        # MEV subsample: eth_getBlockReceipts every mev_stride blocks
        mev_scanned = int((prior_ck or {}).get("mev_blocks_scanned") or 0)
        if mev_phase != "done":
            mev_phase = "in_progress"
            flush_checkpoint(
                status="in_progress",
                next_target_index=len(targets),
                mev_phase_value=mev_phase,
                mev_scanned=mev_scanned,
            )
            for chain in ("ethereum", "gnosis"):
                lo = block_ranges[chain]["from"]
                hi = block_ranges[chain]["to"]
                blocks = list(range(lo, hi + 1, max(1, mev_stride)))
                if mev_max_blocks is not None:
                    blocks = blocks[-mev_max_blocks:]
                resume_from = mev_chain_progress.get(chain)
                if resume_from is not None:
                    blocks = [b for b in blocks if b > resume_from]
                log(f"MEV subsample {chain}: {len(blocks)} blocks stride={mev_stride}")
                for bn in blocks:
                    try:
                        if bn not in ts_cache[chain]:
                            blk = transport.eth_get_block_by_number(chain, bn)
                            ts_cache[chain][bn] = as_int(blk["timestamp"])
                        ts = ts_cache[chain][bn]
                        receipts = transport.eth_get_block_receipts(chain, bn)
                    except Exception as exc:  # noqa: BLE001
                        log(f"  MEV block {bn} skip: {exc}")
                        continue
                    mev_scanned += 1
                    for r in receipts or []:
                        tx = str(r.get("transactionHash") or "")
                        status_raw = r.get("status")
                        status = (
                            1
                            if status_raw in ("0x1", 1, "1")
                            else 0
                            if status_raw in ("0x0", 0, "0")
                            else -1
                        )
                        try:
                            conn.execute(
                                """
                                INSERT INTO transactions
                                (chain, tx_hash, block_number, timestamp, tx_from, status)
                                VALUES (?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    chain,
                                    tx,
                                    bn,
                                    ts,
                                    str(r.get("from") or "").lower(),
                                    status,
                                ),
                            )
                            n_tx += 1
                        except sqlite3.IntegrityError:
                            pass
                    if mev_scanned % 50 == 0:
                        conn.commit()
                        mev_chain_progress[chain] = bn
                        flush_checkpoint(
                            status="in_progress",
                            next_target_index=len(targets),
                            mev_phase_value="in_progress",
                            mev_scanned=mev_scanned,
                        )
                conn.commit()
                mev_chain_progress[chain] = hi
                flush_checkpoint(
                    status="in_progress",
                    next_target_index=len(targets),
                    mev_phase_value="in_progress",
                    mev_scanned=mev_scanned,
                )
            mev_phase = "done"

        # Ensure reference guard still intact after network I/O
        guard.verify_unchanged()
    finally:
        conn.close()

    # Z_alt: uniswap + eth gas occupancy + gnosis gas occupancy (tertile later)
    z_alt = [uni_occ, gas_eth, gas_gno]

    _write_capture_checkpoint(
        ck_path,
        guard=guard,
        payload={
            "job_id": job_id,
            "status": "completed",
            "next_target_index": len(targets),
            "completed_targets": [_target_fingerprint(t) for t in targets],
            "mev_phase": "done",
            "mev_chain_progress": mev_chain_progress,
            "etherscan_strategy": eth_strategy,
            "block_ranges": block_ranges,
            "rpc_urls": {k: redact_url(v) for k, v in rpc_urls.items()},
            "n_events": n_events,
            "n_transactions": n_tx,
            "mev_blocks_scanned": mev_scanned,
            "mev_stride": mev_stride,
            "mev_max_blocks": mev_max_blocks,
            "capture_start_ts": capture_start_ts,
            "capture_end_ts": capture_end_ts,
            "n_bins": n_bins,
            "capture_tail_days": capture_tail_days,
            "window": window.to_dict(),
            "log_targets": [
                {
                    "family": t.get("family"),
                    "chain": t["chain"],
                    "address": t["address"],
                }
                for t in targets
            ],
        },
    )

    return LiveIngestResult(
        raw_db_path=str(db_path),
        bridge_eth_occ=bridge_eth,
        bridge_gnosis_occ=bridge_gno,
        z_alt=z_alt,
        block_ranges=block_ranges,
        rpc_urls={k: redact_url(v) for k, v in rpc_urls.items()},
        n_events=n_events,
        n_transactions=n_tx,
        mev_blocks_scanned=mev_scanned,
        capture_start_ts=capture_start_ts,
        capture_end_ts=capture_end_ts,
        n_bins=n_bins,
        capture_tail_days=capture_tail_days,
        log_targets=[
            {
                "family": t.get("family"),
                "chain": t["chain"],
                "address": t["address"],
            }
            for t in targets
        ],
    )


def rebuild_ingest_from_sqlite(
    window: FrozenLiveWindow,
    *,
    user_id: str,
    job_id: str,
) -> LiveIngestResult:
    """Resume after successful capture — rebuild occupancy from Agent-1 SQLite."""
    live = ensure_live_directory(DiagnosticConfig.DATA_ROOT, user_id)
    ck = json.loads((live / f"checkpoint_{job_id}.json").read_text(encoding="utf-8"))
    db_path = live / f"raw_events_{job_id}.sqlite"
    capture_start_ts = int(ck.get("capture_start_ts") or window.window_start_ts)
    capture_end_ts = int(ck.get("capture_end_ts") or window.window_end_ts)
    n_bins = int(ck.get("n_bins") or window.n_bins)
    bridge_eth = [0] * n_bins
    bridge_gno = [0] * n_bins
    gas_eth = [0] * n_bins
    gas_gno = [0] * n_bins
    uni_occ = [0] * n_bins
    eth_bridge = OMNIBRIDGE_ETH.lower()
    gno_bridge = OMNIBRIDGE_GNOSIS.lower()
    conn = sqlite3.connect(str(db_path))
    try:
        n_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        n_tx = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        rows = conn.execute(
            "SELECT chain, address, payload FROM events"
        ).fetchall()
        for chain, address, payload in rows:
            try:
                body = json.loads(payload)
            except json.JSONDecodeError:
                continue
            ts = int(body.get("blockTime") or 0)
            idx = _minute_index(ts, capture_start_ts, n_bins)
            if idx is None:
                continue
            addr = str(address or "").lower()
            if chain == "ethereum" and addr == eth_bridge:
                bridge_eth[idx] = 1
            elif chain == "gnosis" and addr == gno_bridge:
                bridge_gno[idx] = 1
            if chain == "ethereum":
                gas_eth[idx] = 1
            else:
                gas_gno[idx] = 1
    finally:
        conn.close()
    return LiveIngestResult(
        raw_db_path=str(db_path),
        bridge_eth_occ=bridge_eth,
        bridge_gnosis_occ=bridge_gno,
        z_alt=[uni_occ, gas_eth, gas_gno],
        block_ranges=ck.get("block_ranges") or {},
        rpc_urls=ck.get("rpc_urls") or {},
        n_events=int(n_events),
        n_transactions=int(n_tx),
        mev_blocks_scanned=int(ck.get("mev_blocks_scanned") or 0),
        capture_start_ts=capture_start_ts,
        capture_end_ts=capture_end_ts,
        n_bins=n_bins,
        capture_tail_days=ck.get("capture_tail_days"),
    )


__all__ = [
    "LiveIngestResult",
    "_etherscan_strategy_status",
    "_load_capture_checkpoint",
    "_target_fingerprint",
    "prepare_live_address_books",
    "rebuild_ingest_from_sqlite",
    "run_live_ingestion",
]
