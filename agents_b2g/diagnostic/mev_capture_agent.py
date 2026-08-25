"""Agent 3 — MEVCaptureAgent (cross-chain EOA minute occupancy). Consumes Agent 1 SQLite."""

from __future__ import annotations

from agents_b2g.diagnostic.agents import make_response
from agents_b2g.diagnostic.config import DiagnosticConfig
from agents_b2g.diagnostic.logging_utils import JSONLogger, _safe_call
from agents_b2g.diagnostic.reference_guard import (
    ReferenceArtifactGuard,
    ensure_live_directory,
)
from agents_b2g.diagnostic.subagents.mev_capture import (
    AddressNormalizer,
    CrossChainMatcher,
    EOACodeChecker,
    ExclusionListApplier,
    MEVConfig,
    MEVIntegrityChecker,
    MEVStateArchiver,
    MEVTelemetry,
    MinuteOccupancyBuilder,
    TxFromExtractor,
)
from agents_b2g.diagnostic.types import AgentEnvelope, DiagnosticRunInput, StageContext


class MEVCaptureAgent:
    """Stage 3 — TX-scan MEV cluster; no independent block scan — reads Agent 1 SQLite."""

    agent_name = "MEVCaptureAgent"

    def __init__(self, user_id: str = "wave38"):
        self.user_id = user_id
        self.logger = JSONLogger(self.agent_name, user_id)
        self.reference_guard = ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT)
        self.extractor = TxFromExtractor()
        self.normalizer = AddressNormalizer()
        self.exclusions = ExclusionListApplier()
        self.matcher = CrossChainMatcher()
        self.eoa = EOACodeChecker()
        self.occupancy = MinuteOccupancyBuilder()
        self.telemetry = MEVTelemetry()
        self.integrity = MEVIntegrityChecker()
        self.archiver = MEVStateArchiver()

    def run(
        self,
        run_input: DiagnosticRunInput,
        job_id: str,
        *,
        raw_db_path: str | None = None,
        fixture_mode: bool = True,
        cfg: MEVConfig | None = None,
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
        cfg: MEVConfig | None,
        ingestion_metadata: dict | None,
    ) -> AgentEnvelope:
        options = run_input.get("options") or {}
        cfg = cfg or MEVConfig(
            fixture_mode=fixture_mode or bool(options.get("fixture", True))
        )
        user_id = run_input.get("user_id") or self.user_id
        live_root = ensure_live_directory(DiagnosticConfig.DATA_ROOT, user_id)
        self.reference_guard.verify_unchanged()
        self.reference_guard.assert_write_allowed(live_root / "mev")

        db = raw_db_path
        if not db and ingestion_metadata:
            db = ingestion_metadata.get("raw_db_path")
        if not db:
            return make_response(
                "failed",
                job_id,
                error="MEVCaptureAgent requires Agent 1 raw_db_path (SQLite consumer)",
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
            ("extractor", lambda: self.extractor.run(ctx, cfg=cfg)),
            ("normalizer", lambda: self.normalizer.run(ctx, cfg=cfg)),
            ("exclusions", lambda: self.exclusions.run(ctx, cfg=cfg)),
            ("matcher", lambda: self.matcher.run(ctx, cfg=cfg)),
            ("eoa", lambda: self.eoa.run(ctx, cfg=cfg)),
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
                        {"type": "mev_partial", "metadata": {"steps": sub_results}}
                    ],
                )

        tele = ctx.stage_outputs.get("mev_telemetry") or {}
        meta = {
            "candidate_id": "mev_cluster",
            "fixture_mode": cfg.fixture_mode,
            "raw_db_path": db,
            "occupancy_path": ctx.stage_outputs.get("mev_occupancy_path"),
            "occupancy_jsonl": ctx.stage_outputs.get("mev_occupancy_jsonl"),
            "archive_path": ctx.stage_outputs.get("mev_archive_path"),
            "occupancy_rate": ctx.stage_outputs.get("mev_occupancy_rate"),
            "n_occupied": len(ctx.stage_outputs.get("mev_occupied_minutes") or []),
            "n_cross_chain_eoas": tele.get("n_cross_chain_eoas"),
            "n_exclusion": len(ctx.stage_outputs.get("mev_exclusion") or []),
            "exclusion_hits": ctx.stage_outputs.get("mev_exclusion_hits"),
            "telemetry": tele,
            "subagents": sub_results,
            "join": "t//60",
        }
        return make_response(
            "completed",
            job_id,
            artifacts=[{"type": "mev_capture", "format": "json", "metadata": meta}],
            logs=[
                f"n_occupied={meta['n_occupied']}",
                f"n_cross_eoas={meta['n_cross_chain_eoas']}",
                f"occupancy_rate={meta['occupancy_rate']}",
            ],
        )
