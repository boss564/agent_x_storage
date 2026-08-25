"""Wave 38 Agent 5 subagents — Intent + Stablecoin capture (SQLite consumer)."""

from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents_b2g.diagnostic.config import DiagnosticConfig
from agents_b2g.diagnostic.intent_stable_lib import (
    DEFAULT_INTENT_RESOLVED,
    DEFAULT_STABLE_RESOLVED,
    EVENT_NAME,
    MIN_COVERAGE_INTENT_STABLE,
    TOPIC_BY_EVENT,
    contracts_by_protocol,
    event_key_for_topic,
    family_for_protocol,
    fixture_intent_resolved,
    fixture_stable_resolved,
    load_intent_resolved,
    load_stable_resolved,
    minute_index,
    topic_for,
)
from agents_b2g.diagnostic.reference_guard import ReferenceArtifactGuard, ensure_live_directory
from agents_b2g.diagnostic.types import StageContext, SubagentResult


@dataclass
class IntentStableConfig:
    fixture_mode: bool = True
    n_bins: int = 128
    window_start_ts: int = 1_700_000_000
    intent_resolved_path: Path = field(default_factory=lambda: DEFAULT_INTENT_RESOLVED)
    stable_resolved_path: Path = field(default_factory=lambda: DEFAULT_STABLE_RESOLVED)
    min_coverage_days: float = MIN_COVERAGE_INTENT_STABLE
    min_events: int = 100
    fixture_min_events: int = 8
    fixture_events_per_contract: int = 2


def _is_dir(ctx: StageContext) -> Path:
    live = Path(ctx.data_root)
    if live.name != "live":
        live = ensure_live_directory(DiagnosticConfig.DATA_ROOT, ctx.user_id)
    out = live / "intent_stablecoin"
    out.mkdir(parents=True, exist_ok=True)
    ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT).assert_write_allowed(out)
    return out


def _guard_write(path: Path) -> None:
    ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT).assert_write_allowed(path)


def _ensure_plans(ctx: StageContext, cfg: IntentStableConfig) -> None:
    if "intent_resolved_plan" not in ctx.stage_outputs:
        ctx.stage_outputs["intent_resolved_plan"] = (
            fixture_intent_resolved()
            if cfg.fixture_mode
            else load_intent_resolved(cfg.intent_resolved_path)
        )
    if "stable_resolved_plan" not in ctx.stage_outputs:
        ctx.stage_outputs["stable_resolved_plan"] = (
            fixture_stable_resolved()
            if cfg.fixture_mode
            else load_stable_resolved(cfg.stable_resolved_path)
        )


def _register_contracts(
    ctx: StageContext,
    contracts: list[dict[str, Any]],
    *,
    scanner: str,
) -> list[dict[str, Any]]:
    """Append scanner contracts into the shared capture registry."""
    registry: list[dict[str, Any]] = list(
        ctx.stage_outputs.get("intent_stable_registry") or []
    )
    for c in contracts:
        entry = {
            "scanner": scanner,
            "protocol": c["protocol"],
            "chain": c["chain"],
            "address": str(c["address"]).lower(),
            "events": list(c.get("events") or []),
            "topics": [topic_for(e) for e in (c.get("events") or []) if e in TOPIC_BY_EVENT],
            "family": family_for_protocol(str(c["protocol"])),
            "role": c.get("role"),
        }
        registry.append(entry)
    ctx.stage_outputs["intent_stable_registry"] = registry
    return registry


