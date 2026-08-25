"""Wave 38 Agent 2 subagents — Oracle / Chainlink capture (SQLite consumer)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents_b2g.diagnostic.config import DiagnosticConfig
from agents_b2g.diagnostic.oracle_lib import (
    EXCLUDED_FEEDS,
    TOPIC_ANSWER_UPDATED,
    encode_answer_updated_topics,
    fixture_resolved_plan,
    is_excluded_feed,
    minute_index,
    parse_answer_updated_log,
    plausibility_check,
)
from agents_b2g.diagnostic.reference_guard import ReferenceArtifactGuard, ensure_live_directory
from agents_b2g.diagnostic.types import StageContext, SubagentResult


@dataclass
class OracleConfig:
    fixture_mode: bool = True
    n_bins: int = 128
    window_start_ts: int = 1_700_000_000
    # Coverage thresholds (telemetry / integrity — Bridge reference ≥80% / N≥100)
    min_coverage_days: float = 0.80
    min_events: int = 100
    # Fixture softens N for unit tests
    fixture_min_events: int = 10
    # Live address-book USD quotes may be stale — warn, do not hard-fail
    soft_plausibility: bool = False


def _oracle_dir(ctx: StageContext) -> Path:
    live = Path(ctx.data_root)
    if live.name != "live":
        live = ensure_live_directory(DiagnosticConfig.DATA_ROOT, ctx.user_id)
    out = live / "oracle"
    out.mkdir(parents=True, exist_ok=True)
    ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT).assert_write_allowed(out)
    return out


def _guard_write(path: Path) -> None:
    ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT).assert_write_allowed(path)


# --- S1 ChainlinkProxyResolver -----------------------------------------------


class ChainlinkProxyResolver:
    """AnswerUpdated comes from aggregator, not proxy — resolve aggregator()."""

    subagent_id = "W38-A2-S1"

    def run(self, ctx: StageContext, *, cfg: OracleConfig) -> SubagentResult:
        if cfg.fixture_mode:
            plan = fixture_resolved_plan()
        else:
            # Live: load pre-resolved plan from live/oracle (written by ops) —
            # Agent 2 does not open a second RPC client (consumes Agent 1 + plan).
            plan_path = _oracle_dir(ctx) / "chainlink_resolved.json"
            if not plan_path.is_file():
                return SubagentResult(
                    subagent_id=self.subagent_id,
                    status="failed",
                    error=f"missing resolved plan: {plan_path}",
                )
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            if not plan.get("all_resolved"):
                return SubagentResult(
                    subagent_id=self.subagent_id,
                    status="failed",
                    error="resolved plan not all_resolved",
                )

        proxy_map: dict[str, list[dict[str, Any]]] = {}
        n_aggs = 0
        for chain, cfg_chain in (plan.get("chains") or {}).items():
            rows = []
            for feed in cfg_chain.get("feeds") or []:
                if feed.get("status") != "RESOLVED":
                    continue
                aggs = [a.lower() for a in feed.get("active_aggregators") or []]
                n_aggs += len(aggs)
                rows.append(
                    {
                        "name": feed["name"],
                        "proxy": str(feed.get("proxy", "")).lower(),
                        "current_aggregator": str(
                            feed.get("current_aggregator", "")
                        ).lower(),
                        "active_aggregators": aggs,
                        "latest_answer_usd": feed.get("latest_answer_usd"),
                    }
                )
            proxy_map[chain] = rows

        ctx.stage_outputs["oracle_resolved_plan"] = plan
        ctx.stage_outputs["oracle_proxy_map"] = proxy_map
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={"n_chains": len(proxy_map), "n_aggregators": n_aggs},
            artifacts=({"type": "proxy_map", "data": proxy_map},),
        )


# --- S2 AggregatorPhaseTracker -----------------------------------------------


class AggregatorPhaseTracker:
    """All active aggregators across phases must be in the capture set."""

    subagent_id = "W38-A2-S2"

    def run(self, ctx: StageContext, *, cfg: OracleConfig) -> SubagentResult:
        plan = ctx.stage_outputs.get("oracle_resolved_plan") or {}
        phase_hist: dict[str, dict[str, Any]] = {}
        capture_set: set[tuple[str, str]] = set()
        for chain, cfg_chain in (plan.get("chains") or {}).items():
            for feed in cfg_chain.get("feeds") or []:
                name = feed.get("name", "")
                phases = feed.get("phases") or {}
                phase_hist[f"{chain}:{name}"] = {
                    "n_phases": len(phases),
                    "phases": phases,
                    "active_aggregators": feed.get("active_aggregators") or [],
                }
                for agg in feed.get("active_aggregators") or []:
                    capture_set.add((chain, agg.lower()))

        ctx.stage_outputs["oracle_phase_history"] = phase_hist
        ctx.stage_outputs["oracle_capture_aggregators"] = sorted(
            [{"chain": c, "aggregator": a} for c, a in capture_set],
            key=lambda r: (r["chain"], r["aggregator"]),
        )
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={
                "n_feeds_tracked": len(phase_hist),
                "n_capture_aggregators": len(capture_set),
            },
            artifacts=({"type": "phase_history", "count": len(phase_hist)},),
        )


# --- S6 FeedExclusionEnforcer (before parse/occupancy) -----------------------


class FeedExclusionEnforcer:
    """Hard block USDT/USD Ethereum + GNO/ETH — documented exclusions."""

    subagent_id = "W38-A2-S6"

    def run(self, ctx: StageContext, *, cfg: OracleConfig) -> SubagentResult:
        plan = ctx.stage_outputs.get("oracle_resolved_plan") or {}
        kept: list[dict[str, Any]] = []
        dropped: list[dict[str, str]] = []
        for chain, cfg_chain in (plan.get("chains") or {}).items():
            for feed in cfg_chain.get("feeds") or []:
                name = feed.get("name", "")
                if is_excluded_feed(chain, name):
                    dropped.append({"chain": chain, "feed": name, "reason": "EXCLUDED"})
                    continue
                for agg in feed.get("active_aggregators") or []:
                    kept.append(
                        {
                            "chain": chain,
                            "feed": name,
                            "aggregator": agg.lower(),
                        }
                    )

        # Rebuild capture set without exclusions
        ctx.stage_outputs["oracle_allowed_feeds"] = kept
        ctx.stage_outputs["oracle_excluded_feeds"] = dropped
        ctx.stage_outputs["oracle_capture_aggregators"] = sorted(
            [{"chain": r["chain"], "aggregator": r["aggregator"]} for r in kept],
            key=lambda r: (r["chain"], r["aggregator"]),
        )
        # agg → feed labels for OR builder
        agg_feeds: dict[tuple[str, str], list[str]] = {}
        for r in kept:
            key = (r["chain"], r["aggregator"])
            agg_feeds.setdefault(key, [])
            if r["feed"] not in agg_feeds[key]:
                agg_feeds[key].append(r["feed"])
        ctx.stage_outputs["oracle_agg_feeds"] = {
            f"{c}|{a}": feeds for (c, a), feeds in agg_feeds.items()
        }
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={
                "n_allowed": len(kept),
                "n_excluded": len(dropped),
                "excluded": [f"{d['chain']}:{d['feed']}" for d in dropped],
            },
            artifacts=(
                {
                    "type": "feed_exclusions",
                    "excluded": list(EXCLUDED_FEEDS),
                    "dropped": dropped,
                },
            ),
        )


# --- S4 FeedPlausibilityGate -------------------------------------------------


class FeedPlausibilityGate:
    """latestRoundData band-check — wrong feed / right proxy-type protection."""

    subagent_id = "W38-A2-S4"

    def run(self, ctx: StageContext, *, cfg: OracleConfig) -> SubagentResult:
        plan = ctx.stage_outputs.get("oracle_resolved_plan") or {}
        excluded = {(d["chain"], d["feed"]) for d in (ctx.stage_outputs.get("oracle_excluded_feeds") or [])}
        results: list[dict[str, Any]] = []
        n_fail = 0
        for chain, cfg_chain in (plan.get("chains") or {}).items():
            for feed in cfg_chain.get("feeds") or []:
                name = feed.get("name", "")
                if (chain, name) in excluded:
                    continue
                usd = float(feed.get("latest_answer_usd") or 0.0)
                status, reason = plausibility_check(name, usd)
                results.append(
                    {
                        "chain": chain,
                        "feed": name,
                        "usd": usd,
                        "status": status,
                        "reason": reason,
                    }
                )
                if status != "pass":
                    n_fail += 1
        ctx.stage_outputs["oracle_plausibility"] = results
        if n_fail and not cfg.fixture_mode and not cfg.soft_plausibility:
            return SubagentResult(
                subagent_id=self.subagent_id,
                status="failed",
                error=f"plausibility failed for {n_fail} feed(s)",
                metrics={"n_fail": n_fail},
            )
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={"n_checked": len(results), "n_fail": n_fail, "soft": cfg.soft_plausibility},
            artifacts=({"type": "plausibility", "results": results},),
        )


# --- Fixture seed into Agent 1 SQLite ----------------------------------------


def seed_fixture_answer_updated(ctx: StageContext, cfg: OracleConfig) -> int:
    """Inject AnswerUpdated logs into Agent 1 SQLite for offline Agent 2 tests."""
    db_path = ctx.stage_outputs.get("raw_db_path")
    if not db_path:
        raise FileNotFoundError("raw_db_path missing — run Agent 1 first")
    path = Path(db_path)
    _guard_write(path)
    allowed = ctx.stage_outputs.get("oracle_allowed_feeds") or []
    if not allowed:
        return 0
    conn = sqlite3.connect(str(path))
    inserted = 0
    try:
        for i, row in enumerate(allowed):
            chain = row["chain"]
            agg = row["aggregator"]
            # Spread events across bins for occupancy coverage
            for k in range(3):
                minute = (i * 7 + k * 11) % cfg.n_bins
                ts = cfg.window_start_ts + minute * 60
                current = 2500 * 10**8 if "ETH" in row["feed"] else int(1.0 * 10**8)
                topics = encode_answer_updated_topics(current, 1000 + i * 10 + k)
                data = "0x" + format(ts, "064x")
                tx = f"0x{'f' * 56}{i:04x}{k:04x}"
                log_index = k
                payload = {
                    "address": agg,
                    "topics": topics,
                    "data": data,
                    "logIndex": hex(log_index),
                    "transactionHash": tx,
                    "blockNumber": hex(1000 + minute),
                    "blockTime": ts,
                    "feed": row["feed"],
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
                            1000 + minute,
                            agg,
                            TOPIC_ANSWER_UPDATED,
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


# --- S3 AnswerUpdatedParser --------------------------------------------------


class AnswerUpdatedParser:
    """Read Agent 1 SQLite; Topic0 from keccak; int256 normalize."""

    subagent_id = "W38-A2-S3"

    def run(self, ctx: StageContext, *, cfg: OracleConfig) -> SubagentResult:
        if cfg.fixture_mode:
            n_seed = seed_fixture_answer_updated(ctx, cfg)
            ctx.stage_outputs["oracle_fixture_seeded"] = n_seed

        db_path = ctx.stage_outputs.get("raw_db_path")
        if not db_path or not Path(db_path).is_file():
            return SubagentResult(
                subagent_id=self.subagent_id,
                status="failed",
                error="Agent 1 SQLite missing — Oracle is consumer, not RPC client",
            )

        allowed_aggs = {
            (r["chain"], r["aggregator"])
            for r in (ctx.stage_outputs.get("oracle_allowed_feeds") or [])
        }
        agg_feeds = ctx.stage_outputs.get("oracle_agg_feeds") or {}
        events: list[dict[str, Any]] = []
        n_skip_topic = 0
        n_skip_agg = 0
        n_dedup = 0
        seen: set[tuple[str, str, int]] = set()

        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute(
                "SELECT chain, tx, log_index, block_number, address, topic0, payload FROM events"
            ).fetchall()
        finally:
            conn.close()

        for chain, tx, log_index, block_number, address, topic0, payload_s in rows:
            if str(topic0).lower() != TOPIC_ANSWER_UPDATED.lower():
                n_skip_topic += 1
                continue
            addr = str(address).lower()
            if (chain, addr) not in allowed_aggs:
                n_skip_agg += 1
                continue
            key = (str(chain), str(tx).lower(), int(log_index))
            if key in seen:
                n_dedup += 1
                continue
            seen.add(key)
            payload = json.loads(payload_s)
            payload.setdefault("topics", [topic0])
            if len(payload.get("topics") or []) < 3:
                # Reconstruct from seed format if needed
                continue
            try:
                parsed = parse_answer_updated_log(payload)
            except ValueError:
                continue
            feeds = agg_feeds.get(f"{chain}|{addr}") or [payload.get("feed") or "UNKNOWN"]
            ts = int(payload.get("blockTime") or parsed["updated_at"])
            events.append(
                {
                    "chain": chain,
                    "aggregator": addr,
                    "feed": sorted(feeds)[0],
                    "feeds": feeds,
                    "tx_hash": str(tx).lower(),
                    "log_index": int(log_index),
                    "block_number": int(block_number or 0),
                    "timestamp": ts,
                    **parsed,
                }
            )

        ctx.stage_outputs["oracle_events"] = events
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={
                "n_events": len(events),
                "n_skip_topic": n_skip_topic,
                "n_skip_agg": n_skip_agg,
                "n_dedup": n_dedup,
                "topic0": TOPIC_ANSWER_UPDATED,
            },
            artifacts=({"type": "answer_updated_events", "count": len(events)},),
        )


# --- S5 OROccupancyBuilder ---------------------------------------------------


class OROccupancyBuilder:
    """One candidate occupancy: OR over all allowed feeds / aggregators."""

    subagent_id = "W38-A2-S5"

    def run(self, ctx: StageContext, *, cfg: OracleConfig) -> SubagentResult:
        events = ctx.stage_outputs.get("oracle_events") or []
        occ = [0] * cfg.n_bins
        n_placed = 0
        for ev in events:
            idx = minute_index(int(ev["timestamp"]), cfg.window_start_ts, cfg.n_bins)
            if idx is None:
                continue
            occ[idx] = 1
            n_placed += 1
        rate = sum(occ) / cfg.n_bins if cfg.n_bins else 0.0
        ctx.stage_outputs["oracle_occupancy"] = occ
        ctx.stage_outputs["oracle_occupancy_rate"] = rate
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={
                "n_bins": cfg.n_bins,
                "n_occupied": sum(occ),
                "occupancy_rate": round(rate, 6),
                "n_events_placed": n_placed,
            },
            artifacts=({"type": "oracle_occupancy", "n_occupied": sum(occ)},),
        )


# --- S7 OracleTelemetry ------------------------------------------------------


class OracleTelemetry:
    subagent_id = "W38-A2-S7"

    def run(self, ctx: StageContext, *, cfg: OracleConfig) -> SubagentResult:
        events = ctx.stage_outputs.get("oracle_events") or []
        occ = ctx.stage_outputs.get("oracle_occupancy") or []
        by_feed: dict[str, int] = {}
        by_chain: dict[str, int] = {}
        for ev in events:
            by_feed[ev["feed"]] = by_feed.get(ev["feed"], 0) + 1
            by_chain[ev["chain"]] = by_chain.get(ev["chain"], 0) + 1
        # Day coverage proxy: occupied minutes / bins (fixture); live uses day buckets
        coverage = (sum(occ) / len(occ)) if occ else 0.0
        tele = {
            "n_events": len(events),
            "by_feed": by_feed,
            "by_chain": by_chain,
            "coverage_ratio": round(coverage, 6),
            "occupancy_rate": ctx.stage_outputs.get("oracle_occupancy_rate"),
            "min_coverage_days": cfg.min_coverage_days,
            "min_events": cfg.fixture_min_events if cfg.fixture_mode else cfg.min_events,
        }
        ctx.stage_outputs["oracle_telemetry"] = tele
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics=tele,
            artifacts=({"type": "oracle_telemetry", "data": tele},),
        )


# --- S8 OracleIntegrityChecker -----------------------------------------------


class OracleIntegrityChecker:
    subagent_id = "W38-A2-S8"

    def run(self, ctx: StageContext, *, cfg: OracleConfig) -> SubagentResult:
        events = ctx.stage_outputs.get("oracle_events") or []
        tele = ctx.stage_outputs.get("oracle_telemetry") or {}
        min_n = cfg.fixture_min_events if cfg.fixture_mode else cfg.min_events
        keys = [(e["chain"], e["tx_hash"], e["log_index"]) for e in events]
        n_dup = len(keys) - len(set(keys))
        issues: list[str] = []
        if len(events) < min_n:
            issues.append(f"n_events={len(events)} < {min_n}")
        # Live Pre-Reg §4: day coverage (not minute occupancy rate)
        if not cfg.fixture_mode:
            days = {
                (int(e["timestamp"]) - cfg.window_start_ts) // 86_400
                for e in events
                if minute_index(int(e["timestamp"]), cfg.window_start_ts, cfg.n_bins)
                is not None
            }
            n_days = max(1, (cfg.n_bins + 1439) // 1440)
            day_cov = len(days) / n_days if n_days else 0.0
            tele = {**tele, "day_coverage_ratio": round(day_cov, 6)}
            ctx.stage_outputs["oracle_telemetry"] = tele
            if day_cov < cfg.min_coverage_days:
                issues.append(
                    f"day_coverage={day_cov:.3f} < {cfg.min_coverage_days}"
                )
        elif float(tele.get("coverage_ratio") or 0) < cfg.min_coverage_days:
            issues.append("coverage_below_threshold")
        if n_dup:
            issues.append(f"dup_keys={n_dup}")
        # Window check
        for e in events:
            idx = minute_index(int(e["timestamp"]), cfg.window_start_ts, cfg.n_bins)
            if idx is None:
                issues.append("event_outside_window")
                break
        ok = not issues or (cfg.fixture_mode and n_dup == 0 and len(events) >= min_n)
        ctx.stage_outputs["oracle_integrity_ok"] = ok
        if not ok:
            return SubagentResult(
                subagent_id=self.subagent_id,
                status="failed",
                error="; ".join(issues),
                metrics={"issues": issues},
            )
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={"n_events": len(events), "n_dup": n_dup},
            artifacts=({"type": "oracle_integrity", "ok": True},),
        )


# --- S9 OracleStateArchiver --------------------------------------------------


class OracleStateArchiver:
    subagent_id = "W38-A2-S9"

    def run(self, ctx: StageContext, *, cfg: OracleConfig) -> SubagentResult:
        out_dir = _oracle_dir(ctx)
        occ = ctx.stage_outputs.get("oracle_occupancy") or []
        path = out_dir / f"occupancy_{ctx.job_id}.json"
        _guard_write(path)
        body = {
            "candidate_id": "chainlink",
            "job_id": ctx.job_id,
            "n_bins": len(occ),
            "occupancy": occ,
            "occupancy_rate": ctx.stage_outputs.get("oracle_occupancy_rate"),
            "telemetry": ctx.stage_outputs.get("oracle_telemetry"),
            "excluded_feeds": ctx.stage_outputs.get("oracle_excluded_feeds"),
            "topic0": TOPIC_ANSWER_UPDATED,
            "fixture_mode": cfg.fixture_mode,
        }
        path.write_text(json.dumps(body), encoding="utf-8")
        ctx.stage_outputs["oracle_occupancy_path"] = str(path)
        # Also JSONL events for downstream
        events_path = out_dir / f"events_{ctx.job_id}.jsonl"
        _guard_write(events_path)
        with events_path.open("w", encoding="utf-8") as fh:
            for ev in ctx.stage_outputs.get("oracle_events") or []:
                fh.write(json.dumps(ev) + "\n")
        ctx.stage_outputs["oracle_events_path"] = str(events_path)
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={"occupancy_path": str(path), "events_path": str(events_path)},
            artifacts=(
                {"type": "oracle_archive", "path": str(path)},
                {"type": "oracle_events_jsonl", "path": str(events_path)},
            ),
        )
