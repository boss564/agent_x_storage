"""Wave 38 Agent 3 subagents — MEV-cluster capture (TX scan, SQLite consumer)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents_b2g.diagnostic.config import DiagnosticConfig
from agents_b2g.diagnostic.ingestion_rpc import FixtureRpcTransport, RpcTransport
from agents_b2g.diagnostic.mev_lib import (
    DEFAULT_EXCLUSION_PATH,
    FIXTURE_CONTRACT,
    fixture_seed_transactions,
    is_eoa_code,
    load_exclusion_list,
    minute_bucket,
    normalize_address,
)
from agents_b2g.diagnostic.reference_guard import ReferenceArtifactGuard, ensure_live_directory
from agents_b2g.diagnostic.types import StageContext, SubagentResult


@dataclass
class MEVConfig:
    fixture_mode: bool = True
    n_bins: int = 128
    window_start_ts: int = 1_700_000_000
    window_end_ts: int | None = None
    exclusion_path: Path = field(default_factory=lambda: DEFAULT_EXCLUSION_PATH)
    # Fixture softens occupancy checks
    fixture_min_occupied: int = 3
    min_occupied_minutes: int = 100
    # Optional transport for eth_getCode only (not a second full capture client)
    rpc_transport: RpcTransport | None = None


def _mev_dir(ctx: StageContext) -> Path:
    live = Path(ctx.data_root)
    if live.name != "live":
        live = ensure_live_directory(DiagnosticConfig.DATA_ROOT, ctx.user_id)
    out = live / "mev"
    out.mkdir(parents=True, exist_ok=True)
    ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT).assert_write_allowed(out)
    return out


def _guard_write(path: Path) -> None:
    ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT).assert_write_allowed(path)


def _ensure_tx_table(conn: sqlite3.Connection) -> None:
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


def seed_fixture_transactions(ctx: StageContext, cfg: MEVConfig) -> int:
    db = ctx.stage_outputs.get("raw_db_path")
    if not db:
        return 0
    rows = fixture_seed_transactions(
        window_start_ts=cfg.window_start_ts,
        n_occupied_minutes=max(cfg.fixture_min_occupied, 5),
    )
    conn = sqlite3.connect(str(db))
    try:
        _ensure_tx_table(conn)
        n = 0
        for r in rows:
            try:
                conn.execute(
                    """
                    INSERT INTO transactions
                    (chain, tx_hash, block_number, timestamp, tx_from, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        r["chain"],
                        r["tx_hash"],
                        r["block_number"],
                        r["timestamp"],
                        normalize_address(r["tx_from"]),
                        int(r["status"]),
                    ),
                )
                n += 1
            except sqlite3.IntegrityError:
                pass
        conn.commit()
    finally:
        conn.close()
    return n


# --- S1 TxFromExtractor ------------------------------------------------------


class TxFromExtractor:
    """Top-level TX parsing from Agent-1 SQLite — status=1 only."""

    subagent_id = "W38-A3-S1"

    def run(self, ctx: StageContext, *, cfg: MEVConfig) -> SubagentResult:
        db = ctx.stage_outputs.get("raw_db_path")
        if not db:
            return SubagentResult(
                subagent_id=self.subagent_id,
                status="failed",
                error="missing raw_db_path",
            )
        if cfg.fixture_mode:
            n_seed = seed_fixture_transactions(ctx, cfg)
            ctx.stage_outputs["mev_fixture_seeded"] = n_seed

        conn = sqlite3.connect(str(db))
        try:
            _ensure_tx_table(conn)
            rows = conn.execute(
                """
                SELECT chain, tx_hash, block_number, timestamp, tx_from, status
                FROM transactions
                WHERE status = 1
                """
            ).fetchall()
        finally:
            conn.close()

        txs: list[dict[str, Any]] = []
        n_failed_skipped = 0
        # Also count failed for metrics
        conn = sqlite3.connect(str(db))
        try:
            n_failed_skipped = int(
                conn.execute(
                    "SELECT COUNT(*) FROM transactions WHERE status != 1"
                ).fetchone()[0]
            )
        finally:
            conn.close()

        for chain, tx_hash, block_number, timestamp, tx_from, status in rows:
            txs.append(
                {
                    "chain": chain,
                    "tx_hash": str(tx_hash),
                    "block_number": int(block_number or 0),
                    "timestamp": int(timestamp or 0),
                    "tx_from": str(tx_from or ""),
                    "status": int(status),
                    "minute": minute_bucket(int(timestamp or 0)),
                }
            )

        ctx.stage_outputs["mev_raw_txs"] = txs
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={
                "n_success_tx": len(txs),
                "n_failed_skipped": n_failed_skipped,
                "fixture_seeded": int(ctx.stage_outputs.get("mev_fixture_seeded") or 0),
            },
            artifacts=({"type": "raw_txs", "count": len(txs)},),
        )


