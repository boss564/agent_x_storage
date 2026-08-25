"""Agent 2 — OracleSignalAgent (Chainlink Z_oracle). Consumes Agent 1 SQLite."""

from __future__ import annotations

from pathlib import Path

from agents_b2g.diagnostic.agents import make_response
from agents_b2g.diagnostic.config import DiagnosticConfig
from agents_b2g.diagnostic.logging_utils import JSONLogger, _safe_call
from agents_b2g.diagnostic.reference_guard import (
    ReferenceArtifactGuard,
    ensure_live_directory,
)
from agents_b2g.diagnostic.subagents.oracle_capture import (
    AggregatorPhaseTracker,
    AnswerUpdatedParser,
    ChainlinkProxyResolver,
    FeedExclusionEnforcer,
    FeedPlausibilityGate,
    OracleConfig,
    OracleIntegrityChecker,
    OracleStateArchiver,
    OracleTelemetry,
    OROccupancyBuilder,
)
from agents_b2g.diagnostic.types import AgentEnvelope, DiagnosticRunInput, StageContext


class OracleSignalAgent:
    """Stage 2 — Chainlink capture as Agent-X subagents; no direct RPC."""

    agent_name = "OracleSignalAgent"

    def __init__(self, user_id: str = "wave38"):
        self.user_id = user_id
        self.logger = JSONLogger(self.agent_name, user_id)
        self.reference_guard = ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT)
        self.resolver = ChainlinkProxyResolver()
        self.phases = AggregatorPhaseTracker()
        self.exclusions = FeedExclusionEnforcer()
        self.plausibility = FeedPlausibilityGate()
        self.parser = AnswerUpdatedParser()
        self.occupancy = OROccupancyBuilder()
        self.telemetry = OracleTelemetry()
        self.integrity = OracleIntegrityChecker()
        self.archiver = OracleStateArchiver()

    def run(
        self,
        run_input: DiagnosticRunInput,
        job_id: str,
        *,
        raw_db_path: str | None = None,
        fixture_mode: bool = True,
        cfg: OracleConfig | None = None,
        ingestion_metadata: dict | None = None,
    ) -> AgentEnvelope:
        return _safe_call(
            self.logger,
            self.agent_name,
            self._run_inner,
            run_input,
            job_id,
            raw_db_path,
            fixture_mode,
            cfg,
            ingestion_metadata,
        )

    def _run_inner(
        self,
        run_input: DiagnosticRunInput,
        job_id: str,
        raw_db_path: str | None,
        fixture_mode: bool,
        cfg: OracleConfig | None,
        ingestion_metadata: dict | None,
    ) -> AgentEnvelope:
        options = run_input.get("options") or {}
        cfg = cfg or OracleConfig(
            fixture_mode=fixture_mode or bool(options.get("fixture", True))
        )
        user_id = run_input.get("user_id") or self.user_id
        live_root = ensure_live_directory(DiagnosticConfig.DATA_ROOT, user_id)
        self.reference_guard.verify_unchanged()
        self.reference_guard.assert_write_allowed(live_root / "oracle")

        db = raw_db_path
        if not db and ingestion_metadata:
            db = ingestion_metadata.get("raw_db_path")
        if not db:
            return make_response(
                "failed",
                job_id,
                error="OracleSignalAgent requires Agent 1 raw_db_path (SQLite consumer)",
            )

        ctx = StageContext(
            run_id=run_input.get("run_id") or job_id,
            user_id=user_id,
            job_id=job_id,
            data_root=str(live_root),
            seed=int(options.get("seed", 0)),
            prereg_version=str(options.get("prereg_version", "WAVE38_LIVE_PREREG.md")),
            stage_outputs={"raw_db_path": db},
        )

        # Order: resolve → phases → exclude → plausibility → parse → OR → tele → integrity → archive
        sequence = [
            ("resolver", lambda: self.resolver.run(ctx, cfg=cfg)),
            ("phases", lambda: self.phases.run(ctx, cfg=cfg)),
            ("exclusions", lambda: self.exclusions.run(ctx, cfg=cfg)),
            ("plausibility", lambda: self.plausibility.run(ctx, cfg=cfg)),
            ("parser", lambda: self.parser.run(ctx, cfg=cfg)),
            ("occupancy", lambda: self.occupancy.run(ctx, cfg=cfg)),
            ("telemetry", lambda: self.telemetry.run(ctx, cfg=cfg)),
            ("integrity", lambda: self.integrity.run(ctx, cfg=cfg)),
            ("archiver", lambda: self.archiver.run(ctx, cfg=cfg)),
        ]
        sub_results = []
        for name, fn in sequence:
            result = fn()
            sub_results.append({"step": name, **result.to_dict()})
            if result.status == "failed":
                return make_response(
                    "failed",
                    job_id,
                    error=result.error or f"{name} failed",
                    artifacts=[
                        {"type": "oracle_partial", "metadata": {"steps": sub_results}}
                    ],
                )

        meta = {
            "candidate_id": "chainlink",
            "fixture_mode": cfg.fixture_mode,
            "raw_db_path": db,
            "occupancy_path": ctx.stage_outputs.get("oracle_occupancy_path"),
            "events_path": ctx.stage_outputs.get("oracle_events_path"),
            "occupancy_rate": ctx.stage_outputs.get("oracle_occupancy_rate"),
            "n_occupied": sum(ctx.stage_outputs.get("oracle_occupancy") or []),
            "n_events": len(ctx.stage_outputs.get("oracle_events") or []),
            "excluded_feeds": ctx.stage_outputs.get("oracle_excluded_feeds"),
            "telemetry": ctx.stage_outputs.get("oracle_telemetry"),
            "subagents": sub_results,
        }
        return make_response(
            "completed",
            job_id,
            artifacts=[{"type": "oracle_capture", "format": "json", "metadata": meta}],
            logs=[
                f"n_events={meta['n_events']}",
                f"occupancy_rate={meta['occupancy_rate']}",
            ],
        )