def _scan_protocol(
    ctx: StageContext,
    cfg: IntentStableConfig,
    *,
    subagent_id: str,
    scanner: str,
    protocol: str,
    plan_key: str,
    require_chain: str | None = None,
    allow_empty_events: bool = False,
) -> SubagentResult:
    _ensure_plans(ctx, cfg)
    plan = ctx.stage_outputs[plan_key]
    contracts = contracts_by_protocol(plan, protocol)
    if require_chain:
        contracts = [c for c in contracts if c.get("chain") == require_chain]
    if not contracts:
        return SubagentResult(
            subagent_id=subagent_id,
            status="failed",
            error=f"no {protocol} contracts in resolver"
            + (f" (chain={require_chain})" if require_chain else ""),
        )
    # Gnosis Across must never appear
    if protocol == "across" and any(c.get("chain") == "gnosis" for c in contracts):
        return SubagentResult(
            subagent_id=subagent_id,
            status="failed",
            error="Across on gnosis is excluded — resolver leak",
        )
    _register_contracts(ctx, contracts, scanner=scanner)
    ctx.stage_outputs[f"is_{scanner}_contracts"] = contracts
    return SubagentResult(
        subagent_id=subagent_id,
        status="ok",
        metrics={
            "n_contracts": len(contracts),
            "protocol": protocol,
            "chains": sorted({c["chain"] for c in contracts}),
            "n_topics": sum(len(c.get("events") or []) for c in contracts),
            "allow_empty_events": allow_empty_events,
            "source": plan.get("path") or "fixture",
        },
        artifacts=({"type": f"{scanner}_contracts", "count": len(contracts)},),
    )


# --- S1 AcrossSpokePoolScanner -----------------------------------------------


class AcrossSpokePoolScanner:
    """ETH SpokePool only — FilledRelay + FilledV3Relay (migration-safe)."""

    subagent_id = "W38-A5-S1"

    def run(self, ctx: StageContext, *, cfg: IntentStableConfig) -> SubagentResult:
        return _scan_protocol(
            ctx,
            cfg,
            subagent_id=self.subagent_id,
            scanner="across",
            protocol="across",
            plan_key="intent_resolved_plan",
            require_chain="ethereum",
            allow_empty_events=True,  # FilledV3Relay may be 0 in window
        )


# --- S2 CoWTradeScanner ------------------------------------------------------


class CoWTradeScanner:
    """ETH + Gnosis GPv2Settlement — Trade 7-param signature."""

    subagent_id = "W38-A5-S2"

    def run(self, ctx: StageContext, *, cfg: IntentStableConfig) -> SubagentResult:
        return _scan_protocol(
            ctx,
            cfg,
            subagent_id=self.subagent_id,
            scanner="cow",
            protocol="cow",
            plan_key="intent_resolved_plan",
        )


# --- S3 LitePSMScanner -------------------------------------------------------


class LitePSMScanner:
    """ETH LitePSM — BuyGem/SellGem 3-param (corrected)."""

    subagent_id = "W38-A5-S3"

    def run(self, ctx: StageContext, *, cfg: IntentStableConfig) -> SubagentResult:
        return _scan_protocol(
            ctx,
            cfg,
            subagent_id=self.subagent_id,
            scanner="lite_psm",
            protocol="lite_psm",
            plan_key="stable_resolved_plan",
            require_chain="ethereum",
        )


# --- S4 ClassicPSMScanner ----------------------------------------------------


class ClassicPSMScanner:
    """ETH Classic PSM — legacy migration shield (may have 0 events)."""

    subagent_id = "W38-A5-S4"

    def run(self, ctx: StageContext, *, cfg: IntentStableConfig) -> SubagentResult:
        return _scan_protocol(
            ctx,
            cfg,
            subagent_id=self.subagent_id,
            scanner="classic_psm",
            protocol="classic_psm",
            plan_key="stable_resolved_plan",
            require_chain="ethereum",
            allow_empty_events=True,
        )


# --- S5 CCTPV1Scanner --------------------------------------------------------


class CCTPV1Scanner:
    """ETH CCTP V1 TokenMessenger — DepositForBurn + MintAndWithdraw."""

    subagent_id = "W38-A5-S5"

    def run(self, ctx: StageContext, *, cfg: IntentStableConfig) -> SubagentResult:
        return _scan_protocol(
            ctx,
            cfg,
            subagent_id=self.subagent_id,
            scanner="cctp_v1",
            protocol="cctp_v1",
            plan_key="stable_resolved_plan",
            require_chain="ethereum",
        )


# --- S6 CCTPV2Scanner --------------------------------------------------------