# --- S2 AddressNormalizer ----------------------------------------------------


class AddressNormalizer:
    """Lowercase; strip EIP-55 — consistency across ETH + Gnosis."""

    subagent_id = "W38-A3-S2"

    def run(self, ctx: StageContext, *, cfg: MEVConfig) -> SubagentResult:
        raw = ctx.stage_outputs.get("mev_raw_txs") or []
        out: list[dict[str, Any]] = []
        dropped = 0
        for tx in raw:
            addr = normalize_address(tx.get("tx_from"))
            if not addr:
                dropped += 1
                continue
            row = dict(tx)
            row["tx_from"] = addr
            out.append(row)
        ctx.stage_outputs["mev_normalized_txs"] = out
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={"n_normalized": len(out), "n_dropped_invalid": dropped},
            artifacts=({"type": "normalized_txs", "count": len(out)},),
        )


# --- S3 ExclusionListApplier -------------------------------------------------


class ExclusionListApplier:
    """63 Bridge/Relayer/protocol addresses — pre-registered, not inline in matcher."""

    subagent_id = "W38-A3-S3"

    def run(self, ctx: StageContext, *, cfg: MEVConfig) -> SubagentResult:
        exclusion = load_exclusion_list(cfg.exclusion_path)
        ctx.stage_outputs["mev_exclusion"] = sorted(exclusion)
        kept: list[dict[str, Any]] = []
        dropped: list[str] = []
        for tx in ctx.stage_outputs.get("mev_normalized_txs") or []:
            addr = tx["tx_from"]
            if addr in exclusion:
                dropped.append(addr)
                continue
            kept.append(tx)
        ctx.stage_outputs["mev_filtered_txs"] = kept
        ctx.stage_outputs["mev_exclusion_hits"] = sorted(set(dropped))
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={
                "n_exclusion": len(exclusion),
                "n_kept": len(kept),
                "n_excluded_hits": len(set(dropped)),
            },
            artifacts=({"type": "exclusion", "n": len(exclusion)},),
        )


# --- S4 CrossChainMatcher ----------------------------------------------------


class CrossChainMatcher:
    """Join by t // 60 (same UTC minute), not |Δt| ≤ 60 s."""

    subagent_id = "W38-A3-S4"

    def run(self, ctx: StageContext, *, cfg: MEVConfig) -> SubagentResult:
        eth: set[tuple[str, int]] = set()
        gno: set[tuple[str, int]] = set()
        for tx in ctx.stage_outputs.get("mev_filtered_txs") or []:
            key = (tx["tx_from"], int(tx["minute"]))
            if tx["chain"] == "ethereum":
                eth.add(key)
            elif tx["chain"] == "gnosis":
                gno.add(key)
        pairs = sorted(eth & gno, key=lambda x: (x[1], x[0]))
        ctx.stage_outputs["mev_cross_pairs"] = [
            {"address": a, "minute": m} for a, m in pairs
        ]
        unique_addrs = sorted({a for a, _ in pairs})
        ctx.stage_outputs["mev_cross_addrs"] = unique_addrs
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={
                "n_candidate_pairs": len(pairs),
                "n_unique_addrs": len(unique_addrs),
                "join": "t//60",
            },
            artifacts=({"type": "cross_pairs", "count": len(pairs)},),
        )


# --- S5 EOACodeChecker -------------------------------------------------------


