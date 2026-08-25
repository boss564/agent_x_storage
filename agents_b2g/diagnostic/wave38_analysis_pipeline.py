"""Stages 6 → 7 → 8 → 9 analysis pipeline (contract-first, mock or live bundle)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agents_b2g.diagnostic.cte_entropy_engine_agent import CTEEntropyEngineAgent
from agents_b2g.diagnostic.cte_math import OccupancyBundle
from agents_b2g.diagnostic.gatekeeper_dispatcher_agent import GatekeeperDispatcherAgent
from agents_b2g.diagnostic.live_prereg import Wave38Thresholds, load_wave38_thresholds
from agents_b2g.diagnostic.pre_reg_fdr_guard_agent import PreRegFDRGuardAgent
from agents_b2g.diagnostic.resampling_invariance_agent import ResamplingInvarianceAgent
from agents_b2g.diagnostic.types import (
    AgentEnvelope,
    BlockCause,
    DiagnosticRunInput,
    DiagnosticVerdict,
    StageContext,
)

if TYPE_CHECKING:
    from agents_b2g.diagnostic.ethical_boundary_hook import EthicalOrchestratorProtocol


def _cause_for_verdict(verdict: DiagnosticVerdict) -> BlockCause | None:
    if verdict == DiagnosticVerdict.DIAG_FILTER_ARTIFACT:
        return BlockCause.FILTER_ARTIFACT
    if verdict == DiagnosticVerdict.DIAG_INCONCLUSIVE:
        return BlockCause.INCONCLUSIVE
    return None


def _default_ethical_orchestrator(user_id: str) -> EthicalOrchestratorProtocol:
    """Pipeline owns the Wave 39 instance and injects it into Gatekeeper."""
    from agents_b2g.ethical_boundary import EthicalBoundaryOrchestrator

    return EthicalBoundaryOrchestrator(user_id)


class Wave38AnalysisPipeline:
    """Run CTE → Resampling → PreReg/FDR → Gatekeeper on one occupancy bundle."""

    def __init__(
        self,
        user_id: str = "wave38",
        *,
        ethical_orchestrator: EthicalOrchestratorProtocol | None = None,
    ):
        self.user_id = user_id
        self.cte_agent = CTEEntropyEngineAgent(user_id)
        self.resampling_agent = ResamplingInvarianceAgent(user_id)
        self.guard_agent = PreRegFDRGuardAgent(user_id)
        orch = (
            ethical_orchestrator
            if ethical_orchestrator is not None
            else _default_ethical_orchestrator(user_id)
        )
        self.ethical_orchestrator = orch
        self.gatekeeper = GatekeeperDispatcherAgent(
            user_id,
            ethical_orchestrator=orch,
        )

    def run_stages_6_8_9(
        self,
        bundle: OccupancyBundle,
        *,
        job_id: str = "wave38-analysis",
        thresholds: Wave38Thresholds | None = None,
        run_input: DiagnosticRunInput | None = None,
    ) -> AgentEnvelope:
        """Backward-compatible alias — now runs 6→7→8→9."""
        return self.run_stages_6_7_8_9(
            bundle, job_id=job_id, thresholds=thresholds, run_input=run_input
        )

    def run_stages_6_7_8_9(
        self,
        bundle: OccupancyBundle,
        *,
        job_id: str = "wave38-analysis",
        thresholds: Wave38Thresholds | None = None,
        run_input: DiagnosticRunInput | None = None,
        seed: int | None = None,
    ) -> AgentEnvelope:
        thresholds = thresholds or load_wave38_thresholds()
        resolved_seed = (
            seed if seed is not None else thresholds.seed_default
        )
        ctx = StageContext(
            run_id=job_id,
            user_id=self.user_id,
            job_id=job_id,
            data_root=str(bundle.source),
            seed=resolved_seed,
            prereg_version="WAVE38_LIVE_PREREG.md",
        )

        informativity = self.guard_agent.run(ctx, bundle=bundle, thresholds=thresholds)
        if informativity["status"] == "failed":
            return informativity

        encoding_inert = ctx.stage_outputs.get("encoding_inert") or {}
        cte_result = self.cte_agent.run(
            ctx,
            bundle=bundle,
            thresholds=thresholds,
            encoding_inert=encoding_inert,
        )
        if cte_result["status"] == "failed":
            return cte_result

        resampling = self.resampling_agent.run(
            ctx, bundle=bundle, thresholds=thresholds
        )
        if resampling["status"] == "failed":
            return resampling

        guard_verdict = self.guard_agent.run(ctx, bundle=None, thresholds=thresholds)
        if guard_verdict["status"] == "failed":
            return guard_verdict

        verdict = ctx.stage_outputs.get(
            "preliminary_verdict", DiagnosticVerdict.DIAG_SIGNAL_VALID
        )
        if isinstance(verdict, str):
            verdict = DiagnosticVerdict(verdict)

        run_payload: DiagnosticRunInput = run_input or {
            "run_id": job_id,
            "user_id": self.user_id,
            "options": {
                "seed": resolved_seed,
                "prereg_version": ctx.prereg_version,
            },
        }
        # Ensure seed reaches gatekeeper envelope
        opts = dict(run_payload.get("options") or {})
        opts.setdefault("seed", resolved_seed)
        opts.setdefault("prereg_version", ctx.prereg_version)
        run_payload = {**run_payload, "options": opts}

        fdr = ctx.stage_outputs.get("fdr_status")
        cte_analysis = ctx.stage_outputs.get("cte_analysis")
        resampling_meta = ctx.stage_outputs.get("resampling")

        gate = self.gatekeeper.run(
            run_payload,
            job_id,
            verdict=verdict,
            cause=_cause_for_verdict(verdict),
            cte_by_candidate=ctx.stage_outputs.get("s_tau_input"),
            candidate_roles=ctx.stage_outputs.get("candidate_roles"),
            perm_fail_candidates=ctx.stage_outputs.get("perm_fail_candidates"),
        )
        if gate["status"] != "completed":
            return gate

        meta = gate["artifacts"][0]["metadata"]
        meta["pipeline"] = {
            "stages": ["6_cte", "7_resampling", "8_prereg", "9_gatekeeper"],
            "bundle_source": bundle.source,
            "perm_fragment": ctx.stage_outputs.get("perm_fragment"),
            "resampling_fragment": ctx.stage_outputs.get("resampling_fragment"),
            "rho_min": getattr(resampling_meta, "rho_min", None),
            "rho_spearman_min": thresholds.rho_spearman_min,
            "n_unstable_folds": ctx.stage_outputs.get("n_unstable_folds"),
            "n_unstable_folds_max": thresholds.n_unstable_folds_max,
            "fdr_passed": getattr(fdr, "passed", None),
            "n_unclassified": ctx.stage_outputs.get("n_unclassified"),
            "sum_cte_ref": getattr(cte_analysis, "sum_cte_ref", None),
            "preliminary_verdict": getattr(verdict, "value", str(verdict)),
            "thresholds": thresholds.as_dict(),
        }
        return gate