class CCTPV2Scanner:
    """ETH CCTP V2 — MintAndWithdraw includes feeCollected."""

    subagent_id = "W38-A5-S6"

    def run(self, ctx: StageContext, *, cfg: IntentStableConfig) -> SubagentResult:
        return _scan_protocol(
            ctx,
            cfg,
            subagent_id=self.subagent_id,
            scanner="cctp_v2",
            protocol="cctp_v2",
            plan_key="stable_resolved_plan",
            require_chain="ethereum",
        )


def seed_fixture_intent_stable_events(ctx: StageContext, cfg: IntentStableConfig) -> int:
    """Seed one+ event per registered contract into Agent 1 SQLite."""
    db_path = ctx.stage_outputs.get("raw_db_path")
    if not db_path:
        raise FileNotFoundError("raw_db_path missing — run Agent 1 first")
    path = Path(db_path)
    _guard_write(path)
    registry = ctx.stage_outputs.get("intent_stable_registry") or []
    if not registry:
        return 0
    conn = sqlite3.connect(str(path))
    inserted = 0
    try:
        for i, entry in enumerate(registry):
            chain = entry["chain"]
            addr = entry["address"]
            events = entry.get("events") or []
            if not events:
                continue
            # Prefer primary topic; also seed legacy Across V3 if listed
            for k, event_key in enumerate(events[: cfg.fixture_events_per_contract]):
                if event_key not in TOPIC_BY_EVENT:
                    continue
                topic0 = topic_for(event_key)
                minute = (i * 3 + k * 7) % cfg.n_bins
                ts = cfg.window_start_ts + minute * 60
                tx = f"0x{'b' * 52}{i:04x}{k:04x}"
                log_index = k
                payload = {
                    "address": addr,
                    "topics": [topic0],
                    "data": "0x" + ("00" * 64),
                    "logIndex": hex(log_index),
                    "transactionHash": tx,
                    "blockNumber": hex(3000 + minute),
                    "blockTime": ts,
                    "protocol": entry["protocol"],
                    "event_key": event_key,
                    "event": EVENT_NAME.get(event_key, event_key),
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
                            3000 + minute,
                            addr,
                            topic0,
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


# --- S7 IntentStableOccupancyBuilder -----------------------------------------


class IntentStableOccupancyBuilder:
    """OR over all 6 protocol families → one occupancy series."""

    subagent_id = "W38-A5-S7"

    def run(self, ctx: StageContext, *, cfg: IntentStableConfig) -> SubagentResult:
        db_path = ctx.stage_outputs.get("raw_db_path")
        if not db_path or not Path(db_path).is_file():
            return SubagentResult(
                subagent_id=self.subagent_id,
                status="failed",
                error="Agent 1 SQLite missing — IntentStable is consumer, not RPC client",
            )

        if cfg.fixture_mode:
            n_seed = seed_fixture_intent_stable_events(ctx, cfg)
            ctx.stage_outputs["intent_stable_fixture_seeded"] = n_seed

        registry = ctx.stage_outputs.get("intent_stable_registry") or []
        allow: set[tuple[str, str, str]] = set()
        addr_meta: dict[tuple[str, str], dict[str, Any]] = {}
        for e in registry:
            addr_meta[(e["chain"], e["address"])] = e
            for t in e.get("topics") or []:
                allow.add((e["chain"], e["address"], t.lower()))

        events: list[dict[str, Any]] = []
        n_skip = 0
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
            addr = str(address or "").lower()
            t0 = str(topic0 or "").lower()
            if (chain, addr, t0) not in allow:
                n_skip += 1
                continue
            key = (str(chain), str(tx), int(log_index))
            if key in seen:
                n_dedup += 1
                continue
            seen.add(key)
            payload = json.loads(payload_s) if payload_s else {}
            meta = addr_meta[(chain, addr)]
            ek = event_key_for_topic(t0) or payload.get("event_key")
            events.append(
                {
                    "chain": chain,
                    "tx_hash": str(tx),
                    "log_index": int(log_index),
                    "block_number": int(block_number or 0),
                    "address": addr,
                    "protocol": meta["protocol"],
                    "scanner": meta["scanner"],
                    "family": meta["family"],
                    "event_key": ek,
                    "event": EVENT_NAME.get(str(ek), str(ek)),
                    "timestamp": int(payload.get("blockTime") or 0),
                    "topic0": t0,
                }
            )

        occ = [0] * cfg.n_bins
        per_minute_counts = [0] * cfg.n_bins
        n_placed = 0
        for ev in events:
            idx = minute_index(int(ev["timestamp"]), cfg.window_start_ts, cfg.n_bins)
            if idx is None:
                continue
            occ[idx] = 1
            per_minute_counts[idx] += 1
            n_placed += 1

        rate = sum(occ) / cfg.n_bins if cfg.n_bins else 0.0
        # Tertile dispersion + std for Agent 8 informativity / INERT_ENCODING hint
        occupied_counts = [c for c, bit in zip(per_minute_counts, occ) if bit]
        if occupied_counts:
            mean = sum(occupied_counts) / len(occupied_counts)
            var = sum((c - mean) ** 2 for c in occupied_counts) / len(occupied_counts)
            events_per_minute_std = math.sqrt(var)
        else:
            events_per_minute_std = 0.0

        ctx.stage_outputs["intent_stable_events"] = events
        ctx.stage_outputs["intent_stable_occupancy"] = occ
        ctx.stage_outputs["intent_stable_occupancy_rate"] = rate
        ctx.stage_outputs["intent_stable_per_minute_counts"] = per_minute_counts
        ctx.stage_outputs["intent_stable_events_per_minute_std"] = events_per_minute_std

        out_path = _is_dir(ctx) / f"occupancy_{ctx.job_id}.jsonl"
        _guard_write(out_path)
        with out_path.open("w", encoding="utf-8") as fh:
            for i, bit in enumerate(occ):
                if not bit:
                    continue
                fh.write(
                    json.dumps(
                        {
                            "chain": "cross",
                            "minute_index": i,
                            "timestamp": cfg.window_start_ts + i * 60,
                            "event": "IntentStableORMinute",
                            "or_protocols": True,
                            "n_events": per_minute_counts[i],
                        }
                    )
                    + "\n"
                )
        ctx.stage_outputs["intent_stable_occupancy_jsonl"] = str(out_path)

        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={
                "n_events": len(events),
                "n_occupied": sum(occ),
                "occupancy_rate": round(rate, 6),
                "n_skip": n_skip,
                "n_dedup": n_dedup,
                "or_aggregation": True,
                "n_scanners": len({e["scanner"] for e in registry}),
                "events_per_minute_std": round(events_per_minute_std, 6),
                "fixture_seeded": int(
                    ctx.stage_outputs.get("intent_stable_fixture_seeded") or 0
                ),
            },
            artifacts=({"type": "intent_stable_occupancy", "path": str(out_path)},),
        )


