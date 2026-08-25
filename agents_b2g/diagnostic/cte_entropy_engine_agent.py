"""Agent 6 — CTEEntropyEngineAgent (Wave 38 analysis plane)."""

from __future__ import annotations

from agents_b2g.diagnostic.agents import make_response
from agents_b2g.diagnostic.config import DiagnosticConfig
from agents_b2g.diagnostic.cte_math import CTEAnalysisResult, OccupancyBundle, run_cte_analysis
from agents_b2g.diagnostic.live_prereg import Wave38Thresholds
from agents_b2g.diagnostic.logging_utils import JSONLogger, _safe_call
from agents_b2g.diagnostic.reference_guard import ReferenceArtifactGuard
from agents_b2g.diagnostic.types import AgentEnvelope, DiagnosticRunInput, StageContext


class CTEEntropyEngineAgent:
    agent_name = "CTEEntropyEngineAgent"

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
        encoding_inert: dict[str, bool] | None = None,
    ) -> AgentEnvelope:
        return _safe_call(
            self.logger,
            self.agent_name,
            self._run_inner,
            ctx,
            bundle,
            thresholds,
            encoding_inert,
        )

    def _run_inner(
        self,
        ctx: StageContext,
        bundle: OccupancyBundle,
        thresholds: Wave38Thresholds,
        encoding_inert: dict[str, bool] | None,
    ) -> AgentEnvelope:
        if bundle.source.startswith("reference"):
            return make_response(
                "failed",
                ctx.job_id,
                error="Reference artifacts cannot be used as CTE computation input",
            )

        self.reference_guard.verify_unchanged()
        result = run_cte_analysis(
            bundle,
            thresholds,
            seed=ctx.seed or thresholds.seed_default,
            encoding_inert=encoding_inert,
        )
        self._publish(ctx, result)
        return make_response(
            "completed",
            ctx.job_id,
            artifacts=[
                {
                    "type": "cte_analysis",
                    "format": "json",
                    "metadata": {
                        "perm_fragment": result.perm_fragment,
                        "n_unclassified": result.n_unclassified,
                        "sum_cte_ref": result.sum_cte_ref,
                    },
                }
            ],
            logs=[f"perm_fragment={result.perm_fragment}"],
        )

    @staticmethod
    def _publish(ctx: StageContext, result: CTEAnalysisResult) -> None:
        ctx.stage_outputs["cte_analysis"] = result
        ctx.stage_outputs["s_tau_input"] = result.s_tau_by_candidate
        ctx.stage_outputs["candidate_roles"] = result.candidate_roles
        ctx.stage_outputs["perm_fail_candidates"] = result.perm_fail_candidates
        ctx.stage_outputs["perm_fragment"] = result.perm_fragment
        ctx.stage_outputs["n_unclassified"] = result.n_unclassified
