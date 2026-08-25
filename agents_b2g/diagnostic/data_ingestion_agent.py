"""Agent 1 — DataIngestionAgent (Wave 38 data plane foundation)."""

from __future__ import annotations

from pathlib import Path

from agents_b2g.diagnostic.agents import make_response
from agents_b2g.diagnostic.config import DiagnosticConfig
from agents_b2g.diagnostic.logging_utils import JSONLogger, _safe_call
from agents_b2g.diagnostic.reference_guard import (
    ReferenceArtifactGuard,
    ensure_live_directory,
)
from agents_b2g.diagnostic.subagents.data_ingestion import (
    CheckpointWriter,
    ChunkCoordinator,
    EthBlockScanner,
    GnosisBlockScanner,
    IngestionConfig,
    IngestionTelemetry,
    RawEventStorer,
    ReceiptFetcher,
    RetryScheduler,
    RPCLoadBalancer,
)
from agents_b2g.diagnostic.types import AgentEnvelope, DiagnosticRunInput, StageContext


class DataIngestionAgent:
    """Stage 1 — shared RPC/scan/checkpoint/SQLite for capture agents 2–5."""

    agent_name = "DataIngestionAgent"

    def __init__(self, user_id: str = "wave38"):
        self.user_id = user_id
        self.logger = JSONLogger(self.agent_name, user_id)
        self.reference_guard = ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT)
        self.retry = RetryScheduler()
        self.balancer = RPCLoadBalancer()
        self.chunks = ChunkCoordinator()
        self.eth_scan = EthBlockScanner()
        self.gno_scan = GnosisBlockScanner()
        self.receipts = ReceiptFetcher()
        self.checkpoint = CheckpointWriter()
        self.storer = RawEventStorer()
        self.telemetry = IngestionTelemetry()

    def run(
        self,
        run_input: DiagnosticRunInput,
        job_id: str,
        *,
        fixture_mode: bool | None = None,
        cfg: IngestionConfig | None = None,
    ) -> AgentEnvelope:
        return _safe_call(
            self.logger,
            self.agent_name,
            self._run_inner,
            run_input,
            job_id,
            fixture_mode,
            cfg,
        )

    def _run_inner(
        self,
        run_input: DiagnosticRunInput,
        job_id: str,
        fixture_mode: bool | None,
        cfg: IngestionConfig | None,
    ) -> AgentEnvelope:
        options = run_input.get("options") or {}
        if cfg is None:
            # Default: fixture unless explicitly live+network
            use_fixture = (
                True
                if fixture_mode is None
                else fixture_mode
            )
            if fixture_mode is None and options.get("live") and not options.get("fixture"):
                use_fixture = False
            if options.get("fixture", False):
                use_fixture = True
            cfg = IngestionConfig(fixture_mode=use_fixture)

        live_root = ensure_live_directory(
            DiagnosticConfig.DATA_ROOT, run_input.get("user_id") or self.user_id
        )
        self.reference_guard.verify_unchanged()
        self.reference_guard.assert_write_allowed(live_root)

        ctx = StageContext(
            run_id=run_input.get("run_id") or job_id,
            user_id=run_input.get("user_id") or self.user_id,
            job_id=job_id,
            data_root=str(live_root),
            seed=int(options.get("seed", 0)),
            prereg_version=str(options.get("prereg_version", "WAVE38_LIVE_PREREG.md")),
        )

        sequence = [
            ("retry", lambda: self.retry.run(ctx, cfg=cfg)),
            ("balancer", lambda: self.balancer.run(ctx, cfg=cfg)),
            ("chunks", lambda: self.chunks.run(ctx, cfg=cfg)),
            ("eth_scan", lambda: self.eth_scan.run(ctx, cfg=cfg)),
            ("gno_scan", lambda: self.gno_scan.run(ctx, cfg=cfg)),
            ("receipts", lambda: self.receipts.run(ctx, cfg=cfg)),
            ("checkpoint", lambda: self.checkpoint.run(ctx, cfg=cfg)),
            ("storer", lambda: self.storer.run(ctx, cfg=cfg)),
            ("telemetry", lambda: self.telemetry.run(ctx, cfg=cfg)),
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
                    artifacts=[{"type": "ingestion_partial", "metadata": {"steps": sub_results}}],
                )

        ingestion = {
            "raw_db_path": ctx.stage_outputs.get("raw_db_path"),
            "checkpoint_path": ctx.stage_outputs.get("checkpoint_path"),
            "telemetry": ctx.stage_outputs.get("ingestion_telemetry"),
            "block_ranges": ctx.stage_outputs.get("block_ranges"),
            "rpc_urls": {
                k: redact_safe(v)
                for k, v in (ctx.stage_outputs.get("rpc_urls") or {}).items()
            },
            "fixture_mode": cfg.fixture_mode,
            "subagents": sub_results,
        }
        return make_response(
            "completed",
            job_id,
            artifacts=[
                {
                    "type": "data_ingestion",
                    "format": "json",
                    "metadata": ingestion,
                }
            ],
            logs=[
                f"fixture_mode={cfg.fixture_mode}",
                f"n_blocks={(ingestion.get('telemetry') or {}).get('n_blocks')}",
            ],
        )


def redact_safe(url: str) -> str:
    from agents_b2g.diagnostic.ingestion_rpc import redact_url

    return redact_url(url)