# --- S8 IntentStableTelemetry ------------------------------------------------


class IntentStableTelemetry:
    """Per-protocol counts + informativity hints (Bridge refs ≈ Across 332k …)."""

    subagent_id = "W38-A5-S8"

    def run(self, ctx: StageContext, *, cfg: IntentStableConfig) -> SubagentResult:
        events = ctx.stage_outputs.get("intent_stable_events") or []
        occ = ctx.stage_outputs.get("intent_stable_occupancy") or []
        by_protocol: dict[str, int] = defaultdict(int)
        by_family: dict[str, int] = defaultdict(int)
        by_scanner: dict[str, int] = defaultdict(int)
        by_event: dict[str, int] = defaultdict(int)
        for ev in events:
            by_protocol[str(ev.get("protocol"))] += 1
            by_family[str(ev.get("family"))] += 1
            by_scanner[str(ev.get("scanner"))] += 1
            by_event[str(ev.get("event_key"))] += 1
        coverage = (sum(occ) / len(occ)) if occ else 0.0
        std = float(ctx.stage_outputs.get("intent_stable_events_per_minute_std") or 0.0)
        sat = coverage >= 0.90
        inert_hint = sat and std > 0.0
        tele = {
            "n_events": len(events),
            "by_protocol": dict(by_protocol),
            "by_family": dict(by_family),
            "by_scanner": dict(by_scanner),
            "by_event_key": dict(by_event),
            "coverage_ratio": round(coverage, 6),
            "occupancy_rate": ctx.stage_outputs.get("intent_stable_occupancy_rate"),
            "events_per_minute_std": round(std, 6),
            "occupancy_saturated": sat,
            "inert_encoding_hint": inert_hint,
            "min_coverage_days": cfg.min_coverage_days,
            "min_events": cfg.fixture_min_events if cfg.fixture_mode else cfg.min_events,
            "bridge_ref": {
                "intent_events": 746_000,
                "stablecoin_events": 530_000,
                "across": 332_000,
                "cow": 414_000,
                "psm": 251_000,
                "cctp": 279_000,
            },
            "n_registry": len(ctx.stage_outputs.get("intent_stable_registry") or []),
        }
        ctx.stage_outputs["intent_stable_telemetry"] = tele

        # Soft integrity gates (hard fail only on empty / dups handled in builder metrics)
        min_n = cfg.fixture_min_events if cfg.fixture_mode else cfg.min_events
        issues: list[str] = []
        if len(events) < min_n:
            issues.append(f"n_events={len(events)} < {min_n}")
        scanners = {e["scanner"] for e in (ctx.stage_outputs.get("intent_stable_registry") or [])}
        if len(scanners) < 6:
            issues.append(f"n_scanners={len(scanners)} < 6")
        if issues:
            return SubagentResult(
                subagent_id=self.subagent_id,
                status="failed",
                error="; ".join(issues),
                metrics=dict(tele),
            )
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics=dict(tele),
            artifacts=({"type": "intent_stable_telemetry", "data": tele},),
        )


