"""Wave 38 Agent 1 subagents — DataIngestion (RPC, checkpoint, SQLite)."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents_b2g.diagnostic.ingestion_rpc import (
    FixtureRpcTransport,
    LiveRpcTransport,
    RpcError,
    RpcTransport,
    as_int,
    default_chunk_width,
    redact_url,
)
from agents_b2g.diagnostic.reference_guard import (
    ReferenceArtifactGuard,
    ensure_live_directory,
)
from agents_b2g.diagnostic.types import StageContext, SubagentResult


@dataclass
class IngestionConfig:
    """Shared config for Agent 1 subagents."""

    chains: tuple[str, ...] = ("ethereum", "gnosis")
    fixture_mode: bool = True
    from_block: dict[str, int] = field(default_factory=dict)
    to_block: dict[str, int] = field(default_factory=dict)
    # When fixture: scan last N blocks from latest
    fixture_scan_blocks: int = 8
    max_retries: int = 3
    backoff_base_s: float = 0.05


def _transport(cfg: IngestionConfig) -> RpcTransport:
    if cfg.fixture_mode:
        return FixtureRpcTransport()
    return LiveRpcTransport()


def _live_dir(ctx: StageContext) -> Path:
    root = Path(ctx.data_root)
    # data_root may already be .../wave38/live
    if root.name == "live":
        live = root
    else:
        live = ensure_live_directory(root, ctx.user_id)
    live.mkdir(parents=True, exist_ok=True)
    return live


def _guard_write(path: Path) -> None:
    from agents_b2g.diagnostic.config import DiagnosticConfig

    ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT).assert_write_allowed(path)


# --- S5 RetryScheduler -------------------------------------------------------


class RetryScheduler:
    subagent_id = "W38-A1-S5"

    def run(self, ctx: StageContext, *, cfg: IngestionConfig) -> SubagentResult:
        policy = {
            "max_retries": cfg.max_retries,
            "backoff_base_s": cfg.backoff_base_s,
            "strategy": "exponential",
        }
        ctx.stage_outputs["retry_policy"] = policy
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics=policy,
            artifacts=({"type": "retry_policy", "data": policy},),
        )

    def call(
        self,
        fn,
        *,
        max_retries: int,
        backoff_base_s: float,
        on_retry=None,
    ):
        last: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001
                last = exc
                if on_retry:
                    on_retry(attempt, exc)
                if attempt < max_retries:
                    time.sleep(backoff_base_s * (2 ** (attempt - 1)))
        raise last  # type: ignore[misc]


# --- S6 RPCLoadBalancer ------------------------------------------------------


class RPCLoadBalancer:
    subagent_id = "W38-A1-S6"

    def run(self, ctx: StageContext, *, cfg: IngestionConfig) -> SubagentResult:
        transport = _transport(cfg)
        selected: dict[str, str] = {}
        for chain in cfg.chains:
            if cfg.fixture_mode:
                selected[chain] = transport.active_url(chain)
            else:
                assert isinstance(transport, LiveRpcTransport)
                selected[chain] = transport.probe(chain)
        ctx.stage_outputs["rpc_urls"] = selected
        ctx.stage_outputs["rpc_transport"] = transport
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={"n_chains": len(selected)},
            artifacts=(
                {
                    "type": "rpc_endpoints",
                    "data": {k: redact_url(v) for k, v in selected.items()},
                },
            ),
        )


# --- S4 ChunkCoordinator -----------------------------------------------------


class ChunkCoordinator:
    subagent_id = "W38-A1-S4"

    def run(self, ctx: StageContext, *, cfg: IngestionConfig) -> SubagentResult:
        widths = {chain: default_chunk_width(chain) for chain in cfg.chains}
        if cfg.fixture_mode:
            widths = {c: min(4, cfg.fixture_scan_blocks) for c in cfg.chains}
        ctx.stage_outputs["chunk_widths"] = widths
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics=widths,
            artifacts=({"type": "chunk_widths", "data": widths},),
        )

    @staticmethod
    def shrink(width: int) -> int:
        return max(1, width // 2)


# --- S1 / S2 Block scanners --------------------------------------------------


def _resolve_range(
    transport: RpcTransport,
    chain: str,
    cfg: IngestionConfig,
) -> tuple[int, int]:
    latest = transport.eth_block_number(chain)
    if chain in cfg.from_block and chain in cfg.to_block:
        return cfg.from_block[chain], cfg.to_block[chain]
    if cfg.fixture_mode:
        start = max(0, latest - cfg.fixture_scan_blocks + 1)
        return start, latest
    # Live default: last 64 blocks (smoke); Capture agents 2–5 set window later
    start = max(0, latest - 63)
    return start, latest


class EthBlockScanner:
    subagent_id = "W38-A1-S1"

    def run(self, ctx: StageContext, *, cfg: IngestionConfig) -> SubagentResult:
        return _scan_chain(self.subagent_id, ctx, cfg, "ethereum")


class GnosisBlockScanner:
    subagent_id = "W38-A1-S2"

    def run(self, ctx: StageContext, *, cfg: IngestionConfig) -> SubagentResult:
        return _scan_chain(self.subagent_id, ctx, cfg, "gnosis")


def _scan_chain(
    subagent_id: str,
    ctx: StageContext,
    cfg: IngestionConfig,
    chain: str,
) -> SubagentResult:
    if chain not in cfg.chains:
        return SubagentResult(
            subagent_id=subagent_id,
            status="skipped",
            metrics={"chain": chain},
        )
    transport: RpcTransport = ctx.stage_outputs.get("rpc_transport") or _transport(cfg)
    lo, hi = _resolve_range(transport, chain, cfg)
    widths = ctx.stage_outputs.get("chunk_widths") or {chain: 4}
    width = int(widths.get(chain, 4))
    blocks: list[dict[str, Any]] = []
    cur = lo
    while cur <= hi:
        end = min(cur + width - 1, hi)
        for b in range(cur, end + 1):
            blk = transport.eth_get_block_by_number(chain, b)
            blocks.append(
                {
                    "chain": chain,
                    "number": as_int(blk["number"]) if isinstance(blk.get("number"), str) else blk.get("number", b),
                    "timestamp": as_int(blk["timestamp"])
                    if isinstance(blk.get("timestamp"), str)
                    else blk.get("timestamp"),
                    "hash": blk.get("hash"),
                }
            )
        cur = end + 1
    key = f"blocks_{chain}"
    ctx.stage_outputs[key] = blocks
    ranges = ctx.stage_outputs.setdefault("block_ranges", {})
    ranges[chain] = {"from": lo, "to": hi, "n": len(blocks)}
    return SubagentResult(
        subagent_id=subagent_id,
        status="ok",
        metrics={"chain": chain, "from": lo, "to": hi, "n_blocks": len(blocks)},
        artifacts=({"type": key, "count": len(blocks)},),
    )


# --- S3 ReceiptFetcher -------------------------------------------------------


class ReceiptFetcher:
    subagent_id = "W38-A1-S3"

    def run(self, ctx: StageContext, *, cfg: IngestionConfig) -> SubagentResult:
        transport: RpcTransport = ctx.stage_outputs.get("rpc_transport") or _transport(cfg)
        all_receipts: list[dict[str, Any]] = []
        for chain in cfg.chains:
            blocks = ctx.stage_outputs.get(f"blocks_{chain}") or []
            for blk in blocks:
                num = int(blk["number"])
                receipts = transport.eth_get_block_receipts(chain, num)
                for r in receipts:
                    r = dict(r)
                    r["_chain"] = chain
                    r["_block"] = num
                    r["_timestamp"] = int(blk.get("timestamp") or 0)
                    all_receipts.append(r)
        ctx.stage_outputs["receipts"] = all_receipts
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={"n_receipts": len(all_receipts)},
            artifacts=({"type": "receipts", "count": len(all_receipts)},),
        )


# --- S7 CheckpointWriter -----------------------------------------------------


class CheckpointWriter:
    subagent_id = "W38-A1-S7"

    def run(self, ctx: StageContext, *, cfg: IngestionConfig) -> SubagentResult:
        live = _live_dir(ctx)
        path = live / f"checkpoint_{ctx.job_id}.json"
        _guard_write(path)
        payload = {
            "job_id": ctx.job_id,
            "run_id": ctx.run_id,
            "block_ranges": ctx.stage_outputs.get("block_ranges", {}),
            "rpc_urls": {
                k: redact_url(v)
                for k, v in (ctx.stage_outputs.get("rpc_urls") or {}).items()
            },
            "fixture_mode": cfg.fixture_mode,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        ctx.stage_outputs["checkpoint_path"] = str(path)
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={"checkpoint": str(path)},
            artifacts=({"type": "checkpoint", "path": str(path)},),
        )

    @staticmethod
    def load(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))


# --- S8 RawEventStorer -------------------------------------------------------


class RawEventStorer:
    subagent_id = "W38-A1-S8"

    def run(self, ctx: StageContext, *, cfg: IngestionConfig) -> SubagentResult:
        live = _live_dir(ctx)
        db_path = live / f"raw_events_{ctx.job_id}.sqlite"
        _guard_write(db_path)
        conn = sqlite3.connect(str(db_path))
        try:
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
            # Top-level TX scan table for Agent 3 (MEV) — not event logs
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
            inserted = 0
            skipped = 0
            tx_inserted = 0
            tx_skipped = 0
            for receipt in ctx.stage_outputs.get("receipts") or []:
                chain = receipt.get("_chain", "unknown")
                tx = str(receipt.get("transactionHash") or "")
                status_raw = receipt.get("status")
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
                            as_int(receipt.get("blockNumber", receipt.get("_block", 0))),
                            int(receipt.get("_timestamp") or 0),
                            str(receipt.get("from") or "").lower(),
                            status,
                        ),
                    )
                    tx_inserted += 1
                except sqlite3.IntegrityError:
                    tx_skipped += 1
                for log in receipt.get("logs") or []:
                    log_index = as_int(log.get("logIndex", 0))
                    topics = log.get("topics") or []
                    topic0 = topics[0] if topics else ""
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
                                as_int(log.get("blockNumber", receipt.get("_block", 0))),
                                str(log.get("address") or "").lower(),
                                str(topic0),
                                json.dumps(log, default=str),
                            ),
                        )
                        inserted += 1
                    except sqlite3.IntegrityError:
                        skipped += 1
            conn.commit()
        finally:
            conn.close()
        ctx.stage_outputs["raw_db_path"] = str(db_path)
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={
                "inserted": inserted,
                "dedup_skipped": skipped,
                "tx_inserted": tx_inserted,
                "tx_dedup_skipped": tx_skipped,
                "db": str(db_path),
            },
            artifacts=({"type": "raw_events_sqlite", "path": str(db_path)},),
        )


# --- S9 IngestionTelemetry ---------------------------------------------------


class IngestionTelemetry:
    subagent_id = "W38-A1-S9"

    def run(self, ctx: StageContext, *, cfg: IngestionConfig) -> SubagentResult:
        ranges = ctx.stage_outputs.get("block_ranges") or {}
        n_blocks = sum(int(v.get("n", 0)) for v in ranges.values())
        n_receipts = len(ctx.stage_outputs.get("receipts") or [])
        telemetry = {
            "n_blocks": n_blocks,
            "n_receipts": n_receipts,
            "chains": list(cfg.chains),
            "fixture_mode": cfg.fixture_mode,
            "checkpoint_path": ctx.stage_outputs.get("checkpoint_path"),
            "raw_db_path": ctx.stage_outputs.get("raw_db_path"),
            "block_ranges": ranges,
        }
        ctx.stage_outputs["ingestion_telemetry"] = telemetry
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={"n_blocks": n_blocks, "n_receipts": n_receipts},
            artifacts=({"type": "ingestion_telemetry", "data": telemetry},),
        )
