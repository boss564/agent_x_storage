"""Agent 5 — IntentAndStablecoinAgent (Z_intent ∪ Z_stable). Consumes Agent 1 SQLite."""

from __future__ import annotations

from agents_b2g.diagnostic.agents import make_response
from agents_b2g.diagnostic.config import DiagnosticConfig
from agents_b2g.diagnostic.logging_utils import JSONLogger, _safe_call
from agents_b2g.diagnostic.reference_guard import (
    ReferenceArtifactGuard,
    ensure_live_directory,
)
from agents_b2g.diagnostic.subagents.intent_stable_capture import (
    AcrossSpokePoolScanner,
    CCTPV1Scanner,
    CCTPV2Scanner,
    ClassicPSMScanner,
    CoWTradeScanner,
    IntentStableArchiver,
    IntentStableConfig,
    IntentStableOccupancyBuilder,
    IntentStableTelemetry,
    LitePSMScanner,
)
from agents_b2g.diagnostic.types import AgentEnvelope, DiagnosticRunInput, StageContext


class IntentAndStablecoinAgent:
    """Stage 5 — multi-protocol OR occupancy; SQLite consumer, not RPC client."""

    agent_name = "IntentAndStablecoinAgent"

    def __init__(self, user_id: str = "wave38"):
        self.user_id = user_id
        self.logger = JSONLogger(self.agent_name, user_id)
        self.reference_guard = ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT)
        self.across = AcrossSpokePoolScanner()
        self.cow = CoWTradeScanner()
        self.lite_psm = LitePSMScanner()
        self.classic_psm = ClassicPSMScanner()
        self.cctp_v1 = CCTPV1Scanner()
        self.cctp_v2 = CCTPV2Scanner()
        self.occupancy = IntentStableOccupancyBuilder()
        self.telemetry = IntentStableTelemetry()
        self.archiver = IntentStableArchiver()

    def run(
        self,
        run_input: DiagnosticRunInput,
        job_id: str,
        *,
        raw_db_path: str | None = None,
        fixture_mode: bool = True,
        cfg: IntentStableConfig | None = None,
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
        cfg: IntentStableConfig | None,
        ingestion_metadata: dict | None,
    ) -> AgentEnvelope:
        options = run_input.get("options") or {}
        cfg = cfg or IntentStableConfig(
            fixture_mode=fixture_mode or bool(options.get("fixture", True))
        )
        user_id = run_input.get("user_id") or self.user_id
        live_root = ensure_live_directory(DiagnosticConfig.DATA_ROOT, user_id)
        self.reference_guard.verify_unchanged()
        self.reference_guard.assert_write_allowed(live_root / "intent_stablecoin")

        db = raw_db_path
        if not db and ingestion_metadata:
            db = ingestion_metadata.get("raw_db_path")
        if not db:
            return make_response(
                "failed",
                job_id,
                error=(
                    "IntentAndStablecoinAgent requires Agent 1 raw_db_path "
                    "(SQLite consumer)"
                ),
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

        sequence = [
            ("across", lambda: self.across.run(ctx, cfg=cfg)),
            ("cow", lambda: self.cow.run(ctx, cfg=cfg)),
            ("lite_psm", lambda: self.lite_psm.run(ctx, cfg=cfg)),
            ("classic_psm", lambda: self.classic_psm.run(ctx, cfg=cfg)),
            ("cctp_v1", lambda: self.cctp_v1.run(ctx, cfg=cfg)),
            ("cctp_v2", lambda: self.cctp_v2.run(ctx, cfg=cfg)),
            ("occupancy", lambda: self.occupancy.run(ctx, cfg=cfg)),
            ("telemetry", lambda: self.telemetry.run(ctx, cfg=cfg)),
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
                        {
                            "type": "intent_stable_partial",
                            "metadata": {"steps": sub_results},
                        }
                    ],
                )

        tele = ctx.stage_outputs.get("intent_stable_telemetry") or {}
        meta = {
            "candidate_id": "intent_stablecoin",
            "families": ["intent_relayers", "stablecoin_mint_burn"],
            "fixture_mode": cfg.fixture_mode,
            "raw_db_path": db,
            "occupancy_path": ctx.stage_outputs.get("intent_stable_occupancy_path"),
            "events_path": ctx.stage_outputs.get("intent_stable_events_path"),
            "occupancy_jsonl": ctx.stage_outputs.get("intent_stable_occupancy_jsonl"),
            "occupancy_rate": ctx.stage_outputs.get("intent_stable_occupancy_rate"),
            "n_occupied": sum(ctx.stage_outputs.get("intent_stable_occupancy") or []),
            "n_events": len(ctx.stage_outputs.get("intent_stable_events") or []),
            "n_registry": len(ctx.stage_outputs.get("intent_stable_registry") or []),
            "min_coverage_days": cfg.min_coverage_days,
            "telemetry": tele,
            "subagents": sub_results,
            "or_aggregation": True,
        }
        return make_response(
            "completed",
            job_id,
            artifacts=[
                {"type": "intent_stable_capture", "format": "json", "metadata": meta}
            ],
            logs=[
                f"n_events={meta['n_events']}",
                f"n_occupied={meta['n_occupied']}",
                f"occupancy_rate={meta['occupancy_rate']}",
            ],
        )
