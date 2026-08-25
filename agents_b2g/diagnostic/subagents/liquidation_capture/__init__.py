"""Wave 38 Agent 4 subagents — Liquidation cascade capture (SQLite consumer)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents_b2g.diagnostic.config import DiagnosticConfig
from agents_b2g.diagnostic.liquidation_lib import (
    DEFAULT_RESOLVED_PATH,
    MIN_COVERAGE_LIQ,
    SEL_GET_RESERVES_LIST,
    TOPIC_LIQUIDATION_CALL,
    encode_liquidation_call_log,
    fixture_resolved_pools,
    load_resolved_pools,
    minute_index,
    parse_liquidation_log,
    pools_by_protocol,
)
from agents_b2g.diagnostic.reference_guard import ReferenceArtifactGuard, ensure_live_directory
from agents_b2g.diagnostic.types import StageContext, SubagentResult


@dataclass
class LiquidationConfig:
    fixture_mode: bool = True
    n_bins: int = 128
    window_start_ts: int = 1_700_000_000
    resolved_path: Path = field(default_factory=lambda: DEFAULT_RESOLVED_PATH)
    # Coverage: liquidations event-driven → ≥40% (Bridge coverage_gate)
    min_coverage_days: float = MIN_COVERAGE_LIQ
    min_events: int = 100
    fixture_min_events: int = 8
    fixture_events_per_pool: int = 3


def _liq_dir(ctx: StageContext) -> Path:
    live = Path(ctx.data_root)
    if live.name != "live":
        live = ensure_live_directory(DiagnosticConfig.DATA_ROOT, ctx.user_id)
    out = live / "liquidations"
    out.mkdir(parents=True, exist_ok=True)
    ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT).assert_write_allowed(out)
    return out


def _guard_write(path: Path) -> None:
    ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT).assert_write_allowed(path)


def _load_plan(cfg: LiquidationConfig) -> dict[str, Any]:
    if cfg.fixture_mode:
        return fixture_resolved_pools()
    return load_resolved_pools(cfg.resolved_path)


def _ensure_plan(ctx: StageContext, cfg: LiquidationConfig) -> dict[str, Any]:
    plan = ctx.stage_outputs.get("liq_resolved_plan")
    if plan is None:
        plan = _load_plan(cfg)
        ctx.stage_outputs["liq_resolved_plan"] = plan
    return plan


# --- S1 AaveV3PoolScanner ----------------------------------------------------


class AaveV3PoolScanner:
    """ETH + Gnosis Aave v3 pools from resolver — addresses not hardcoded."""

    subagent_id = "W38-A4-S1"

    def run(self, ctx: StageContext, *, cfg: LiquidationConfig) -> SubagentResult:
        plan = _ensure_plan(ctx, cfg)
        pools = pools_by_protocol(plan, "aave_v3")
        if not pools:
            return SubagentResult(
                subagent_id=self.subagent_id,
                status="failed",
                error="no aave_v3 pools in resolver",
            )
        ctx.stage_outputs["liq_aave_pools"] = pools
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={
                "n_pools": len(pools),
                "chains": sorted({p["chain"] for p in pools}),
                "source": plan.get("path") or "fixture",
            },
            artifacts=({"type": "aave_pools", "count": len(pools)},),
        )


# --- S2 SparkPoolScanner -----------------------------------------------------


class SparkPoolScanner:
    """ETH + Gnosis Spark pools — same scanner logic, distinct addresses."""

    subagent_id = "W38-A4-S2"

    def run(self, ctx: StageContext, *, cfg: LiquidationConfig) -> SubagentResult:
        plan = _ensure_plan(ctx, cfg)
        pools = pools_by_protocol(plan, "spark")
        if not pools:
            return SubagentResult(
                subagent_id=self.subagent_id,
                status="failed",
                error="no spark pools in resolver",
            )
        ctx.stage_outputs["liq_spark_pools"] = pools
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={
                "n_pools": len(pools),
                "chains": sorted({p["chain"] for p in pools}),
                "source": plan.get("path") or "fixture",
            },
            artifacts=({"type": "spark_pools", "count": len(pools)},),
        )


def seed_fixture_liquidation_calls(ctx: StageContext, cfg: LiquidationConfig) -> int:
    """Inject LiquidationCall logs into Agent 1 SQLite for offline tests."""
    db_path = ctx.stage_outputs.get("raw_db_path")
    if not db_path:
        raise FileNotFoundError("raw_db_path missing — run Agent 1 first")
    path = Path(db_path)
    _guard_write(path)
    pools = list(ctx.stage_outputs.get("liq_aave_pools") or []) + list(
        ctx.stage_outputs.get("liq_spark_pools") or []
    )
    if not pools:
        return 0
    conn = sqlite3.connect(str(path))
    inserted = 0
    try:
        for i, pool in enumerate(pools):
            chain = pool["chain"]
            addr = str(pool["pool"]).lower()
            for k in range(cfg.fixture_events_per_pool):
                minute = (i * 5 + k * 13) % cfg.n_bins
                ts = cfg.window_start_ts + minute * 60
                topics, data = encode_liquidation_call_log(
                    collateral="0x1111111111111111111111111111111111111111",
                    debt="0x2222222222222222222222222222222222222222",
                    user="0x3333333333333333333333333333333333333333",
                    debt_to_cover=10**18 * (k + 1),
                    liq_collateral=5 * 10**17 * (k + 1),
                    liquidator="0x4444444444444444444444444444444444444444",
                    receive_atoken=False,
                )
                tx = f"0x{'a' * 56}{i:04x}{k:04x}"
                log_index = k
                payload = {
                    "address": addr,
                    "topics": topics,
                    "data": data,
                    "logIndex": hex(log_index),
                    "transactionHash": tx,
                    "blockNumber": hex(2000 + minute),
                    "blockTime": ts,
                    "protocol": pool["protocol"],
                }
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
                            2000 + minute,
                            addr,
                            TOPIC_LIQUIDATION_CALL,
                            json.dumps(payload),
                        ),
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    pass
        conn.commit()
    finally:
        conn.close()
    return inserted


# --- S3 LiquidationCallParser ------------------------------------------------


class LiquidationCallParser:
    """Topic0 keccak + 7-param decode from Agent 1 SQLite events."""

    subagent_id = "W38-A4-S3"

    def run(self, ctx: StageContext, *, cfg: LiquidationConfig) -> SubagentResult:
        if cfg.fixture_mode:
            n_seed = seed_fixture_liquidation_calls(ctx, cfg)
            ctx.stage_outputs["liq_fixture_seeded"] = n_seed

        db_path = ctx.stage_outputs.get("raw_db_path")
        if not db_path or not Path(db_path).is_file():
            return SubagentResult(
                subagent_id=self.subagent_id,
                status="failed",
                error="Agent 1 SQLite missing — Liquidation is consumer, not RPC client",
            )

        pool_set = {
            (p["chain"], str(p["pool"]).lower())
            for p in (
                list(ctx.stage_outputs.get("liq_aave_pools") or [])
                + list(ctx.stage_outputs.get("liq_spark_pools") or [])
            )
        }
        pool_meta = {
            (p["chain"], str(p["pool"]).lower()): p
            for p in (
                list(ctx.stage_outputs.get("liq_aave_pools") or [])
                + list(ctx.stage_outputs.get("liq_spark_pools") or [])
            )
        }

        events: list[dict[str, Any]] = []
        n_skip_topic = 0
        n_skip_pool = 0
        n_dedup = 0
        seen: set[tuple[str, str, int]] = set()

        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute(
                "SELECT chain, tx, log_index, block_number, address, topic0, payload "
                "FROM events"
            ).fetchall()
        finally:
            conn.close()

        for chain, tx, log_index, block_number, address, topic0, payload_s in rows:
            if str(topic0).lower() != TOPIC_LIQUIDATION_CALL.lower():
                n_skip_topic += 1
                continue
            key = (str(chain), str(tx), int(log_index))
            if key in seen:
                n_dedup += 1
                continue
            seen.add(key)
            addr = str(address or "").lower()
            if (chain, addr) not in pool_set:
                n_skip_pool += 1
                continue
            payload = json.loads(payload_s) if payload_s else {}
            log = {
                "address": addr,
                "topics": payload.get("topics") or [topic0],
                "data": payload.get("data", "0x"),
            }
            try:
                parsed = parse_liquidation_log(log)
            except ValueError:
                n_skip_pool += 1
                continue
            ts = int(payload.get("blockTime") or 0)
            meta = pool_meta[(chain, addr)]
            events.append(
                {
                    "chain": chain,
                    "tx_hash": str(tx),
                    "log_index": int(log_index),
                    "block_number": int(block_number or 0),
                    "pool": addr,
                    "protocol": meta.get("protocol"),
                    "timestamp": ts,
                    "topic0": TOPIC_LIQUIDATION_CALL,
                    **parsed,
                }
            )

        ctx.stage_outputs["liq_events"] = events
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={
                "n_events": len(events),
                "n_skip_topic": n_skip_topic,
                "n_skip_pool": n_skip_pool,
                "n_dedup": n_dedup,
                "topic0": TOPIC_LIQUIDATION_CALL,
                "fixture_seeded": int(ctx.stage_outputs.get("liq_fixture_seeded") or 0),
            },
            artifacts=({"type": "liquidation_events", "count": len(events)},),
        )


# --- S4 ReservesListVerifier -------------------------------------------------


class ReservesListVerifier:
    """Schicht-B: getReservesList() / n_reserves from resolver confirms active pool."""

    subagent_id = "W38-A4-S4"

    def run(self, ctx: StageContext, *, cfg: LiquidationConfig) -> SubagentResult:
        pools = list(ctx.stage_outputs.get("liq_aave_pools") or []) + list(
            ctx.stage_outputs.get("liq_spark_pools") or []
        )
        results: list[dict[str, Any]] = []
        n_fail = 0
        for p in pools:
            n_res = int(p.get("n_reserves") or 0)
            ok = n_res > 0 and p.get("status") == "RESOLVED"
            if not ok:
                n_fail += 1
            results.append(
                {
                    "protocol": p.get("protocol"),
                    "chain": p.get("chain"),
                    "pool": p.get("pool"),
                    "n_reserves": n_res,
                    "selector": SEL_GET_RESERVES_LIST,
                    "ok": ok,
                }
            )
        ctx.stage_outputs["liq_reserves_check"] = results
        if n_fail:
            return SubagentResult(
                subagent_id=self.subagent_id,
                status="failed",
                error=f"reserves check failed for {n_fail} pool(s)",
                metrics={"n_fail": n_fail, "n_pools": len(pools)},
            )
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={
                "n_pools": len(pools),
                "n_fail": 0,
                "selector": SEL_GET_RESERVES_LIST,
            },
            artifacts=({"type": "reserves_check", "results": results},),
        )


# --- S5 PoolAddressRegistry --------------------------------------------------


class PoolAddressRegistry:
    """Address-book consistency vs resolver output."""

    subagent_id = "W38-A4-S5"

    def run(self, ctx: StageContext, *, cfg: LiquidationConfig) -> SubagentResult:
        plan = ctx.stage_outputs.get("liq_resolved_plan") or {}
        expected = {
            (p["protocol"], p["chain"], str(p["pool"]).lower())
            for p in (plan.get("pools") or [])
        }
        scanned = {
            (p["protocol"], p["chain"], str(p["pool"]).lower())
            for p in (
                list(ctx.stage_outputs.get("liq_aave_pools") or [])
                + list(ctx.stage_outputs.get("liq_spark_pools") or [])
            )
        }
        missing = sorted(expected - scanned)
        extra = sorted(scanned - expected)
        ok = not missing and not extra and len(scanned) == 4
        registry = [
            {"protocol": a, "chain": b, "pool": c} for a, b, c in sorted(scanned)
        ]
        ctx.stage_outputs["liq_pool_registry"] = registry
        if not ok:
            return SubagentResult(
                subagent_id=self.subagent_id,
                status="failed",
                error=f"registry mismatch missing={missing} extra={extra}",
                metrics={"n_registry": len(scanned)},
            )
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={"n_registry": len(scanned), "n_expected": len(expected)},
            artifacts=({"type": "pool_registry", "pools": registry},),
        )


# --- S6 CascadeOccupancyBuilder ----------------------------------------------


class CascadeOccupancyBuilder:
    """One occupancy series — OR over Aave+Spark on ETH+Gnosis (not four streams)."""

    subagent_id = "W38-A4-S6"

    def run(self, ctx: StageContext, *, cfg: LiquidationConfig) -> SubagentResult:
        events = ctx.stage_outputs.get("liq_events") or []
        occ = [0] * cfg.n_bins
        n_placed = 0
        by_pool: dict[str, int] = {}
        for ev in events:
            idx = minute_index(int(ev["timestamp"]), cfg.window_start_ts, cfg.n_bins)
            if idx is None:
                continue
            occ[idx] = 1
            n_placed += 1
            key = f"{ev['chain']}:{ev['protocol']}"
            by_pool[key] = by_pool.get(key, 0) + 1
        rate = sum(occ) / cfg.n_bins if cfg.n_bins else 0.0
        ctx.stage_outputs["liq_occupancy"] = occ
        ctx.stage_outputs["liq_occupancy_rate"] = rate
        ctx.stage_outputs["liq_events_by_pool"] = by_pool

        # Sparse JSONL: one line per occupied minute
        out_path = _liq_dir(ctx) / f"liq_occupancy_{ctx.job_id}.jsonl"
        _guard_write(out_path)
        with out_path.open("w", encoding="utf-8") as fh:
            for i, bit in enumerate(occ):
                if not bit:
                    continue
                row = {
                    "chain": "cross",
                    "minute_index": i,
                    "timestamp": cfg.window_start_ts + i * 60,
                    "event": "LiquidationCascadeMinute",
                    "or_pools": True,
                }
                fh.write(json.dumps(row) + "\n")
        ctx.stage_outputs["liq_occupancy_jsonl"] = str(out_path)

        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={
                "n_bins": cfg.n_bins,
                "n_occupied": sum(occ),
                "occupancy_rate": round(rate, 6),
                "n_events_placed": n_placed,
                "or_aggregation": True,
            },
            artifacts=({"type": "liq_occupancy", "path": str(out_path)},),
        )


# --- S7 LiqTelemetry ---------------------------------------------------------


class LiqTelemetry:
    """Pool-specific event counts (Bridge ref ≈ 2_865 in 90d window)."""

    subagent_id = "W38-A4-S7"

    def run(self, ctx: StageContext, *, cfg: LiquidationConfig) -> SubagentResult:
        events = ctx.stage_outputs.get("liq_events") or []
        occ = ctx.stage_outputs.get("liq_occupancy") or []
        by_protocol: dict[str, int] = {}
        by_chain: dict[str, int] = {}
        for ev in events:
            by_protocol[str(ev.get("protocol"))] = (
                by_protocol.get(str(ev.get("protocol")), 0) + 1
            )
            by_chain[ev["chain"]] = by_chain.get(ev["chain"], 0) + 1
        coverage = (sum(occ) / len(occ)) if occ else 0.0
        tele = {
            "n_events": len(events),
            "by_protocol": by_protocol,
            "by_chain": by_chain,
            "by_pool_key": ctx.stage_outputs.get("liq_events_by_pool"),
            "coverage_ratio": round(coverage, 6),
            "occupancy_rate": ctx.stage_outputs.get("liq_occupancy_rate"),
            "min_coverage_days": cfg.min_coverage_days,
            "min_events": cfg.fixture_min_events if cfg.fixture_mode else cfg.min_events,
            "bridge_ref_n_events": 2865,
        }
        ctx.stage_outputs["liq_telemetry"] = tele
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics=dict(tele),
            artifacts=({"type": "liq_telemetry", "data": tele},),
        )


# --- S8 LiqIntegrityChecker --------------------------------------------------


class LiqIntegrityChecker:
    """Window + dedup (chain, tx_hash, log_index); coverage gate ≥40%."""

    subagent_id = "W38-A4-S8"

    def run(self, ctx: StageContext, *, cfg: LiquidationConfig) -> SubagentResult:
        events = ctx.stage_outputs.get("liq_events") or []
        tele = ctx.stage_outputs.get("liq_telemetry") or {}
        min_n = cfg.fixture_min_events if cfg.fixture_mode else cfg.min_events
        keys = [(e["chain"], e["tx_hash"], e["log_index"]) for e in events]
        n_dup = len(keys) - len(set(keys))
        coverage = float(tele.get("coverage_ratio") or 0.0)
        # Live: day coverage (Pre-Reg §4), not minute occupancy rate
        if not cfg.fixture_mode:
            from agents_b2g.diagnostic.liquidation_lib import minute_index as _mi

            days = {
                (int(e["timestamp"]) - cfg.window_start_ts) // 86_400
                for e in events
                if _mi(int(e["timestamp"]), cfg.window_start_ts, cfg.n_bins) is not None
            }
            n_days = max(1, (cfg.n_bins + 1439) // 1440)
            coverage = len(days) / n_days if n_days else 0.0
            tele = {**tele, "day_coverage_ratio": round(coverage, 6)}
            ctx.stage_outputs["liq_telemetry"] = tele
        # Fixture: occupancy rate over bins stands in for day coverage
        min_cov = 0.0 if cfg.fixture_mode else cfg.min_coverage_days
        issues: list[str] = []
        if n_dup:
            issues.append(f"duplicates={n_dup}")
        if len(events) < min_n:
            issues.append(f"n_events={len(events)} < {min_n}")
        if coverage < min_cov:
            issues.append(f"coverage={coverage} < {min_cov}")
        ok = not issues
        ctx.stage_outputs["liq_integrity_ok"] = ok
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok" if ok else "failed",
            error="; ".join(issues) if issues else None,
            metrics={
                "n_events": len(events),
                "n_dup": n_dup,
                "coverage_ratio": coverage,
                "min_coverage_days": cfg.min_coverage_days,
                "dedup_key": "(chain, tx_hash, log_index)",
                "integrity_ok": ok,
            },
            artifacts=({"type": "liq_integrity", "ok": ok},),
        )


# --- S9 LiqStateArchiver -----------------------------------------------------


class LiqStateArchiver:
    """WORM under wave38/live/liquidations/ only; reference_guard active."""

    subagent_id = "W38-A4-S9"

    def run(self, ctx: StageContext, *, cfg: LiquidationConfig) -> SubagentResult:
        out_dir = _liq_dir(ctx)
        occ = ctx.stage_outputs.get("liq_occupancy") or []
        path = out_dir / f"occupancy_{ctx.job_id}.json"
        _guard_write(path)
        body = {
            "candidate_id": "liquidations",
            "job_id": ctx.job_id,
            "n_bins": len(occ),
            "occupancy": occ,
            "occupancy_rate": ctx.stage_outputs.get("liq_occupancy_rate"),
            "telemetry": ctx.stage_outputs.get("liq_telemetry"),
            "pool_registry": ctx.stage_outputs.get("liq_pool_registry"),
            "topic0": TOPIC_LIQUIDATION_CALL,
            "min_coverage_days": cfg.min_coverage_days,
            "fixture_mode": cfg.fixture_mode,
            "or_aggregation": True,
        }
        path.write_text(json.dumps(body), encoding="utf-8")
        ctx.stage_outputs["liq_occupancy_path"] = str(path)

        events_path = out_dir / f"events_{ctx.job_id}.jsonl"
        _guard_write(events_path)
        with events_path.open("w", encoding="utf-8") as fh:
            for ev in ctx.stage_outputs.get("liq_events") or []:
                fh.write(json.dumps(ev) + "\n")
        ctx.stage_outputs["liq_events_path"] = str(events_path)
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={
                "occupancy_path": str(path),
                "events_path": str(events_path),
                "occupancy_jsonl": ctx.stage_outputs.get("liq_occupancy_jsonl"),
            },
            artifacts=(
                {"type": "liq_archive", "path": str(path)},
                {"type": "liq_events_jsonl", "path": str(events_path)},
            ),
        )