class EOACodeChecker:
    """Two-stage: all tx.from already collected; eth_getCode only on cross-chain addrs."""

    subagent_id = "W38-A3-S5"

    def run(self, ctx: StageContext, *, cfg: MEVConfig) -> SubagentResult:
        addrs = list(ctx.stage_outputs.get("mev_cross_addrs") or [])
        transport = cfg.rpc_transport
        if transport is None and cfg.fixture_mode:
            transport = FixtureRpcTransport(
                contract_code={FIXTURE_CONTRACT: "0x6080604052"}
            )
        if transport is None:
            return SubagentResult(
                subagent_id=self.subagent_id,
                status="failed",
                error="EOACodeChecker requires rpc_transport for eth_getCode",
            )

        eoa_ok: dict[str, bool] = {}
        for addr in addrs:
            try:
                code = transport.eth_get_code("ethereum", addr)
            except Exception:  # noqa: BLE001
                code = transport.eth_get_code("gnosis", addr)
            eoa_ok[addr] = is_eoa_code(code)

        eoa_pairs = [
            p
            for p in (ctx.stage_outputs.get("mev_cross_pairs") or [])
            if eoa_ok.get(p["address"])
        ]
        ctx.stage_outputs["mev_eoa_map"] = eoa_ok
        ctx.stage_outputs["mev_eoa_pairs"] = eoa_pairs
        n_eoa = sum(1 for v in eoa_ok.values() if v)
        n_contract = sum(1 for v in eoa_ok.values() if not v)
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={
                "n_checked": len(addrs),
                "n_eoa": n_eoa,
                "n_contract": n_contract,
                "n_eoa_pairs": len(eoa_pairs),
                "two_stage": True,
            },
            artifacts=({"type": "eoa_filter", "n_eoa": n_eoa},),
        )


# --- S6 MinuteOccupancyBuilder -----------------------------------------------


class MinuteOccupancyBuilder:
    """Sparse JSONL — one line per occupied minute (not dense over full window)."""

    subagent_id = "W38-A3-S6"

    def run(self, ctx: StageContext, *, cfg: MEVConfig) -> SubagentResult:
        occupied: dict[int, list[str]] = {}
        for p in ctx.stage_outputs.get("mev_eoa_pairs") or []:
            m = int(p["minute"])
            occupied.setdefault(m, []).append(p["address"])

        # Dense reference length for rate (Bridge: 129_600); fixture uses n_bins
        if cfg.window_end_ts is not None:
            n_window = max(
                1,
                minute_bucket(cfg.window_end_ts)
                - minute_bucket(cfg.window_start_ts)
                + 1,
            )
        else:
            n_window = max(cfg.n_bins, 1)

        out_path = _mev_dir(ctx) / f"mev_occupancy_{ctx.job_id}.jsonl"
        _guard_write(out_path)
        with out_path.open("w", encoding="utf-8") as fh:
            for minute in sorted(occupied):
                eoas = sorted(set(occupied[minute]))
                row = {
                    "chain": "cross",
                    "minute": minute,
                    "timestamp": minute * 60,
                    "n_eoas": len(eoas),
                    "eoas": eoas[:20],
                    "event": "CrossChainEoaMinute",
                }
                fh.write(json.dumps(row) + "\n")

        # Sparse vector for downstream (1 = occupied minute index relative to window)
        base = minute_bucket(cfg.window_start_ts)
        dense = [0] * n_window
        for m in occupied:
            idx = m - base
            if 0 <= idx < n_window:
                dense[idx] = 1

        rate = sum(dense) / n_window if n_window else 0.0
        ctx.stage_outputs["mev_occupancy_jsonl"] = str(out_path)
        ctx.stage_outputs["mev_occupancy"] = dense
        ctx.stage_outputs["mev_occupancy_rate"] = rate
        ctx.stage_outputs["mev_occupied_minutes"] = sorted(occupied.keys())
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={
                "n_occupied_minutes": len(occupied),
                "n_window_minutes": n_window,
                "sparse": True,
                "occupancy_rate": rate,
            },
            artifacts=({"type": "occupancy_jsonl", "path": str(out_path)},),
        )


# --- S7 MEVTelemetry ---------------------------------------------------------