# --- S9 IntentStableArchiver -------------------------------------------------


class IntentStableArchiver:
    """WORM under wave38/live/intent_stablecoin/; reference_guard active."""

    subagent_id = "W38-A5-S9"

    def run(self, ctx: StageContext, *, cfg: IntentStableConfig) -> SubagentResult:
        out_dir = _is_dir(ctx)
        occ = ctx.stage_outputs.get("intent_stable_occupancy") or []
        path = out_dir / f"occupancy_{ctx.job_id}.json"
        _guard_write(path)
        body = {
            "candidate_id": "intent_stablecoin",
            "families": ["intent_relayers", "stablecoin_mint_burn"],
            "job_id": ctx.job_id,
            "n_bins": len(occ),
            "occupancy": occ,
            "occupancy_rate": ctx.stage_outputs.get("intent_stable_occupancy_rate"),
            "telemetry": ctx.stage_outputs.get("intent_stable_telemetry"),
            "registry": ctx.stage_outputs.get("intent_stable_registry"),
            "topics": TOPIC_BY_EVENT,
            "min_coverage_days": cfg.min_coverage_days,
            "fixture_mode": cfg.fixture_mode,
            "or_aggregation": True,
        }
        path.write_text(json.dumps(body), encoding="utf-8")
        ctx.stage_outputs["intent_stable_occupancy_path"] = str(path)

        events_path = out_dir / f"events_{ctx.job_id}.jsonl"
        _guard_write(events_path)
        with events_path.open("w", encoding="utf-8") as fh:
            for ev in ctx.stage_outputs.get("intent_stable_events") or []:
                fh.write(json.dumps(ev) + "\n")
        ctx.stage_outputs["intent_stable_events_path"] = str(events_path)
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={
                "occupancy_path": str(path),
                "events_path": str(events_path),
                "occupancy_jsonl": ctx.stage_outputs.get("intent_stable_occupancy_jsonl"),
            },
            artifacts=(
                {"type": "intent_stable_archive", "path": str(path)},
                {"type": "intent_stable_events_jsonl", "path": str(events_path)},
            ),
        )
