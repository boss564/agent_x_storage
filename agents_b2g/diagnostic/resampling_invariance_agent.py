"""Agent 7 — ResamplingInvarianceAgent (Lag-Spearman, Amendment A1)."""

from __future__ import annotations

from agents_b2g.diagnostic.agents import make_response
from agents_b2g.diagnostic.config import DiagnosticConfig
from agents_b2g.diagnostic.cte_math import OccupancyBundle
from agents_b2g.diagnostic.live_prereg import Wave38Thresholds
from agents_b2g.diagnostic.logging_utils import JSONLogger, _safe_call
from agents_b2g.diagnostic.reference_guard import ReferenceArtifactGuard
from agents_b2g.diagnostic.resampling_math import run_lag_spearman_resampling
from agents_b2g.diagnostic.types import AgentEnvelope, StageContext


class ResamplingInvarianceAgent:
    agent_name = "ResamplingInvarianceAgent"

    def __init__(self, user_id: str = "wave38"):
        self.user_id = user_id
        self.logger = JSONLogger(self.agent_name, user_id)
        self.reference_guard = ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT)

    def run(
        self,
        ctx: StageContext,
        *,
        bundle: OccupancyBundle,
        thresholds: Wave38Thresholds,
    ) -> AgentEnvelope:
        return _safe_call(
            self.logger,
            self.agent_name,
            self._run_inner,
            ctx,
            bundle,
            thresholds,
        )

    def _run_inner(
        self,
        ctx: StageContext,
        bundle: OccupancyBundle,
        thresholds: Wave38Thresholds,
    ) -> AgentEnvelope:
        if bundle.source.startswith("reference"):
            return make_response(
                "failed",
                ctx.job_id,
                error="Reference artifacts cannot be used as resampling input",
            )
        self.reference_guard.verify_unchanged()

        result = run_lag_spearman_resampling(bundle, thresholds)
        ctx.stage_outputs["resampling"] = result
        ctx.stage_outputs["resampling_fragment"] = result.resampling_fragment
        ctx.stage_outputs["n_unstable_folds"] = result.n_unstable_folds

        return make_response(
            "completed",
            ctx.job_id,
            artifacts=[
                {
                    "type": "resampling_lag_spearman",
                    "format": "json",
                    "metadata": {
                        "resampling_fragment": result.resampling_fragment,
                        "n_unstable_folds": result.n_unstable_folds,
                        "rho_min": result.rho_min,
                        "rho_spearman_min": thresholds.rho_spearman_min,
                        "peak_lag_retention": result.peak_lag_retention,
                        "n_folds": len(result.folds),
                        "p_sign_note": result.p_sign_descriptive.get("note"),
                    },
                }
            ],
            logs=[
                f"resampling_fragment={result.resampling_fragment}",
                f"rho_min={result.rho_min}",
            ],
        )