class MEVTelemetry:
    """Cross-chain EOA count + occupancy rate (Bridge ref: 2_587 EOAs / 74_237 min)."""

    subagent_id = "W38-A3-S7"

    def run(self, ctx: StageContext, *, cfg: MEVConfig) -> SubagentResult:
        eoa_map = ctx.stage_outputs.get("mev_eoa_map") or {}
        cross_eoas = sorted(a for a, ok in eoa_map.items() if ok)
        telemetry = {
            "n_cross_chain_eoas": len(cross_eoas),
            "n_occupied_minutes": len(ctx.stage_outputs.get("mev_occupied_minutes") or []),
            "occupancy_rate": ctx.stage_outputs.get("mev_occupancy_rate"),
            "n_exclusion": len(ctx.stage_outputs.get("mev_exclusion") or []),
            "n_exclusion_hits": len(ctx.stage_outputs.get("mev_exclusion_hits") or []),
            "fixture_mode": cfg.fixture_mode,
            "join": "t//60",
        }
        ctx.stage_outputs["mev_telemetry"] = telemetry
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics=dict(telemetry),
            artifacts=({"type": "mev_telemetry", "data": telemetry},),
        )


# --- S8 MEVIntegrityChecker --------------------------------------------------


class MEVIntegrityChecker:
    """Window + dedup validation; dedup key (chain, tx_hash) — top-level TXs have no log_index."""

    subagent_id = "W38-A3-S8"

    def run(self, ctx: StageContext, *, cfg: MEVConfig) -> SubagentResult:
        txs = ctx.stage_outputs.get("mev_normalized_txs") or []
        keys = [(t["chain"], t["tx_hash"]) for t in txs]
        n_dup = len(keys) - len(set(keys))
        occupied = ctx.stage_outputs.get("mev_occupied_minutes") or []
        min_occ = (
            cfg.fixture_min_occupied if cfg.fixture_mode else cfg.min_occupied_minutes
        )
        ok = n_dup == 0 and len(occupied) >= min_occ
        issues: list[str] = []
        if n_dup:
            issues.append(f"duplicate_tx_keys={n_dup}")
        if len(occupied) < min_occ:
            issues.append(f"occupied={len(occupied)} < min={min_occ}")
        # Exclusion must have removed fixture bridge address when present
        hits = set(ctx.stage_outputs.get("mev_exclusion_hits") or [])
        excl = set(ctx.stage_outputs.get("mev_exclusion") or [])
        if cfg.fixture_mode and hits and not hits.issubset(excl):
            issues.append("exclusion_hit_not_in_list")
            ok = False
        ctx.stage_outputs["mev_integrity_ok"] = ok
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok" if ok else "failed",
            error="; ".join(issues) if issues else None,
            metrics={
                "n_dup": n_dup,
                "n_occupied": len(occupied),
                "integrity_ok": ok,
                "dedup_key": "(chain, tx_hash)",
            },
            artifacts=({"type": "integrity", "ok": ok},),
        )


# --- S9 MEVStateArchiver -----------------------------------------------------


class MEVStateArchiver:
    """WORM archive under wave38/live/mev/ only; reference_guard active."""

    subagent_id = "W38-A3-S9"

    def run(self, ctx: StageContext, *, cfg: MEVConfig) -> SubagentResult:
        out_dir = _mev_dir(ctx)
        occ = ctx.stage_outputs.get("mev_occupancy") or []
        path = out_dir / f"occupancy_{ctx.job_id}.json"
        _guard_write(path)
        body = {
            "candidate_id": "mev_cluster",
            "job_id": ctx.job_id,
            "n_bins": len(occ),
            "occupancy": occ,
            "occupancy_rate": ctx.stage_outputs.get("mev_occupancy_rate"),
            "telemetry": ctx.stage_outputs.get("mev_telemetry"),
            "exclusion_n": len(ctx.stage_outputs.get("mev_exclusion") or []),
            "exclusion_hits": ctx.stage_outputs.get("mev_exclusion_hits"),
            "integrity_ok": ctx.stage_outputs.get("mev_integrity_ok"),
            "join": "t//60",
            "fixture_mode": cfg.fixture_mode,
        }
        path.write_text(json.dumps(body), encoding="utf-8")
        ctx.stage_outputs["mev_occupancy_path"] = str(path)
        ctx.stage_outputs["mev_archive_path"] = str(path)
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={
                "archive": str(path),
                "occupancy_path": str(path),
                "occupancy_jsonl": ctx.stage_outputs.get("mev_occupancy_jsonl"),
            },
            artifacts=({"type": "mev_archive", "path": str(path)},),
        )
